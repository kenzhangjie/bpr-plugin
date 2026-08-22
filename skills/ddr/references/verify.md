# 输出前质检清单

## 写入策略(必须先决定,再开始写)

- [ ] 估算最终 HTML 大小:章节数 × 每章 ~6KB + 骨架/CSS ~25KB
- [ ] **若估算 > 30KB 或章节 > 5**:必须用骨架 Write + 逐章 Edit 的分块策略(详见 `lessons-learned.md` L3)
- [ ] 骨架 Write 时,每章只写 `<!-- BODY:chN -->` 占位,不要把 turn / bilingual 写进去
- [ ] 骨架 Write 完成后,逐章 Edit,**顺序执行**,不要 parallel
- [ ] 写完最后一章后跑 `wc -c <file>` 自检,**按版型对号入座**:

      | 版型 | 正常区间 |
      |---|---|
      | essay / blog 双语 | 25-120 KB |
      | podcast 英文双语 | 90-300 KB |
      | 中文模式(书面正文 + 折叠底档)| 250-1,100 KB |

      > 2026-08-07 按已发布的 120 篇实测重定。旧值写的是「70-110KB」,只覆盖英文双语:
      > 全库**中位 138 KB**、最大 1,083 KB(13 章 / 3,194 turn 的中文长访谈),
      > 也就是说旧闸对大多数产出恒为「异常」—— 恒响的闸等于没有闸。
      > **明显低于区间**才是危险信号(多半漏章或覆盖率不足);偏高只要过了下面的覆盖闸就正常。
- [ ] **若曾经在生成中出现** "API Error: socket connection closed" → 下次必须分块

## 覆盖率硬闸(transcript 模式,必查 — 见 L6)

- [ ] **逐字全量,不是精选/摘要**:每个发言轮次、每句都做了 `.bilingual` 对照
- [ ] **比对源稿覆盖率**:`渲染 .turn 数 ÷ 源稿 >> 轮次数` 和 `渲染 en 句数 ÷ 源稿句数`,**任一 < ~85% = 不合格**,回 step 5 补全
- [ ] ⚠️ **只看 en=zh 配对数相等 ≠ 自检通过**——配对齐但只覆盖半篇也会"全绿",必须额外比源稿
- [ ] **时间戳已注入**(podcast 模式):跑过 `scripts/enrich/add_timestamps.py`,`.timestamp` 数接近 `.turn` 数(超短插话除外),时间单调递增、末值 ≤ 总时长
- [ ] **英文 PREP 源清洗跑过**:`clean_en.py finalize` 词覆盖 **≥0.98**(<0.98 = 丢句,回 PREP 重派该窗)
- [ ] **传了 `--windows`**(2026-08-07 起必做):否则只有一个全局 coverage,**说不出是哪一窗** ——
      "回 Step 2 重派该窗"这条硬规则就没法执行。看 stdout 的
      `逐窗覆盖:N 窗,最差 #k = 0.xxx`,以及 `WARN: 这些窗覆盖 < 0.98,回 Step 2 重派:#7, #12`
- [ ] **看了 `added_ratio`**:> 0.05 时抽查那几段有没有加译 / 复述 / 幻觉。
      覆盖率只管"源词有没有被盖住",凭空加一整段完全不掉分 —— 这是它补的另半边(报告项,不拦)
- [ ] **glossary 真的用上了**(2026-08-01 新增,别再靠巧合):
  - [ ] Step 1 跑过 `clean_en.py --scan <transcript>`,命中项进了 brief;`seen_in_source` 非空的错法在子代理 prompt 里点了名
  - [ ] finalize 那步 stdout 是 `专名硬映射 N 条`(N>0),**不是** `WARN: 专名硬映射为空` —— 覆盖率 `ok=True` 不代表硬映射跑过,两个闸互相独立
  - [ ] 收尾传了 `--names`,而且用**带 `seen_as` 的新形态**(老形态只写第 1 列,而硬映射只吃第 3 列
        → 飞轮只让参考表变长,纠错层原地不动)。看 stdout 的 `错法 += M 条`
  - [ ] 往 glossary 加过词就跑一次 `clean_en.py --check-glossary`(拒收的短键 / 冲突 / 与保护名单碰撞)
- [ ] **英文纠错冒烟**:跑 `tests/fixtures/asr-clean-en-regression.md`,已知错专名全修对;存疑走 `⟨?⟩` 不硬编

