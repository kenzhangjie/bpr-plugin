# BPR · 踩坑日志 (Lessons Learned)

> 这份文件记录每次 BPR 出错的**症状 + 根因 + 硬规则**。
> SKILL.md 只引用这里的"硬规则"清单,不复述病史。
> 加新规则时:**先记症状,再写规则**,不要只写规则——未来的你需要看到症状才记得为什么。

---

## L1 · 主持人 / 嘉宾误识别 (2026-05-07)

### 症状
生成 Anton Osika × Harry Stebbings (20VC) 的 HTML 时,hero kicker 写成了
`20VC · Lenny / Harry Stebbings · 2026 · 双语整理`——把 `Lenny` 莫名混进了
一个跟 Lenny 完全无关的 20VC 节目。

### 根因
SKILL.md 长期只举 Lenny's Podcast 一个例子,LLM 把 Lenny 当成了默认锚点。

### 硬规则

1. **主持人和嘉宾必须从原文提取,不准默认。**
   生成 hero/footer 之前,先在 transcript 开头/结尾找:
   - 说话人标记 (`Lenny:` / `Harry:` / `Speaker 1:`)
   - "Today my guest is X" / "I'm host Y" 类介绍句
   - 元数据(YouTube 标题、podcast feed 描述)
   原文是 Harry Stebbings,**绝不能**写 Lenny;反之亦然。

2. **Podcast slug 必须匹配实际节目**,不允许泛指 `podcast` / `interview`:
   | Podcast | slug |
   |---|---|
   | Lenny's Podcast | `lennys-podcast` |
   | 20VC | `20vc` |
   | Dwarkesh Podcast | `dwarkesh-podcast` |
   | Sequoia Training Data | `training-data` |
   | Y Combinator | `y-combinator` |
   | Naval Podcast | `naval-podcast` |
   | AI Summit | `ai-summit` |

3. **文件名必须包含嘉宾 slug**(podcast 模式):
   `{YYYY-MM-DD}_{podcast-slug}_{guest-slug}-{topic-slug}.html`
   例:`2026-05-06_20vc_anton-osika-lovable.html`
   只写 topic 不写嘉宾(`lovable-200m-arr-playbook.html`)→ 同节目多嘉宾文件
   会互相认不出来。

4. **找不到主持人时**:
   hero kicker 写 `{publication} · Episode · {date}`,**不要瞎填一个名字**。
   嘉宾必须找到——找不到说明 transcript 不完整,告诉用户而不是编。

5. **Hero kicker 的 4 个示例模板**(防单一锚点):
   - Lenny → `Lenny's Podcast with Lenny Rachitsky · YYYY-MM-DD · 双语整理`
   - 20VC → `20VC with Harry Stebbings · YYYY-MM-DD · 双语整理`
   - Dwarkesh → `Dwarkesh Podcast with Dwarkesh Patel · YYYY-MM-DD · 双语整理`
   - Training Data → `Training Data with Sonya Huang · YYYY-MM-DD · 双语整理`
   - Y Combinator → `Y Combinator · Garry Tan × {Guest} · YYYY-MM-DD · 双语整理`

   生成时**根据原文 podcast 选对应模板**,不是套第一个例子。

---

## L2 · 桌面布局错位 (踩坑 5 次后定版)

### 症状
- 1440 / 1920 / 2560 三档屏宽下,TOC 与正文之间出现"半页空白死区"
- Hero 上方出现"巨字号下划线链接"或"长方形空盒"(mobile-only 元素泄漏)

### 根因
1. 用 grid 做 TOC + main 双列,各档屏宽间距不稳定
2. mobile-only 元素的 base 规则没写 `display:none`,只在 media query 里写

### 硬规则

1. **布局方案**:`fixed TOC + container margin-left:260px`
   **不要**用 grid。**也不要**用 `margin:0 auto + padding-left` 伪布局。

2. **DOM 结构**(必须):
   - `<button class="theme-toggle">` 是 `<body>` 直接子元素
   - `<button class="toc-mobile">` 是 `<body>` 直接子元素
   - `<div class="toc-overlay">` 是 `<body>` 直接子元素(包裹 mobile nav)
   - `<nav class="toc">` 是 `<body>` 直接子元素(桌面 fixed)
   - `<div class="container">` 内部依次:`.hero` / `.tldr` / 多个 `.chapter` / `<footer>`
   - **以上元素绝不能放进 `.container` 内部**

