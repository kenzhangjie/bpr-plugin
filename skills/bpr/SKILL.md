---
name: bpr
description: 把英文 podcast transcript / 字幕 / 访谈文本 / 博客 essay / 长文 article 转换为编辑设计风格的双语阅读 HTML。当用户输入 "/bpr" 后跟字幕、transcript、播客文本、博客 URL 或粘贴的英文长文,或明确要求"双语阅读器"/"podcast 整理"/"博客整理"时触发。覆盖 SRT、纯文本 transcript、有时间戳的 transcript、博客/essay 四种输入。输出单文件 HTML,包含 Hero、TL;DR、章节正文、目录、深色模式。
---

# BPR · Bilingual Podcast / Essay Reader

> **占位符约定**:
> - `<SKILL_DIR>` = 本 skill 安装目录(模型从已 Read 的 SKILL.md 文件路径推算,通常形如 `~/.claude/plugins/.../skills/bpr/`)
> - `<output_dir>` = 输出文件落盘目录,默认 `~/Documents/Transcript/`,首次使用时询问用户偏好

## 触发条件
- 用户输入 `/bpr <内容>` 或 `/bpr` 后跟 transcript / 博客 URL / 长文文本
- 用户上传字幕文件并要求"做成双语阅读器"
- 用户明确说"按 BPR 规则"

## 核心步骤

| # | 步骤 | 加载哪些 reference |
|---|---|---|
| 0 | URL 输入预处理(YouTube → yt-dlp 拉字幕;blog → WebFetch) | `references/rules.md` "URL 输入处理" |
| 1 | 识别输入类型(SRT / 带时间戳 transcript / 纯文本 transcript / blog essay) | — |
| 2 | 预处理(合并跨条句、提取说话人、标注时间戳;auto-subs 需要重断句+加标点) | — |
| 3 | 章节切分(按下方"自适应"表) | — |
| 4 | 提炼 TL;DR(按下方"自适应"表 + 描述性 h2) | `references/rules.md` 看每条 TL;DR 的 4 元素格式 |
| 5 | **逐句翻译**(三步法,每章每段都跑,不跳过) | **`references/translation-prompt.md`** 必读 |
| 6 | 生成 HTML | **`templates/base.html`** copy 骨架 + `references/rules.md` 看双语对照 / inline link 规范 |
| 7 | 质量自检 | `references/checklist.md` |
| 8 | **(可选)海报阶段**:仅当 `海报`/`分享版`/`poster` 修饰词出现时跑 | **`references/poster-rules.md`** + `references/poster-template.html` + `scripts/crop_and_share.py` |

> **加载策略**:不要在第 1 步就读完所有 reference。只在到达对应步骤时再读对应文件,节省 context。
> **YouTube URL 输入**:走 step 0 调用 `scripts/fetch_youtube.sh`,**不要**假装能直接 WebFetch 到 transcript。

## 自适应规模

### 章节数

| 输入字数 | 章节数 |
|---|---|
| < 1,500 | 3-5 |
| 1,500 - 6,000 | 5-8 |
| 6,000 - 15,000 | 8-12 |
| > 15,000 | 12-18(可分 part) |

不要为了凑数硬切。3 章自然 > 5 章碎片。

### TL;DR 数量

| 输入规模 | TL;DR 条数 |
|---|---|
| < 1,500 字 / < 15 min | 3-5 |
| 1,500 - 6,000 字 / 15-30 min | 5-7 |
| 6,000 - 15,000 字 / 30-90 min | 8-12 |
| > 15,000 字 / > 90 min | 12-18(可分组) |

## 翻译规则(简版,完整规则见 `translation-prompt.md`)

- **每章每段都跑三步法**(Translate → Reflect → Improve),不跳过、不偷懒、不在意 token 消耗
- 每章只输出 Step 3 改进版,Step 1/2 是内部自检
- 术语保留原文:PM / IC / PMF / AI-first / builder / ROI / CAC / LTV / ARR / agent / harness / agentic / RAG 等
- 口语感保留:uh / um → 呃 / 嗯
- 引用人名:英文 + 中文并存(第一次出现;之后只用英文)
- inline link **preserve**:英文段写 `<a>`,中文段同一个 `<a>`,不重复打印 URL 文本
- 不粉饰、不意译、不漏内容
- 不编造任何 URL / 头像 / LinkedIn

