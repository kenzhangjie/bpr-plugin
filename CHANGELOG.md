# Changelog

All notable changes to this plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this plugin adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v1.6.3 — 2026-08-02

**reader 自带划线收藏 + 修掉 publish 里会删 landing 的守卫。**

- **模板加 `mark.ken.solar/embed.js`**:划线收藏以前靠发布后跑 `inject-embed.mjs` 事后注入,于是两条漏法——批量重渲染会把标签冲掉(114 篇里 12 篇栽在同一分钟的重渲染上),注入器跑完之后新发布的压根没有。标签进模板,生成即带。
- **`publish.md` 的 `INDEX.html` 守卫改用 Python 读真实 dirent**(L5)。原来的 `[ -f .../INDEX.html ] && rm` 在 macOS 大小写不敏感 FS 上,目录里只有小写 `index.html` 时判断也为真,会把 landing 页删掉——它想防的问题它自己会造成。

## v1.6.2 — 2026-07-23

**CLEAN 硬化(grilling 三项)+ 修 ch11 render bug。**

- **RENDER 脚本化**(Q3):新增 `scripts/publish/render_zh.py`,中文模式渲染从 agent 手写改为确定性脚本(消灭 L2/L3 render 回归)。render.md 改为指向脚本。
- **CLEAN 输出格式硬约束 + 修 bug**:子代理曾输出 `**Speaker N ts**` markdown 内联,导致渲染成字面文本(ch11 实测)。clean.md 钉死"turn 头独占行 `Speaker N HH:MM:SS`、禁 markdown 加粗";render_zh.py 解析器同时兼容两种格式兜底。
- **保真闸**(Q1):clean.md 新增 Step C.5——每窗 Polish 后 haiku 对账子代理核 missing/altered,非空打回重做、仍不过标 `⟨?丢失⟩`。
- **专名飞轮**(Q6):Analyze 专名自动 append 进 glossary.txt(去重/权重)+ ≤10字 子集吐 hotword-candidates.txt。
- 修 Step D 陈旧示例(阿帕比→Anthropic,非 "a paper")。

## v1.6.1 — 2026-07-23

**ASR 源头优化 Round 2 + landing 排序恢复。** (spec: `docs/superpowers/specs/2026-07-23-asr-source-round2-design.md`)

- **火山 ASR 迁 2.0(seedasr)裸跑**:2.0 传 `corpus.context` 会 55000001,故不传 context;基础字准更强(Anthropic/CoWork/scaling 零偏置即对)。env `VOLC_ASR_RESOURCE` 可回退 1.0。
- **热词文件层**:2.0 实测接受 `corpus.boosting_table_name`(与 context 不同路径)→ 恢复为源头字准手段(`--boosting`/env `VOLC_ASR_BOOSTING`,火山自学习平台建表)。
- **shownote → CLEAN**:`fetch_xiaoyuzhou.sh` 抓完整 shownote(不再只 og:desc[:500]);`clean.md` 的 Analyze/Review 读 shownote + podcast 名 + glossary 做专名纠错参考(shownote 是比 ASR 更可信的独立信源)。实测:Aultimate→Altimeter、小俊→小珺、阿帕比→Anthropic。
- **glossary 定位**:从"ASR context 底料"改为"CLEAN 纠错词库"(`词|权重` 格式,多期 shownote 沉淀,CLEAN 读词忽略权重)。
- **landing 排序恢复**(`build_index.py`):`内容时间`/`新增时间` 排序按钮 + `added-dates.json` 新增时间清单(Vercel birthtime 不可信,清单为准);扁平 `#entryList` + 客户端年份分隔。
- e2e:Freda 投资札记第2集 全链路跑通(fetch→2.0+热词→CLEAN 35 agent→STRUCTURE→RENDER),成品发布 bpr.ken.solar。

## v1.6.0 — 2026-07-23

**新增 CLEAN 阶段(ASR 后处理三步法)**,治火山 ASR 中文逐字稿两大硬伤:中英混录同音/近音错词 + 逐字口语可读性差。

