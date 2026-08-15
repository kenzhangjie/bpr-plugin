# Changelog

All notable changes to this plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this plugin adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v1.7.4 — 2026-08-15

**逐窗覆盖闸此前基本抓不到丢句 —— 它一直在比错的东西;顺带修掉一个恒响的假警报和一个相对路径 bug。**

### Fixed

- **逐窗覆盖闸对真丢句不敏感**(最要紧的一条)。`finalize()` 拿**每个源窗**去比
  **整份输出**的词表(`out_c`),而 `_cov` 用的是多重集下界 `min(需要, 拥有)`。
  一份 15,000 词的稿子里,任一窗的词几乎都能在别处找到 —— 某窗整段丢掉,分数照样
  接近 1。真实数据实测:删掉 5 句正文,逐窗最低仍有 **0.990**,直接放行。
  - 现在按词序位置把源窗映射到**输出的同位片段**再比,单侧留
    `WINDOW_MARGIN_WORDS = 150` 词余量吸收纠错/拆 turn 造成的漂移。
    同一变异现在报 `#1(0.949)`,并指向删句的那一窗;整个 turn(43 句)丢失报 `#13(0.700)`。
  - **为什么以前没发现**:既有测试 `localizes_the_dropped_window` 用的是互不重叠的
    词表(`alpha bravo` vs `foxtrot golf`),比整篇也能发现丢失 —— 真实稿子不长那样。
    新增的回归用**近邻没有、远处有**的真实形态词表,并断言窗远大于余量
    (小窗会让局部片段被余量撑成整篇,测试退化成永远为真)。
- **`[music]` 让覆盖闸恒响假警报**。PREP 明令子代理删掉 `[music]` / `[applause]` /
  `[ __ ]` 这些字幕噪声标记,而 `norm_words` 把 `[music]` 算成一个词 "music",
  于是**照做反而掉分**:151 词的片头删 4 个 `[music]` = 0.974,卡在 0.98 闸下,
  正文一个字没丢。现在 `norm_words` 先丢掉整个 `[bracketed]` 段(两侧一视同仁),
  与 `add_timestamps.py` 早有的同名函数对齐。
  - 这条和上一条是连着的:这个假警报长期在响,掩盖了逐窗闸其实不工作 ——
    "抓到过丢句"其实抓到的是 `[music]`。恒响的闸等于没有闸,还会给出虚假信心。
- **`fetch_youtube.sh` 用相对路径调用必挂**。第 35 行 `cd "$OUT_DIR"` 在算
  `SCRIPT_DIR` **之前**,而 `BASH_SOURCE` 是调用方写的路径 —— 相对调用在 cd 之后
  就解析不到,报 `cd: scripts/fetch: No such file or directory`,读起来像装坏了或
  版本不对,其实与版本无关。`SCRIPT_DIR` 已挪到 cd 之前。

### Tests

- 3 条新回归,均已用**变异证据**验过(在修复前的实现上全部失败):
  `test_norm_words_drops_bracketed_caption_markers`、
  `test_finalize_noise_markers_do_not_lower_coverage`、
  `test_finalize_per_window_catches_drop_despite_shared_vocabulary`。
- 全量 155 passed。

## v1.7.3 — 2026-08-07

**修一个正在静默改错内容的专名替换 + 三处闸门从"喊口号"变成"能执行" + 删掉零使用的海报分支。**

### Fixed

