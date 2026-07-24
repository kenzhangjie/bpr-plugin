# 英文 PREP 源清洗(专名纠错 + 说话人归属)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 BPR 英文双语路补上源清洗——在 PREP 阶段用 YouTube description 当 ground truth 做专名纠错 + 说话人归属 + 拆合并 `>>`,替掉渲染前手写 regex,并跨期沉淀。

**Architecture:** 沿用 BPR「agent 想、脚本拼」的分工。LLM 部分(读 description 定 brief、逐窗纠错+归属)由主 agent 按 `references/prep-and-modes.md` 的新章节派子代理完成;确定性部分(切窗、词覆盖硬闸、correct_table 硬映射、glossary 回写、产出 turn-list JSON)收进一个可单测的纯脚本 `scripts/prep/clean_en.py`。不新开流水线阶段、不改 TRANSLATE 四步、不改中文 CLEAN。

**Tech Stack:** Python 3.9(`from __future__ import annotations` 以支持 `list[str]` 注解)、pytest 8.4、标准库 `json/re/html/collections`。无第三方依赖。

## Global Constraints

- 源仍是 YouTube 字幕,**不引入火山 ASR**(见 memory `bpr-english-no-volc-asr`)。
- **英文逐字**:除专名/明显拼写外,英文原词不改写、不删句(含口语水词)。词覆盖硬闸 **≥98%**。
- **不做书面化**(交 TRANSLATE.Polish);**不碰 TRANSLATE 四步、不碰中文 CLEAN**。
- 拿不准的词标 `⟨?候选⟩`,**绝不硬编**(confidently wrong 比留错更坏)。
- `~/.config/volc/glossary.txt` 中英**共用**,格式 `专名|权重`(读时忽略权重)。
- `~/.config/volc/correct_table.json` 升**双语**,只放无歧义硬映射。
- Python 3.9 兼容:禁用运行时 `X | Y` 类型;文件头写 `from __future__ import annotations`。
- 提交信息结尾带:`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。当前在 `main`,首个 commit 前先开分支 `feat/english-prep-correction`。

---

### Task 0: 开分支

- [ ] **Step 1: 建分支**

```bash
cd /Users/ken/dev/bpr-plugin
git checkout -b feat/english-prep-correction
git status
```
Expected: `On branch feat/english-prep-correction`,工作区干净(spec 已在 `docs/superpowers/specs/` 提交或未跟踪均可)。

---

### Task 1: `clean_en.py` — 解析 `>>` 块 + 切窗

**Files:**
- Create: `skills/bpr/scripts/prep/clean_en.py`
- Test: `skills/bpr/tests/test_clean_en.py`

**Interfaces:**
- Produces: `parse_blocks(raw: str) -> list[str]`(html 反转义、按 `>>` 切、去空白、丢空块);`split_windows(blocks: list, size: int = 25) -> list[list]`

- [ ] **Step 1: 写失败测试**

Create `skills/bpr/tests/test_clean_en.py`:
```python
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "prep"))
import clean_en as ce


def test_parse_blocks_splits_on_marker_and_unescapes():
    raw = "90% use Codex. &gt;&gt; Yeah. &gt;&gt;   That's true."
    assert ce.parse_blocks(raw) == ["90% use Codex.", "Yeah.", "That's true."]


def test_parse_blocks_drops_empty():
    assert ce.parse_blocks(">> >>  >> hi") == ["hi"]


def test_split_windows_chunks_by_size():
    blocks = [str(i) for i in range(53)]
    w = ce.split_windows(blocks, size=25)
    assert [len(x) for x in w] == [25, 25, 3]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/ken/dev/bpr-plugin/skills/bpr && python3 -m pytest tests/test_clean_en.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'clean_en'`.

- [ ] **Step 3: 写最小实现**

Create `skills/bpr/scripts/prep/clean_en.py`:
```python
#!/usr/bin/env python3
"""英文 PREP 源清洗 —— 确定性部分(agent 派子代理做纠错/归属,本脚本做拼装与闸门)。

见 references/prep-and-modes.md「英文子模式源清洗」与
docs/superpowers/specs/2026-07-24-bpr-english-prep-correction-design.md。
"""
from __future__ import annotations
import html, re


def parse_blocks(raw: str) -> list[str]:
    """把扁平字幕流按 >> 切成块(html 反转义、去空白、丢空块)。"""
    text = html.unescape(raw)
    parts = re.split(r">>\s*", text)
    return [p.strip() for p in parts if p.strip()]


