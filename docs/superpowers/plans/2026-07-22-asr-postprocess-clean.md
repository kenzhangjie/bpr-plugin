# BPR CLEAN 阶段(ASR 后处理三步法)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 BPR 中文模式流水线新增 CLEAN 阶段,用 analyze/review/polish 三步把火山 ASR 逐字口语 transcript 变成纠错后的书面正文,同时保留可折叠逐字底档。

**Architecture:** CLEAN 阶段插在 PREP 与 STRUCTURE 之间,仅中文模式触发。主代理全稿跑一次 Analyze(出术语表+存疑清单),按 ~25 turn 切窗分派子代理做 Review+Polish(独立 context,只回书面中文),主代理 verbatim 持有原稿。RENDER 把书面版作阅读面、原始逐字塞进每章可折叠 `<details>`。

**Tech Stack:** 这是一个 Claude Code skill(markdown references + HTML 模板 + Python fetch 脚本)。CLEAN 的智能活由子代理按 `clean.md` 规程执行,无独立运行时脚本。验证靠 grep 一致性检查 + 渲染 fixture + 回归样本。

## Global Constraints

- **仅中文模式触发 CLEAN**(CJK ≥ 60%,沿用 `prep-and-modes.md` 现有判定);英文双语模式不跑。
- **`enable_ddc` 保持 False**(`~/.config/volc/volc_asr.py` 已是);口水清洗交给 Polish,底档要真逐字。
- **Polish 铁律**:只改"怎么说",不改"说了什么" —— 每个论点/数字/专名/因果必须保下来,不许为通顺吞信息。
- **保留逐字底档**:CLEAN 之前的火山原始 transcript 永不改,可折叠留档。
- **禁硬编码绝对路径**:仓库 CI 有 `no-hardcoded-paths` 检查,所有路径用 `~/` 不用 `/Users/ken/`。
- **改源不改 cache**:所有编辑落 `/Users/ken/dev/bpr-plugin/`(源仓库),实现完 reinstall 覆盖 cache;直接改 cache 会在插件更新时丢失。
- **不可判词标注不硬编**:Class 4 用 `⟨?猜测⟩` 标注,渲染成 `<mark class="asr-uncertain">`。
- 分支已在 `feat/asr-postprocess-clean`;沿用,不新开。

---

### Task 1: 同步 ingest.md 的 --meta/context 偏置到源仓库

之前的 context 偏置改动只落到了 cache,源仓库 `ingest.md` 的火山命令仍是旧版。先把它对齐,消除源/cache 漂移。

**Files:**
- Modify: `skills/bpr/references/ingest.md`(火山 Step B,约 line 226-238)

**Interfaces:**
- Produces: 源仓库 ingest.md 的火山命令带 `--meta`,并说明三层偏置(context / boosting / correct_table)。

- [ ] **Step 1: 确认源仓库当前是旧命令**

Run: `grep -n 'volc_asr.py' ~/dev/bpr-plugin/skills/bpr/references/ingest.md`
Expected: 命中一行 `python3 ~/.config/volc/volc_asr.py "$AUDIO_URL" "$WORKDIR/transcript.txt"`(无 `--meta`)。

- [ ] **Step 2: 替换成带 --meta 的命令 + 三层偏置说明**

把该命令行改为:

```bash
AUDIO_URL=$(python3 -c "import json;print(json.load(open('$WORKDIR/metadata.json'))['audio_url'])")
# --meta 把本期标题/简介 + ~/.config/volc/glossary.txt 常驻专名表拼成 context 偏置喂给模型,
# 中英混录的英文品牌名/术语在识别阶段就转对,别再靠事后 correct_table 替换。
python3 ~/.config/volc/volc_asr.py "$AUDIO_URL" "$WORKDIR/transcript.txt" --meta "$WORKDIR/metadata.json"
```

并在其后补一段"质量偏置三层(强→弱)":1) `corpus.context`(--meta 自动 + glossary.txt);2) `corpus.boosting_table_name`(--boosting 控制台表);3) `correct_table.json`(事后替换,兜底)。

- [ ] **Step 3: 验证**

Run: `grep -c 'meta\|glossary\|boosting' ~/dev/bpr-plugin/skills/bpr/references/ingest.md`
Expected: ≥ 3。

- [ ] **Step 4: Commit**

```bash
cd ~/dev/bpr-plugin
git add skills/bpr/references/ingest.md
git commit -m "fix(ingest): 同步火山 --meta/context 偏置到源仓库(修 cache 漂移)"
```

---

