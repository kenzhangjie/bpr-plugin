# BPR 本地 PDF 输入 · 设计

- 日期:2026-08-03
- 基线版本:1.6.3(`c8c91f3`;clone / cache / origin 三处已对齐)
- 状态:已与 Ken 逐节确认,待实施

## 背景

bpr 现有四种输入模式(SRT / 带时间戳 transcript / 纯文本 transcript / blog-essay),都围绕 URL 与 yt-dlp metadata 设计。本地文档只在两处被顺带提及:

- `references/ingest.md:37` — PDF 链接 → "让用户先下载到本地,再 `/bpr <文件路径>`"
- `references/ingest.md:192` — 妙记导出 TXT → "把 TXT 文件路径给 BPR"

即 `/bpr <路径>` 被默认存在,但**输入模式判定表里没有这一行,也没有任何格式解析脚本**。`.txt` / `.md` 靠 Read 直读能跑通;PDF 无路径;元数据(标题 / 作者 / 发布日期)在本地文档上必然掉到 `ingest.md` 的 P5「问用户」,而文件名第一段必须是真实发布日期是硬规则(`ingest.md:321`,"绝不静默用今天")。

## 目标与范围

**目标**:`/bpr <path.pdf>` 能跑完整流水线,产出与现有 essay 版型一致的阅读 HTML,含正文图表。

**Ken 确认的输入品类**:研报 / 白皮书 / 行业报告、书籍章节 / 电子书导出、**扫描件 / 图片型 PDF**。论文 / arXiv 不在范围(不做双栏脚注与 reference 截断的特化)。

**范围内**:文字层提取、扫描件 OCR、图表抽取与自托管、元数据尽力提取 + 一次性确认。

**范围外**:论文特化处理、`.docx` / `.epub`(`textutil` 可后补,不在本 spec)、表格转 markdown(留 `--tables=md` 开关,默认不走)。

## 核心判断

1. **这件事 90% 是 INGEST 一层的活。** STRUCTURE / CLEAN / TRANSLATE / RENDER / VERIFY / PUBLISH 全部零改动,靠"新脚本输出形状对齐现有脚本"实现。
2. **OCR 错字与 ASR 错字同性质**(专名错、同音字、断句乱),而 CLEAN 阶段(Analyze 定术语表 → 分窗 Review 纠错 → Polish 书面化)本就是为火山 ASR 错字写的。中文扫描件 OCR 完直接进 CLEAN,英文进 PREP 英文子模式——都是现成的。
3. **研报的图表大多是矢量而非位图。** Wind / Excel 导出的图在 PDF 里是填充矩形与 path,`page.get_images()` 会**静默返回空**。必须靠矢量绘图区域聚类 + 区域截图。这是本设计最大的技术风险点。

## 依赖

| 依赖 | 状态 | 用途 |
|---|---|---|
| `fitz`(PyMuPDF 1.26.5) | **已装**,`~/Library/Python/3.9/...`(`pip --user` 装在 Apple python 3.9) | 文字层探测、布局取文、渲页、嵌图、矢量绘图、`find_tables()`、元数据 |
| `ocrmac`(Apple Vision) | **需装**:`pip3 install --user ocrmac` | 扫描件 OCR。离线免费,中英质量均好 |

`/usr/bin/python3` 未被 PEP 668 锁定,`pip3 install --user` 可用(现有 fitz 即此方式)。

**实施第一步**:装完 `ocrmac` 后**先验其真实 API 形状**(返回结构、语言偏好参数名)再写调用,不拿印象当事实。

## 架构:三个脚本,按现有目录语义分工

`scripts/fetch/` = 拿原料,`scripts/enrich/` = 加料。

| 新增文件 | 职责 | 依赖 |
|---|---|---|
| `scripts/fetch/extract_pdf.py` | 文字层探测 → 布局感知取文 → 尽力出 metadata。主路径,必须成功 | fitz |
| `scripts/fetch/ocr_pdf.py` | 仅无文字层时被调用:渲页 → Apple Vision → 带页码文本 | fitz + ocrmac |
| `scripts/enrich/extract_pdf_images.py` | 图表抽取 + 过滤 + 落 `images/<stem>/`,输出与 `extract_images.py` 同形 | fitz |

