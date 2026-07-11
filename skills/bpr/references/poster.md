# 海报模式规则 / Poster Rules

> /bpr 海报阶段专用。**触发**:命令以 `/bpr all` 开头(`/bpr all <URL>` 或 `/bpr all <transcript>`)。先按主流程出双语 HTML,再读这个文件做海报。

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

> **重要约定**:海报源 HTML 和 raw PNG 都是**临时中间产物**,放 `/tmp/`,**不要**落到 Transcript 目录。
> 最终 Transcript 目录只有 `<stem>.html` + `<stem>-poster.png` 两个文件。

### 1. 复制模板到 /tmp

```bash
cp /Users/ken/.claude/skills/bpr-skill/templates/poster-template.html \
   "/tmp/<stem>-poster.html"
```

### 2. 用 Edit 工具改三件事(对象是 /tmp 下的副本)
- `<title>` 和 hero h1 / .title-cn
- 各 section 的文案 / 卡片
- footer 的 source URL + 日期

**不要触碰**:CSS / 整体 layout / section class 名

### 3. Chrome headless 渲染(到 /tmp)

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --hide-scrollbars --disable-gpu \
  --force-device-scale-factor=2 \
  --window-size=1080,12000 \
  --screenshot="/tmp/<stem>-poster-raw.png" \
  "file:///tmp/<stem>-poster.html"
```

⚠️ 路径有空格的话用引号包,`file://` 必须是绝对路径。

### 4. Crop 到 Transcript 目录(直接最终命名,无 -hidpi 后缀)

```bash
/usr/bin/python3 /Users/ken/.claude/skills/bpr-skill/scripts/poster/crop_and_share.py \
  /tmp/<stem>-poster-raw.png \
  "/Users/ken/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/<stem>-poster.png"
```

> 注:用 `/usr/bin/python3` 而不是 `python3`,因为 brew 的 python3 可能是损坏版本(已踩坑)。系统 3.9 自带 Pillow 走得通。

脚本会:
1. 找最后一行 brightness>120 的像素位置
2. 加 80px padding 后裁掉下方空白
3. 输出 2x retina(2160 宽)hidpi PNG 到 Transcript 目录
4. 删除 raw 中间文件(/tmp/<stem>-poster-raw.png)

### 5. 清理中间 poster HTML

```bash
rm /tmp/<stem>-poster.html
```

(crop 脚本只删 raw PNG,不会动 HTML——必须手动删。)

> 需要分享小图(1080 宽)自己 `sips -Z 1080 <stem>-poster.png --out <stem>-poster-share.png`。降采样可选,放大不可逆。

### 5. Verify(强制清单,渲染完每一项都要确认)

#### 自动化检查(grep)
```bash
# 不应该有任何残留水印 / 模板占位文本
grep -iE 'watermark|harry同学|整理 ·|©|<!-- *\{' "<stem>-poster.html" && echo "❌ 残留" || echo "✅ 无残留"
```

#### 视觉自查(用 Read 工具看 PNG)
- [ ] **没有水印泄漏** —— 没有对角重复文字、没有 "整理 · X"、没有 "© 2026 X"
- [ ] **没有模板占位** —— 没有 `<!-- {kicker} -->` / `<!-- {publication} -->` 这种没替换掉的注释
- [ ] **section 没有溢出** —— 卡片文字没被截断、表格列没溢出 1080 宽
- [ ] **底部没有大块空白** —— crop 脚本应该已经处理,但要看一眼
- [ ] **顶部没有空白** —— 偶尔会有 hero 上方一片空,通常是 mobile-only 元素泄漏到桌面
- [ ] **中文字体加载** —— 中文不是方框 / 不是 fallback 衬线乱码
- [ ] **Hero 标题没换错行** —— 长标题要能在合适位置断行,不要孤悬一个字
- [ ] **数字 / quote / takeaway 这三个核心 section 都在**(海报识别度的关键)
- [ ] **footer 只有 source URL + 日期**,无品牌签名

#### 文件健康
- [ ] PNG 在 3-8 MB 之间(过大 = 没 optimize,过小 = 内容稀疏 / crop 切多了)
- [ ] 宽度 = 2160(`identify` / `sips -g pixelWidth`)
- [ ] 文件名 = `<stem>-poster.png`(无 `-hidpi` 后缀)
- [ ] Transcript 目录下**不应该**还有 `<stem>-poster.html`(已 step 5 删)
- [ ] `/tmp/<stem>-poster-raw.png` 已被 crop 脚本删除

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

**Transcript 目录最终只有 2 个产物**:

| 文件 | 用途 |
|---|---|
| `<stem>.html` | 双语 HTML reader(BPR 主输出) |
| `<stem>-poster.png` | 2160 宽,2x retina,归档 + 分享通用 |

中间产物全部放 `/tmp/`,跑完手动清理(crop 脚本会自动删 raw,但 poster.html 要 step 5 显式删):

| 中间文件(临时,/tmp 下) | 何时删 |
|---|---|
| `/tmp/<stem>-poster.html` | step 5 显式 `rm` |
| `/tmp/<stem>-poster-raw.png` | crop 脚本自动删 |

需要分享小图自己 `sips -Z 1080 <stem>-poster.png --out <stem>-poster-share.png`。