3. **mobile-only 元素 base 必须写 `display:none`**,只在
   `@media(max-width:1099px)` 里切回 `display:block` / `display:flex`:
   ```css
   .toc-mobile{ display:none }              /* base */
   .toc-overlay{ display:none }             /* base */
   @media(max-width:1099px){
     .toc-mobile{ display:flex }
     .toc-overlay.open{ display:block }
   }
   ```

4. **正确实现完整代码** → 直接 copy `templates/base.html`,不要重写。

5. **生成完后必须自查**:1440 / 1920 / 2560 三档屏宽,有没有半页空白 /
   巨字号链接 / 空盒 → 有 = 某个 mobile-only 元素 base `display:none` 漏写了。

---

## L3 · 大文件单次写入 socket 超时

### 症状
单次 `Write` 写一个 80KB+ 的 HTML,流式响应跑十几分钟,Anthropic API socket 中途断开:
```
API Error: The socket connection was closed unexpectedly.
For more information, pass 'verbose: true' in the second argument to fetch()
```

### 根因
报错来自 Claude Code 内部 fetch,**不是 skill 的错误**——但 skill 必须改写策略规避。
单次 Write 越大,流式响应越久,断开概率越高。

### 硬规则

**任何 HTML 预计 > 30KB 或 > 5 章 → 必须分块写入。**

#### 标准分块流程

1. **第一次 `Write`** ── 只写**骨架** (~30-40KB):
   - DOCTYPE / `<head>` / 全部 CSS / `<body>` 开头
   - 浮动按钮 / 桌面 nav.toc / mobile nav.toc(TOC 列表先写完整,因为短)
   - `<div class="container">` 开头
   - `<header class="hero">` 完整内容
   - `<section class="tldr">` 完整内容(包含全部 12-18 条 TL;DR)
   - **每个章节只写空壳**:
     ```html
     <section class="chapter" id="chN">
       <div class="ch-num">Chapter 0N</div>
       <h2>Title</h2>
       <div class="ch-zh">中文副标题</div>
       <!-- BODY:chN -->
     </section>
     ```
   - `<footer>` / `</div>` / `<script>` / `</body></html>`

2. **后续每章一次 `Edit`** ── 把 `<!-- BODY:chN -->` 替换成完整 turn / bilingual 内容:
   - `old_string`: `<!-- BODY:chN -->`
   - `new_string`: 该章节所有 `.turn` / `.bilingual` / `.callout` / `.pull` 块
   - 每章 Edit ≈ 3-8KB,远低于 socket 风险阈值
   - **顺序执行**,不要 parallel

3. **写完最后一章后**直接报告完成,不需要再 Write 一次整体。

#### 何时可以一次写完

- 总字数 < 8000 字 / 章节数 ≤ 5 / 预计 HTML < 30KB → 一次 Write OK
- **博客 essay 模式**通常较短,经常可以一次写完
- **长 podcast (60+ min)** 几乎一定要分块

#### 进一步降级

如果第一次 Write 骨架仍然超时:
- 只 Write 到 `</section>` of `.tldr`,后面所有章节用 Edit 在 `</footer>` 之前追加
- 或:Write 骨架时连 TL;DR 也只写空壳,TL;DR 也用一次 Edit 补全

#### 自检

写完后跑 `wc -c <file>`,确认大小符合预期(70-110KB 是 12-13 章长 podcast 的正常区间)。

---

## L4 · WebFetch 把博客原文摘要化 (2026-05-07)

### 症状

跑 `/bpr https://andrewchen.com/the-adjacent-user-theory/` 时,
WebFetch 返回的"原文"长度约 2000 词,带着 `## Overview` / `## Core Concept`
这种结构化小标题,看起来像散文摘要。

按这份"原文"做出的双语 HTML 句对句对照——句子全是模型重写过的英文,
不是 Bangaly Kaba 的原话。用户反馈:**结果很一般**。

### 根因

`WebFetch` 工具内部有一个"小快模型",会把长 HTML 压缩成结构化摘要返回,
即使 prompt 里写了 "verbatim",它仍然压。这是工具行为,不是 prompt 能改的。

