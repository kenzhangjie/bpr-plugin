---
name: bpr
description: 把 podcast transcript / 字幕 / 访谈文本 / 博客 essay / 长文 article 转换为编辑设计风格的阅读 HTML。**英文**素材默认双语对照;**中文**素材自动切换到 "TL;DR + 非共识 + 章节回顾" 浓缩模式(CJK ≥ 60% 自动判定)。当用户输入 "/bpr" 后跟字幕、transcript、播客文本、博客 URL 或粘贴的长文,或明确要求"双语阅读器"/"podcast 整理"/"博客整理"时触发。覆盖 SRT、纯文本 transcript、有时间戳的 transcript、博客/essay 四种内容;URL 输入支持 YouTube / 小宇宙 / Bilibili。输出单文件 HTML,包含 Hero、TL;DR、(中文模式) 非共识 takes、章节正文、目录、深色模式。
---

# BPR · Bilingual Podcast / Essay Reader

## 触发条件
- 用户输入 `/bpr <内容>` 或 `/bpr` 后跟 transcript / 博客 URL / 长文文本 → 只出 HTML
- 用户输入 `/bpr all <内容>` → 出 HTML **+** 海报 hidpi PNG
- 用户上传字幕文件并要求"做成双语阅读器"
- 用户明确说"按 BPR 规则"

## 核心步骤

| # | 步骤 | 加载哪些 reference |
|---|---|---|
| 0 | URL 输入预处理 + **提取发布日期**(YouTube → `scripts/fetch_youtube.sh`;**小宇宙** → `scripts/fetch_xiaoyuzhou.sh` + 飞书妙记;**Bilibili** → `scripts/fetch_bilibili.sh` + 飞书妙记;blog → `scripts/extract_metadata.py`,curl 抓页面跑 7 种策略) | `references/rules.md` "URL 输入处理" + "发布日期提取" |
| 1 | 识别输入类型(SRT / 带时间戳 transcript / 纯文本 transcript / blog essay) | — |
| 2 | 预处理(合并跨条句、提取说话人、标注时间戳;auto-subs 需要重断句+加标点) | — |
| **2.5** | **🆕 语言检测**:统计 CJK 字符占比。**≥ 60% → 切到中文模式**(跳过 step 5 翻译,改走 TL;DR + 非共识 + 章节回顾结构);**< 60% → 英文双语模式**(继续原流程)| `references/rules.md` "中文模式 (Chinese-Only Mode)" |
| 3 | 章节切分(按下方"自适应"表) | — |
| 4 | 提炼 TL;DR(按下方"自适应"表 + 描述性 h2)+(**中文模式**)非共识 takes | `references/rules.md` 看每条 TL;DR 的 4 元素格式 + 中文模式的 2 元素格式 |
| 5 | **逐句翻译**(三步法,每章每段都跑,不跳过)— **仅英文双语模式跑此步**,中文模式跳过 | **`references/translation-prompt.md`** 必读 |
| 6 | 生成 HTML | **`templates/base.html`** copy 骨架 + `references/rules.md` 看双语对照 / inline link 规范 / 中文模式版型 |
| 6.5 | **🆕 时间戳(podcast 模式默认跑,不用等用户提)**:`python3 scripts/add_timestamps.py <transcript.*.vtt> <reader.html>`,给每个 `.turn` 注入 `<span class="timestamp">`。VTT 是滚动字幕,脚本已做滚动重建,别手写解析 | `scripts/add_timestamps.py`(见 L6) |
| 7 | 质量自检 — **含覆盖率硬闸(见 L6),不达标必须回 step 5 补全,不是只看 en=zh 配对** | `references/checklist.md` |
| 8 | **(可选)海报阶段**:仅当命令以 `/bpr all` 开头时跑 | **`references/poster-rules.md`** + `templates/poster-template.html` + `scripts/crop_and_share.py` |
| 9 | **重建 landing index**(每次都跑):扫 Transcript 目录所有 `*.html` → 重新生成 `index.html` | `scripts/build_index.py` |
| 10 | **部署到 bpr.ken.solar**(每次都跑):`cd "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript" && brctl download . && NODE_USE_ENV_PROXY=1 vercel --prod --yes`(`NODE_USE_ENV_PROXY=1` 必带:Node fetch/undici 默认不读 http_proxy,国内直连 vercel.com 会被 GFW 重置报 `socket disconnected before secure TLS`;curl 能通≠CLI 能通) | — |

