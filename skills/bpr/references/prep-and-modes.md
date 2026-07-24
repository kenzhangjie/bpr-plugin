# PREP · 预处理 / 断句 / 模式判定

> 阶段 2 · PREP 专用。清洗断句、说话人、时间戳、auto-subs 重建;统计 CJK 占比 → 选模式(英文双语 / 中文浓缩)。

---

## auto-subs 预处理(模式退化)

YouTube 只拿到 auto-subs(无标点、无 speaker)时,PREP 先做退化处理再进翻译:

1. **在翻译 Step 1 之前**,先做"重新断句 + 加标点"——把流式无标点文本切成正常英文句子。这步走在三步法之前,不影响"每段都跑三步法"的硬规则
2. **从 metadata 推断 speaker**:`uploader = host` / `description 里的 guest = 嘉宾`,根据语境分 turn(谁在提问 / 谁在回答)
3. **如果不能可靠区分谁在说话**:退化成 **essay 模式渲染**(不写 `.speaker / .turn`),保留章节级时间戳标注。**不要瞎猜 speaker**——猜错比退化更糟

---

## 英文子模式源清洗(专名纠错 + 说话人归属)

> 设计文档:`docs/superpowers/specs/2026-07-24-bpr-english-prep-correction-design.md`。解决 2026-07-24 Lenny × Andrew Ambrosino 那期实测暴露的两个痛——YT 自动字幕专名错听(OpenAI→"Opening Eye"、Codex→"Codeex")、说话人归属靠手拆——过去全靠手写 regex + 人肉判断,这节把它变成可重复的 agent 流程。

### 触发条件
**CJK < 60%**(判定见上"语言检测算法")且输入是 **transcript 类**(有 `>>` 或 speaker 信号)。**essay(单作者、无说话人轮换的博客/长文)跳过本节**,直接走原有 PREP 流程。

对应脚本:`scripts/prep/clean_en.py`(`parse_blocks` / `split_windows` / `load_mappings` / `apply_correct_table` / `norm_words` / `word_coverage` / `append_glossary` / `finalize` + CLI)。**中文专名纠错走 `clean.md` 的 CLEAN 三步法,英文不跑那套(不书面化,逐字交 TRANSLATE)**——两条源清洗路径平行、互不调用。

### Step 1 · Analyze-lite(主代理,全稿 1 次)
读两份 ground truth,产出一份小 brief(塞进后续每个子代理 prompt,保跨窗一致):
- **`metadata.json`** 的 **description + title**(YouTube fetch 已抓到):从中找 "my guest is X" 类介绍句认嘉宾,`uploader`/channel 名认主持。
- **`~/.config/volc/glossary.txt`**:读专名即可,**忽略 `|` 后的权重**(权重是给火山热词表用的,对英文纠错无意义,同 `clean.md` 约定)。

产出 brief 三项:
1. **本期专名表**(正确英文拼写,如 OpenAI / Codex / ChatGPT / Ambrosino)。
2. **说话人身份**:host = uploader/channel,guest = description 里 "my guest is X" 认出的人名 → 映射成 role。
3. **存疑清单**:brief 里拿不准、留给子代理核实的候选词。

### Step 2 · 逐窗子代理(归属 + 纠错)
主代理先跑 `split_windows(parse_blocks(raw))` 切窗(默认每窗 ~25 个 `>>` 块)。**主代理 verbatim 持有原文**(抗压缩铁律),每窗派一个独立子代理,只回结构化 turn 列表,不夹带解释。

派发 prompt 模板:
```
你在做英文 podcast 字幕的专名纠错 + 说话人归属。这是第 N 窗原始字幕块,和全局 brief。

【全局 brief】
本期专名表(正确拼写):{names}
说话人身份:host={host}, guest={guest}
存疑清单:{suspects}

【原始字幕块(本窗,已按 >> 切开)】
{raw_window}

分两件事做,只输出最终 JSON,不要解释:
1) 专名纠错:按 brief 把错听的专名改成正确英文拼写(如 "Opening Eye"→OpenAI、
   "Codeex"→Codex、"chatd"→ChatGPT)。除专名 + 明显拼写错误外,**英文逐字保留**
   (含口语水词 um/like/you know),不改写、不删句、不概括。拿不准的词标
   `⟨?你的猜测⟩`,不硬编——confidently wrong 比留疑更坏。
2) 说话人归属 + 拆合并块:按 host/guest 身份判每段话是谁说的;如果一个 `>>`
   块把一问一答挤在一起,在语义拐点拆成多个 turn。

**输出格式(硬约束,只输出这个 JSON,不要 markdown 包裹、不要额外文字)**:
[{"speaker": "Host 名字或 Guest 名字", "sents": ["逐句纠错后的英文句子", "..."]}, ...]
```