事后用 curl 重新抓同一个 URL,得到 6,302 词原文(比 WebFetch 多 3 倍),
且每段都是 Bangaly 的连续散文,没有 `## Overview` 这种小标题——后者是
WebFetch 自己加的结构化包装。

### 硬规则

1. **抓博客 / 长文 / podcast 文章页 → 一律 curl**:

   ```bash
   curl -s -L \
     -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ..." \
     "<URL>" -o /tmp/bpr-raw.html
   ```

   然后用 Python regex / sed 提取 `<article>` 或主正文 div。

2. **WebFetch 只保留给"我想知道这页面大致讲什么"的摘要场景** —— 比如
   要确认这个 URL 是不是用户想要的内容、看一下作者是谁。**绝不用于 BPR 主流程的正文输入**。

3. **抓完后做 sanity check**:
   - 字数与预期相符(博客 essay 一般 1.5K-8K 词,长 podcast 文章页 5-15K)
   - 没有出现 `## Overview` / `**Compounds Over Time**:` 这种 WebFetch 风格的小标题
   - 段落是连续散文,不是 bullet point 拼接
   - **不符合 → curl 重抓,而不是将就用**

4. **GitHub URL 例外**:用 `gh` CLI(`gh pr view`/`gh issue view`),不走 curl 也不走 WebFetch。

5. **登录墙 / paywall**:curl 拿到的是登录页 → 直接告诉用户抓不到,让 ta 粘 raw text,**不要去试 WebFetch 兜底**(WebFetch 可能拿到带摘要的预览页,质量更糟)。

### 关联工具

- **`scripts/fetch/extract_metadata.py`** — 抓 URL 的发布日期 + 标题 + 作者,内部已经走 curl,直接调即可
- **`scripts/fetch/fetch_youtube.sh`** — YouTube 走 yt-dlp,跟 curl 是平行路径,各管一摊

---

## L5 · macOS 大小写不敏感 FS + Vercel 大小写敏感路由 (2026-05-08)

### 症状

`build_index.py` 跑完,本地 `ls` 看 `index.html` 存在(15KB)。
`vercel --prod` 部署成功,但 `https://bpr.ken.solar/` 一直返回 **HTTP 404**,
单篇 transcript 文件却 HTTP 200。

### 根因

Transcript 目录里**有遗留的 `INDEX.html`(大写)**——之前 stale 那个还没清掉。
macOS 默认 APFS 文件系统**大小写不敏感但保留(case-insensitive but case-preserving)**:

- Python `open("index.html", "w")` 在 case-insensitive FS 上**匹配到**已有的 `INDEX.html`
- 写入操作**只更新内容,不会重命名文件**——磁盘上仍然是 `INDEX.html`
- Vercel 路由是**大小写敏感的**——只把小写 `index.html` 当 root

结果:文件确实部署上去了,但 Vercel 把它当成普通文件 `INDEX.html`,
访问 `/INDEX.html` 才能命中,访问 `/` 没有 root,404。

### 硬规则

1. **build_index.py 跑之前**先清掉任何遗留的大写 `INDEX.html`:
   ```bash
   [ -f "~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/INDEX.html" ] && \
     rm "~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/INDEX.html"
   ```

2. **写文件用"先删后写"模式**,而不是直接 `write_text`:
   ```python
   if INDEX_PATH.exists():
       INDEX_PATH.unlink()
   INDEX_PATH.write_text(html)
   ```
   保证磁盘文件名是小写。

3. **部署后必须 curl 测 root**:
   ```bash
   curl -s -o /dev/null -w "HTTP %{http_code}\n" https://bpr.ken.solar/
   ```
   不是 200 → 立刻去看磁盘文件名(`ls *.html | grep -i index`)。

4. **更通用的教训**:**Vercel / Cloudflare / 任何 web 服务器都是大小写敏感的**——
   静态资源文件名(尤其 index.html / favicon.ico / robots.txt)必须严格小写。

### 关联

- L1-L3 都是"产物正确但显示错"——L5 加进来:产物**和**文件名都正确,但**因为 FS 大小写差异导致路由不匹配**

---

## L6 · 逐字稿被压成精选 + 时间戳对不上 (2026-06-22, No Priors × Lip Bu Tan)