- **流水线 7→8 阶段**:PREP 与 STRUCTURE 之间插入 **CLEAN**(仅中文模式)。见新 `references/clean.md`。
- **analyze / review / polish 三步法**(翻译四步法去掉 Translate):Analyze 全稿定术语表 + 存疑清单 → 按 ~25 turn 切窗,子代理 Review(纠错)+ Polish(书面化)。错词四分类:同音近音 / 专名 / 断句直接改,真不可判标 `⟨?候选词⟩` 不硬编。
- **中文正文铁律修订**:旧「逐字全量、不概括」→ **书面正文 + 可折叠逐字底档**(每章 `<details>` 留档,内容 == 火山原稿,不丢);Polish 只改「怎么说」不改「说了什么」,书面化 ≠ 概括。
- **渲染**(`render.md` + `base.html`):中文书面正文 + `<details class="raw-transcript">` 折叠底档 + `<mark class="asr-uncertain">` 存疑标注样式。
- **VERIFY 双路径**(`verify.md`):英文双语走句数覆盖闸,**中文 CLEAN 走实体覆盖闸**(数字/专名/论点实体不丢);加零幻觉抽查 + 4 词回归样本 fixture。
- **火山 ASR 偏置反哺**(`ingest.md`):`volc_asr.py --meta` 把标题/简介 + `~/.config/volc/glossary.txt` 拼成 `corpus.context` 偏置,识别阶段就少错;`enable_ddc` 保持关(底档要真逐字)。

## v1.5.0 — 2026-07-12

**架构重构(behavior-preserving)**,治四层乱:

- **SKILL.md 269→69 行**:11 步 + 2.5/6.2/6.5 半步 + 满屏 🆕 → 7 阶段线性主线(INGEST → PREP → STRUCTURE → TRANSLATE → RENDER → VERIFY → PUBLISH),海报为可选分支。
- **references 按阶段拆**:675 行 `rules.md` + `design-system.md` → `ingest / prep-and-modes / translate / render / verify / publish / poster`(+ lessons-learned);`translation-prompt→translate`、`checklist→verify`、`poster-rules→poster` git mv 保历史。
- **scripts 按职责分组**:`fetch/ enrich/ publish/ poster/`,全局路径更新;清除 7 处 stale 绝对路径(旧 `bpr-skill/` base、`<ver>` cache 路径)+ 修幽灵脚本 `extract_publish_date→extract_metadata`。
- **翻译硬约束明文化**(`translate.md`):① 四步法 Analyze→Translate→Review→Polish 一步不省;② 英文逐字全覆盖 + **中文 Polish 去口语词**(呃/嗯/you know/I mean),推翻旧"口语感保留"——EN 留 / ZH 去,不对称。这是本次唯一有意的行为改动。
- **产物约定**(`publish.md`):`Transcript/` 结构固定(`<stem>.html` / `<stem>-poster.png` / `images/<stem>/` / `index.html`)。
- **修内部损坏**:补回 `extract_images.py`(1.4.3 引用却未 ship)+ `figure.from-source` CSS + lessons L7。
- **治版本漂移**:以功能超集 cache/1.4.1 为基线对账;此后 source of truth = 本 repo,发布流程固定(改 repo → bump → /plugin 更新 → repoint pin)。

## v1.4.2 — 2026-06-23

- transcript 模式默认**逐字全量 + 覆盖率硬闸**(渲染轮次/句数 ÷ 源稿 <~85% 判不合格,回 step5 补全;不再只看 en=zh 配对)— 见 L6
- 新增 `scripts/add_timestamps.py`:YouTube **滚动字幕重建** + 首句匹配,podcast 模式 step 6.5 默认注入 `.turn` 时间戳
- step 10 部署命令加 `NODE_USE_ENV_PROXY=1`(国内 Node fetch 走代理,防 vercel TLS 重置)
- lessons-learned 新增 L6;checklist 加覆盖率/时间戳两节

## [Unreleased]

## [1.4.1] - 2026-05-13

### Fixed
- **`scripts/fetch_xiaoyuzhou.sh` 元数据提取** — 加 JSON-LD PodcastEpisode 解析,
  从 `<script type="application/ld+json">` 块里读 `datePublished`(真实发布
  日期 YYYY-MM-DD)、`partOfSeries.name`(节目真名,例如"张小珺Jùn｜商业访谈录"
  而不是泛指"小宇宙")、`timeRequired`(ISO 8601 时长)。
  影响:文件名日期不再 null;hero kicker 不再写错节目名。