OCR 是唯一带外部依赖、会失败、会慢的部分,单独隔离,主路径不受其拖累。

## 数据流

```
/bpr <path.pdf>
  │
  ├─ INGEST ── extract_pdf.py <pdf> --workdir W
  │              ├─ 文字层探测 → text_ratio(定义见下)
  │              │     ≥ 0.8   → 文字层模式(直接取文)
  │              │     ≤ 0.2   → 扫描件模式(整本走 ocr_pdf.py)
  │              │     0.2~0.8 → 混合模式(逐页判,OCR 只补空页)
  │              ├─ 取文:get_text("blocks") → 分栏排序 → 剥页眉页脚 → 接行尾断词
  │              └─ 产出 W/body.txt + W/pages.jsonl + W/metadata.json
  │
  ├─ 元数据一次性确认(候选值 + 命中来源 + 置信度 → Ken 改一行或直接过)
  │
  ├─ PREP    CJK ≥60% → 中文浓缩 / <60% → 英文双语              [现成,不改]
  ├─ CLEAN   扫描件必跑 / 文字层 PDF 默认跳过                     [现成,不改]
  ├─ STRUCTURE → TRANSLATE                                       [现成,不改]
  ├─ RENDER  enrich: extract_pdf_images.py
  │            └─ anchors/hero/skipped/coverage → render.md:147-152 零改动
  └─ VERIFY → PUBLISH                                            [现成,不改]
```

### 三档探测(而非二元)

**`text_ratio` 定义为页级比例,不是字符比例**:`有效文字页数 / 总页数`,其中"有效文字页"= 该页 `get_text()` 去空白后 ≥ 50 字符。用页级而非字符级,是因为要回答的问题是"哪些页需要 OCR",而字符比例会被一页长正文稀释掉十页空白图。

研报最常见形态是"正文有文字层,但图表页 / 附录页是整页扫描图"。二元判定会让这类文档**丢掉整页内容且不报警**。混合模式逐页判、只对空页 OCR,代价是 `body.txt` 需按页序拼接。

### 产物

| 文件 | 内容 | 消费者 |
|---|---|---|
| `W/body.txt` | 干净正文,段落间空行,**无页码污染** | PREP / STRUCTURE |
| `W/pages.jsonl` | 每页一条 `{page, text, source:"text"\|"ocr"}` | 底档,错字定位到页(借用 CLEAN 保留逐字底档的思路) |
| `W/metadata.json` | 7 键,与 `extract_metadata.py` 同形 | INGEST 元数据确认 / hero / 文件名 |
| `W/tables.json` | 表格 bbox 单一真源(见「表格默认当图处理」) | `extract_pdf_images.py` |

## `extract_pdf.py` · 正文提取四机制

### ① 分栏检测 — 按 block 中心 x 聚类,不猜版式

`get_text("blocks")` 的默认顺序对双栏不可靠。取所有 block 中心 x,判断是否存在一条分界线使绝大多数 block 完整落在一侧且不跨界、两侧 block 数都够多 → 判双栏,按 `(栏号, y0)` 排序;否则按 `y0` 单栏排。**跨栏宽 block**(通栏标题 / 通栏表)单独按 y 位置插回。

三栏不做(YAGNI)。

### ② 页眉页脚剥离 — 靠跨页重复,不靠 regex

取每页顶部 / 底部各 8% 区域的 block,文本归一化(数字全替为 `#`),**在 ≥60% 页面上重复出现者判为页眉页脚,删**。