### Task 2: 新建 clean.md — CLEAN 阶段核心规程

这是本计划最大的交付物:CLEAN 阶段的完整规程,子代理照它执行。

**Files:**
- Create: `skills/bpr/references/clean.md`

**Interfaces:**
- Produces: `references/clean.md`,含 6 个必备小节:① 触发条件 ② Analyze 规程 ③ 切窗规则 ④ 子代理 Review+Polish prompt 模板 ⑤ 错词四分类 ⑥ 存疑标注约定。SKILL.md(Task 3)、prep-and-modes.md(Task 4)、render.md(Task 5)会引用本文件。

- [ ] **Step 1: 写 clean.md 骨架 + 触发条件 + Analyze**

创建文件,写入头部与前两节:

```markdown
# CLEAN · ASR 后处理三步法(analyze / review / polish)

> 阶段 3(新增)· 仅中文模式。把火山逐字口语 transcript 纠错并书面化,保留逐字底档。
> 位置:PREP 之后、STRUCTURE 之前。英文双语模式不跑(走 translate.md 四步法)。

## 触发条件
- PREP 判定 CJK ≥ 60%(中文模式)→ 跑 CLEAN。
- 英文/双语 → 跳过。

## Step A · Analyze(主代理,全稿 1 次)
在切窗分派前,通读全稿产出一份 brief,塞进每个子代理 prompt(保跨窗一致):
1. **领域术语表**:本期专名(人/公司/产品/模型名)+ 高频英文术语,标注哪些保留英文、哪些固定中文。AI/科技/投资/growth 领域优先。
2. **说话人 + 语气**:host / guest 分别的语气。
3. **存疑词清单**:扫全稿标出可疑中英混词(疑似同音/近音错、拼写不成词的英文),供 Review 重点核。
> Analyze 产出的专名清单,完成后回写 `~/.config/volc/glossary.txt`(Ken 过目合入),反哺下期 ASR 偏置。
```

- [ ] **Step 2: 写切窗规则**

追加:

```markdown
## Step B · 切窗
- CLEAN 在语义切章(STRUCTURE)之前,不能按章切 → 按**固定 turn 窗口(~25 条)**切。
- 窗口边界对齐到 turn 边界(±几条弹性),不切碎一个说话人的连续发言。
- 每窗子代理拿:该窗逐字原文 + 全局 Analyze brief(术语表 + 存疑清单 + 语气)。
```

- [ ] **Step 3: 写子代理 Review+Polish prompt 模板**

追加(这是执行的核心,必须逐字可用):

````markdown
## Step C · 子代理 Review+Polish(每窗 1 个,独立 context)
默认每窗一个子代理,先 Review 再 Polish,只回书面中文。主代理 verbatim 持有原窗(抗压缩铁律)。

派发 prompt 模板:
```
你在做中文播客 ASR 逐字稿的纠错 + 书面化。这是第 N 窗逐字原文,和全局 brief。

【全局 brief】
术语表:{glossary}
说话人/语气:{speakers}
存疑词清单:{suspects}

【逐字原文(本窗)】
{raw_window}

分两步做,只输出最终书面中文:
1) Review(纠错,只对原文负责):按上下文 + 术语表修同音/近音错词、专名、断句。
   不可判的词绝不硬编,标 ⟨?你的猜测⟩ 留待定夺。
2) Polish(书面化,只改怎么说不改说了什么):去口水词(呃/就是/对吧/然后…)、
   合并重组成通顺书面段落。**每个论点/数字/专名/因果必须保下来**,通顺不许吞信息。

按说话人分段输出,保留时间戳锚点。不要输出解释,只要正文。
```

高密度章(非共识金句)可升级:Review、Polish 各一次独立调用(见 translate.md 极致版)。
````

- [ ] **Step 4: 写错词四分类 + 存疑标注约定**

追加:

```markdown
## Step D · 错词四分类
| 类 | 例 | 处理 |
|---|---|---|
| 1 同音/近音 | skating→scaling、constrain→constraint、unprobability→unpredictability | 上下文直接改 |
| 2 专名 | 克洛蔻→Claude、阿帕比→a paper、小俊→小珺 | 术语表比对后改 |
| 3 断句/标点 | 两句黏一句 | 重新断句 |
| 4 真不可判 | 连人都拿不准 | 标 ⟨?猜测⟩ 不硬编;confidently wrong 比留错更坏 |

## Step E · 存疑标注约定
- Review 阶段不可判词写 `⟨?候选词⟩`(如 `⟨?a paper⟩`)。
- RENDER 阶段(render.md)把 `⟨?X⟩` 转成 `<mark class="asr-uncertain" title="ASR存疑">X?</mark>`,可点可 grep。
```

