# BPR v1.5.0 架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 bpr 插件做一次 behavior-preserving 重构:7 阶段主线、references 按阶段拆、scripts 分组、固定 source-of-truth,发布 v1.5.0。

**Architecture:** 单 `bpr` skill 内部重整(方案 A)。以**手改过的 `cache/1.4.1` 为内容基线**(repo 1.4.3 是退化版),先对账合并再重构。核心步骤是 LLM 驱动,不拆子 skill、不抽 CLI。

**Tech Stack:** Markdown(SKILL.md + references)、Python/Bash 脚本、Claude Code 插件机制、git。

**工作目录:** `~/dev/bpr-plugin`(分支 `refactor/v1.5.0-architecture`)。**绝不改 `~/.claude/plugins/cache/`**。

## Global Constraints

- **纯重构:BPR 生成的 HTML/海报/流程能力不变**,唯一有意行为改动 = 硬约束 2 的"中文去口语词"。
- **硬约束 1**:英文正文翻译走完整四步 **Analyze → Translate → Review → Polish**,一步不省。
- **硬约束 2**:英文行逐字逐句保留(含口语词)、句级全覆盖不压缩(覆盖率闸 <~85% 回补);中文行 Polish 步删无意义口语水词(呃/嗯/you know/I mean/the thing is),但保留有语义的迟疑/强调。推翻旧"口语感保留 uh/um→呃/嗯"。TL;DR·速读 与 Contrarian Takes 两块不受逐字约束。
- **基线**:内容以 `~/.claude/plugins/cache/bpr-marketplace/bpr/1.4.1/skills/bpr/` 为准(功能最全),不以 repo 1.4.3。
- **脚本路径**:重构后 SKILL.md 与所有 reference 引用的脚本路径必须指向新的 `scripts/{fetch,enrich,publish,poster}/` 分组,无残留旧扁平路径。

---

## File Structure(重构后 `skills/bpr/`)

```
SKILL.md                     # 7 阶段主线编排(瘦身)
references/
  ingest.md                  # URL 处理 / 发布日期提取 / 抓取流程
  prep-and-modes.md          # 断句/说话人/VTT重建 + 中文模式(CJK≥60%)规范
  translate.md               # 四步法 + 逐字全覆盖 + 中文去口语词(两条硬约束)
  render.md                  # 三版型 + inline link + 图自托管 + design-system(并入)
  verify.md                  # checklist + 覆盖率硬闸
  publish.md                 # index 重建 + 部署 + Transcript/ 产物约定
  poster.md                  # 海报流程
  lessons-learned.md         # "为什么"附录(逐条注明已固化到哪个阶段文档)
scripts/
  fetch/   {fetch_youtube.sh, fetch_xiaoyuzhou.sh, fetch_bilibili.sh, extract_metadata.py, clean_vtt.py}
  enrich/  {add_timestamps.py, extract_images.py}
  publish/ {build_index.py}
  poster/  {crop_and_share.py}
templates/                   # base.html, poster-template.html(内容不动)
```
（删除:`references/rules.md`、`references/design-system.md`、`references/checklist.md`、`references/poster-rules.md` 的内容并入上述新文件后删除原文件;`references/translation-prompt.md` → 更名/并入 `translate.md`。）

---

### Task 1: 对账 — 把 cache/1.4.1 改进合并进 clone 作基线

**Files:**
- Modify: `~/dev/bpr-plugin/skills/bpr/**`(从 cache/1.4.1 覆盖入超集文件)

**Interfaces:**
- Produces: 一个功能=cache/1.4.1 的 clone 基线(含四步法、extract_images.py、覆盖闸、design-system.md、add_timestamps.py),供后续重构在其上进行。

- [ ] **Step 1: 全量 diff,列出 cache/1.4.1 独有或更新的文件**

Run:
```bash
CACHE="$HOME/.claude/plugins/cache/bpr-marketplace/bpr/1.4.1/skills/bpr"
REPO="$HOME/dev/bpr-plugin/skills/bpr"
diff -rq "$CACHE" "$REPO"
```
Expected: 列出差异 —— 至少含 `Only in $CACHE/scripts: extract_images.py`、`Only in $CACHE/references: design-system.md`、SKILL.md/translation-prompt.md/rules.md/lessons-learned.md/checklist.md/base.html differ。记录清单。