### Step 3 · 拼装 + 词覆盖硬闸(主代理,确定性)
把各窗子代理返回的 JSON 按窗序拼成一份完整 turns 列表,写成文件,跑 `clean_en.py` 的 CLI:

```bash
python3 scripts/prep/clean_en.py \
  --turns <拼好的 turns.json> \
  --raw <原始逐字稿 txt> \
  --out <输出路径 turns.clean.json> \
  --names <本期专名清单 JSON,可选,回写 glossary>
```

CLI 内部调用 `finalize(turns, raw, mappings)`:对每句套 `apply_correct_table`,再用 `word_coverage` 算整体覆盖率。**覆盖率 < 0.98 视为丢句**——CLI 以非零退出码 + `WARN` 提示打回,**主代理需把该窗打回 Step 2 重派一次**;重做仍不过,该处标 `⟨?丢失⟩` 留人工,不无限重试。这是把"英文 verbatim"从软约束升级成硬闸。

### Step 4 · 确定性后处理 + 专名飞轮
`finalize` 已经在拼装时自动套用了双语 `correct_table.json`(`load_mappings` 读入、`apply_correct_table` 无歧义硬映射补遗漏;长键优先避免短键抢先命中长专名)。**英文由这一步套用,不跑 `volc_asr.py`**(那是中文专用)。

传 `--names` 时,CLI 会调 `append_glossary` 把本期专名清单去重后 append 进共用 `~/.config/volc/glossary.txt`(`专名|默认权重` 格式,与中文飞轮同一份文件)。跑得越多,专名越准——复利同 `clean.md`。

### 降级(不幻觉)
- **description 缺失/无用** → 专名靠 glossary + 上下文猜;说话人靠启发式(**提问者 = host**)。
- **说话人真分不出** → 退化成 **essay 模式**(不写 `.speaker` / `.turn`),保留章节级时间戳,**不瞎猜 speaker**——引 `lessons-learned.md` L1「主持人/嘉宾必须从 metadata + transcript 提取,不准默认」,猜错比退化更糟。

### 产出契约
本节最终产出**扁平说话人 turn 列表**(章节未知,STRUCTURE 才切):
```json
[{ "speaker": "Lenny" | "Andrew" | "SpeakerN",
   "sents": ["verbatim corrected english sentence", "..."] }, ...]
```
无时间戳——RENDER 阶段由 `scripts/enrich/add_timestamps.py` 反查 VTT 注入,不在本节处理。这份 JSON 直接交 **STRUCTURE** 切章 + 出 TL;DR 英文金句;**TRANSLATE** 消费其中的英文句做四步法,拿到的已是干净、分好人的源(TRANSLATE 四步法本身不改)。

---

## 中文模式 (Chinese-Only Mode)

**触发条件:CJK 字符占 transcript 主体 ≥ 60%** —— 自动检测,**不需要用户加修饰词**。

### 为什么单独一套?

中文 podcast / blog / 访谈不需要翻译(省掉英文双语对照那一半),但**正文仍要完整覆盖内容**。读者想要的是:
1. **可扫读的速读层**(TL;DR,5-15 条 + 🔥 非共识 takes)—— 放顶部
2. **书面正文**(说话人 + 时间戳 + CLEAN 书面重写,中文单语)—— 放正文,逐字口语原稿降级为可折叠底档

——本质是"顶部给速读笔记,正文给书面稿,底层留逐字底档",**不是**把整集压成摘要。铁律详见下方"中文模式正文规则(2026-07-22 修订)"。

### 中文模式正文规则(2026-07-22 修订)
- **旧规则(2026-07-11)**:中文正文逐字全量、不概括。
- **新规则**:正文经 CLEAN 阶段(见 `clean.md`)**书面重写**为可读正文;**逐字口语原稿降级为可折叠底档**(每章 `<details>` 留档,内容 == 火山原始 transcript,不丢)。
- 铁律不变的部分:**Polish 只改"怎么说"不改"说了什么"**,每个论点/数字/专名/因果必须保下来 —— 书面化 ≠ 概括。

### 语言检测算法

```python
def detect_language(text: str) -> str:
    """Return 'zh' if Chinese-dominant, 'en' otherwise."""
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    total = cjk + latin
    if total < 100: return 'en'  # 太短无法判断,默认双语
    return 'zh' if cjk / total >= 0.6 else 'en'
```

**判定时机**:在预处理(Step 2)之后、章节切分(Step 3)之前。一旦判定中文,**整个流程切到中文分支**。

### 中文模式输出结构