- [ ] **Step 5: 验证 clean.md 六节齐全**

Run: `grep -cE '^## (触发条件|Step A|Step B|Step C|Step D|Step E)' ~/dev/bpr-plugin/skills/bpr/references/clean.md`
Expected: 6。

- [ ] **Step 6: Commit**

```bash
cd ~/dev/bpr-plugin
git add skills/bpr/references/clean.md
git commit -m "feat(clean): 新增 CLEAN 阶段规程(analyze/review/polish 三步法)"
```

---

### Task 3: SKILL.md 流水线加 CLEAN 阶段(7→8)

**Files:**
- Modify: `skills/bpr/SKILL.md`(流水线阶段表 + 抓取硬提醒区)

**Interfaces:**
- Consumes: `references/clean.md`(Task 2)。
- Produces: SKILL.md 流水线表含 CLEAN 行,阶段编号重排。

- [ ] **Step 1: 看现有阶段表**

Run: `grep -n 'STRUCTURE\|PREP\|阶段' ~/dev/bpr-plugin/skills/bpr/SKILL.md | head`
Expected: 看到 7 阶段表(INGEST/PREP/STRUCTURE/TRANSLATE/RENDER/VERIFY/PUBLISH)。

- [ ] **Step 2: 在 PREP 与 STRUCTURE 之间插入 CLEAN 行**

在流水线表 PREP 行后加(保持表格式):

```markdown
| **3 · CLEAN** | **(仅中文模式)** ASR 后处理三步:Analyze 全稿定术语表+存疑清单 → 按 ~25 turn 切窗,子代理 Review(纠错)+ Polish(书面化)→ 产出书面正文,保留逐字底档。英文模式跳过。 | `references/clean.md` |
```

并把其后 STRUCTURE→PUBLISH 的阶段编号 3-7 顺延为 4-8。

- [ ] **Step 3: 验证**

Run: `grep -c 'CLEAN\|clean.md' ~/dev/bpr-plugin/skills/bpr/SKILL.md`
Expected: ≥ 2。
Run: `grep -oE '\*\*8 · PUBLISH\*\*' ~/dev/bpr-plugin/skills/bpr/SKILL.md`
Expected: 命中(PUBLISH 现在是第 8 阶段)。

- [ ] **Step 4: Commit**

```bash
cd ~/dev/bpr-plugin
git add skills/bpr/SKILL.md
git commit -m "feat(skill): 流水线插入 CLEAN 阶段(7→8),中文模式专用"
```

---

### Task 4: prep-and-modes.md 修订逐字铁律 + CLEAN 交接

**Files:**
- Modify: `skills/bpr/references/prep-and-modes.md`(中文模式输出结构 + 2026-07-11 铁律段)

**Interfaces:**
- Consumes: `references/clean.md`(Task 2)。
- Produces: 中文模式正文规则从"逐字全量"改为"书面正文 + 逐字底档可折叠";指向 CLEAN。

- [ ] **Step 1: 定位旧铁律**

Run: `grep -n '逐字全量\|2026-07-11\|不概括' ~/dev/bpr-plugin/skills/bpr/references/prep-and-modes.md`
Expected: 命中"中文模式正文也要逐字全量,别只概括"附近。

- [ ] **Step 2: 修订铁律段**

把该段改写为(保留历史脉络,声明升级):

```markdown
### 中文模式正文规则(2026-07-22 修订)
- **旧规则(2026-07-11)**:中文正文逐字全量、不概括。
- **新规则**:正文经 CLEAN 阶段(见 `clean.md`)**书面重写**为可读正文;**逐字口语原稿降级为可折叠底档**(每章 `<details>` 留档,内容 == 火山原始 transcript,不丢)。
- 铁律不变的部分:**Polish 只改"怎么说"不改"说了什么"**,每个论点/数字/专名/因果必须保下来 —— 书面化 ≠ 概括。
```

- [ ] **Step 3: 中文模式输出结构里,正文那节指向 CLEAN**

在"章节正文"描述处加一句:`正文由 CLEAN 阶段产出(书面版);逐字底档见 render.md 的 <details> 约定`。

- [ ] **Step 4: 验证**

Run: `grep -c '2026-07-22\|书面\|底档\|clean.md' ~/dev/bpr-plugin/skills/bpr/references/prep-and-modes.md`
Expected: ≥ 3。

- [ ] **Step 5: Commit**