- [ ] **Step 2: 用 cache/1.4.1 覆盖 clone 的 skill 内容(建立基线)**

Run:
```bash
CACHE="$HOME/.claude/plugins/cache/bpr-marketplace/bpr/1.4.1/skills/bpr"
REPO="$HOME/dev/bpr-plugin/skills/bpr"
rsync -a --delete --exclude='.DS_Store' "$CACHE"/ "$REPO"/
```
说明:`--delete` 让 clone 的 skill 目录严格等于 cache/1.4.1(cache 是功能超集)。仅同步 `skills/bpr/`,不碰 repo 的 `.claude-plugin/`、`CHANGELOG.md`、`docs/`。

- [ ] **Step 3: 验证四步法与关键脚本已在基线**

Run:
```bash
cd "$HOME/dev/bpr-plugin/skills/bpr"
grep -c "Analyze" references/translation-prompt.md
test -f scripts/extract_images.py && echo "extract_images OK"
test -f references/design-system.md && echo "design-system OK"
grep -rl "覆盖率" references/ | head
```
Expected: `Analyze` ≥ 1;两个 OK 打印;覆盖率在 references 里有命中。

- [ ] **Step 4: Commit**

```bash
cd "$HOME/dev/bpr-plugin"
git add skills/bpr
git commit -m "refactor(baseline): 以 cache/1.4.1 改进覆盖 repo 作重构基线(四步法/extract_images/覆盖闸)"
```

---

### Task 2: SKILL.md → 7 阶段主线

**Files:**
- Modify: `~/dev/bpr-plugin/skills/bpr/SKILL.md`

**Interfaces:**
- Consumes: Task 1 基线的 SKILL.md。
- Produces: 7 阶段(INGEST/PREP/STRUCTURE/TRANSLATE/RENDER/VERIFY/PUBLISH)+ 海报可选分支;引用指向 Task 3 将建的 per-phase references(先按目标文件名写,Task 3 补齐)。

- [ ] **Step 1: 重写 SKILL.md 的"核心步骤"表为 7 阶段**

把原 11 步表替换为 spec §4.1 的 7 阶段表;删除所有 `🆕`、`2.5/6.2/6.5` 半步编号;TRANSLATE 阶段明确指向 `references/translate.md` 并一句话点出两条硬约束;各阶段"加载哪些 reference"列改指向 per-phase 文件(ingest.md/prep-and-modes.md/translate.md/render.md/verify.md/publish.md/poster.md)。保留 frontmatter 的 `name`/`description` 不变(触发词不变)。

- [ ] **Step 2: 验证无半步/无🆕/7 阶段齐**

Run:
```bash
cd "$HOME/dev/bpr-plugin/skills/bpr"
echo "🆕 count:"; grep -c "🆕" SKILL.md
echo "半步编号:"; grep -cE "\b(2\.5|6\.2|6\.5)\b" SKILL.md
echo "阶段:"; grep -cE "INGEST|PREP|STRUCTURE|TRANSLATE|RENDER|VERIFY|PUBLISH" SKILL.md
```
Expected: 🆕 = 0;半步 = 0;阶段命中 ≥ 7。

- [ ] **Step 3: Commit**

```bash
cd "$HOME/dev/bpr-plugin"
git add skills/bpr/SKILL.md
git commit -m "refactor(skill): SKILL.md 11步+半步 → 7 阶段线性主线,清除 🆕"
```

---

### Task 3: 拆 references(散掉 rules.md)+ 两条硬约束写进 translate.md

**Files:**
- Create: `references/ingest.md` `prep-and-modes.md` `translate.md` `render.md` `verify.md` `publish.md` `poster.md`
- Delete: `references/rules.md` `design-system.md` `checklist.md` `poster-rules.md` `translation-prompt.md`(内容迁移后)
- Modify: `SKILL.md`(引用路径核对)