> **加载策略**:不要在第 1 步就读完所有 reference。只在到达对应步骤时再读对应文件,节省 context。
> **YouTube URL 输入**:走 step 0 调用 `scripts/fetch_youtube.sh`,**不要**假装能直接 WebFetch 到 transcript。
> **小宇宙 / Bilibili URL 输入**:走 step 0 调用对应 fetch 脚本,**没字幕的内容必经飞书妙记转录**——详见 `references/rules.md` "小宇宙 / Bilibili → 飞书妙记 一站式流程"。
> **中文判定**(step 2.5):**完全自动**,不接受用户用修饰词覆盖。CJK ≥ 60% → 中文模式,否则双语。
> **Step 9 + 10 注意**:macOS 文件系统大小写不敏感但**保留**——见 `lessons-learned.md` L5。如果 Transcript 目录里有遗留的 `INDEX.html`(大写),build_index.py 会"覆盖"内容但保留大写文件名,Vercel 不会把它当 root,bpr.ken.solar 会 404。修法:`rm INDEX.html` 再跑 build_index。

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

### Podcast / Interview / 访谈 transcript (英文)
- 渲染 `.turn / .speaker / .timestamp`
- Hero kicker:`{Podcast} with {Host} · {YYYY-MM-DD} · 双语整理`
  → 主持人 / 嘉宾从原文提取,**4 个 podcast 模板范例**见 `lessons-learned.md` L1
- 文件名 → 见上方"输出"章节的四种 pattern

### Blog post / Essay / 单作者长文 (英文)
- **不**渲染 `.turn / .speaker / .timestamp`,正文用 `.body-block` + `.bilingual` 句级对照
- Hero kicker:`{Publication} · Essay · {YYYY-MM-DD}`
  例:`Anthropic Blog · Essay · 2025-04-29` / `nav.al · Essay · 2024-04-28` / `Paul Graham · Essay · 2025-XX-XX`
- `.chapter-meta` 用关键词概括,不放时间戳
- 文件名 → 见上方"输出"章节的四种 pattern

### 🆕 中文模式 (Chinese-Only Mode)
- 触发:step 2.5 检测到 CJK ≥ 60%(完全自动)
- **不**跑翻译三步法,正文是浓缩中文摘要,不是逐句对照
- Hero kicker:`{Podcast} with {Host} · {YYYY-MM-DD} · 中文整理`(关键词是"中文整理",跟英文版的"双语整理"区分)
- 结构:Hero → TL;DR(中文 2 元素)→ 🔥 **非共识 takes**(中文 verbatim 引用 + 为什么非共识)→ 章节回顾(200-400 字/章浓缩)→ Footer
- **非共识 section 是中文模式的灵魂**——做不好整篇就是简陋摘要器,严格按 `rules.md` "非共识 section 写作原则" 写
- 完整规范、CSS 类名(`.contrarian` / `.contrarian-quote` / `.contrarian-why`)、章节模板见 `references/rules.md` "中文模式 (Chinese-Only Mode)" section

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
- `带批注` → 在 callout 中加入 `[Ken note]`

> 注:**海报输出不再用修饰词触发**。改为子命令前缀:`/bpr all <内容>` 即同时出 HTML + 海报 hidpi PNG。详见下方"海报模式"。

## 海报模式 / Share Poster

当用户命令以 **`/bpr all`** 开头,**先按常规流程出双语 HTML**,然后**再加一步**生成 hidpi 长图 PNG。

### 触发判定
- 命令首 token 是 `all`(`/bpr all <URL>` / `/bpr all <transcript>`)→ 海报阶段必跑
- 命令没有 `all` 但用户事后说"做成图"/"出张海报" → 用已生成的 BPR HTML 内容,跑海报阶段
- 用户说"只要图,不要 HTML" → 仍按完整 BPR 流程提炼内容,只是跳过 HTML 落盘
- **不再支持** `海报` / `分享版` / `poster` 这类后置修饰词触发(已废弃)

### 硬要求(运行前先验证)

