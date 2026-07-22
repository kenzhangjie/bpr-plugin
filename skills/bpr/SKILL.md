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

## 流水线 · 8 阶段

按顺序走。每个阶段到达时才读对应 reference(省 context),不要一开始读完所有。

| 阶段 | 做什么 | 读哪个 reference / 用哪个脚本 |
|---|---|---|
| **1 · INGEST** | 解析输入:URL 预处理 + 提取发布日期/标题/作者;判输入类型(SRT / 带时间戳 transcript / 纯文本 transcript / blog essay)。文件名也在此阶段按元信息定。 | `references/ingest.md`(URL 处理 / 发布日期 / 文件名规则)· `scripts/fetch/*` |
| **2 · PREP** | 预处理:合并跨条句、提取说话人、标注时间戳、auto-subs 重断句+加标点、VTT 滚动重建;**统计 CJK 占比 → 选模式**(≥60% 中文浓缩 / <60% 英文双语)。 | `references/prep-and-modes.md`(断句 + 中文模式判定与规范)· `scripts/fetch/clean_vtt.py` |
| **3 · CLEAN** | **(仅中文模式)** ASR 后处理三步:Analyze 全稿定术语表+存疑清单 → 按 ~25 turn 切窗,子代理 Review(纠错)+ Polish(书面化)→ 产出书面正文,保留逐字底档。英文模式跳过。 | `references/clean.md` |
| **4 · STRUCTURE** | 章节切分 + 提炼 TL;DR(描述性 h2)+(中文模式)🔥 非共识 takes。规模按下方"自适应"表。 | `references/render.md`(TL;DR 4 元素 / 中文 2 元素格式)· 下方自适应表 |
| **5 · TRANSLATE** | **仅英文双语模式**跑。逐句翻译走**四步法** + 逐字全覆盖 + 中文去口语词(两条硬约束)。中文模式跳过。 | **`references/translate.md`(必读:四步法 + 逐字 + 去口语词)** |
| **6 · RENDER** | 用 `templates/base.html` 骨架建 HTML(双语对照 / essay / 中文逐字三种版型)。`enrich` 子动作:essay 跑正文图自托管、podcast 注入时间戳。 | `references/render.md`(版型 / inline link / hero-meta 来源行)· `scripts/enrich/{extract_images,add_timestamps}.py` |
| **7 · VERIFY** | 质量自检 + **覆盖率硬闸**(渲染句数 ÷ 源稿 <~85% 回 TRANSLATE 补;不止查 en=zh 配对)。 | `references/verify.md` |
| **8 · PUBLISH** | 重建 landing index → 部署 bpr.ken.solar(proxy 直连)。 | `references/publish.md`(产物约定 + 部署)· `scripts/publish/build_index.py` |

**海报(可选分支)**:命令以 `/bpr all` 开头时,在 RENDER 后追加一步出 hidpi PNG。详见 `references/poster.md` · `scripts/poster/crop_and_share.py`。

> **抓取硬提醒**:YouTube / 小宇宙 / Bilibili 走 INGEST 的 `scripts/fetch/*`,**不要**假装能直接 WebFetch 到 transcript;小宇宙/Bilibili 无字幕内容必经飞书妙记转录(见 `references/ingest.md`)。
> **模式判定**:CJK ≥ 60% → 中文模式,**完全自动**,不接受修饰词覆盖(见 `references/prep-and-modes.md`)。
> **发布大小写坑**:Transcript 目录若有遗留 `INDEX.html`(大写),会导致 bpr.ken.solar 404 —— `rm INDEX.html` 再跑 build_index(见 `references/publish.md`)。

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

## 硬规则(生成 HTML 前必读 → `references/lessons-learned.md`)
- **L1 主持人/嘉宾识别**:不准默认 Lenny;podcast slug 不许泛指;文件名必带嘉宾 slug。
- **L2 桌面布局**:`fixed TOC + margin-left:260px`;mobile-only 元素 base 必须 `display:none`。
- **L3 分块写入**:HTML > 30KB 或 > 5 章必须用骨架 Write + 逐章 Edit。
- **关键**:所有 HTML 结构 + CSS 直接从 `templates/base.html` copy,**不要重写、不要再发明**。

## 修饰词
`只英文`(跳过中文)· `深色`(暗色,已默认可切)· `简洁`(减装饰)· `正式`(去口语化)· `速读`(默认只显中文)· `学习`(双语并排两列)· `带批注`(callout 加 `[Ken note]`)。
> 海报**不再用修饰词触发**,改为子命令前缀 `/bpr all`(见 `references/poster.md`)。

## 错误处理
- < 500 字:提示并询问要不要继续。
- 非英文源(非中/英):询问目标语言。
- > 50K 字:询问是否分文件。
- YouTube auto-subs(无标点/无 speaker):PREP 先重断句+加标点;无法可靠分 speaker → 退化成 essay 模式渲染。
- URL 输入细节 → `references/ingest.md`。