```bash
cd ~/dev/bpr-plugin
git add skills/bpr/references/prep-and-modes.md
git commit -m "docs(prep): 中文正文铁律改为书面正文+逐字底档(2026-07-22)"
```

---

### Task 5: render.md + base.html — 书面正文 + 可折叠底档

书面正文渲染与底档折叠是一起变的(render 指令引用 CSS),合为一个任务。

**Files:**
- Modify: `skills/bpr/templates/base.html`(`<style>` 末尾加 CSS)
- Modify: `skills/bpr/references/render.md`(中文模式渲染指令)
- Test: `skills/bpr/tests/fixtures/clean-render-sample.html`(手写小样验证折叠)

**Interfaces:**
- Consumes: `⟨?X⟩` 存疑约定(Task 2 Step E)。
- Produces: `.raw-transcript` / `.asr-uncertain` 两个 CSS 类;render.md 说明书面正文 + `<details>` 底档 + 存疑 `<mark>`。

- [ ] **Step 1: base.html 加 CSS**

在 `<style>` 末尾(现有中文模式扩展样式附近)追加:

```css
/* ── CLEAN 阶段:可折叠逐字底档 + 存疑标注 ── */
details.raw-transcript{margin:24px 0 8px; border-top:1px dashed var(--rule)}
details.raw-transcript summary{
  font-family:var(--sans); font-size:12.5px; letter-spacing:.04em;
  color:var(--ink-faint); cursor:pointer; padding:10px 0; list-style:none;
}
details.raw-transcript summary::before{content:"▸ "; color:var(--accent)}
details.raw-transcript[open] summary::before{content:"▾ "}
details.raw-transcript .turn{opacity:.85}
mark.asr-uncertain{
  background:transparent; color:var(--accent);
  border-bottom:1px dotted var(--accent-soft); cursor:help;
}
```

- [ ] **Step 2: render.md 加中文模式渲染指令**

在 render.md 中文模式版型处加一节:

```markdown
### 中文模式正文(CLEAN 之后)
- 书面正文为默认阅读面:按说话人分段,`<div class="turn">` + `<p class="zh">`(书面句)。
- 每章末尾放逐字底档:`<details class="raw-transcript"><summary>展开逐字原稿</summary>{该章火山原始 turn,带时间戳}</details>`。
- Analyze/Review 标的 `⟨?X⟩` → 渲染为 `<mark class="asr-uncertain" title="ASR存疑">X?</mark>`。
```

- [ ] **Step 3: 写渲染小样 fixture**

创建 `skills/bpr/tests/fixtures/clean-render-sample.html`:一个最小 HTML,内联上面的 CSS,含一个书面 `.turn`、一个 `<details class="raw-transcript">`(内放逐字 turn)、一个 `<mark class="asr-uncertain">a paper?</mark>`。

- [ ] **Step 4: 验证折叠与样式**

Run: `open ~/dev/bpr-plugin/skills/bpr/tests/fixtures/clean-render-sample.html`
Expected(肉眼):底档默认收起,点击 summary 展开;`▸/▾` 箭头切换;`a paper?` 显红色点下划线。

- [ ] **Step 5: Commit**

```bash
cd ~/dev/bpr-plugin
git add skills/bpr/templates/base.html skills/bpr/references/render.md skills/bpr/tests/fixtures/clean-render-sample.html
git commit -m "feat(render): 中文模式书面正文 + 可折叠逐字底档 + 存疑标注样式"
```

---

### Task 6: verify.md — 实体覆盖闸 + 回归样本

**Files:**
- Modify: `skills/bpr/references/verify.md`
- Test: `skills/bpr/tests/fixtures/asr-clean-regression.md`(回归样本)

**Interfaces:**
- Produces: verify.md 的覆盖闸从句数级改实体级;回归 fixture 定义 4 个已知错 → 期望修正。

- [ ] **Step 1: 定位旧句数闸**

Run: `grep -n '85%\|句数\|覆盖' ~/dev/bpr-plugin/skills/bpr/references/verify.md`
Expected: 命中"渲染句数 ÷ 源稿 <~85%"硬闸。

- [ ] **Step 2: 覆盖闸改实体级(仅中文 CLEAN 场景)**

在该闸处补一段:

```markdown
### 中文模式(CLEAN 之后)覆盖闸
书面重写会合并句子,句数比失效 → 改**实体级覆盖**:
底档里出现的数字 / 专名 / 论点实体,书面版必须都在。抽查缺失即回 CLEAN 补。
英文双语模式仍用句数闸(不变)。
```

- [ ] **Step 3: 写回归 fixture**