| 工具 | 检查 |
|---|---|
| `python3 -c "from PIL import Image"` | macOS 默认有 Pillow,没装就 `pip3 install Pillow` |
| Headless Chrome | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` 存在 |
| 模板文件 | `templates/poster-template.html`(本 skill 自带) |
| crop 脚本 | `scripts/crop_and_share.py`(本 skill 自带) |

### 工作流(详见 `references/poster-rules.md`)

1. **复用 BPR 已提炼的内容**:hero / TL;DR(取 3-6 条最强)/ 章节关键金句 / 引用 → 不要重新读原文
2. **挑 5-9 个海报 section** —— 不用每节都填,根据内容性质选,但 hero/stats/quotes/takeaways 几乎必出
3. **复制模板到临时位置**:`cp templates/poster-template.html /tmp/<slug>-poster.html`(中间产物,不要落到 Transcript 目录)
4. **填入内容**:用 Edit 工具改 hero / 各 section 文案 / 章节金句
5. **Chrome 渲染**:headless,2x retina,1080×12000 画布,输出 raw PNG 到临时位置
6. **裁剪**:`scripts/crop_and_share.py raw.png "/Users/ken/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/<stem>-poster.png"`(直接输出最终命名,无 `-hidpi` 后缀)
7. **清理中间产物**:删除 `/tmp` 下的 poster HTML 和 raw PNG(crop 脚本已自动删 raw)
8. **报告 2 个产物**:`<stem>.html`(双语 HTML reader)+ `<stem>-poster.png`(海报)。**不保留 poster HTML**——它是一次性中间产物。

### ⚠️ 无水印硬规则

`poster-template.html` **不包含**:
- 对角重复的 `.watermark-layer`(SVG repeating)
- "整理 · {作者名}" 的 hero 右上 chip
- footer 右下的 brand 区块、头像圆、`© 2026 X` 版权行

模板里这些位置都是干净的——**不要从其他海报复制带水印的版本回来**。如果用户**主动要求**加水印,再单独按要求加。

### 输出文件名

海报阶段最终**只产出 2 个文件**:

| 产物 | 文件 |
|---|---|
| 双语 HTML(主输出)| `<stem>.html` |
| 海报(归档 + 分享)| `<stem>-poster.png`(2160 宽,2x retina) |

两个文件都落到 `/Users/ken/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/`。

**中间产物**(`<stem>-poster.html` 和 `<stem>-poster-raw.png`)放在 `/tmp/`,跑完不要拷到 Transcript 目录。crop 脚本会自动删 raw PNG;poster HTML 由调用流程在 step 7 删除。

需要分享小图(1080 宽)就 `sips -Z 1080 <stem>-poster.png --out <stem>-poster-share.png`(降采样可选,放大不可逆)。

## 输出

### 文件名(必须遵守)

**核心规则**:
- 用 `_` 分隔主要部分(date / source / person / topic)
- 用 `-` 在词内部和多词组合(`anton-osika` / `lovable-200m-arr`)
- 全小写,无空格 / 中文 / 大写
- **日期 = 内容发布日期**,不是处理日期 → **直接跑 `python3 scripts/extract_metadata.py <URL>`**,完整规则见 `references/rules.md` "发布日期提取"
  - 提取优先级:`extract_metadata.py`(博客)/ `fetch_youtube.sh` metadata.json(YouTube)→ Episode 平台页 → WebSearch → 问用户
  - **拿不到时必须问用户,绝不静默用今天**

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

### 真值表(URL → 文件名)

跑 `extract_metadata.py` 拿到 `date` + `source_slug`,再加上从内容里抓的 `guest`/`author`/`topic`,组装成下面这种:

| 输入 URL | 输出文件名 |
|---|---|
| `https://www.lennysnewsletter.com/p/building-lovable-anton-osika` | `2025-03-09_lennys-podcast_anton-osika_lovable-10m-arr-60-days.html` |
| `https://andrewchen.com/the-adjacent-user-theory/` | `2020-07-01_andrew-chen_adjacent-user-theory.html` |
| `https://paulgraham.com/writes.html` | `2024-10-01_paul-graham_writes-and-write-nots.html` |
| `https://www.youtube.com/watch?v=SlGRN8jh2RI`(Sequoia AI Ascent · Boris Cherny)| `2026-04-XX_sequoia_boris-cherny_coding-is-solved.html` |
| `https://www.anthropic.com/news/writing-effective-tools` | `2025-04-29_anthropic-blog_dianne-penn_writing-effective-tools.html` |
| `https://nav.al/specific-knowledge` | `2018-XX-XX_naval_specific-knowledge.html` |

**几个隐含规则**:
- `lennys-podcast` 已含 host(Lenny Rachitsky)→ 文件名只写 guest(`anton-osika`)
- `paul-graham` / `naval` / `andrew-chen` 单作者站 → 不重复写作者,直接 `{date}_{source-slug}_{topic}`
- `sequoia` / `y-combinator` 多主持节目 → 文件名要带 host × guest(若适用)或单 guest
- `anthropic-blog` / 其他 publication blog → `{date}_{publication}_{author}_{topic}`

### 输出路径

`/Users/ken/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/`

## 错误处理

- < 500 字:提示并询问要不要继续
- 非英文源:询问目标语言
- > 50K 字:询问是否分文件
- URL 输入:见 `references/rules.md` "URL 输入处理"
- YouTube auto-subs(无标点 / 无 speaker):预处理时先重断句 + 加标点,再走三步法翻译;无法可靠分 speaker → 退化成 essay 模式
