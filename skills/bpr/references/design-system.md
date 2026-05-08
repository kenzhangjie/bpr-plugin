# BPR · Design System(why,not what)

> CSS / DOM 完整代码 → `templates/base.html`,直接 copy。
> 本文件解释**设计决定背后的原因**,LLM 不需要,但你(Ken)和未来的 maintainer 需要。

## 美学锚点

- 编辑设计风格(Editorial)——参考:The New Yorker / The Atlantic / Stratechery
- 不是 SaaS landing page、不是 Notion 风、不是 Medium 默认
- 关键词:**克制 / 留白 / 字体层级 / 暖色基底**

## 字体选择

| 用途 | 字体 | 为什么 |
|---|---|---|
| 英文显示 | Playfair Display(serif,可变粗细)| 编辑感强,有 italic 优雅,适合 hero 大字 |
| 中文显示 | Noto Serif SC | 与 Playfair 字重接近,中英混排不打架 |
| UI / 元数据 | Inter | sans 中性,适合 toc / timestamp / kicker |
| 代码 | ui-monospace 系统栈 | 无需引入,系统字体自动选 SF Mono / Menlo |

## 主色板

### 浅色(默认)
- 背景 `#f5efe4`(暖米)——比纯白柔和、阅读久了不刺眼
- 强调 `#b04a2f`(红土)——编辑风经典色,有"印刷油墨"的厚度
- 主文字 `#2a2520` / 次文字 `#5c554c` / 浅文字 `#8a8278`
- 分割线 `#c9bfae`

### 深色
- 背景 `#1a1612`(深棕,不是黑)——避免纯黑的"仪表盘感"
- 强调 `#e07050`(红土提亮)
- 文字 / 分割线对应同色相变化

## 字号梯度(为什么大胆)

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

## 视觉装饰

- **不**用 emoji
- **不**用渐变背景
- **不**用阴影 box-shadow(除非必要)
- 强调用**红土色 underline / left border**,不用粗体不用大号
- TL;DR 的数字编号用 `decimal-leading-zero`(01 / 02 / ...)增加印刷感
- 章节之间的视觉节奏:80px 上下间距(给眼睛"翻页"的呼吸)

## 章节标题结构

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

## TOC 视觉规范

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

## 桌面布局选型

最终方案:**fixed TOC + container `margin-left:260px`**。

详见 `lessons-learned.md` L2——里面有踩坑历史和**为什么 grid / `margin:0 auto + padding-left` 都不行**的解释。

## 代码样式

`code` / `pre` 必须有专门样式,不能裸奔。原因:之前生成的 HTML 里 inline `<code>` 没样式时,渲染成跟正文一样字体的小字 —— 比如 `claude-api skill` 这种 token 看不出来是代码标识。

CSS 已经在 `templates/base.html` 写好,直接用。

## 打印样式

`@media print`:
- 隐藏 toc / 浮动按钮 / overlay
- container 撑满页面、padding 变小
- 章节 `break-inside:avoid` 避免章节中间分页
- 链接颜色变文字色,去掉 underline