零站点特化规则即可自动清除研报三类标配噪声:机构名(「XX证券研究所」)、免责提示行(「请务必阅读正文之后的免责声明部分」)、页码(「第 # 页 共 # 页」)。

**守卫:总页数 < 4 时整个跳过本机制**。样本不足时「≥60% 页面重复」会把正文误判成页眉——两页文档里出现两次的短语完全可能是正文。跳过时在 stdout 说明。

### ③ 行尾断词与段落边界

- 英文:行尾 `-` 且下行小写开头 → 去连字符拼接;否则保留
- 中文:直接拼接,不补空格
- 段落边界:block 垂直间距 > 中位行距 × 1.3

### ④ 尾部免责声明截断

研报尾部常有 3–5 页免责声明 / 评级说明 / 分析师承诺,它们是正文块,机制 ② 抓不到。检测尾部标志性小节标题(免责声明 / 评级说明 / 分析师承诺 / Disclosures / Disclaimer)后截断。

**必须在 stdout 明确报「截掉了 N 页,起点是第 X 页的『免责声明』」**,默认截,`--no-truncate` 关。不静默截断——静默会有一天吃掉真正文。

### 表格默认当图处理

`--tables` 默认 `img`。理由:复用图表管线零新代码;研报表格排版复杂,转 markdown 的**错位是静默的**(数字串到隔壁列不会被发现),比缺表危险;阅读器是给人看的,不需机器可算。`--tables=md` 显式启用 `find_tables()` 出 markdown。

**两个脚本必须对表格区域达成一致,靠单一真源而非各跑一次**:

- `extract_pdf.py` 跑 `find_tables()`,把命中的表格 bbox 写进 `W/tables.json`
- `img` 模式下,`extract_pdf.py` 从 `body.txt` **剔除**表格区域的文本,原位留 `[[table:p{页}-{序}]]` 锚记。不剔除的话,表格既成图、其乱序文字层又留在正文里,会同时污染 TL;DR 和翻译
- `extract_pdf_images.py` **读 `W/tables.json`**,不自己再跑一次 `find_tables()`——两次调用的 bbox 未必一致,锚点会错位
- `md` 模式下不剔除、不留锚记,表格以 markdown 留在 `body.txt`,图表脚本跳过表格区域

## 元数据提取与确认

### 策略链(前面命中即停)

| 字段 | 策略链 |
|---|---|
| `title` | PDF `/Info` Title → **垃圾过滤**(含 `.doc` / `Microsoft Word` / `untitled` 一律弃)→ 封面首页最大字号 block |
| `author` / `publication` | `/Info` Author → 封面文本中的机构名(尾含 证券 / 研究所 / 研究院 / Research / Capital / Institute) |
| `date` | **封面正文日期**(`2026年7月` / `2026-07-15` / `July 2026`)→ `/Info` CreationDate → 仅有年份则补 `YYYY-01-01` |
| `source_slug` | 机构名转 kebab(`zhongjin` / `morgan-stanley`) |

**`CreationDate` 优先级刻意排在封面正文之后**:它记的是 PDF 文件何时生成,一份 2023 年研报被重新导出一次,CreationDate 就变成今年。封面上印的日期才是发布日期。这正是 `ingest.md:321` 要防的事。

**仅有出版年时补 `YYYY-01-01`**(Ken 已定),保持文件名格式恒为 `YYYY-MM-DD`,不动 `build_index.py`。

### 7 键的两处重新解释

- `source` — 填 `pdf:info-title` / `pdf:cover-maxfont` / `pdf:cover-text` / `pdf:cover-org` / `pdf:info-creationdate` / `pdf:none`,复用现有"告诉你哪条策略命中"的调试语义
- `canonical` — 本地 PDF 填**绝对文件路径**;若 Ken 手上有原始下载 URL,可在确认步补入,hero 即可带真来源

### 确认交互

跑完打一张表,Ken 确认或改一行:

```
字段          候选值                          来源                置信度
title         中国AI算力产业深度报告            pdf:cover-maxfont    high
publication   中金公司研究部                   pdf:cover-org        high
date          2026-07-15                      pdf:cover-text       high
source_slug   zhongjin                        derived              medium
canonical     /Users/ken/Downloads/xxx.pdf    local-path           —
```

置信度只三档(high / medium / low),由**命中的是哪条策略**决定,不做玄学评分。全 high 时提示"没异常,直接进流程?",不逼逐字段过。

## `ocr_pdf.py`

```
ocr_pdf.py <pdf> --pages 7,12-15 --dpi 300 --lang zh-Hans,en --out W/ocr.jsonl
```

`get_pixmap(dpi=300)` 渲页 → Apple Vision(accurate 级 + 语言偏好 + 语言纠正开)。每页一条 `{page, text, mean_confidence, line_count}`。默认 `--dpi 300`、`--lang zh-Hans,en`;`--pages` 省略时全本。

三个守卫:

- **低置信页要报出来**:`mean_confidence < 0.5` 或行数异常少 → 标 `low_confidence`,最后汇总列出,由 Ken 决定是否人工核那几页
- **依赖缺失不静默降级**:未装则明确报 `pip3 install --user ocrmac` 并非零退出(与 `ingest.md:93` 对 yt-dlp 的处理一致)
- **顺序执行不并发**:60 页 × ~0.5s ≈ 30s,够用,不为此引线程池

## `extract_pdf_images.py`

```
extract_pdf_images.py --pdf <path> --blocks blocks.json --stem <stem> \
                      --transcript-dir <dir> [--refresh] [--min-dim 100] [--tables img|md]
```

CLI 对齐 `extract_images.py`,只把 `--html` 换成 `--pdf`(`--content-class` 对 PDF 无意义,去掉)。

### 候选来源三类,统一成"页面上一块矩形 → 一张 PNG"

| 来源 | 手段 |
|---|---|
| 嵌入位图 | `page.get_image_info(xrefs=True)` 拿实际绘制 bbox + xref(比 `get_images()` 可靠,后者有重复引用与掩码噪声) |
| **矢量图表** | `page.get_drawings()` 的 bbox 聚类出绘图密集矩形 → `get_pixmap(clip=bbox, dpi=200)` 截图 |
| 表格 | `find_tables()` 给 bbox → 同样 clip 截图 |

三类统一后,过滤 / 锚点 / 命名共用一条路。

### 过滤 — 把现有语义翻译到 PDF

`MIN_DIM = 100` 沿用。现有 `NOISE_RE`(匹配文件名里 logo/avatar/icon)在 PDF 无文件名可匹配,换三条等效判据:

- 面积占页 < 2% → 弃
- **跨页重复出现** → 弃(与机制 ② 同款思路,用 bbox 位置 + 尺寸指纹,专治页头 logo 与水印)
- 极细长比例 → 弃(分割线、表格边框)

### 锚点与图题 — 比 HTML 那条路更准

- **锚点**:现有靠归一化正文文本反查 `article_index`(`extract_images.py:166`)。PDF 有 bbox 与阅读顺序,直接锚到阅读顺序上紧邻其前的文本 block,无需文本匹配
- **图题**:取图 bbox 上下 40pt 内、以 `图` / `表` / `Figure` / `Table` / `Exhibit` 开头的 block 作 `alt`。研报图表必有「图1:…」与「资料来源:Wind」,这是 HTML 路径拿不到的质量

### 输出形状

`{anchors, hero, skipped, coverage}` 与现有一致;`variant` **直接复用** `extract_images.py:143` 按宽高比分 banner/portrait/square/wide 的函数,保证 CSS class 完全一致 → `render.md:147-152` 插图规则零改动。

**唯一形状偏差**:`skipped` 现有为 `{url, reason}`,PDF 无 url,改为 `{page, bbox, reason}`。该字段仅供人工诊断,不进 HTML,不影响渲染。

**`hero[]` 对 PDF 恒为空**:研报封面页的图几乎全是机构 logo 与装饰底纹,当 hero 只会让阅读页顶上一张废图。所有图一律走 `anchors[]` 按锚点落进正文。若某份 PDF 确实该有 hero 图,人工在 RENDER 阶段指定,不由脚本猜。

## 错误处理

| 情况 | 行为 |
|---|---|
| 非 PDF(magic 非 `%PDF`) | 报错退出 2 |
| 加密(`doc.needs_pass`) | 明确报"已加密,给密码或先解密",退出 |
| **禁复制的研报**(`get_text()` 全空但 `get_fonts()` 非空) | 与扫描件**分开判**:提示"文字层被权限锁,退到 OCR"后走 OCR |
| `text_ratio` 中间档但 `ocrmac` 未装 | 报"有 N 页需 OCR,跳过会丢这几页",让 Ken 选装依赖或显式接受缺失。**不静默丢** |
| OCR 整本低置信 | 提示可能 dpi 不足,建议 `--dpi 400` 重试 |
| 图表候选 N 但抽出 0 | 明确报出。专防矢量图静默零结果 |
| > 200 页 | 询问是否分 part(现有 >50K 字问分文件规则的延伸) |
| < 500 字 | 沿用 `SKILL.md:66` 现有规则 |

"禁复制"与"扫描件"刻意分开判:研报常设禁止复制,若混报为扫描件,会被误当成文件质量问题而非权限问题。

## 测试

对齐 `tests/test_clean_en.py` 风格:pytest + `sys.path.insert` 直接 import 脚本模块 + 纯函数单测 + `tmp_path`。

**fixture PDF 全部用 fitz 在 `tmp_path` 里合成,不往仓库塞真研报**(版权 + 体积)。

| 测试文件 | 覆盖 |
|---|---|
| `tests/test_extract_pdf.py` | 分栏判定(合成单栏 / 双栏)、跨页重复页眉页脚剥离(合成 3 页同页脚)、行尾断词拼接、**date 策略链优先级(封面文本必须赢过 CreationDate)**、title 垃圾过滤、免责声明截断有报告 |
| `tests/test_ocr_pdf.py` | 不测识别质量(属 Vision)。测页范围解析 `7,12-15`、依赖缺失报错路径(monkeypatch import 失败)、低置信标记 |
| `tests/test_extract_pdf_images.py` | 合成含矢量绘图 + 小 logo 的 PDF:矢量区域被抽出、小 logo 被 skip 且 reason 正确、**输出 JSON 键集与 `extract_images.py` 完全一致** |

最后一条是"下游零改动"承诺的唯一守卫:键集一旦漂移,RENDER 会静默出错图。

**端到端**:拿 Ken 一份真研报实跑,并按 CLAUDE.md §8 明确标注哪些实测过、哪些未测。

## 要改的现有文件

| 文件 | 改动 |
|---|---|
| `references/ingest.md` | 输入模式判定表加「本地 PDF」一行;新增一节 PDF 流程;`ingest.md:37` 的"PDF 链接 → 让用户下载"接上新流程 |
| `SKILL.md` | 流水线表第 1 行 reference 列补新脚本;错误处理节补 PDF 三条 |
| `references/render.md` | enrich 节注明 PDF 源走 `extract_pdf_images.py`,输出同形 |
| `references/lessons-learned.md` | 记一条硬规则:**研报图表是矢量的,`get_images()` 静默返回空,必须靠区域截图** |

## 发版

三处版本号必须一起 bump(上一个 commit `c8c91f3` 正是为漏其中一处而补):

- `.claude-plugin/marketplace.json:9`(`metadata.version`)
- `.claude-plugin/marketplace.json:16`(`plugins[0].version`)
- `.claude-plugin/plugin.json:4`

## 实施阶段

三个脚本不必一次做完。按可独立验证、可独立发版切分:

| 阶段 | 内容 | 可独立验证的产出 |
|---|---|---|
| **1** | `extract_pdf.py` + 元数据确认 + 四处文档改动 + 发版 | 文字层研报能跑完整流水线出 HTML(无图) |
| **2** | `extract_pdf_images.py` | 同一份研报重跑,图表落地且锚点正确 |
| **3** | `ocr_pdf.py` + 混合模式接线 | 扫描件能跑通,低置信页有报告 |

阶段 1 单独就有用(书籍章节、白皮书基本都是文字层单栏),先落地它能最快拿到真实反馈,再决定 2、3 的细节要不要调。

## 成功标准

1. `/bpr <文字层研报.pdf>` 跑通到 PUBLISH,正文无页眉页脚残留,图表落地且锚点位置正确
2. `/bpr <扫描件.pdf>` 跑通,OCR 后经 CLEAN 产出书面正文,低置信页有汇总报告
3. 文件名日期来自封面而非 CreationDate / 今天
4. 三个新脚本的单测全绿,且图表脚本的输出键集与 `extract_images.py` 逐键一致
5. `render.md` / `templates/base.html` / STRUCTURE / TRANSLATE / VERIFY / PUBLISH **零改动**