## 输入模式差异

### Podcast / Interview / 访谈 transcript
- 渲染 `.turn / .speaker / .timestamp`
- Hero kicker:`{Podcast} with {Host} · {YYYY-MM-DD} · 双语整理`
  → 主持人 / 嘉宾从原文提取,**4 个 podcast 模板范例**见 `lessons-learned.md` L1
- 文件名 → 见上方"输出"章节的四种 pattern

### Blog post / Essay / 单作者长文
- **不**渲染 `.turn / .speaker / .timestamp`,正文用 `.body-block` + `.bilingual` 句级对照
- Hero kicker:`{Publication} · Essay · {YYYY-MM-DD}`
  例:`Anthropic Blog · Essay · 2025-04-29` / `nav.al · Essay · 2024-04-28` / `Paul Graham · Essay · 2025-XX-XX`
- `.chapter-meta` 用关键词概括,不放时间戳
- 文件名 → 见上方"输出"章节的四种 pattern

## 硬规则(必读 → `references/lessons-learned.md`)

生成 HTML 前**必须**读 `lessons-learned.md`,里面记录了:
- **L1 主持人/嘉宾识别**:不准默认 Lenny,podcast slug 不许泛指,文件名必带嘉宾 slug
- **L2 桌面布局**:`fixed TOC + margin-left:260px`,DOM 结构强约束,mobile-only 元素 base 必须 `display:none`
- **L3 分块写入**:HTML > 30KB 或 > 5 章必须用骨架 Write + 逐章 Edit

**关键**:所有 HTML 结构 + CSS 直接从 `templates/base.html` copy 骨架,**不要重写、不要再发明**。

## 修饰词

- `只英文` → 跳过中文
- `深色` → 暗色主题(已默认支持切换)
- `简洁` → 减少装饰
- `正式` → 去口语化
- `速读` → 折叠双语,默认只显中文
- `学习` → 双语并排两列
- `带批注` → 在 callout 中加入 `[Reader note]`
- **`海报` / `分享版` / `poster`** → 在双语 HTML 之外**额外**生成一张可分享的长图 PNG(深色,1080 宽,无水印)

## 海报模式 / Share Poster

当用户在 `/bpr` 命令里附带 `海报` / `分享版` / `poster` 修饰词,**先按常规流程出双语 HTML**,然后**再加一步**生成长图 PNG。

### 触发判定
- 修饰词出现 → 海报阶段必跑
- 没出现但用户事后说"做成图"/"出张海报" → 用已生成的 BPR HTML 内容,跑海报阶段
- 用户说"只要图,不要 HTML" → 仍按完整 BPR 流程提炼内容,只是跳过 HTML 落盘

### 硬要求(运行前先验证)

