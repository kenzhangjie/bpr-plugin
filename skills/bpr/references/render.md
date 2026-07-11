# RENDER · 版型 / TL;DR / inline link / 双语对照 / 图自托管 / 设计系统

> 阶段 5 · RENDER 专用。用 `templates/base.html` 骨架建页(双语对照 / essay / 中文逐字三种版型);`enrich` 子动作 = essay 正文图自托管 + podcast 时间戳。CSS/DOM 完整代码全在 `templates/base.html`,直接 copy,不要重写。

---

## TL;DR 标题写法

- `tldr-label` 固定写 `TL;DR · 速读`
- `tldr h2` **不写死数字**(❌ "11 条来自 Anthropic 内部的判断")
- `tldr h2` 用**描述性主题**(✓ "Anthropic PM 的工作怎么变了")
- 数字可以提,但不是唯一核心信息

## 每条 TL;DR 格式

每条由 4 个元素组成。**DOM 书写顺序固定**(claim → quote → context → explain),**视觉顺序由 CSS `order:` 控制**(`.tldr li` 是 flex column),所以生成时照常按下面顺序写 `<p>`,不用手动调序:

1. **中文论点**(15 字内)— `.tldr-claim` ·(渲染:斜体、深色,视觉第 2)
2. **英文金句**(原文 ≤ 30 词)— `.tldr-quote` ·(渲染:**粗体、最深、字号最大,视觉第 1 = 每条的标题**)
3. **英文上下文**(原文 1-2 句,40-80 词,提供金句的对话语境)— `.tldr-context` ·(渲染:轻灰,视觉第 3)
4. **中文解释**(≤ 60 中文字,1-2 句)— `.tldr-explain` ·(渲染:轻灰,视觉第 4)

> 视觉层级(2026-06 调整,模板已固化):**英文金句(粗体最深)→ 中文论点(斜体深)→ 英文上下文(轻灰)→ 中文解释(轻灰)**。英文金句是每条 TL;DR 的视觉锚点,不再是中文论点。

### 英文上下文 (`.tldr-context`) 写作原则

- 直接从 transcript / 原文复制,不改写、不润色
- 取金句**前后相邻**的 1-2 句话(不是金句本身)
- 让读者看到金句"为什么会出现"——前因或紧接的展开
- 视觉上比金句弱:更小字号 / 普通体(非斜体)/ 颜色更浅
- 如果金句本身已经独立成段、前后没有可补充的自然延伸,**可以省略**这一项
  (省略 > 硬塞低质量上下文)

### 例子

```html
<li>
  <p class="tldr-claim">大厂光环不再加分,可能反而扣分</p>
  <p class="tldr-quote">"Your brands don't matter as much as how modern you are in your ability to deliver product."</p>
  <p class="tldr-context">"What if the established brands are working in a way that's not current? You work there for six years, you come out, and it feels like you're in a totally different world."</p>
  <p class="tldr-explain">在 Meta 干两年把某个算法跑快一点的故事,放进"现在公司怎么造产品"的对话里会显得非常苍白。</p>
</li>
```

CSS 已经写在 `templates/base.html`,不要重复定义。

## 金句优先级

1. 反直觉/反共识(最优先)
2. 有数字/数据支撑
3. 全文重复出现的核心论点
4. 押韵或对称结构(如 "...is dead, ...is alive")

## inline link 处理

- 原文 inline link **必须 preserve**,不能删
- 英文段:写 `<a href="...">link text</a>`(保留原 link text 和原 URL)
- 中文段:在中文翻译对应位置写**同一个 `<a>`**,link text 翻译,URL 保持
- **不要**在中文段重复打印 URL 文本(`(https://...)` 之类)——视觉噪音
- bare link("Learn more in our docs.") → 英文段保留 `<a>`,中文段也保留 `<a>` 同 URL

## 双语对照输出

### 适用条件
- 英文素材(YouTube / Podcast / 英文 article / 英文 transcript / 博客 essay):必须输出双语对照版
- 中文素材:仅输出单一中文版,不需要对照

### 对照颗粒度

- **句级对照**:原文一句英文紧跟一句中文,**不是段落级**
- 一个英文句子包成一个对照单元(`<div class="bilingual">` + `<p class="en">` + `<p class="zh">`)
- 长复合句允许在自然停顿处(分号、连接词)拆成 2 句对照
- 不允许"一段英文 + 一段中文翻译"的段落级对照(信息密度太低,难对位)

### 对照视觉规范

CSS 已经写在 `templates/base.html`(`.bilingual` / `.bilingual .en` / `.bilingual .zh`),
直接用,不要重新定义。