- **`小红书` 被改成 `肖弘书`**(最要紧的一条)。`glossary.txt` 第 3 列的
  `肖弘|20|小红,小宏,小虹` 配上**无词边界的子串替换**,会把「小红书 / 小红帽 / 小红点」
  全改坏。危险在于它发生在 **ASR 输出那一刻**(CLEAN 之前):CLEAN 的 prompt 写着
  "专名与 shownote/glossary 不一致时信 glossary",子代理不会去纠;Step C.5 保真闸
  只查"丢没丢"不查"改没改错";VERIFY 同理 —— **三道网全穿**。
  - 新增 **`skills/bpr/scripts/lib/glossary_lib.py`** 作为 glossary 的**单一实现**。
    此前同一份替换逻辑在两处各写了一遍(`volc_asr.py` 的 `str.replace` 和
    `clean_en.py` 的 `apply_correct_table`),**两份都漏了词边界** —— 修一处漏一处。
    `~/.config/volc/volc_asr.py` 现在 import 这一份;找不到插件时**跳过该层并 WARN**,
    不回退到旧实现。
  - 三层防护:① **保护名单优先**(glossary 第 1 列全部正确名 + `~/.config/volc/protect.txt`,
    单次扫描的正则里保护分支排在错法分支前面)· ② **拉丁键强制词边界**
    (`Codeex→Codex` 不咬 `Codeexes`)· ③ **长度闸**(CJK 键 <3 字、拉丁 <4 字直接拒收 + WARN)。
  - 新增 `clean_en.py --check-glossary` 体检:列出被拒收的短键、冲突(同一错法映射到
    多个正确名)、与保护名单的碰撞;有冲突/碰撞退出码 1。
  - 数据侧:`glossary.txt` 里 5 个 2 字错法(`小红/小宏/小虹/潘乐/涛哥`)移入停用注释块,
    正确名留在第 1 列;新增 `protect.txt`(小红帽/小红点/小红花)。
- **`base.html` 还在拉 Noto Serif SC**。CJK 走 Google Fonts 单页要拉 38 个子集分片
  共 2.5MB,国内无代理直接白屏。2026-07-29 已把 113 篇产出事后 sed 成系统宋体栈,
  但**模板没改**,于是 2026-08-06 新渲染的那篇又退回去了 —— 修好的东西被模板反复弄坏。
  现在 `base.html` / `build_index.py` / `render.md` 三处一起改掉,与线上 Vercel 端
  `bin/build_index.py` 对齐。
- **`verify.md` 的体积自检区间失效**。写的是「正常 70-110KB」,而全库 120 篇**中位
  138KB**、最大 1,083KB —— 对大多数产出恒为「异常」。改成按版型分档(essay 25-120KB /
  英文双语 90-300KB / 中文模式 250-1,100KB),并说明**偏低才危险**。
- **CHANGELOG 补齐 v1.7.0 / v1.7.1 / v1.7.2**(此前三个版本零记录,见下)。

### Changed

- **覆盖率闸能定位到窗了**(P3)。`clean_en.py finalize` 原来只吐一个全局 `coverage`,
  而 `prep-and-modes.md` 要求"把该窗打回 Step 2 重派" —— 拿不到窗号,这条硬规则
  **根本执行不了**。新增 `--windows`,输出逐窗覆盖率 + 最差窗号,直接打
  `WARN: 这些窗覆盖 < 0.98,回 Step 2 重派:#7(0.612), #12(0.883)`。
- **新增 `added_ratio` 抓加译/幻觉**。`word_coverage` 只问"源词有没有被盖住",子代理
  凭空加一整段**完全不掉分**。加译率是它的反向指标(报告项,不拦 —— 专名纠错本身会
  贡献少量新词)。
- **中文实体覆盖闸脚本化**:新增 `skills/bpr/scripts/verify/entity_coverage.py`,
  直接对账成品的「折叠底档」与「书面正文」。此前 verify.md 只写了一行"人工抽查" ——
  抽查 ≠ 检索,漏掉的恰恰是没抽到的那条。
  - 按**数值**而不是字面比对:`1700万` ↔ `一千七百万`、`190` ↔ `一百九`、`10万` ↔ `十万`
    都算兑上(第一版按字面比,在两篇已发布成品上报了 3 个「丢失」,人工复核**全是假警报**)。
  - 非对称设计:**来源只取阿拉伯数字**(中文里 一/二/三 同时是普通词,当来源会造出
    16-26 个假警报),**兑账两边都认**。年份与拉丁专名降级为软报告(ASR 常把年份读碎,
    CLEAN 规范化是对的;拉丁专名"消失"多半是 CLEAN 纠对了拼写)。
  - 剔掉时间戳与 `<summary>` 版面数字(`1:26:23` 会被读成 1/26/23;
    「展开逐字原稿（125 段）」的段数是渲染产物)。
  - 实测:两篇长中文成品的待核项从 26 / 16 条降到 **1 / 1 条**,剩下的都是 ASR 把数字
    读碎(`拿了大概7000` 下一句才是 `8千万美金`)。**非空 ≠ 一定有 bug**,措辞已如实。