创建 `skills/bpr/tests/fixtures/asr-clean-regression.md`:

```markdown
# CLEAN 回归样本(冒烟用)
输入(火山原始,含 4 个已知错):
- "就非常第一性原理,skating law 是这样"
- "那个产品是克洛蔻做的"
- "第二是一个 constrain 吧"
- "比如说 unprobability 就对吧"

期望 CLEAN 输出修正为:
- skating → scaling
- 克洛蔻 → Claude
- constrain → constraint
- unprobability → unpredictability
零幻觉:不得给不可判词编造答案(应标 ⟨?⟩)。
```

- [ ] **Step 4: verify.md 引用回归样本**

在 verify.md 加一行:`CLEAN 冒烟:跑 tests/fixtures/asr-clean-regression.md,4 个错词须全修对。`

- [ ] **Step 5: 验证**

Run: `grep -c '实体\|regression\|scaling' ~/dev/bpr-plugin/skills/bpr/references/verify.md ~/dev/bpr-plugin/skills/bpr/tests/fixtures/asr-clean-regression.md`
Expected: 两文件均命中。

- [ ] **Step 6: Commit**

```bash
cd ~/dev/bpr-plugin
git add skills/bpr/references/verify.md skills/bpr/tests/fixtures/asr-clean-regression.md
git commit -m "feat(verify): CLEAN 实体级覆盖闸 + 4 词回归样本"
```

---

### Task 7: reinstall + 端到端回归冒烟

把源仓库改动装进 cache,跑真实回归,确认三步法在真链路上生效。

**Files:**
- 无新增;验证 Task 1-6 的集成。

**Interfaces:**
- Consumes: 全部前置任务。

- [ ] **Step 1: reinstall 插件覆盖 cache**

Run: `grep -rl 'CLEAN' ~/.claude/plugins/cache/bpr-marketplace/ | head`
Expected(reinstall 前):可能为空(cache 还是旧的)。执行插件 reinstall(`/plugin` 或 marketplace 更新流程),再跑一次同 grep,Expected:命中 clean.md / SKILL.md。

- [ ] **Step 2: 回归冒烟 — 4 词修正**

用 `tests/fixtures/asr-clean-regression.md` 的输入,按 clean.md 走一遍 Analyze→Review→Polish(可在当前会话手动驱动一窗),检查输出:

Expected:`scaling / Claude / constraint / unpredictability` 四词全部出现且正确;无为不可判词杜撰。

- [ ] **Step 3: 端到端 — 真实一期(可选但推荐)**

对一期真实小宇宙中文 URL 跑 `/bpr`,确认:书面正文可读(口水基本清空)、每章底档可折叠展开且 == 火山原稿、`<mark class="asr-uncertain">` 无杜撰、实体覆盖闸通过。

> 未验边界:若无网络/无飞书或火山额度,Step 3 标记为"e2e 未验",Step 2 的离线回归为最低验证线。

- [ ] **Step 4: 收尾 commit(若有微调)**

```bash
cd ~/dev/bpr-plugin
git add -A && git commit -m "chore(clean): 端到端回归通过,CLEAN 阶段上线" || echo "无改动可提交"
```

---

## Self-Review

**Spec coverage(逐节对照 spec §):**
- §3 架构/数据流 → Task 3(SKILL 流水线)+ Task 2(clean.md 定义流程)✓
- §4 三步分工 → Task 2 Step 1/3(Analyze + 子代理模板)✓
- §5 错词四分类 → Task 2 Step 4 ✓
- §6 切窗 → Task 2 Step 2 ✓
- §7 底档保留/渲染 → Task 5 ✓
- §8 反哺闭环 → Task 2 Step 1(Analyze 回写 glossary.txt 说明)✓ · Task 1(--meta 消费 glossary)✓
- §9 VERIFY 改造 → Task 6 ✓
- §11 文件清单 → Task 1-6 覆盖全部;`volc_asr.py` 确认无需改(enable_ddc 已 False)✓
- §12 成功标准 → Task 7 回归冒烟 ✓
- 无遗漏。

**Placeholder scan:** 无 TBD/TODO;每个改动步骤给了实际内容块(CSS、prompt 模板、表格、fixture 内容)。clean.md 大段内容以真实可用文本给出,非"类似上文"。✓

**Type/命名一致性:** `.raw-transcript` / `.asr-uncertain` / `⟨?X⟩` / `--meta` / `clean.md` 在 Task 2/5/6 间引用一致;阶段编号 CLEAN=3、PUBLISH=8 在 Task 3 内自洽。✓