### 对照内容要求

- **保留原文 verbatim**,不省略口头语(you know / I mean / like 等可酌情保留以体现语气)
- 中文翻译以"信达雅"中的"达"为先——准确传递意思 > 字面对照
- 专有名词、公司名、人名保持英文原文(Stripe / DoorDash / Keith Rabois)
- 数字、单位保留原文($10M 不翻成"一千万美元")
- 引用他人:"翻译原则"中"人名英文 + 中文翻译并存"

### 与 TL;DR 的关系

- TL;DR 区域**仍然只用中文**,不做对照(追求最大信息密度)
- TL;DR 中的英文金句保留斜体英文 + 中文解释(按"每条 TL;DR 格式"规则)
- 对照只应用于**正文**(transcript / 博客内容)

### HTML 输出结构示例(blog / essay 模式)

```html
<div class="body-block">
  <div class="bilingual">
    <p class="en">"The idea of a PM makes no sense in the future."</p>
    <p class="zh">"未来'产品经理'这个概念将变得毫无意义。"</p>
  </div>
  <div class="bilingual">
    <p class="en">"The skill is more like being a CEO now — what are we building and why?"</p>
    <p class="zh">"这项技能现在更像是做 CEO — 思考的是:我们在构建什么、为什么要构建它。"</p>
  </div>
</div>
```

(podcast 模式:把 `.bilingual` 包在 `.turn-body` 内,前面有 `.turn-head` 显示 speaker + timestamp。)

### 例外

- 用户明确要求"只排英文" → 跳过中文,仅输出英文版
- 用户明确要求"只要中文" → 跳过英文,仅输出中文版
- 默认行为(无修饰词)= 双语对照

---

## 正文图自托管 (essay/blog 模式, step 6.2)

**目标**:把源站正文配图**下载到本地**跟 HTML 一起部署,不热链。规范早已存在于仓库(`images/<stem>/` + `<figure class="from-source ...">`),现由 `scripts/enrich/extract_images.py` 自动化。

**流程**:
1. essay/blog 模式,curl 到 raw HTML + 切好 article blocks(JSON,和渲染用的同一份)之后,跑:
   ```bash
   python3 scripts/enrich/extract_images.py \
     --html <raw.html> --blocks <article.json> \
     --stem <文件名去掉.html> \
     --transcript-dir "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript"
   # 源站正文容器 class 不是 available-content 时加 --content-class <class>
   # 源站配图更新、要强制重下:加 --refresh
   ```
2. 脚本 stdout 返回 JSON:`{anchors:[[article_index,{file,variant,alt}]...], hero:[...], skipped:[...], coverage:{...}}`。
3. 渲染时:
   - `hero[]` 的图放在**第一章正文开头**(或 hero 之后),variant 恒为 banner。
   - `anchors[]` 每条在**对应 article_index 的正文块之后**注入:
     ```html
     <figure class="from-source {variant}"><img loading="lazy" src="{file}" alt="{alt}"></figure>
     ```
   - `file` 已是相对路径 `images/<stem>/NN_slug.ext`,直接用。
4. **step 7 自检**:看 `coverage.ratio`,< ~0.9 在报告里显式警告"N 张图没抓到";`skipped[]` 里的原因(download-failed / too-small)也列给用户。

**规则**(与 L7 同步):自托管不热链;失败跳过不回退;尺寸/关键词去噪;变体按宽高比;`.manifest.json` 幂等;Substack 正文常重复两份,按图 id 去重(脚本已处理)。

**podcast 模式不跑**(YouTube/小宇宙/B站 正文基本无内嵌图)。

---

## Design System(why,not what)

> CSS / DOM 完整代码 → `templates/base.html`,直接 copy。
> 本节解释**设计决定背后的原因**,LLM 不需要,但你(Ken)和未来的 maintainer 需要。

### 美学锚点

- 编辑设计风格(Editorial)——参考:The New Yorker / The Atlantic / Stratechery
- 不是 SaaS landing page、不是 Notion 风、不是 Medium 默认
- 关键词:**克制 / 留白 / 字体层级 / 暖色基底**

### 字体选择

| 用途 | 字体 | 为什么 |
|---|---|---|
| 英文显示 | Playfair Display(serif,可变粗细)| 编辑感强,有 italic 优雅,适合 hero 大字 |
| 中文显示 | Noto Serif SC | 与 Playfair 字重接近,中英混排不打架 |
| UI / 元数据 | Inter | sans 中性,适合 toc / timestamp / kicker |
| 代码 | ui-monospace 系统栈 | 无需引入,系统字体自动选 SF Mono / Menlo |

