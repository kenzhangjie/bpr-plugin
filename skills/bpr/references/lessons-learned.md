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