### 中文模式(CLEAN 之后)覆盖闸

书面重写会合并句子,句数比失效 → 改**实体级覆盖**:
底档里出现的数字 / 专名 / 论点实体,书面版必须都在。英文双语模式仍用句数闸(不变)。

- [ ] **跑实体覆盖脚本,不再人工抽查**(2026-08-07 脚本化 —— 抽查 ≠ 检索,漏掉的恰恰是没抽到的):

      ```bash
      python3 scripts/verify/entity_coverage.py --html <reader.html>
      ```

      直接对账成品的「折叠底档」与「书面正文」两侧。三档输出:
      - **数值(硬闸)** —— 底档里的阿拉伯数字,书面版必须能兑上(中文数字写法也认:
        `1700万` ↔ `一千七百万`、`190` ↔ `一百九`)。非空 → 退出码 1
      - **年份(软报告)** —— ASR 常把年份读碎(`21年` / `1819年`),CLEAN 规范化是对的
      - **拉丁专名(软报告)** —— CLEAN 合法纠拼写会让它"消失",扫一眼别是漏整段

      **非空 ≠ 一定有 bug**:实测两篇已发布长中文成品各剩 1 条,都是 ASR 把数字读碎
      (`拿了大概7000` 下一句才是 `8千万美金`)。逐条看,真吞了才回 CLEAN 补那一窗。
- [ ] **CLEAN 冒烟**:跑 `tests/fixtures/asr-clean-regression.md`,4 个错词须全修对。
- [ ] **零幻觉抽查**:抽查渲染里的 `<mark class="asr-uncertain">` 标注,确认是"存疑标注"而非模型杜撰的答案(见 clean.md Step E)。

## 来源行(hero-meta,必填 — 见 SKILL.md "来源行")

- [ ] `.hero-meta` 有来源行:`来源:{平台} · {节目} · {日期} · 时长 · 约 N 词 · N 章 · 逐字双语对照`(essay 省时长、写"全文双语对照";中文模式写"中文整理")
- [ ] **词数 / 章数是真实值**(词数=源稿英文词数,章数=实际章节数),不是占位
- [ ] ⚠️ **写了"逐字双语对照"就必须真的过了上面的覆盖率硬闸**——覆盖率 <85% 却写"逐字" = 撒谎,回 step 5 补全

## 翻译

- [ ] **每章每段都跑了三步法**(参 `translate.md`)——**不跳过、不偷懒、不在意 token 消耗**
- [ ] 每章正文翻译完后扫一遍——没有"被...所..."句式、没有连续 3+ 个"的"字定语、没有"X 这种东西" / "对于 X 来说" / "在...的情况下" 之类的填充结构
- [ ] **作者语气抓对了**:Naval / PG / Karpathy / Lenny / Anthropic-blog / Schopenhauer 的语气有明显区别(参 `translate.md` 速查表)
- [ ] **术语前后一致**:同一概念(agency / leverage / specific knowledge)在全文里要么都保留英文、要么都用同一个中文译法,不能混

## 主持人 / 嘉宾(podcast 模式)

- [ ] **Substack 播客:跑过 `fetch_substack_transcript.py` 了吗?**(2026-08-23 加)
      成功 → `.speaker` 用官方 `speaker_map` 的真名字;退出码 3 → 在报告里**明说**
      "说话人为启发式推断,未与官方标注对账"。
- [ ] **第三个说话人查过没有**:赞助商口播嘉宾 / 联合主持 / 第二嘉宾。
      启发式只会二分 host/guest,**整段并进主持人也不会掉任何一个闸**
      ——覆盖闸只问词丢没丢,加译闸只问词多没多,**没有闸在问"这句是谁说的"**。
      渲染时第三方用 `data-role="sponsor"`(base.html 已有配色,与 host/guest 都区分得开)。
- [ ] 主持人和嘉宾都在原文里**找到了**(不是猜的、不是默认的)
- [ ] Hero kicker 里的姓名 = transcript 里实际出现的姓名,**没有默认 Lenny**
- [ ] **podcast slug 匹配实际节目**(参 `lessons-learned.md` L1 的 slug 表),不允许泛指 `podcast` / `interview`
- [ ] **文件名包含嘉宾 slug**(单一主持节目):`{date}_{podcast}_{guest}_{topic}.html`