| 工具 | 检查 |
|---|---|
| `python3 -c "from PIL import Image"` | macOS 默认有 Pillow,没装就 `pip3 install Pillow` |
| Headless Chrome | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` 存在 |
| 模板文件 | `references/poster-template.html`(本 skill 自带) |
| crop 脚本 | `scripts/crop_and_share.py`(本 skill 自带) |

### 工作流(详见 `references/poster-rules.md`)

1. **复用 BPR 已提炼的内容**:hero / TL;DR(取 3-6 条最强)/ 章节关键金句 / 引用 → 不要重新读原文
2. **挑 5-9 个海报 section** —— 不用每节都填,根据内容性质选,但 hero/stats/quotes/takeaways 几乎必出
3. **复制模板**:`cp references/poster-template.html <output_dir>/<slug>-poster.html`
4. **填入内容**:用 Edit 工具改 hero / 各 section 文案 / 章节金句
5. **Chrome 渲染**:headless,2x retina,1080x8000 画布,输出 raw PNG
6. **裁剪 + 降采样**:`scripts/crop_and_share.py raw.png hidpi.png share.png`
7. **报告 3 个产物**:HTML reader / hidpi 海报 / 分享版海报

### ⚠️ 无水印硬规则

`poster-template.html` **不包含**:
- 对角重复的 `.watermark-layer`(SVG repeating)
- "整理 · {作者名}" 的 hero 右上 chip
- footer 右下的 brand 区块、头像圆、`© 2026 X` 版权行

模板里这些位置都是干净的——**不要从其他海报复制带水印的版本回来**。如果用户**主动要求**加水印,再单独按要求加。

### 输出文件名

海报阶段沿用 BPR 文件名 stem,加后缀:

| 产物 | 文件 |
|---|---|
| 双语 HTML | `<stem>.html`(原 BPR 输出) |
| 海报源 HTML | `<stem>-poster.html` |
| 海报 hidpi | `<stem>-poster-hidpi.png`(2160 宽,2x retina) |
| 海报分享版 | `<stem>-poster-share.png`(1080 宽,~2MB) |

四个文件都落到 `<output_dir>`(默认 `~/Documents/Transcript/`)。

## 输出

### 文件名(必须遵守)

**核心规则**:
- 用 `_` 分隔主要部分(date / source / person / topic)
- 用 `-` 在词内部和多词组合(`anton-osika` / `lovable-200m-arr`)
- 全小写,无空格 / 中文 / 大写
- **日期 = 内容发布日期**,不是处理日期
  - YouTube → metadata.json 的 `upload_date`(YYYYMMDD → YYYY-MM-DD)
  - 博客 → 文章页 `<time>` / meta 标签 / 顶端日期
  - 都拿不到 → 明确问用户,**不要静默用今天**

**四种 pattern**:

| 内容类型 | 模板 | 例子 |
|---|---|---|
| Podcast 访谈(单一固定主持人:20VC / Lenny / Dwarkesh / Naval Podcast / Training Data) | `{date}_{podcast}_{guest}_{topic}.html` | `2024-09-12_20vc_anton-osika_lovable-200m-arr.html` |
| Podcast 多主持 / 轮值(Y Combinator / Acquired / Pivot / All-In) | `{date}_{podcast}_{host}-x-{guest}_{topic}.html` | `2024-11-08_y-combinator_garry-tan-x-anton-osika_vibe-coding.html` |
| Essay 单作者站(paulgraham.com / nav.al / andrewchen.com) | `{date}_{author}_{topic}.html` | `2025-04-29_paul-graham_writes-and-write-nots.html` |
| Essay 多作者刊(Anthropic Blog / Substack with guests / Medium / Stratechery) | `{date}_{publication}_{author}_{topic}.html` | `2025-04-29_anthropic-blog_dianne-penn_writing-effective-tools.html` |

**Source slug 隐含 host / 单作者博客时,不重复写人**:
- `20vc` 已 = Harry → 不再写 `harry-stebbings`
- `lennys-podcast` 已 = Lenny → 不写
- `naval-podcast` 已 = Naval × Nivi → 不写
- `paul-graham` 已 = PG → 不单独写作者
- 多主持节目 / 多作者刊才显式写人

**主题 slug 控制 4-7 个 word**,从 h1 / hero-zh 抓最具体的 hook:
- ✅ `lovable-200m-arr` / `writes-and-write-nots` / `six-months-to-one-day`
- ❌ `the-future-of-product-management-in-the-age-of-ai`(超过 8 个 word)

**总长度目标 50-70 字符**(Finder 列表视图舒适宽度),> 80 字符 → 缩 topic。

### 输出路径

`<output_dir>`(默认 `~/Documents/Transcript/`,首次使用询问用户)

## 错误处理

- < 500 字:提示并询问要不要继续
- 非英文源:询问目标语言
- > 50K 字:询问是否分文件
- URL 输入:见 `references/rules.md` "URL 输入处理"
- YouTube auto-subs(无标点 / 无 speaker):预处理时先重断句 + 加标点,再走三步法翻译;无法可靠分 speaker → 退化成 essay 模式