- **`fetch_xiaoyuzhou.sh` / `fetch_bilibili.sh` 的 Next-step 提示** — 改用
  相对路径调用 `lark-cli drive +upload`。实战发现 lark-cli 对 `--file` 参数有
  unsafe-path 校验,绝对路径(如 `/tmp/bpr-xyz-XXX/audio.m4a`)会被拒;
  必须 `cd $WORKDIR && lark-cli drive +upload --file ./audio.m4a`。
- **`references/rules.md` 妙记流程加 Step 0 scope 前置检查** — lark-cli 错误
  提示 "run lark-cli auth login --scope X" 是误导,所需 scope 必须先在 app
  开发者后台开通才能拉。新增"必须存在的 7 个 minutes/vc scope"清单 +
  `lark-cli auth scopes | grep -E 'minutes|vc:note'` 一行验证 + 兜底方案
  (妙记 Web UI 手动上传 → 导出逐字稿,绕开所有 minutes scope 审批)。

### Notes
- 这三条都是 2026-05-13 跑 BPR v1.4.0 首次端到端测试时
  (姚顺宇 4 小时访谈,小宇宙 episode 140)暴露的真实坑。
  v1.4.1 是把这些教训沉淀进代码 + 文档。

## [1.4.0] - 2026-05-13

### Added
- **`scripts/fetch_xiaoyuzhou.sh`** — 小宇宙(xiaoyuzhoufm.com)episode 抓取脚本。
  curl 拿 og:audio meta → 下载 mp3/m4a → 写 metadata.json(title / podcast /
  publish_date / audio_url)。**不内置转录**——由调用方走飞书妙记
  (lark-minutes skill: drive +upload → minutes +upload → vc +notes)。
- **`scripts/fetch_bilibili.sh`** — Bilibili 抓取脚本。yt-dlp 包装,先尝试
  uploaded subs(zh-CN / zh-Hans / zh / ai-zh / en)→ 没字幕则下载
  bestaudio[m4a] 给妙记转录。默认带 `--cookies-from-browser chrome` 应对
  会员/私人视频。
- **中文模式 (Chinese-Only Mode)** — CJK 字符 ≥ 60% 自动判定为中文素材,
  **跳过翻译三步法**,改走 TL;DR + 🔥 非共识 takes + 章节回顾 的浓缩结构。
  - 新 CSS:`.contrarian` / `.contrarian-quote` / `.contrarian-why` /
    `.ch-summary` / `.ch-pull` / `body[data-mode="zh-only"]` 等
  - 完整规范见 `references/rules.md` "中文模式 (Chinese-Only Mode)" section
  - 非共识 section 是中文模式的灵魂——做不好就是简陋摘要器,
    严格按 rules 里的写作原则执行

### Changed
- **SKILL.md 核心步骤表** — 新增 step 2.5 "语言检测",在预处理之后、章节切分
  之前判定语言;中文素材绕开 step 5 翻译。
- **`references/rules.md` URL 分支表** — 加 xiaoyuzhou.fm + bilibili.com 两行,
  新增"小宇宙 / Bilibili → 飞书妙记 一站式流程" section 详细列出 lark-cli
  drive +upload → minutes +upload → vc +notes 的完整 pipeline。
- **`templates/base.html` 底部说明区** — 加 CHINESE-ONLY MODE 模板示例
  (TL;DR + contrarian + ch-summary 怎么写)。

### Notes
- 中文模式判定**完全自动**,不接受用户修饰词覆盖——保持判定单一来源。
- 飞书妙记转录依赖 lark-cli + 个人空间额度。**首次使用**前需
  `lark-cli auth login`(详见 lark-shared skill)。

## [1.3.0] - 2026-05-11

### Removed
- Optional `/private/` link in index meta-bar(v1.2.0 加的功能)。
  原本的意图是 "让你给私有内容留个入口",但实际使用中发现:
  既然有内容,通常会单独绑子域名(`private.example.com`)再 rewrite,
  在公开主站 surface 一个 `/private/` 链接反而泄露了私域存在。
  把这逻辑彻底移除,private 内容由用户自己决定怎么链。