## TL;DR

- [ ] 每条都有英文金句原文(没有凭空总结)
- [ ] 每条都有英文上下文(`.tldr-context`)或合理省略
- [ ] h2 标题用**描述性主题**,不写死"X 条..."硬编码数字
- [ ] 数量符合 SKILL.md "TL;DR 数量" 表

## 章节

- [ ] 章节数符合 SKILL.md "章节数" 表
- [ ] 标题之间无重复
- [ ] 双语段落数量一致(没漏译)

## 桌面布局(参 `lessons-learned.md` L2,**最终定版 = fixed + margin-left**)

- [ ] **直接 copy `templates/base.html` 骨架**,没有自己重写 CSS
- [ ] `.container` 用 `max-width:780px; margin-left:260px`(@1100px+),**禁止** grid 布局
- [ ] `.toc` 用 `position:fixed; left:24px; top:80px`,**不**用 sticky / grid 列
- [ ] 浮动按钮(`.toc-mobile` / `.theme-toggle`)是 `<body>` 子节点,**不在 `.container` 内**
- [ ] `<nav class="toc">` 是 `<body>` 子节点(fixed),**不在 `.container` 内**
- [ ] mobile-only 元素 base 规则有 `display:none`,只在 `@media(max-width:1099px)` 里切回 `display:block`
- [ ] 在 1440 / 1920 / 2560 三档屏宽下肉眼检查:hero 上方没有巨字号下划线链接、没有空白长方形;TOC 与正文之间没有"半页空白死区"

## inline link

- [ ] 原文 inline link 在英文段保留 `<a href="...">` 不丢
- [ ] 中文段对应位置写**同一个**链接(URL 一致),不重复打印 URL 文本
- [ ] bare link("Learn more in our docs.")在两段都保留 `<a>`

## blog / essay 模式专属

- [ ] **不**渲染 `.turn / .speaker / .timestamp`(它们是 podcast 模式专属)
- [ ] Hero kicker 用 `{publication} · Essay · YYYY-MM-DD` 模板
- [ ] `.chapter-meta` 用关键词概括,不放时间戳
- [ ] 正文用 `.body-block` + `.bilingual` 句级对照

## podcast 模式专属

- [ ] Sponsor / Outro 段已正确标记
- [ ] 时间戳单调递增,没乱序
- [ ] 多说话人时,每人有独立 `.speaker` 颜色

## 通用

- [ ] HTML 在 Chrome 和 Safari 都能正常打开
- [ ] 暗色主题对比度 ≥ WCAG AA
- [ ] 阅读列宽 ≤ 800px(中英文混排最佳宽度)
- [ ] print stylesheet 有效(Cmd+P 预览)
- [ ] 没有编造的 URL / 头像 / LinkedIn
- [ ] **文件名日期 = 内容发布日期**,不是处理日期。提取顺序(参 `ingest.md` "发布日期提取"):
  - YouTube → `metadata.json` 的 `upload_date`(`scripts/fetch/fetch_youtube.sh` 已自动跑)
  - 博客 / essay → 跑 `python3 scripts/fetch/extract_metadata.py <URL>`(7 种策略,JSON-LD / OG / wp-uploads / body-text 等)
  - Podcast 非 YouTube → WebSearch 找 Spotify / Apple Podcasts / Substack / libsyn 页
  - 拿不到 → 问用户,**绝不静默用今天**;**禁止 WebFetch 兜底**(L4)
- [ ] Hero kicker 里的日期 = 文件名日期,两处一致
- [ ] 文件名遵守四种 pattern(参 SKILL.md "输出 / 文件名"):
  - 单一主持 podcast → `{date}_{podcast}_{guest}_{topic}.html`(host 隐含在 podcast slug)
  - 多主持 podcast → `{date}_{podcast}_{host}-x-{guest}_{topic}.html`
  - 单作者博客 → `{date}_{author}_{topic}.html`
  - 多作者刊 → `{date}_{publication}_{author}_{topic}.html`
- [ ] 主要分隔符是 `_`,词内 / 多词组合用 `-`(`anton-osika_lovable-200m-arr` 而不是 `anton-osika-lovable-200m-arr`)
- [ ] 全小写,无空格 / 中文 / 大写
- [ ] 总长度 ≤ 80 字符,目标 50-70
- [ ] 输出到 `~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/`