### 主色板

#### 浅色(默认)
- 背景 `#f5efe4`(暖米)——比纯白柔和、阅读久了不刺眼
- 强调 `#b04a2f`(红土)——编辑风经典色,有"印刷油墨"的厚度
- 主文字 `#2a2520` / 次文字 `#5c554c` / 浅文字 `#8a8278`
- 分割线 `#c9bfae`

#### 深色
- 背景 `#1a1612`(深棕,不是黑)——避免纯黑的"仪表盘感"
- 强调 `#e07050`(红土提亮)
- 文字 / 分割线对应同色相变化

### 字号梯度(为什么大胆)

`hero h1` = **54px** 固定,不 clamp 缩小。原因:
- 编辑风的关键是"hero 必须有印刷感的视觉冲击"
- 缩小 h1 → 看起来像博客 / SaaS landing,丢掉所有 character
- 用户审美明确表达过"喜欢大胆 hero h1 + 紧凑正文"

字号从大到小的层级:
- hero h1:54px
- chapter h2:34px
- tldr h2:32px
- hero-zh:22px / ch-zh:20px / tldr-claim:18px / hero-lede:18px
- 正文 zh:16.5px / 正文 en:15.5px italic / tldr-quote:15px italic
- tldr-context:13.5px / chapter-meta + ch-range:12px / kicker:11-12px

### 视觉装饰

- **不**用 emoji
- **不**用渐变背景
- **不**用阴影 box-shadow(除非必要)
- 强调用**红土色 underline / left border**,不用粗体不用大号
- TL;DR 的数字编号用 `decimal-leading-zero`(01 / 02 / ...)增加印刷感
- 章节之间的视觉节奏:80px 上下间距(给眼睛"翻页"的呼吸)

### 章节标题结构

**英文是主标题**(serif h1/h2 大字号),**中文是副标题**(serif-zh,小一档,加粗但不抢戏)。

```html
<header class="hero">
  <div class="hero-eyebrow">{Podcast} with {Host} · {date} · 双语整理</div>
  <h1>From Six Months to <em>One Day</em></h1>
  <div class="hero-zh">六个月被压成一天 · Anthropic 怎么造产品</div>
  <p class="hero-lede">"<原文金句>"</p>
</header>

<section class="chapter">
  <div class="ch-num">Chapter 01</div>
  <h2>Six Months to One Day</h2>
  <div class="ch-zh">六个月 → 一天 · PM 周期被压成一周</div>
  <div class="ch-range">00:00 — 11:00 · Cat 的角色 · 慢 PM 时代结束</div>
</section>
```

**为什么不把中文塞进 h2 inline**:
- 中英文行高 / 字重不同,inline 会让 baseline 错位
- 视觉上读者需要先抓主标题,再看副标题——分行更清晰

### TOC 视觉规范

- 列宽 **240px**(中文 TOC 项 7-12 字最舒服)
- 字号 13.5px,line-height 1.45
- 标签用**描述性中文**,不要电报体:
  - ✅ "六个月 → 一天"、"角色融合 · taste 才稀缺"、"在龙卷风眼里保持冷静"
  - ❌ "流程极简"、"龙卷风眼里"、"工具分工"
- 编号写进链接文字本身,**不**用 CSS counter `::before`
  - ✅ `<li><a href="#ch1">01 · 六个月 → 一天</a></li>`
  - ❌ counter prefix 视觉上跟标题字号脱节
- TL;DR 项前**不加编号**(它不是章节)
- active 态用 `:has(a.active)` 给 li 加左侧 3px 红色边框 + 字色 accent + weight 500
- 顶端用 `Contents · 目录` 双语标签,letter-spacing .22em,UI 字体不是 serif

### 桌面布局选型

最终方案:**fixed TOC + container `margin-left:260px`**。

详见 `lessons-learned.md` L2——里面有踩坑历史和**为什么 grid / `margin:0 auto + padding-left` 都不行**的解释。

### 代码样式

`code` / `pre` 必须有专门样式,不能裸奔。原因:之前生成的 HTML 里 inline `<code>` 没样式时,渲染成跟正文一样字体的小字 —— 比如 `claude-api skill` 这种 token 看不出来是代码标识。

CSS 已经在 `templates/base.html` 写好,直接用。

### 打印样式

`@media print`:
- 隐藏 toc / 浮动按钮 / overlay
- container 撑满页面、padding 变小
- 章节 `break-inside:avoid` 避免章节中间分页
- 链接颜色变文字色,去掉 underline