- **专名飞轮补上第 3 列**(P4)。`append_glossary` 只写 `名|权重`,而硬映射**只吃第 3 列**
  → 飞轮只让参考表变长,纠错层原地不动(实测 284 条专名只对应 38 条硬映射)。
  `--names` 现接受 `[{"term": "Codex", "seen_as": ["Codeex"]}]`,把本期真见过的错法
  merge 进第 3 列(过长度闸 + 保护名单 + 冲突检查,拒收项走 stderr)。老形态仍兼容。
- 测试从 104 例增至 **152 例**(新增 `test_glossary_lib.py` 19 例、`test_entity_coverage.py` 24 例、
  `test_clean_en.py` 补 5 例)。

### Removed

- **海报分支**(`references/poster.md` 207 行 + `templates/poster-template.html` 879 行 +
  `scripts/poster/crop_and_share.py`)。上线两个多月、**120 篇产出里 0 张海报**,
  却占着 1,141 行并让每次读 SKILL.md 都要绕过它。`/bpr all` 保留为别名(不报错,
  行为 == `/bpr`);要恢复去 git 历史里捞。
  > `build_index.py` 里还有约 150 行海报画廊代码(`posters.html` / lightbox / 缩略图)。
  > 它在本次改动**之前就已经是死代码**(0 张海报 → 分支永不进入),按"不删非我造成的
  > 死代码"的规矩留着,单独记一笔待处理。
- README 目录树同步到实际结构(自 1.5.0 重构后一直还写着 `rules.md` / `checklist.md`
  这些已改名的文件)。

## v1.7.2 — 2026-08-07

**单文件字数上限 50K → 100K。**

- 8.5 万字 / 3.5 小时的中文访谈实测单文件可承载(渲染 17 章 + 740 turn 书面正文 +
  740 turn 折叠底档正常),原来的 50K 闸会无谓地把它劝去分文件。
- ⚠️ **这个版本曾只存在于本地 plugin cache**,git 上没有 —— 下一次 `/plugin update`
  会静默把它冲回 1.7.1。1.7.3 把它补进仓库。发版必须走 `tools/release.sh`,
  别直接改 cache 目录。

## v1.7.1 — 2026-08-05

**修 `base.html` 注释污染:每一个渲染产物的内容都翻倍了。**(PR #6)

- 骨架模板里的占位符注释与嵌套注释,会让渲染器把示例内容当正文一起输出。
  实测同一篇:文件 119KB → **225KB**、`.chapter` 11 → **25**、`.bilingual` 256 → **514**,
  essay 模式正文还会整块不可见。
- 坑在于**浏览器里看不出来**:内容被填进注释,DOM 自检全绿,只有 `wc -c` 体积闸能发现。
  这也是 1.7.3 把 verify.md 体积区间修准的动机之一。

## v1.7.0 — 2026-08-04

**本地 PDF 输入(阶段 1)。**(PR #5)

- `/bpr <path.pdf>` 能把**文字层 PDF**(研报 / 白皮书 / 书籍章节)解析成干净正文 + 元数据。
  新增 `scripts/fetch/extract_pdf.py`(剥跨页页眉页脚、接行尾断词、双栏按栏序拉直)
  与 `scripts/fetch/pdf_layout.py`;产物 `body.txt` / `pages.jsonl` / `metadata.json` / `tables.json`。
- **下游零改动**:靠 `metadata.json` 与既有 `extract_metadata.py` 的 7 键同形,
  `STRUCTURE / TRANSLATE / RENDER / VERIFY / PUBLISH` 一行没动。
- 退出码约定:`0` 成功 · `2` 输入非法(非 PDF / 已加密)· `3` 需要 OCR(含"只有个别页
  无文字层"——研报最常见形态,跳过那几页就是静默丢内容)。
- 发布日期**必须来自封面正文,不是 PDF CreationDate**(旧研报重新导出会变成今天)。
- 设计文档:`docs/superpowers/specs/2026-08-03-bpr-pdf-input-design.md`。

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