### 症状
1. 跑 YouTube(8,528 词,111 个 `>>` 轮次)做出的 reader,只有 40 轮 / 146 句对照 —— **内容被压到约一半**,大量来回和细节(整段投资哲学、IPO/并购数字、Cadence/Synopsys 等)被丢。用户两次指出"这不是逐字稿"。
2. 加时间戳第一次只匹配上 **4/49** 轮,其余全卡在同一个时间。

### 根因
1. **把 step 5「翻译」默默做成了「每章挑代表性句子」**,而规则要求逐句 verbatim、不省略。面对 YouTube 那种无标点、滚动重复的字幕,偷懒选了"出个好读摘要"。**而 step 7 自检只查了 en=zh 配对(内部一致性),没查"覆盖率 vs 源稿"**,所以漏网。
2. VTT 解析器两个 bug:① 只抓 `<c>` 标签里的词,**漏掉每条 cue 的裸首词**;② **没处理 YouTube 滚动字幕**(每条 cue = 上条全文 + 新增几词),词流错乱重复 → 首句匹配全废。

### 硬规则
1. **transcript 模式默认就出逐字全量**,不许"精选/摘要"。每个发言轮次、每句都要 `.bilingual` 对照(口语词酌情保留,但不省略信息)。
2. **step 7 覆盖率硬闸**:生成后比对源稿——`渲染的 .turn 数 / 源稿 >> 轮次数` 和 `渲染 en 句数 / 源稿句数` **任一 < ~85% = 不合格**,必须回 step 5 补全。**只看 en=zh 配对不算自检通过。**
3. **时间戳用 `scripts/enrich/add_timestamps.py`,别手写 VTT 解析**:它做了滚动重建(只取每条 cue 新增尾词)+ 裸首词。podcast 模式 **step 6.5 默认跑**,不用等用户要求。超短插话(<4 个有辨识度的词)匹配不到就留空,不硬塞。
4. **根因共性**:YouTube 上传/自动字幕 = 脏 + 滚动 + 有逐词时间但无干净句子/说话人结构。做逐字+时间戳本就是苦活,必须一次做满,别等用户两轮纠错。

---

## L7 · essay/blog 正文图被漏掉(2026-07-10, Lenny "tech workers 2026")

### 症状
跑 Lenny's Newsletter 一篇**数据调查报告**,做出的双语 reader **一张图都没有** —— 而原文 16 张调查图表本身就是核心内容。用户当场指出"图片没发布"。第一次补救时又走了**热链 substackcdn**,与仓库既有的自托管规范不一致。

### 根因
1. 早期抓正文只提取 `<h*>/<p>/<li>/<blockquote>` 文本块,**完全没处理 `<img>/<figure>`**;skill 的 `templates/base.html` 也**没有 figure CSS**,所以即便抓了也无处渲染。而仓库里**过去的产物早已有自托管规范**(`images/<stem>/NN_slug.ext` + `<figure class="from-source banner|portrait|square|wide">` + 配套 CSS),只是从没固化进 skill。
2. Substack 页面正文**重复出现两份**:第一份纯文本无图,第二份才带图(`<a class="image-link" href="全分辨率URL">`)。只扫第一份 → 0 图。

### 硬规则
1. **essay/blog 模式默认跑 step 6.2 `extract_images.py`**,把正文图**下载自托管**到 `images/<stem>/`,按锚点注入 `<figure class="from-source ...">`。**podcast 模式跳过**(基本无内嵌图)。
2. **一律自托管,不热链**:热链源站 CDN 会因签名/防盗链失效,且破坏仓库一致性。下载失败**重试2次→跳过并进报告**,不回退热链。
3. **去噪**:只抓正文容器内的图;下载后 Pillow 读尺寸,**长宽任一 < 100px**(icon/头像)丢弃;URL/alt 命中 `avatar|icon|logo|profile|button|badge|emoji|spacer` 丢弃;报告里列出被跳过的图。
4. **变体按宽高比**:ratio≥1.8 banner / <0.8 portrait / 否则 短边<500 square 否则 wide。正文开头之前的大图当 `01_hero`(banner)。
5. **幂等**:`images/<stem>/.manifest.json` 记 `id→file`,re-run 复用不重下;`重抓图 / --refresh` 强制全重下。
6. **step 7 覆盖率闸门加一条图片项**:`成功下载 / 正文候选图 < ~90%` → 报告显式警告,别默默交缺图版本。
7. **Substack 类页面正文常重复两份**:抓图要扫全区域并**按图片 id 去重**(`extract_images.py` 已做),别只取第一份。

