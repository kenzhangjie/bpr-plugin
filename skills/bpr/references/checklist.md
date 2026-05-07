# 输出前质检清单

## 写入策略(必须先决定,再开始写)

- [ ] 估算最终 HTML 大小:章节数 × 每章 ~6KB + 骨架/CSS ~25KB
- [ ] **若估算 > 30KB 或章节 > 5**:必须用骨架 Write + 逐章 Edit 的分块策略(详见 `lessons-learned.md` L3)
- [ ] 骨架 Write 时,每章只写 `<!-- BODY:chN -->` 占位,不要把 turn / bilingual 写进去
- [ ] 骨架 Write 完成后,逐章 Edit,**顺序执行**,不要 parallel
- [ ] 写完最后一章后跑 `wc -c <file>` 自检,正常区间 70-110KB(12-13 章长 podcast)
- [ ] **若曾经在生成中出现** "API Error: socket connection closed" → 下次必须分块

## 翻译

- [ ] **每章每段都跑了三步法**(参 `translation-prompt.md`)——**不跳过、不偷懒、不在意 token 消耗**
- [ ] 每章正文翻译完后扫一遍——没有"被...所..."句式、没有连续 3+ 个"的"字定语、没有"X 这种东西" / "对于 X 来说" / "在...的情况下" 之类的填充结构
- [ ] **作者语气抓对了**:Naval / PG / Karpathy / Lenny / Anthropic-blog / Schopenhauer 的语气有明显区别(参 `translation-prompt.md` 速查表)
- [ ] **术语前后一致**:同一概念(agency / leverage / specific knowledge)在全文里要么都保留英文、要么都用同一个中文译法,不能混

## 主持人 / 嘉宾(podcast 模式)

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
- [ ] **文件名日期 = 内容发布日期**,不是处理日期(YouTube → metadata.json `upload_date`;博客 → 文章页 `<time>`;拿不到 → 问用户)
- [ ] 文件名遵守四种 pattern(参 SKILL.md "输出 / 文件名"):
  - 单一主持 podcast → `{date}_{podcast}_{guest}_{topic}.html`(host 隐含在 podcast slug)
  - 多主持 podcast → `{date}_{podcast}_{host}-x-{guest}_{topic}.html`
  - 单作者博客 → `{date}_{author}_{topic}.html`
  - 多作者刊 → `{date}_{publication}_{author}_{topic}.html`
- [ ] 主要分隔符是 `_`,词内 / 多词组合用 `-`(`anton-osika_lovable-200m-arr` 而不是 `anton-osika-lovable-200m-arr`)
- [ ] 全小写,无空格 / 中文 / 大写
- [ ] 总长度 ≤ 80 字符,目标 50-70
- [ ] 输出到 `<output_dir>`(默认 `~/Documents/Transcript/`)
