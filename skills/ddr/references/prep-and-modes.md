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
**CJK < 60%**(判定见下「语言检测算法」)且输入是 **transcript 类**(有 `>>` 或 speaker 信号)。**essay(单作者、无说话人轮换的博客/长文)跳过本节**,直接走原有 PREP 流程。

> ⏭ **先看有没有官方 speaker 标注**(2026-08-23 加,Substack 播客**默认走这条**):
> INGEST 的 Step B2 若跑成 `fetch_substack_transcript.py`,`substack_turns.json`
> 已经是本节的产出契约格式(已切句)——**Step 2 的逐窗说话人归属子代理整段跳过**,
> 拿到的是**真名字不是推断**,还省掉约 10 个子代理。
>
> ⚠️ **但 Step 1 的 glossary 扫描 + 专名纠错一步都不能省**。官方稿同样是机器转录,
> 实测与 YT 轨**错法完全一致**(`Code Pilot` / `Instruct GPT` / `Dolly` /
> `stable diffusion` 一个不少)。"官方"只保证说话人和断句,不保证专名。
> 跳过这层 = 静默出一篇专名全错的稿子。
> 具体做法:仍跑 `clean_en.py --scan`,把命中项塞进纠错子代理的 prompt,
> 只是这些子代理**只做专名纠错,不再做说话人归属**。
>
> 为什么值得专门加这一步:启发式"提问方 = 主持人"只能二分 host/guest。实测一期
> Lenny 访谈里,赞助商口播嘉宾整段 12 句被并进主持人,**覆盖闸和加译闸都查不出来**
> ——它们只问"词有没有丢/有没有多",不问"这句是谁说的"。归属错误在本流水线里
> **没有任何自动闸能兜**,只能靠源头拿到真标注。

对应脚本:
- `scripts/prep/clean_en.py` —— 切窗 / 拼装 / 闸门(`parse_blocks` / `split_windows` /
  `word_coverage` / `added_ratio` / `finalize` + CLI)
- `scripts/lib/glossary_lib.py` —— **glossary 的单一实现**(解析 / 构映射 / 套用 / 体检 /
  回写)。`~/.config/volc/volc_asr.py` import 的是同一份;两边曾各写一遍,而且两份都漏了
  词边界,详见 Step 4 的踩坑框。

**中文专名纠错走 `clean.md` 的 CLEAN 三步法,英文不跑那套(不书面化,逐字交 TRANSLATE)**——两条源清洗路径平行、互不调用。

### Step 1 · Analyze-lite(主代理,全稿 1 次)
读两份 ground truth,产出一份小 brief(塞进后续每个子代理 prompt,保跨窗一致):
- **`metadata.json`** 的 **description + title**(YouTube fetch 已抓到):从中找 "my guest is X" 类介绍句认嘉宾,`uploader`/channel 名认主持。
- **`~/.config/volc/glossary.txt`**:**必须用脚本反查全表,禁止人眼扫前几行判断"跟本期无关"**:

  ```bash
  python3 scripts/prep/clean_en.py --scan "$WORKDIR/transcript.txt"
  ```

  输出 `[{"term","misspellings","seen_in_source"}]` —— `term` 进 brief 的专名表,
  `misspellings` 进存疑清单,`seen_in_source` 非空的**必须**在 prompt 里点名(这些错法已确证出现在本期源里)。
  权重列(`|` 后第 2 列)忽略——那是给火山热词表用的,对英文纠错无意义(同 `clean.md` 约定)。

> ⚠️ **踩坑(2026-08-01,ILTB × Sam Altman)**:那次只 `head -20` 看了 glossary 前 20 行,
> 全是中文播客的名字,就判定"本期用不上"跳过了。实际全表 248 条里本期命中 **18 条**,
> 其中 `Codeex→Codex` 的错法在源字幕里真出现了 2 次。最后是靠手写存疑清单**碰巧**兜住的。
> **抽样判断 ≠ 检索**;glossary 只有几百条,全扫一遍是毫秒级的事,没有省的理由。

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
# 先把 split_windows 切出来的原始窗存成 JSON(list[str] 或 list[list[str]])——
# 不传 --windows 只能拿到一个全局数字,说不出「哪一窗」。
python3 scripts/prep/clean_en.py \
  --turns <拼好的 turns.json> \
  --raw <原始逐字稿 txt> \
  --windows <原始窗 windows.json> \
  --out <输出路径 turns.clean.json> \
  --names <本期专名清单 JSON,回写 glossary —— 见 Step 4,不是可选>