**Interfaces:**
- Consumes: Task 1 基线的 rules.md(669行)/translation-prompt.md/checklist.md/poster-rules.md/design-system.md。
- Produces: 8 个 per-phase reference(含 lessons-learned.md);SKILL.md 的引用全部可解析。

- [ ] **Step 1: 按阶段迁移内容**

把 `rules.md` 的段落按主题搬到对应新文件:URL处理/发布日期→`ingest.md`;断句+中文模式→`prep-and-modes.md`;双语对照/inline link/版型→`render.md`(并入 `design-system.md` 全文);覆盖率/自检→`verify.md`(并入 `checklist.md`);部署→`publish.md`。`translation-prompt.md` → `translate.md`。`poster-rules.md` → `poster.md`。

- [ ] **Step 2: translate.md 明文化两条硬约束**

在 `translate.md` 写入(逐字,来自 Global Constraints):四步法 Analyze→Translate→Review→Polish;英文逐字全覆盖 + 覆盖率闸;**中文 Polish 去口语词**(列举 呃/嗯/you know/I mean/the thing is)+ 边界(保留有语义迟疑/强调)+ 明确"推翻旧口语保留规则";TL;DR/Contrarian 例外。给一个前面 spec 里的 EN/ZH 对照例子。

- [ ] **Step 3: publish.md 写产物约定**

写入 spec §4.5 的 `Transcript/` 结构(`<stem>.html` / `<stem>-poster.png` / `images/<stem>/` / `index.html`)+ 部署命令(proxy 直连)。

- [ ] **Step 4: 删旧文件 + 核对 SKILL.md 引用**

Run:
```bash
cd "$HOME/dev/bpr-plugin/skills/bpr"
rm references/rules.md references/design-system.md references/checklist.md references/poster-rules.md references/translation-prompt.md
echo "残留旧引用(应为空):"; grep -rnE "rules\.md|design-system\.md|checklist\.md|poster-rules\.md|translation-prompt\.md" SKILL.md references/ | grep -v lessons-learned
echo "四步+去口语词在 translate.md:"; grep -c "Analyze" references/translate.md; grep -c "口语词\|去水词\|口语水词" references/translate.md
```
Expected: 残留旧引用为空;translate.md 含 Analyze ≥1、去口语词 ≥1。

- [ ] **Step 5: Commit**

```bash
cd "$HOME/dev/bpr-plugin"
git add -A skills/bpr/references skills/bpr/SKILL.md
git commit -m "refactor(refs): rules.md 669行 → 按阶段 7 个 reference;两条硬约束写进 translate.md"
```

---

### Task 4: scripts 分组 + 全局路径更新

**Files:**
- Move: `scripts/*.{py,sh}` → `scripts/{fetch,enrich,publish,poster}/`
- Modify: `SKILL.md` + `references/*.md`(所有脚本路径)

**Interfaces:**
- Produces: `scripts/fetch|enrich|publish|poster/` 结构;所有文档引用指向新路径。

- [ ] **Step 1: git mv 脚本到分组**

Run:
```bash
cd "$HOME/dev/bpr-plugin/skills/bpr/scripts"
mkdir -p fetch enrich publish poster
git mv fetch_youtube.sh fetch_xiaoyuzhou.sh fetch_bilibili.sh extract_metadata.py clean_vtt.py fetch/
git mv add_timestamps.py extract_images.py enrich/
git mv build_index.py publish/
git mv crop_and_share.py poster/
```

- [ ] **Step 2: 更新文档里的脚本路径**

在 SKILL.md 与 references/ 里,把 `scripts/<name>` 批量改成 `scripts/<group>/<name>`(逐个确认组别:fetch_* / extract_metadata / clean_vtt → fetch;add_timestamps / extract_images → enrich;build_index → publish;crop_and_share → poster)。

- [ ] **Step 3: 验证无残留旧扁平路径**

Run:
```bash
cd "$HOME/dev/bpr-plugin/skills/bpr"
grep -rnE "scripts/(fetch_youtube|fetch_xiaoyuzhou|fetch_bilibili|extract_metadata|clean_vtt|add_timestamps|extract_images|build_index|crop_and_share)\b" SKILL.md references/ | grep -vE "scripts/(fetch|enrich|publish|poster)/"
```
Expected: 空(所有引用都带 group 前缀)。

