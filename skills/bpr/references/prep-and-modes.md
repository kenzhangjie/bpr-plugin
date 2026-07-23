# PREP · 预处理 / 断句 / 模式判定

> 阶段 2 · PREP 专用。清洗断句、说话人、时间戳、auto-subs 重建;统计 CJK 占比 → 选模式(英文双语 / 中文浓缩)。

---

## auto-subs 预处理(模式退化)

YouTube 只拿到 auto-subs(无标点、无 speaker)时,PREP 先做退化处理再进翻译:

1. **在翻译 Step 1 之前**,先做"重新断句 + 加标点"——把流式无标点文本切成正常英文句子。这步走在三步法之前,不影响"每段都跑三步法"的硬规则
2. **从 metadata 推断 speaker**:`uploader = host` / `description 里的 guest = 嘉宾`,根据语境分 turn(谁在提问 / 谁在回答)
3. **如果不能可靠区分谁在说话**:退化成 **essay 模式渲染**(不写 `.speaker / .turn`),保留章节级时间戳标注。**不要瞎猜 speaker**——猜错比退化更糟

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