```

跑完看 stdout **第一行**:正常是 `专名硬映射 N 条(来自 glossary 第 3 列)· 保护名单 M 项`。
如果看到 `WARN: 专名硬映射为空` 或 `WARN: glossary 读不到`,说明**这一层空转了**,
先修 glossary 再继续 —— 别把 `coverage ok=True` 当成"全都跑过了"(覆盖率闸和硬映射是两回事)。

CLI 内部调用 `finalize(turns, raw, corrections, windows=...)`,产出三个数:

| 输出 | 问的是什么 | 不过怎么办 |
|---|---|---|
| `coverage` | 源词多重集被输出覆盖的比例 | < 0.98 视为丢句 |
| **逐窗覆盖 + 最差窗号** | **每一窗**的词有没有出现在输出里 | **把 WARN 点名的那几窗打回 Step 2 重派** |
| `added_ratio` | 输出里多出来的词占源词的比例 | > 0.05 只提醒,不拦(见下) |

**为什么必须传 `--windows`**(2026-08-07 修):`coverage` 只有一个全局数字,而本节要求
"把该窗打回 Step 2 重派" —— 拿不到窗号,这条硬规则**根本执行不了**。传了之后 CLI 直接打
`WARN: 这些窗覆盖 < 0.98,回 Step 2 重派:#7(0.612), #12(0.883)`,照着重派即可。
重做仍不过,该处标 `⟨?丢失⟩` 留人工,不无限重试。

**`added_ratio` 补的是另半边**:`coverage` 只问"源词有没有被盖住",子代理凭空加一整段
**完全不掉分**。加译率偏高 = 疑似加译 / 复述 / 幻觉。专名纠错本身会贡献少量新词(变体
只在源侧),所以它是**报告项不是硬闸** —— 偏高时抽查那几段,别机械重派。

当 LLM 纠正了一个尚未进 glossary 第 3 列的专名时,词覆盖可能略降(该变体只在源侧);
这属正常,沿用"标 `⟨?丢失⟩` 留人工"的逃生口。

### Step 4 · 确定性后处理 + 专名飞轮
`finalize` 在拼装时自动套用双语硬映射,补子代理的遗漏。映射来自 **`glossary.txt` 第 3 列
(错法)** —— 这是专名的**单一真源**。**英文由这一步套用,不跑 `volc_asr.py`**(那是中文专用)。

替换逻辑本身在 **`scripts/lib/glossary_lib.py`**,`volc_asr.py` import 的是同一份。
不许再各写一份 —— 它们曾经各写一份,而且**两份都没有词边界**(下面那条踩坑)。

> ⚠️ **踩坑(2026-08-07):`小红书` 被改成 `肖弘书`。**
> `肖弘|20|小红,小宏,小虹` 配上无边界的子串替换,把「小红书 / 小红帽 / 小红点」全改坏了。
> 更糟的是它发生在 **ASR 输出那一刻**(CLEAN 之前),而 CLEAN 的 prompt 写着"专名与
> glossary 不一致时信 glossary",VERIFY 的覆盖闸只查"有没有丢"不查"有没有被改错"
> —— 三道网全穿。现在三层防护:
> 1. **保护名单优先** —— glossary 第 1 列全部正确名 + `~/.config/volc/protect.txt`
>    里的常用词;同一起点上保护项永远赢。
> 2. **拉丁键强制词边界** —— `Codeex→Codex` 不会咬到 `Codeexes`。
> 3. **长度闸** —— CJK 键 < 3 字、拉丁键 < 4 字直接拒收 + WARN(2 字 CJK 键本质
>    不安全,未知碰撞防不住)。
>
> 加词之后跑一次体检:
> ```bash
> python3 scripts/prep/clean_en.py --check-glossary
> ```
> 列出被拒收的短键、冲突(同一错法映射到多个正确名)、与保护名单的碰撞。有冲突/碰撞时退出码 1。

> ⚠️ **旧文档说的 `correct_table.json` 已于 2026-07-25 并入 glossary 第 3 列**。
> `--correct-table` 只作遗留兼容,默认不启用;硬编那个路径会读到一个不存在的文件而**静默空转**
> (2026-08-01 实测:映射 0 条,脚本照样打印 `ok=True`)。现在缺文件会 WARN 到 stderr。

**回写飞轮(必做,不是可选)**:收尾传 `--names`,CLI 会把本期新专名 append 进
`~/.config/volc/glossary.txt`(与中文飞轮同一份文件)。不传 = 这一轮学到的专名全丢,
下期从零再猜。

**`--names` 要用带错法的新形态**(2026-08-07 起):

```json
[{"term": "Codex",      "seen_as": ["Codeex"]},
 {"term": "Ambrosino",  "seen_as": ["Ambercino", "Ambersino"]},
 {"term": "Legora",     "seen_as": []}]
```

只传 `["Codex", "Legora"]` 这种老形态仍然能跑,但**只写第 1 列**。而 `apply_correct_table`
**只吃第 3 列** —— 于是飞轮只让参考表变长,纠错层原地不动(2026-08-07 实测:284 条专名
只对应 38 条硬映射)。`seen_as` 填**本期源里真见过的错法**,这一层才会随着跑的期数变厚。

CLI 会打印 `glossary += N 条专名 · 错法 += M 条 · 拒收 K 条`,拒收原因走 stderr
(短键 / 已映射到别的正确名 / 与保护名单碰撞)。

> 只回写**确认过拼写**的专名(查过官网/报道的),别把 `⟨?⟩` 里的猜测写进真源——污染 glossary 比漏记更贵。
> 错法同理:本期真见过才填,没见过就只给 `"seen_as": []`。

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