---

## L8 · PDF 分栏只能在 line 级做 + 研报图表是矢量的 (2026-08-03)

**踩坑一:block 级分栏行不通。**
`page.get_text("blocks")` 会把**同一基线上的左右栏文字合并进同一个 block** ——
栏在 block 内部就已经糊在一起,任何 block 级的 x 判据都拿不到栏边界。更糟的是
block 级的「通栏」判据会把所有合并后的正文块**全部误判成通栏**,结果左右栏交替串成一片。

**修法**:全程用 `get_text("dict")` 的 `blocks[].lines[]`(每行带 bbox)。先滤掉宽度
> 页宽 40% 的宽行(通栏标题会填平真空隙),再按行 `x0` 找最大间隙定 gutter,
且要求 gutter 两侧各有 ≥3 行——少了这条约束,单栏文档正文右侧的大片空白会被当成 gutter。

**踩坑二:研报图表大多是矢量而非位图。**
`page.get_images()` 对 Wind / Excel 导出的图表会**静默返回空**(它们在 PDF 里是填充矩形
与 path,不是嵌入位图)。必须靠 `get_drawings()` 的 bbox 聚类 + `get_pixmap(clip=bbox)`
做区域截图。静默零结果比报错更危险——不检查 coverage 就会以为「这份 PDF 没图」。

两条都是 2026-08-03 用合成 PDF 实测的结论,详见
`docs/superpowers/specs/2026-08-03-bpr-pdf-input-design.md`。

---

## L9 · PDF 版面层三个「静默丢内容」的坑 (2026-08-03)

**坑一:页眉页脚不能靠「剔上下 8% 带」实现。**
带内也可能是真正文——页边距紧于 8%(A4 约 67pt)的 PDF 每页首尾都是正文。
无条件剔带把它们无声吃掉,而且 `page_count < 4` 那条「样本不足就不删」的守卫
只关掉了 drop_set,带剔除照旧,2 页文档反而丢得更多。
**修法**:内容真源(`content_lines`,全量不剔)与版式判定视图(`body_lines`,剔带,
**只给 gutter 探测用**)分开。删除的唯一依据是跨页重复统计出的 drop_set。

**坑二:drop_set 的过滤方向极易搞反。**
drop_set 是从**带内**行推出来的,若拿去过滤**带外**的行,对真页眉页脚零作用,
唯一能命中的是正文区里归一化后与页眉同形的行。而 `norm_hf` 把数字全替成 `#`,
同模板的正文行跨页会归一成同一串 —— 实测一份 5 页 × 38 行的文档 body 被删空成一个换行。
**修法**:过滤对象必须是 `content_lines`(含带内),并**如实报出实际删除行数**
(与「模式条数」是两个数,只报模式条数看不出删空)。

**坑三:段落切分不能只看 bbox 的 y0。**
y0 被字号污染:标题字号大 → y0 被上抬 → 它前后的行间距被压小,同时中位行距
被标题周围的大间距抬高,`limit` 被推高,两条 delta 规则一起失灵,标题就粘进
相邻段落。72 个贴近真实研报的配置里 41 个粘连,留白 ≤0.3 倍行距时必粘。
**修法**:`y1 - y0` 就是字号的现成代理。按**页面中位行高**分「高行 / 常规行」,
类别切换即断段(`TALL_RATIO = 1.12`)。**必须跟中位比,不能跟相邻行比** ——
fitz 会把行尾 6.5pt 的脚注上标切成独立一行(行高 8.93),相邻比较会把一页
均匀正文切成 5 段。

**另:`text_ratio ≥ 0.8` 判 `text` 不代表每页都有文字层。**
最多 20% 的页可以完全没有文字层,而「正文有文字层、图表页/附录页是整页扫描图」
正是研报最常见形态。需要 OCR 的判断必须**与 mode 解耦**:只要有任一页缺文字层
就报错退出(exit 3),不管 mode 是 `text` 还是 `mixed`。
