# 海报模式规则 / Poster Rules

> /bpr 海报阶段专用。先按主流程出双语 HTML,再读这个文件做海报。

---

## 输入复用原则

**不要重新读原文**。海报阶段的输入 = 你刚刚为 BPR 双语 HTML 生成的内容:
- Hero(英文标题 + 中文副标题 + lede 金句 + 嘉宾/作者抬头)
- TL;DR 列表(每条已经有 claim + quote + context + explain)
- 章节标题 + 章节关键金句 + 引用块

直接从这些素材里挑出 5-9 个最强的"卡片",装到海报模板对应位置。**不要去 verbatim 文本里再翻一遍**。

---

## 海报视觉锚点

照搬 `poster-template.html` 的视觉系统,**不要重写 CSS**:

- 1080px 宽,垂直排版
- 深底 `#0B0F19` + 紫 `#8B5CF6` / 橙 `#F97316` / 青 `#22D3EE` 三色 accent
- 标题渐变白→灰(`-webkit-background-clip:text`)
- Section 间距 72px
- **无对角水印 / 无 footer 品牌区块 / 无 hero 右上 chip**——模板已经清掉了,不要加回来

---

## 9 个 section 怎么选

模板有 9 个槽位,**不需要每个都填**。按内容性质挑 5-9 个:

| # | Section | 适合的内容 | BPR 素材来源 |
|---|---|---|---|
| **Hero** | 始终保留 | 标题 + 副标题 + lede 金句 + 抬头 | BPR hero 直接搬 |
| **01 数字** | 内容里有具体数字(规模 / 增速 / 时长 / $) | 选 3 个最有冲击力的 stats | TL;DR + 章节里 grep 数字 |
| **02 核心论点** | 文章有 "X ≠ Y" 或反共识对照结构 | 大等式 + 左右两块对照 | TL;DR 第一条通常就是 |
| **03 演化 / 对比** | 旧做法 vs 新做法 / Before-After | 3 行表格 | 章节里"过去 → 现在"的段落 |
| **04 单点深挖** | 有一个值得画图的产品/架构决策 | Before-After 卡片 | 章节里最具体的案例 |
| **05 技术 / 概念栈** | 内容点了多个工具 / 概念 / 理念 | 4-5 个小卡 | 章节里出现的关键词 |
| **06 角色 / 三连** | 三类人 / 三种状态 / 三阶段 | 3 张大色卡 | 内容里天然成三组的元素 |
| **07 组织 / 人** | 偏管理 / 文化 / 反直觉观察 | 4 张小卡 | TL;DR 里偏"软"的几条 |
| **08 金句** | 任何文章都该有 | 3 条原文金句 + 中译 | TL;DR 的 quote 字段直接搬 |
| **Takeaways** | 始终保留 | 3 列(对 X / 对 Y / 对 Z) | TL;DR 的 explain 重组分类 |

### 必出 section
- Hero
- TL;DR 改写的 stats / quotes / takeaways(至少出 2 个)

### 选填 section
- 02 核心论点 → 内容是否有清晰的"反共识对照"
- 03 演化对比 → 内容是否讲"以前 vs 现在"
- 04 单点深挖 → 是否有一个具体决策值得放大
- 05 / 06 / 07 → 看内容性质

### 不强求
- 一篇 essay 没数字 → 跳过 01,把 hero 下面直接接 thesis
- 一篇技术深文没角色三连 → 跳过 06
- 一篇业务复盘没架构 Before-After → 跳过 04

**5 章干净海报 > 9 章硬凑碎片**。

---

## 内容写作原则

### Stats 卡(01)
- `num` 字段:具体数字,带单位($10M / 7 天 / 65%+ / 8 个 → / 30 秒)
- `label` 字段:数字代表什么(15 字内)
- `sublabel` 字段:**为什么这个数字重要**(30 字内,带 `<b>` 强调关键词)

### Thesis 等式(02)
- `<span class="dim">` 旧观点 / 表面看法
- `<span class="neq">≠</span>` 中间符号(等于 / 不等于 / →)
- `<span class="strong">` 真正洞察 / 反共识结论
- 下面 compare 卡分 `bad`(红)和 `good`(绿)两块,各 1-3 行论证

### Quotes 卡(08)
- 直接从 BPR 的 TL;DR `quote` 字段搬,**保留英文原文**
- 中译写一行(灰色,不抢戏)
- 三色边框轮换:`accent`(默认橙)/ `alt`(紫)/ `third`(青)
- ≤ 30 词,选最锋利的

### Takeaways(09)
- 标准三列:`对 X 的 / 对 Y 的 / 对 Z 的`
- 每列 3-4 个 bullet
- 关键词加 `<b>`
- 从 BPR 的 TL;DR explain 字段重组,**按受众分类**

---

## 渲染流程(标准命令)

### 1. 复制模板

```bash
cp <SKILL_DIR>/references/poster-template.html \
   "<output_dir>/<stem>-poster.html"
```

> 占位符:`<SKILL_DIR>` = 本 skill 安装目录(从 SKILL.md 路径推算);`<output_dir>` = 默认 `~/Documents/Transcript/`

### 2. 用 Edit 工具改三件事
- `<title>` 和 hero h1 / .title-cn
- 各 section 的文案 / 卡片
- footer 的 source URL + 日期

**不要触碰**:CSS / 整体 layout / section class 名

### 3. Chrome headless 渲染

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --hide-scrollbars --disable-gpu \
  --force-device-scale-factor=2 \
  --window-size=1080,8000 \
  --screenshot="<output_dir>/<stem>-poster-raw.png" \
  "file://<output_dir>/<stem>-poster.html"
```

⚠️ 路径有空格的话用引号包,`file://` 必须是绝对路径。

### 4. Crop + 降采样

```bash
python3 <SKILL_DIR>/scripts/crop_and_share.py \
  <output_dir>/<stem>-poster-raw.png \
  <output_dir>/<stem>-poster-hidpi.png \
  <output_dir>/<stem>-poster-share.png
```

脚本会:
1. 找最后一行 brightness>120 的像素位置
2. 加 80px padding 后裁掉下方空白
3. 输出 hidpi 版(2x retina,2160 宽)
4. 输出分享版(downsample 到 1080 宽)
5. 删除 raw 中间文件

### 5. Verify
- Read 一下 share PNG 检查视觉
- 确认无水印、无溢出、无残留模板内容

---

## 常见失败 / 兜底

| 症状 | 原因 / 应对 |
|---|---|
| 截图全黑 | `file://` 路径忘记 URL-encode 空格 → 改用绝对路径 |
| 截图底部还有大块空白 | crop 脚本 brightness 阈值 120 调到 80 |
| 截图被截断(底部内容缺了) | window-size 高度从 8000 调到 12000 |
| 字体没加载 | 模板用系统字体 PingFang SC,Mac 默认有;Linux 渲染机要装中文字体 |
| 海报 section 太多溢出超长 | 删 section,留 5-6 个最关键的 |

---

## 输出约定

| 文件 | 用途 |
|---|---|
| `<stem>.html` | 双语 HTML reader(BPR 主输出) |
| `<stem>-poster.html` | 海报源 HTML |
| `<stem>-poster-hidpi.png` | 2160 宽,2x retina,文档归档用 |
| `<stem>-poster-share.png` | 1080 宽,~2MB,直接发朋友圈 / Telegram / Slack |

四个全部落到 `<output_dir>`(默认 `~/Documents/Transcript/`),**不另开子目录**。