- [ ] **Step 4: Commit**

```bash
cd "$HOME/dev/bpr-plugin"
git add -A skills/bpr
git commit -m "refactor(scripts): 按职责分组 fetch/enrich/publish/poster + 全局路径更新"
```

---

### Task 5: 版本发布 v1.5.0 + repoint pin + 清孤儿

**Files:**
- Modify: `.claude-plugin/plugin.json`(version)、`CHANGELOG.md`
- Modify: `~/.claude/plugins/installed_plugins.json`(pin)

**Interfaces:**
- Produces: repo main 上的 v1.5.0;Claude Code 生效版本 = 1.5.0。

- [ ] **Step 1: bump 版本 + CHANGELOG**

`.claude-plugin/plugin.json` 的 `version` 改 `1.5.0`;`CHANGELOG.md` 顶部加 `## v1.5.0 — 2026-07-11` 条目(7 阶段重构 / references 按阶段拆 / scripts 分组 / 四步法+去口语词硬约束 / 对账 cache 漂移)。

- [ ] **Step 2: 合并到 main 并推送**

Run:
```bash
cd "$HOME/dev/bpr-plugin"
git add -A && git commit -m "release: v1.5.0 架构重构"
git checkout main && git merge --no-ff refactor/v1.5.0-architecture -m "merge: v1.5.0 架构重构"
git push origin main
```
（GFW:若 push 失败,`env -u ALL_PROXY -u all_proxy git push` 或走系统 TUN 直连。）

- [ ] **Step 3: 更新 Claude Code 缓存到 1.5.0 并 repoint pin**

用户在 Claude Code 里跑 `/plugin` 刷新 bpr-marketplace,使其拉到 1.5.0;然后改 `installed_plugins.json` 的 `bpr@bpr-marketplace` installPath/version → 1.5.0,删孤儿 `cache/.../1.4.3`(及旧 1.4.1)。

Run(验证生效):
```bash
python3 -c "import json;e=json.load(open('$HOME/.claude/plugins/installed_plugins.json'))['plugins']['bpr@bpr-marketplace'][0];print(e['version'], e['installPath'])"
ls "$HOME/.claude/plugins/cache/bpr-marketplace/bpr/"
```
Expected: version = 1.5.0,installPath 存在;cache 下只剩 1.5.0(孤儿已清)。

---

### Task 6: 端到端验证(behavior-preserving 冒烟)

**Files:** 无(只跑不改)

- [ ] **Step 1: 新会话触发 /bpr,跑三类样本**

在**新 Claude Code 会话**(确保加载 1.5.0)里各跑一次:① 一篇短英文 essay URL;② 一篇中文源(CJK≥60% 走浓缩);③ 一个带字幕的 podcast 片段。

- [ ] **Step 2: 逐项核对**

对英文样本核对:四步法执行(内部 Analyze→Translate→Review→Polish)、英文行逐字全覆盖(覆盖率闸通过)、中文行已去口语词(呃/嗯/you know 不出现在中文)、TL;DR/正文/目录/深色模式与旧版一致。中文样本:TL;DR+Contrarian+章节回顾结构在。podcast:时间戳注入、逐字覆盖。

- [ ] **Step 3: 记录结果**

在 `docs/superpowers/plans/` 追加一行验证结论(通过/问题)。若任一项与旧行为不符(除去口语词这一有意改动),回对应 Task 修正。

---

## Self-Review

**1. Spec coverage:** §4.1→Task2;§4.2→Task3;§4.3→Task4;§4.4→Task1+Task5;§4.5→Task3(publish.md);硬约束1/2→Task3(translate.md)+Task6(验证);基线判断→Task1。全覆盖。

**2. Placeholder scan:** 无 TBD/TODO;每步含具体命令与期望输出。内容迁移类步骤(Task3 Step1)是文档搬运,给了主题→目标文件映射,非占位。

**3. Type/path consistency:** 脚本分组命名(fetch/enrich/publish/poster)在 Task4 各步一致;新 reference 文件名在 File Structure、Task2、Task3 一致;installPath/version 字段名与 installed_plugins.json 实际一致。