def split_windows(blocks: list, size: int = 25) -> list[list]:
    """按固定大小切窗,供逐窗派子代理。"""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/ken/dev/bpr-plugin/skills/bpr && python3 -m pytest tests/test_clean_en.py -q`
Expected: PASS(3 passed)。

- [ ] **Step 5: 提交**

```bash
cd /Users/ken/dev/bpr-plugin
git add skills/bpr/scripts/prep/clean_en.py skills/bpr/tests/test_clean_en.py
git commit -m "feat(bpr): clean_en parse_blocks + split_windows

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `apply_correct_table` — 双语无歧义硬映射

**Files:**
- Modify: `skills/bpr/scripts/prep/clean_en.py`
- Test: `skills/bpr/tests/test_clean_en.py`

**Interfaces:**
- Produces: `load_mappings(path: str) -> dict`(读 correct_table.json 的 `mappings`);`apply_correct_table(text: str, mappings: dict) -> str`(**长键优先**替换,避免短键先命中)

- [ ] **Step 1: 写失败测试**(append 到 test 文件)

```python
def test_apply_correct_table_longest_key_first():
    m = {"Hockey Stick": "X", "Hockey Sticky Gross": "Hockey Stick Growth"}
    assert ce.apply_correct_table("we saw Hockey Sticky Gross here",
                                  m) == "we saw Hockey Stick Growth here"


def test_apply_correct_table_bilingual():
    m = {"Opening Eye": "OpenAI", "克洛蔻": "Claude"}
    assert ce.apply_correct_table("克洛蔻 vs Opening Eye", m) == "Claude vs OpenAI"


def test_apply_correct_table_noop_when_no_match():
    assert ce.apply_correct_table("nothing here", {"X": "Y"}) == "nothing here"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: FAIL — `AttributeError: module 'clean_en' has no attribute 'apply_correct_table'`.

- [ ] **Step 3: 写实现**(append 到 clean_en.py;顶部 import 补 `json`)

```python
import json