## [1.2.0] - 2026-05-11

### Added
- `scripts/build_index.py` major upgrade (synced from production-vendored version,
  37 KB ↑ from 12 KB):
  - `infer_tags()` — auto-detect format / topic tags from h1 + zh + eyebrow content
  - Tag filter UI (`tag-chip` buttons, JS filter, count badges)
  - Separate `posters.html` page — visual gallery for entries with `-poster.png`
  - Image lightbox modal for poster preview
  - OpenGraph meta tags (`og:title` / `og:image` / `og:url`) for social sharing
  - "Latest card" URL detection — surfaces newest poster as OG image
  - Top-nav link to posters page from index
- Optional `private/` link in index meta-bar — renders only when
  `~/Documents/Transcript/private/` exists locally. Lets you surface a
  password-protected section (e.g. staticrypt-encrypted page) without forcing
  other users to have one.

### Changed
- `collect_entries()` now skips both `index.html` and `posters.html`
- Build output now includes both `index.html` and `posters.html` in one run

## [1.1.0] - 2026-05-09

### Added
- `scripts/build_index.py` — 扫 Transcript 目录重建 landing `index.html`
- `scripts/extract_metadata.py` — 从博客 URL 抓发布日期 + source slug(7 种策略)
- SKILL.md step 0:发布日期提取要求(博客调 `extract_metadata.py`,YouTube 用 metadata.json)
- SKILL.md step 9:每次跑完重建 landing index
- SKILL.md step 10:每次跑完 vercel 部署到 bpr.ken.solar

### Changed
- 海报触发从修饰词 (`海报` / `分享版` / `poster`) 改为子命令前缀 `/bpr all <内容>`
- `templates/poster-template.html` 从 `references/` 移到 `templates/`(对齐 base.html 的位置)
- 文件名规则强化:日期 = 内容发布日期(必跑 extract_metadata.py),拿不到必须问用户,不再静默用今天

### Removed
- 修饰词 `海报` / `分享版` / `poster` 的支持(被 `/bpr all` 取代)

## [1.0.0] - 2026-05-07

### Added
- Initial release
- Plugin scaffold (`.claude-plugin/plugin.json` + `marketplace.json`)
- Skill `bpr` — 双语阅读器,覆盖 podcast / essay / 字幕 / 长文 四种输入
  - `SKILL.md` 主流程(0-7 步:URL 处理 → 类型识别 → 预处理 → 章节切分 → TL;DR → 三步法翻译 → HTML 渲染 → 自检)
  - `references/rules.md` — URL 输入处理 / 双语对照 / inline link 规范
  - `references/translation-prompt.md` — Translate → Reflect → Improve 三步法完整 prompt
  - `references/design-system.md` — 编辑设计风格视觉系统说明
  - `references/checklist.md` — 输出前自检清单
  - `references/lessons-learned.md` — 历史踩坑总结(L1 主持人识别 / L2 桌面布局 / L3 分块写入)
  - `references/poster-template.html` — 海报模式模板(无水印,1080 宽深色)
  - `references/poster-rules.md` — 海报模式工作流(9-section 框架 + Chrome 渲染 + crop)
- Scripts
  - `scripts/fetch_youtube.sh` — yt-dlp 字幕抓取
  - `scripts/clean_vtt.py` — VTT 去时间戳 / 去重清洗
  - `scripts/crop_and_share.py` — 海报自动裁剪 + 降采样(hidpi + share 双输出)
- `templates/base.html` — 双语 HTML 骨架(深色模式、目录、章节锚点)
- 修饰词支持:`只英文` / `深色` / `简洁` / `正式` / `速读` / `学习` / `带批注` / `海报`
- 文件名四种 pattern:single-host podcast / multi-host podcast / single-author essay / multi-author publication
- MIT license

[Unreleased]: https://github.com/kenzhangjie/bpr-plugin/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.3.0
[1.2.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.2.0
[1.1.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.1.0
[1.0.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.0.0