```
Hero
  - kicker:{podcast} with {host} · {YYYY-MM-DD} · 中文整理
  - h1:中文标题(直接用原标题,不需翻译)
  - hero-zh:一句话概括(20-40 字)
  - hero-lede:最核心金句(选一条) + 一段背景(80-120 字)
─────────────────
TL;DR · 速读 (5-15 条)
  - 每条:加粗中文论点 + 一句解释(不需要英文 quote / context 双语三明治结构)
─────────────────
🔥 非共识 · Contrarian Takes (3-8 条)
  - 每条:嘉宾原话引用(中文 verbatim,带 .pull 样式)
  - 配一个 "为什么非共识" 短解释 (中文,1-2 句)
  - 可选:多数人怎么想(对比锚点)
─────────────────
章节正文:书面正文 + 可折叠逐字底档 (8-12 章)
  - 正文由 CLEAN 阶段产出(书面版);逐字底档见 render.md 的 <details> 约定
  - 底档结构:ASR 逐句原文按说话人合并成 `.turn`(speaker + timestamp + 逐句 `<p class="zh">`),折进 `<details>`
  - 覆盖率改用**信息/实体级覆盖**(口径见 `verify.md`),不再用句数 ≥85% 硬闸;正文书面重写,底档逐字留存,不丢内容
  - 中文单语,没有 .bilingual(不需要翻译)
─────────────────
Footer(来源 + 元信息)
```

### 中文模式与 podcast / essay 模式的区别

| 维度 | 英文双语模式 | 中文模式 |
|---|---|---|
| 翻译三步法 | ✓ 每段都跑 | ✗ 不跑 |
| `.bilingual` 双语对照块 | ✓ 句级 | ✗ 不渲染(中文单语) |
| `.turn-head` speaker / timestamp | 视情况渲染 | ✓ **底档渲染**(逐字 turn 收进可折叠 `<details>`) |
| TL;DR 4 元素结构 | 中文论点 + 英文金句 + 英文上下文 + 中文解释 | **仅 2 元素**:中文论点 + 中文解释 |
| **非共识 section** | ✗ 不渲染 | ✓ **必须有** |
| 章节正文 | 逐句双语对照 | 书面正文(CLEAN 重写)+ 可折叠逐字底档 |

### 非共识 section 写作原则

这是中文模式的灵魂。**做不好,整篇就是简陋摘要器**。

**什么算非共识**:
- 嘉宾说出来跟**主流认知不一样**的判断(例:"AGI 5 年内"在 2020 是非共识,2026 是共识)
- **反直觉**的因果(例:"做更少的事才能做更多")
- **嘉宾独有的判断**,你在别处听不到(例:Naval 的 specific knowledge、PG 的 live in the future)
- **行业内部人才知道的内幕逻辑**(例:"国内 AI 创业 80% 资源花在合规上")

**什么不算非共识**:
- 复述主流观点(❌ "AI 会改变所有行业")
- 数据陈述(❌ "我们这个季度增长了 30%"——这是事实不是判断)
- 老生常谈的鸡汤(❌ "保持初心很重要")

**格式**:
```html
<section class="contrarian">
  <div class="contrarian-label">🔥 非共识 · Contrarian Takes</div>
  <div class="contrarian-item">
    <p class="contrarian-quote">"原话引用,verbatim 中文"</p>
    <p class="contrarian-why"><strong>为什么非共识 · </strong>多数人觉得 X,他说 Y,因为 Z。</p>
  </div>
  ...
</section>
```

CSS 写在 `templates/base.html` 的"中文模式扩展样式"section。

### 章节正文:书面正文 + 可折叠逐字底档(中文模式)

正文由 CLEAN 阶段(见 `clean.md`)产出书面版:说话人 + 时间戳保留,内容书面重写为可读中文,但**书面化 ≠ 概括**——每个论点/数字/专名/因果必须保下来,Polish 只改"怎么说"不改"说了什么"。

逐字口语原稿按章放进可折叠底档,内容 == ASR 原始 transcript,不丢、不概括,供读者对照查证。**渲染细节(HTML 结构、`<details>` 约定、CSS)见 `render.md`**,本文件不重复规定。

> **弃用**:旧的 `.ch-summary` 200-400 字浓缩版型已不用;`ch-pull` 也不再需要(金句已在非共识区)。

### 文件名约定(中文模式)

文件名跟双语模式一样,**但日期、source slug、嘉宾名等元数据要从中文 metadata 抓**:
- 小宇宙:`{date}_{podcast}_{host}_{topic}.html`(host slug 用拼音)
- B 站:`{date}_{uploader}_{topic}.html`

例:`2026-05-13_kechuang-50-ren_zhang-yiming_AI-and-bytedance.html`(科创 50 人:张一鸣谈 AI 与字节)