def load_mappings(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def apply_correct_table(text: str, mappings: dict) -> str:
    """套用无歧义硬映射。长键优先,避免短键抢先命中长专名。"""
    for key in sorted(mappings, key=len, reverse=True):
        text = text.replace(key, mappings[key])
    return text
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: PASS(6 passed)。

- [ ] **Step 5: 提交**

```bash
git add skills/bpr/scripts/prep/clean_en.py skills/bpr/tests/test_clean_en.py
git commit -m "feat(bpr): clean_en load_mappings + apply_correct_table (longest-key-first)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `word_coverage` — 逐字保真硬闸

**Files:**
- Modify: `skills/bpr/scripts/prep/clean_en.py`
- Test: `skills/bpr/tests/test_clean_en.py`

**Interfaces:**
- Produces: `norm_words(s: str) -> list[str]`(小写、仅留 a-z0-9 + 空格);`word_coverage(src: str, out: str) -> float`(源词多重集被输出覆盖的比例,`collections.Counter` 取交集)

- [ ] **Step 1: 写失败测试**

```python
def test_word_coverage_full():
    assert ce.word_coverage("OpenAI makes Codex", "OpenAI makes Codex") == 1.0


def test_word_coverage_detects_drop():
    # 输出丢了一整句 → 覆盖明显 < 1
    cov = ce.word_coverage("a b c d e f g h i j", "a b c d e")
    assert cov == 0.5


def test_word_coverage_ignores_case_and_punct():
    assert ce.word_coverage("Hello, world!", "hello world") == 1.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: FAIL — `AttributeError: ... 'word_coverage'`.

- [ ] **Step 3: 写实现**(append;顶部 import 补 `from collections import Counter`)

```python
from collections import Counter


def norm_words(s: str) -> list[str]:
    s = html.unescape(s).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return s.split()


def word_coverage(src: str, out: str) -> float:
    """源词多重集被输出覆盖的比例。丢句 → 比例下降。1.0 = 全覆盖。"""
    sc, oc = Counter(norm_words(src)), Counter(norm_words(out))
    total = sum(sc.values())
    if total == 0:
        return 1.0
    covered = sum(min(n, oc.get(w, 0)) for w, n in sc.items())
    return covered / total
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: PASS(9 passed)。

- [ ] **Step 5: 提交**

```bash
git add skills/bpr/scripts/prep/clean_en.py skills/bpr/tests/test_clean_en.py
git commit -m "feat(bpr): clean_en word_coverage gate (multiset overlap)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `append_glossary` — 专名飞轮(去重回写)

**Files:**
- Modify: `skills/bpr/scripts/prep/clean_en.py`
- Test: `skills/bpr/tests/test_clean_en.py`

**Interfaces:**
- Produces: `append_glossary(names: list, path: str, default_weight: int = 5) -> int`(读现有(剥 `|权重`)→ 大小写不敏感去重 → append 新 `name|weight` → 返回新增条数)

- [ ] **Step 1: 写失败测试**(用 tmp_path,不碰真 glossary)

```python
def test_append_glossary_dedups_and_appends(tmp_path):
    g = tmp_path / "glossary.txt"
    g.write_text("OpenAI|6\nClaude|7\n", encoding="utf-8")
    added = ce.append_glossary(["openai", "Codex", "Anthropic"], str(g))
    assert added == 2  # openai 已存在(大小写不敏感),Codex/Anthropic 新增
    lines = g.read_text(encoding="utf-8").splitlines()
    assert "OpenAI|6" in lines and "Claude|7" in lines
    assert "Codex|5" in lines and "Anthropic|5" in lines


def test_append_glossary_creates_file(tmp_path):
    g = tmp_path / "new.txt"
    added = ce.append_glossary(["Vercel"], str(g))
    assert added == 1
    assert g.read_text(encoding="utf-8").strip() == "Vercel|5"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: FAIL — `AttributeError: ... 'append_glossary'`.

- [ ] **Step 3: 写实现**(append;顶部 import 补 `import os`)

```python
import os


def append_glossary(names: list, path: str, default_weight: int = 5) -> int:
    """新专名去重后 append 进共用 glossary.txt(格式 name|weight)。返回新增条数。"""
    existing = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            term = line.strip().split("|", 1)[0]
            if term:
                existing[term.lower()] = True
    added = []
    for n in names:
        n = n.strip()
        if n and n.lower() not in existing:
            existing[n.lower()] = True
            added.append(n)
    if added:
        with open(path, "a", encoding="utf-8") as f:
            for n in added:
                f.write(f"{n}|{default_weight}\n")
    return len(added)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: PASS(11 passed)。

- [ ] **Step 5: 提交**

```bash
git add skills/bpr/scripts/prep/clean_en.py skills/bpr/tests/test_clean_en.py
git commit -m "feat(bpr): clean_en append_glossary (dedup, shared glossary.txt)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `finalize` + CLI — 拼装 + 闸门 + 后处理 + 产出契约 JSON

**Files:**
- Modify: `skills/bpr/scripts/prep/clean_en.py`
- Test: `skills/bpr/tests/test_clean_en.py`

**Interfaces:**
- Consumes: `parse_blocks`、`apply_correct_table`、`load_mappings`、`word_coverage`、`append_glossary`
- Produces: `finalize(turns: list, raw: str, mappings: dict, gate: float = 0.98) -> dict`
  - 输入 `turns` = 各窗子代理拼起来的 `[{"speaker","sents":[...]}]`
  - 对每句套 `apply_correct_table`;整体算 `word_coverage(raw, 拼接的所有 sents)`
  - 返回 `{"turns":[...], "coverage": float, "ok": bool}`(`ok = coverage >= gate`)
  - CLI:`--turns a.json --raw raw.txt --correct-table PATH --glossary PATH --names names.json --out out.json`,把 §5 契约写 `--out`,并调 `append_glossary`;`ok=False` 时非零退出并打印警告

- [ ] **Step 1: 写失败测试**

```python
def test_finalize_applies_table_and_reports_coverage():
    turns = [{"speaker": "Lenny", "sents": ["Opening Eye ships Codeex."]},
             {"speaker": "Andrew", "sents": ["Yeah, Codeex is great."]}]
    raw = "Opening Eye ships Codex. >> Yeah, Codex is great."
    m = {"Opening Eye": "OpenAI", "Codeex": "Codex"}
    r = ce.finalize(turns, raw, m)
    assert r["turns"][0]["sents"][0] == "OpenAI ships Codex."
    assert r["turns"][1]["sents"][0] == "Yeah, Codex is great."
    assert r["ok"] is True and r["coverage"] >= 0.98


def test_finalize_flags_dropped_content():
    turns = [{"speaker": "Lenny", "sents": ["only one sentence kept"]}]
    raw = ("only one sentence kept >> a whole second turn that the agent "
           "dropped entirely with many distinct words here")
    r = ce.finalize(turns, raw, {})
    assert r["ok"] is False and r["coverage"] < 0.98
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: FAIL — `AttributeError: ... 'finalize'`.

- [ ] **Step 3: 写实现**(append;顶部 import 补 `import argparse, sys`)

```python
def finalize(turns: list, raw: str, mappings: dict, gate: float = 0.98) -> dict:
    out_turns = []
    for t in turns:
        out_turns.append({
            "speaker": t["speaker"],
            "sents": [apply_correct_table(s, mappings) for s in t["sents"]],
        })
    joined = " ".join(s for t in out_turns for s in t["sents"])
    cov = word_coverage(raw, joined)
    return {"turns": out_turns, "coverage": cov, "ok": cov >= gate}


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True, help="拼好的 turns JSON")
    ap.add_argument("--raw", required=True, help="原始逐字稿(算覆盖用)")
    ap.add_argument("--correct-table",
                    default=os.path.expanduser("~/.config/volc/correct_table.json"))
    ap.add_argument("--glossary",
                    default=os.path.expanduser("~/.config/volc/glossary.txt"))
    ap.add_argument("--names", help="本期专名清单 JSON(list),用于回写 glossary")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    turns = json.load(open(a.turns, encoding="utf-8"))
    raw = open(a.raw, encoding="utf-8").read()
    mappings = load_mappings(a.correct_table) if os.path.exists(a.correct_table) else {}
    res = finalize(turns, raw, mappings)
    json.dump(res["turns"], open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if a.names and os.path.exists(a.names):
        added = append_glossary(json.load(open(a.names, encoding="utf-8")), a.glossary)
        print(f"glossary += {added}")
    print(f"coverage {res['coverage']:.3f}  ok={res['ok']}")
    if not res["ok"]:
        print("WARN: 词覆盖 < 0.98,疑似丢句,回 Step 2 重派该窗", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_clean_en.py -q`
Expected: PASS(13 passed)。

- [ ] **Step 5: 提交**

```bash
git add skills/bpr/scripts/prep/clean_en.py skills/bpr/tests/test_clean_en.py
git commit -m "feat(bpr): clean_en finalize + CLI (coverage gate, table, glossary writeback)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: correct_table.json 升双语

**Files:**
- Modify: `~/.config/volc/correct_table.json`(用户配置,非仓库;`clean_en.py` 与 `volc_asr.py` 共读)

**Interfaces:**
- Consumes: Task 2 的 `load_mappings` / `apply_correct_table`(结构不变,仍是 `{"mappings":{...}}`)

- [ ] **Step 1: 备份**

```bash
cp ~/.config/volc/correct_table.json ~/.config/volc/correct_table.json.bak
```

- [ ] **Step 2: 更新 `_note` 并加英文段**

把 `_note` 改为(说明双路共读 + 英文由 clean_en 套用):
```
"杠杆1B 客户端硬映射表(中英双语)。只放无歧义专名硬映射;有歧义的交 LLM 上下文判断,别放这里。中文路由 volc_asr.py/llm_correct.py 套用,英文路由 clean_en.py 套用。踩坑即加,下次自动生效。"
```
在 `mappings` 里(中文条目之后)追加英文无歧义硬映射(仅放**复现**且无歧义的;只错一次的交 LLM,不进表):
```json
    "Opening Eye": "OpenAI",
    "opening eye": "OpenAI",
    "Codeex": "Codex",
    "Ambercino": "Ambrosino",
    "Ambersino": "Ambrosino"
```
> ⚠️ 只加**无歧义**项;像 "chatd/cloud" 这类依赖上下文(cloud design vs cloud storage)的**不进表**,交 Step 2 的 LLM 纠错(见 prep-and-modes.md)。

- [ ] **Step 3: 验证仍是合法 JSON 且能加载**

Run:
```bash
python3 -c "import json,os; m=json.load(open(os.path.expanduser('~/.config/volc/correct_table.json')))['mappings']; print(len(m),'mappings'); assert m['Codeex']=='Codex' and m['潘乐']=='潘乱'"
```
Expected: 打印条数,无 AssertionError。

- [ ] **Step 4: 用真实表跑一次 finalize 冒烟**

Run:
```bash
cd /Users/ken/dev/bpr-plugin/skills/bpr && python3 -c "
import sys; sys.path.insert(0,'scripts/prep'); import clean_en as ce, os
m=ce.load_mappings(os.path.expanduser('~/.config/volc/correct_table.json'))
print(ce.apply_correct_table('Opening Eye ships Codeex by Ambercino', m))"
```
Expected: `OpenAI ships Codex by Ambrosino`。
(无独立仓库 commit;此为用户配置文件。)

---

### Task 7: `prep-and-modes.md` — 英文子模式源清洗全节(agent 行为规范)

**Files:**
- Modify: `skills/bpr/references/prep-and-modes.md`

**Interfaces:**
- 消费 Task 1–5 的脚本(切窗、finalize CLI);产出主 agent 逐窗派子代理的 prompt 模板与降级规则

- [ ] **Step 1: 追加新章节**(在「auto-subs 预处理」之后)

内容须含(照抄 spec §4–§5 落成可执行步骤):
1. **触发**:CJK<60% 且 transcript 类;essay 跳过。
2. **Step 1 Analyze-lite**:主 agent 读 `metadata.json` 的 description+title + `glossary.txt`(忽略 `|` 权重)→ 产出 brief(专名表正确拼写 / host=uploader·guest=description 里 "my guest is X" / 存疑清单)。
3. **Step 2 逐窗子代理**(`split_windows(parse_blocks(raw))`):贴出完整派发 prompt 模板(专名纠错 + 说话人归属 + 拆合并块;英文逐字;`⟨?⟩` 存疑),要求返回 `[{speaker,sents:[...]}]`。
4. **Step 3 拼装+闸门**:主 agent 把各窗 JSON 拼起来 → 跑 `clean_en.py finalize`(词覆盖<0.98 打回重派该窗)。
5. **Step 4 后处理+飞轮**:finalize 已套 correct_table + 回写 glossary(传 `--names`)。
6. **降级**:无 description → 启发式(提问者=host);说话人分不出 → essay 模式(不写 speaker/turn),不瞎猜(引 L1)。
7. **产出契约**:§5 的 turn-list JSON,交 STRUCTURE。

- [ ] **Step 2: 校验引用一致**

Run: `grep -n "clean_en\|finalize\|split_windows\|0.98\|essay" skills/bpr/references/prep-and-modes.md`
Expected: 命中上述关键词,函数名与 Task 1–5 完全一致(`parse_blocks`/`split_windows`/`finalize`)。

- [ ] **Step 3: 提交**

```bash
git add skills/bpr/references/prep-and-modes.md
git commit -m "docs(bpr): PREP English sub-mode source cleaning (correction + speaker attribution)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 串接 SKILL.md / ingest.md / verify.md

**Files:**
- Modify: `skills/bpr/SKILL.md`(流水线表 PREP 行 + 英文流程串上源清洗;不新增阶段)
- Modify: `skills/bpr/references/ingest.md`(YouTube 段:产出交 PREP 英文子模式,description 作 ground truth)
- Modify: `skills/bpr/references/verify.md`(覆盖闸加英文项)

- [ ] **Step 1: SKILL.md**

PREP 行(阶段 2)描述补:「英文子模式:用 description 做专名纠错 + 说话人归属 + 拆合并 `>>`(见 prep-and-modes.md);中文走 CLEAN」。流水线图**不变**(仍 8 阶段)。

- [ ] **Step 2: ingest.md**

YouTube「Step D · 喂给 BPR 正常流程」补一句:transcript + `metadata.json`(含 `description`)交 **PREP 英文子模式**做源清洗;`description` 是纠专名/认 host-guest 的 ground truth(= 小宇宙 shownote 角色)。

- [ ] **Step 3: verify.md**

「覆盖率硬闸」加两条:
- 英文 PREP 源清洗跑过:`clean_en.py finalize` 词覆盖 **≥0.98**(<0.98 = 丢句,回 PREP 重派该窗)。
- 英文纠错冒烟:跑 `tests/fixtures/asr-clean-en-regression.md`,已知错专名全修对;存疑走 `⟨?⟩` 不硬编。

- [ ] **Step 4: 校验**

Run: `grep -n "英文子模式\|PREP 英文\|0.98\|asr-clean-en-regression" skills/bpr/SKILL.md skills/bpr/references/ingest.md skills/bpr/references/verify.md`
Expected: 三个文件各命中相应关键词。

- [ ] **Step 5: 提交**

```bash
git add skills/bpr/SKILL.md skills/bpr/references/ingest.md skills/bpr/references/verify.md
git commit -m "docs(bpr): wire English PREP source cleaning into SKILL/ingest/verify

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 英文纠错回归 fixture(冒烟)

**Files:**
- Create: `skills/bpr/tests/fixtures/asr-clean-en-regression.md`

- [ ] **Step 1: 写 fixture**(仿中文 `asr-clean-regression.md`)

```markdown
# 英文 PREP 源清洗回归样本(冒烟用)

输入(YouTube 自动字幕,含已知专名错 + 一个合并 >> 块):
- "90% of people at Opening Eye use Codeex."
- "today my guest is Andrew Ambercino. >> Thank you for having me. what does the team look like? >> Everybody is very agentic."

期望源清洗输出:
- 专名修正:Opening Eye → OpenAI;Codeex → Codex;Ambercino → Ambrosino
- 说话人归属 + 拆合并块:第二条按语义拆成
  - Lenny: "today my guest is Andrew Ambrosino." / "what does the team look like?"
  - Andrew: "Thank you for having me." / "Everybody is very agentic."
- 逐字:除专名外英文不改写、不删句(词覆盖 ≥0.98)
- 零幻觉:不可判词标 ⟨?候选⟩,不硬编(见 prep-and-modes.md 降级 + spec §4)
```

- [ ] **Step 2: 断言 fixture 里的无歧义错词已进 correct_table(确定性可查)**

Run:
```bash
python3 -c "import json,os; m=json.load(open(os.path.expanduser('~/.config/volc/correct_table.json')))['mappings']; assert all(k in m for k in ['Opening Eye','Codeex','Ambercino']); print('ok')"
```
Expected: `ok`(证明冒烟里的无歧义项确定性可修;说话人拆分交端到端 Task 10 人工核)。

- [ ] **Step 3: 提交**

```bash
git add skills/bpr/tests/fixtures/asr-clean-en-regression.md
git commit -m "test(bpr): English ASR correction + >> split regression fixture

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 端到端验收(agent 手动跑,非单测)

**Files:** 无(验收记录写进 PR 描述)

- [ ] **Step 1: 全量单测**

Run: `cd /Users/ken/dev/bpr-plugin/skills/bpr && python3 -m pytest tests/ -q`
Expected: 全绿(13 passed)。

- [ ] **Step 2: 重跑 Lenny × Andrew 那期(P3KDebPTUrw),走新 PREP 英文子模式**

按 `prep-and-modes.md` 新章节:拉字幕+metadata → Analyze-lite → 逐窗子代理纠错+归属 → `clean_en.py finalize`。**验收判据**:
- 全程**不手写任何 regex**;
- 专名全对(OpenAI/Codex/ChatGPT/Ambrosino…);
- 合并 `>>` 被自动拆成正确 speaker;
- `finalize` 覆盖 ≥0.98;
- 新专名已写进 `glossary.txt`。

- [ ] **Step 3: 降级用例**

构造一个 `description` 为空的 metadata,确认退化到启发式/essay 模式而非报错/幻觉。

- [ ] **Step 4: 收尾**

按 `superpowers:finishing-a-development-branch` 决定 merge / PR。PR 描述贴 Step 2 验收结果(哪些实测、哪些未验)。

---

## Self-Review

- **Spec 覆盖**:§2 决策(不进 TRANSLATE.Review / 不新阶段)→ Task 7/8 文档落实;§4 Step1-5 → Task 1/5(切窗)+ Analyze-lite/子代理(Task 7 prose)+ 覆盖闸(Task 3/5)+ correct_table(Task 2/6)+ 飞轮(Task 4);§5 契约 → Task 5 finalize 输出;§6 边界 → Task 7/8 文档;§7 改动清单逐条对应 Task 1–9;§8 验证 → Task 9/10;§9 降级 → Task 7 Step1.6 + Task 10 Step3。无遗漏。
- **Placeholder 扫描**:无 TBD/TODO;所有 code step 附完整代码与期望输出。
- **类型一致**:`parse_blocks/split_windows/apply_correct_table/load_mappings/word_coverage/norm_words/append_glossary/finalize/_main` 命名跨 Task 一致;`finalize` 输入/输出结构与 §5 契约、Task 5 测试一致。
- **注意**:Task 6 改的是用户配置(`~/.config/volc/`),不进仓库 commit;`glossary.txt` 由飞轮自动写,不手 commit。
