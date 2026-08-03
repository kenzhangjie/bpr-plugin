# BPR 本地 PDF 输入 · 阶段 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/bpr <path.pdf>` 能把文字层 PDF(研报 / 白皮书 / 书籍章节)解析成干净正文 + 元数据,跑完现有流水线出阅读 HTML。

**Architecture:** 新增两个模块放在 `skills/bpr/scripts/fetch/`:`pdf_layout.py` 是零 IO 的纯函数层(行提取、页眉页脚剥离、分栏、段落组装),`extract_pdf.py` 是 CLI 层(文字层探测、元数据策略链、表格剔除、免责声明截断、产物写出)。输出 `metadata.json` 与现有 `extract_metadata.py` 的 7 键同形,所以下游 PREP / STRUCTURE / TRANSLATE / RENDER / VERIFY / PUBLISH 零改动。

**Tech Stack:** Python 3.9.6(`/usr/bin/python3`)、PyMuPDF 1.26.5(`fitz`,已装于 `~/Library/Python/3.9`)、pytest 8.4.2。

**Spec:** `docs/superpowers/specs/2026-08-03-bpr-pdf-input-design.md`

**范围:** 仅阶段 1。阶段 2(`extract_pdf_images.py` 图表抽取)与阶段 3(`ocr_pdf.py` 扫描件 OCR)各自成 plan。本阶段遇到无文字层 PDF 时**明确报错并指向阶段 3**,不静默产出空正文。

## Global Constraints

- **Python 3.9.6**,不能用 3.10+ 语法:**禁止** `X | None` 形式的 union、`match` 语句。所有模块首行写 `from __future__ import annotations`(与 `tests/test_clean_en.py:1` 一致)。
- **不新增第三方依赖。** 阶段 1 只用 `fitz`(已装)与标准库。`ocrmac` 属阶段 3,本阶段不装不引。
- 测试命令一律 `cd skills/bpr && /usr/bin/python3 -m pytest tests/ -q`。
- **fixture PDF 全部用 fitz 在 `tmp_path` 里合成**,禁止把真研报二进制提交进仓库。
- 中文字体在 fitz 里用 `fontname="china-s"`,英文用默认 `helv`。
- 文件名日期硬规则(`references/ingest.md:321`):**绝不静默用今天**。仅有出版年时补 `YYYY-01-01`。
- 元数据 JSON **恒为 7 键**:`date` / `title` / `author` / `publication` / `source_slug` / `canonical` / `source`。不增删键。
- 常量阈值(spec 已定,写成模块级常量,不要散落成魔法数):`HF_BAND = 0.08`、`HF_THRESHOLD = 0.6`、`HF_MIN_PAGES = 4`、`WIDE_RATIO = 0.40`、`MIN_PER_COL = 3`、`MIN_GUTTER = 8.0`、`GAP_FACTOR = 1.3`、`MIN_PAGE_CHARS = 50`、`TEXT_RATIO_HI = 0.8`、`TEXT_RATIO_LO = 0.2`。
- 所有"丢内容"的行为必须在 stdout 报出来(截断了几页、跳过了哪些页、剔了几条页眉)。**静默丢弃是本计划的头号禁忌。**
- worktree:`~/dev/bpr-pdf-input`,分支 `feat/pdf-input`。**不要**在 `~/.claude/plugins/marketplaces/bpr-marketplace`(被托管的 clone)里改动。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `skills/bpr/scripts/fetch/pdf_layout.py`(新建) | 纯函数版面层:行提取、跨页重复页眉页脚、gutter 探测、阅读顺序、断词、段落组装。零 IO,零 CLI |
| `skills/bpr/scripts/fetch/extract_pdf.py`(新建) | CLI 层:参数、访问性探测、text_ratio、元数据策略链、表格剔除、免责声明截断、写产物 |
| `skills/bpr/tests/pdf_fixtures.py`(新建) | 合成 PDF 的 builder,给三个测试文件共用 |
| `skills/bpr/tests/test_pdf_layout.py`(新建) | 版面层单测 |
| `skills/bpr/tests/test_extract_pdf.py`(新建) | CLI 层单测 + 端到端 |
| `skills/bpr/references/ingest.md`(改) | 输入模式判定表加一行;新增本地 PDF 一节;接上 `:37` 那行 |
| `skills/bpr/SKILL.md`(改) | 流水线表第 1 行补脚本;错误处理节补 PDF 条目 |
| `skills/bpr/references/lessons-learned.md`(改) | 记 L5:fitz block 级分栏不可用 |
| `.claude-plugin/marketplace.json` / `.claude-plugin/plugin.json`(改) | 三处版本号 bump |

**为什么拆两个模块而不是 spec 里说的一个:** 版面算法是这里唯一需要密集单测的部分(分栏、页眉页脚、段落边界都是易错逻辑),把它剥成零 IO 的纯函数层后,测试不需要碰文件系统;CLI 层则只测策略链与产物形状。合起来会是一个 400+ 行、测试要反复造临时文件的大文件。

---

### Task 1: `pdf_layout.py` — 行提取与跨页重复页眉页脚

**Files:**
- Create: `skills/bpr/scripts/fetch/pdf_layout.py`
- Create: `skills/bpr/tests/pdf_fixtures.py`
- Create: `skills/bpr/tests/test_pdf_layout.py`

**Interfaces:**
- Consumes: 无(首个任务)
- Produces:
  - `norm_hf(text: str) -> str` — 数字归一化成 `#`,两端去空白
  - `body_lines(page) -> list` — 元素为 5 元组 `(x0, y0, x1, y1, text)`,已剔页眉页脚带,已丢空行
  - `hf_lines(page) -> list` — 页眉页脚带内的行,**已经过 `norm_hf`**,元素为 str
  - `find_repeated_hf(doc) -> set` — 应删的归一化文本集合;`doc.page_count < HF_MIN_PAGES` 时返回 `set()`
  - `pdf_fixtures.build_report_pdf(path, npages=5, two_col=True, header=True, cover=True) -> None`

- [ ] **Step 1: 写 fixture builder**

创建 `skills/bpr/tests/pdf_fixtures.py`:

```python
from __future__ import annotations

import fitz

A4_W, A4_H = 595, 842


def build_report_pdf(path, npages=5, two_col=True, header=True, cover=True,
                     creation_date="D:20260801093000+08'00'",
                     title="Microsoft Word - draft.doc",
                     author="中金公司研究部"):
    """合成一份研报样子的 PDF。

    header=True  → 每页加相同页眉「中金公司研究部」+ 含页码的页脚
    two_col=True → 正文分左右两栏(x=60 / x=320)
    cover=True   → 第 1 页加 28pt 大标题与「2026年7月15日」
    """
    doc = fitz.open()
    for pno in range(npages):
        page = doc.new_page(width=A4_W, height=A4_H)
        if header:
            page.insert_text((60, 40), "中金公司研究部", fontsize=8, fontname="china-s")
            page.insert_text(
                (60, 810),
                f"请务必阅读正文之后的免责声明部分  第 {pno + 1} 页 共 {npages} 页",
                fontsize=8, fontname="china-s")
        if cover and pno == 0:
            page.insert_text((60, 200), "中国AI算力产业深度报告", fontsize=28, fontname="china-s")
            page.insert_text((60, 240), "2026年7月15日", fontsize=11, fontname="china-s")
        page.insert_text((60, 90), f"Heading {pno + 1} spanning the whole width here",
                         fontsize=16)
        for i in range(6):
            page.insert_text((60, 130 + i * 20), f"left p{pno + 1} line{i} text", fontsize=10)
            if two_col:
                page.insert_text((320, 130 + i * 20), f"right p{pno + 1} line{i} text",
                                 fontsize=10)
    doc.set_metadata({"title": title, "author": author, "creationDate": creation_date})
    doc.save(str(path))
    doc.close()
```

- [ ] **Step 2: 写失败的测试**

创建 `skills/bpr/tests/test_pdf_layout.py`:

```python
from __future__ import annotations

import pathlib
import sys

import fitz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pdf_layout as pl
from pdf_fixtures import build_report_pdf


def test_norm_hf_replaces_digits_and_strips():
    assert pl.norm_hf("  第 12 页 共 345 页 ") == "第 # 页 共 # 页"


def test_body_lines_excludes_header_and_footer(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    doc = fitz.open(p)
    texts = [l[4] for l in pl.body_lines(doc[1])]
    doc.close()
    assert not any("中金公司研究部" in t for t in texts)
    assert not any("免责声明" in t for t in texts)
    assert any(t.startswith("left p2") for t in texts)


def test_body_lines_returns_five_tuples_with_bbox(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    doc = fitz.open(p)
    line = pl.body_lines(doc[1])[0]
    doc.close()
    assert len(line) == 5
    x0, y0, x1, y1, text = line
    assert x1 > x0 and y1 > y0 and isinstance(text, str)


def test_find_repeated_hf_catches_header_and_numbered_footer(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    doc = fitz.open(p)
    hf = pl.find_repeated_hf(doc)
    doc.close()
    assert "中金公司研究部" in hf
    assert any("免责声明" in t and "#" in t for t in hf)


def test_find_repeated_hf_skips_short_documents(tmp_path):
    """< HF_MIN_PAGES 页时样本不足,整个机制跳过——两页里出现两次的短语可能是正文。"""
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=2)
    doc = fitz.open(p)
    hf = pl.find_repeated_hf(doc)
    doc.close()
    assert hf == set()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_pdf_layout.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdf_layout'`

- [ ] **Step 4: 写实现**

创建 `skills/bpr/scripts/fetch/pdf_layout.py`:

```python
"""PDF 版面层 · 纯函数,零 IO。

为什么全程在 line 级而不是 block 级:fitz 的 get_text("blocks") 会把同一基线上
的左右栏文字合并进同一个 block,栏在 block 内部就已经糊在一起,任何 block 级的
x 判据都拿不到栏边界(2026-08-03 实测)。见 references/lessons-learned.md L5。
"""
from __future__ import annotations

import re
from collections import Counter

HF_BAND = 0.08          # 页眉页脚带:上下各占页高比例
HF_THRESHOLD = 0.6      # 在 ≥60% 页面重复出现即判为页眉页脚
HF_MIN_PAGES = 4        # 少于这么多页就不做重复检测(样本不足)

NUM_RE = re.compile(r"\d+")


def norm_hf(text):
    """归一化页眉页脚文本:数字全替成 # ,两端去空白。

    页码每页都变,不归一化就永远统计不到重复。
    """
    return NUM_RE.sub("#", text.strip())


def _iter_lines(page):
    """yield (x0, y0, x1, y1, text) —— line 级,text 已拼好且非空。"""
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:        # type 0 = 文本块,1 = 图像块
            continue
        for line in blk["lines"]:
            text = "".join(s["text"] for s in line["spans"]).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            yield (x0, y0, x1, y1, text)


def _bands(page):
    h = page.rect.height
    return h * HF_BAND, h * (1 - HF_BAND)


def body_lines(page):
    """正文行(剔掉页眉页脚带)。返回 [(x0, y0, x1, y1, text)]。"""
    top, bot = _bands(page)
    return [l for l in _iter_lines(page) if not (l[3] <= top or l[1] >= bot)]


def hf_lines(page):
    """页眉页脚带内的行,已 norm_hf。返回 [str]。"""
    top, bot = _bands(page)
    return [norm_hf(l[4]) for l in _iter_lines(page) if l[3] <= top or l[1] >= bot]


def find_repeated_hf(doc):
    """跨页重复出现的页眉页脚文本集合(已归一化)。

    页数 < HF_MIN_PAGES 时返回空集:样本不足,「≥60% 页面重复」会把正文误判成页眉。
    """
    n = doc.page_count
    if n < HF_MIN_PAGES:
        return set()
    counter = Counter()
    for page in doc:
        counter.update(set(hf_lines(page)))     # set:同页出现两次只算一次
    return {t for t, c in counter.items() if c >= n * HF_THRESHOLD}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_pdf_layout.py -q`
Expected: PASS,5 passed

- [ ] **Step 6: 跑全量测试确认没弄坏现有的**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/ -q`
Expected: PASS,26 passed(现有 21 + 新增 5)

- [ ] **Step 7: 提交**

```bash
cd ~/dev/bpr-pdf-input
git add skills/bpr/scripts/fetch/pdf_layout.py skills/bpr/tests/pdf_fixtures.py skills/bpr/tests/test_pdf_layout.py
git commit -- skills/bpr/scripts/fetch/pdf_layout.py skills/bpr/tests/pdf_fixtures.py skills/bpr/tests/test_pdf_layout.py -m "feat(pdf): 版面层行提取与跨页重复页眉页脚剥离"
```

---

### Task 2: `pdf_layout.py` — gutter 探测与阅读顺序

**Files:**
- Modify: `skills/bpr/scripts/fetch/pdf_layout.py`(追加)
- Modify: `skills/bpr/tests/test_pdf_layout.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 `body_lines(page)`、`norm_hf(text)`、`find_repeated_hf(doc)`
- Produces:
  - `find_gutter(page) -> float` 或 `None` — 双栏时返回栏间分界 x,单栏返回 `None`
  - `page_lines(page, drop_set) -> list` — 阅读顺序排好的 5 元组行列表,已剔 `drop_set` 里的页眉页脚

- [ ] **Step 1: 写失败的测试**

追加到 `skills/bpr/tests/test_pdf_layout.py`:

```python
def test_find_gutter_detects_two_columns(tmp_path):
    p = tmp_path / "two.pdf"
    build_report_pdf(p, npages=5, two_col=True)
    doc = fitz.open(p)
    g = pl.find_gutter(doc[1])
    doc.close()
    assert g is not None
    # 左栏文字止于 x≈212,右栏起于 x=320,分界必须落在两者之间
    assert 212 < g < 320


def test_find_gutter_returns_none_for_single_column(tmp_path):
    """单栏文档正文右侧有大片空白,不能把它当成 gutter。"""
    p = tmp_path / "one.pdf"
    build_report_pdf(p, npages=5, two_col=False)
    doc = fitz.open(p)
    g = pl.find_gutter(doc[1])
    doc.close()
    assert g is None


def test_page_lines_two_column_reading_order(tmp_path):
    """双栏页:通栏标题在最前,左栏全部行先于右栏全部行。"""
    p = tmp_path / "two.pdf"
    build_report_pdf(p, npages=5, two_col=True)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    texts = [l[4] for l in pl.page_lines(doc[1], drop)]
    doc.close()

    assert texts[0].startswith("Heading 2")
    lefts = [i for i, t in enumerate(texts) if t.startswith("left")]
    rights = [i for i, t in enumerate(texts) if t.startswith("right")]
    assert len(lefts) == 6 and len(rights) == 6
    assert max(lefts) < min(rights)


def test_page_lines_single_column_keeps_y_order(tmp_path):
    p = tmp_path / "one.pdf"
    build_report_pdf(p, npages=5, two_col=False)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    texts = [l[4] for l in pl.page_lines(doc[1], drop)]
    doc.close()
    assert texts[0].startswith("Heading 2")
    assert [t for t in texts if t.startswith("left")] == [
        f"left p2 line{i} text" for i in range(6)]


def test_page_lines_drops_repeated_hf(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    texts = [l[4] for l in pl.page_lines(doc[1], drop)]
    doc.close()
    assert not any("中金" in t or "免责" in t for t in texts)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_pdf_layout.py -q`
Expected: FAIL — `AttributeError: module 'pdf_layout' has no attribute 'find_gutter'`

- [ ] **Step 3: 写实现**

追加到 `skills/bpr/scripts/fetch/pdf_layout.py`:

```python
WIDE_RATIO = 0.40       # 行宽 > 页宽 40% → 视为通栏,不参与 gutter 聚类
MIN_PER_COL = 3         # gutter 两侧各至少这么多行
MIN_GUTTER = 8.0        # 栏间空隙至少 8pt


def find_gutter(page):
    """双栏时返回栏间分界 x,单栏返回 None。

    做法:滤掉通栏宽行(它们会填平真空隙),剩余行按 x0 排序,遍历切分点找
    「左侧 max(x1) 与右侧 min(x0) 之间的最大间隙」。
    两侧各需 ≥ MIN_PER_COL 行 —— 少了这条,单栏文档右侧的空白会被误判成 gutter。
    """
    width = page.rect.width
    lines = body_lines(page)
    narrow = [l for l in lines if (l[2] - l[0]) <= width * WIDE_RATIO]
    if len(narrow) < MIN_PER_COL * 2:
        return None

    ordered = sorted(narrow, key=lambda l: l[0])
    best = None
    for k in range(MIN_PER_COL, len(ordered) - MIN_PER_COL + 1):
        left_max_x1 = max(l[2] for l in ordered[:k])
        right_min_x0 = min(l[0] for l in ordered[k:])
        gap = right_min_x0 - left_max_x1
        if gap >= MIN_GUTTER and (best is None or gap > best[0]):
            best = (gap, (left_max_x1 + right_min_x0) / 2.0)

    if best is None:
        return None
    gutter = best[1]
    # 必须落在页面中部,否则就是「正文 + 一侧空白」而非双栏
    return gutter if width * 0.25 < gutter < width * 0.75 else None


def page_lines(page, drop_set):
    """该页按阅读顺序排好的行,已剔 drop_set 内的页眉页脚。

    双栏排序规则:以通栏行的 y 把页面切成 band,band 内先左栏(y 序)再右栏(y 序),
    通栏行本身排在其 band 之首。
    """
    lines = [l for l in body_lines(page) if norm_hf(l[4]) not in drop_set]
    gutter = find_gutter(page)
    if gutter is None:
        return sorted(lines, key=lambda l: (round(l[1], 1), l[0]))

    spanning, left, right = [], [], []
    for line in lines:
        if line[0] < gutter - 2 and line[2] > gutter + 2:
            spanning.append(line)
        elif (line[0] + line[2]) / 2.0 < gutter:
            left.append(line)
        else:
            right.append(line)

    spanning.sort(key=lambda l: l[1])
    cuts = [l[1] for l in spanning]
    bounds = [float("-inf")] + cuts + [float("inf")]

    out = []
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        if i > 0:
            out.append(spanning[i - 1])
        out.extend(sorted((l for l in left if lo < l[1] < hi), key=lambda l: l[1]))
        out.extend(sorted((l for l in right if lo < l[1] < hi), key=lambda l: l[1]))
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_pdf_layout.py -q`
Expected: PASS,10 passed

- [ ] **Step 5: 提交**

```bash
cd ~/dev/bpr-pdf-input
git commit -- skills/bpr/scripts/fetch/pdf_layout.py skills/bpr/tests/test_pdf_layout.py -m "feat(pdf): line 级 gutter 探测与双栏阅读顺序"
```

---

### Task 3: `pdf_layout.py` — 断词拼接与段落组装

**Files:**
- Modify: `skills/bpr/scripts/fetch/pdf_layout.py`(追加)
- Modify: `skills/bpr/tests/test_pdf_layout.py`(追加)

**Interfaces:**
- Consumes: Task 2 的 `page_lines(page, drop_set)`
- Produces:
  - `join_lines(prev: str, nxt: str) -> str` — 两行拼接,处理断词与中英空格
  - `lines_to_paragraphs(lines, gap_factor=GAP_FACTOR) -> list` — 5 元组行列表 → 段落字符串列表

- [ ] **Step 1: 写失败的测试**

追加到 `skills/bpr/tests/test_pdf_layout.py`:

```python
def test_join_lines_removes_hyphen_before_lowercase():
    assert pl.join_lines("infra-", "structure spending") == "infrastructure spending"


def test_join_lines_keeps_hyphen_before_uppercase():
    """行尾连字符 + 下行大写,通常是复合专名(如 Sino-US),不能吃掉连字符。"""
    assert pl.join_lines("Sino-", "US trade") == "Sino-US trade"


def test_join_lines_no_space_between_cjk():
    assert pl.join_lines("中国算力", "产业规模") == "中国算力产业规模"


def test_join_lines_space_between_ascii_words():
    assert pl.join_lines("total addressable", "market size") == \
        "total addressable market size"


def test_lines_to_paragraphs_breaks_on_large_vertical_gap():
    # 行距 12,第 3 行前留 40 的大间距 → 应切成两段
    lines = [
        (60, 100, 200, 110, "first para line one"),
        (60, 112, 200, 122, "first para line two"),
        (60, 152, 200, 162, "second para starts"),
    ]
    paras = pl.lines_to_paragraphs(lines)
    assert len(paras) == 2
    assert paras[0] == "first para line one first para line two"
    assert paras[1] == "second para starts"


def test_lines_to_paragraphs_breaks_on_column_switch():
    """y 回跳 = 换栏,必须强制断段,否则左栏末句会和右栏首句黏在一起。"""
    lines = [
        (60, 300, 200, 310, "left column last line"),
        (320, 100, 460, 110, "right column first line"),
    ]
    paras = pl.lines_to_paragraphs(lines)
    assert paras == ["left column last line", "right column first line"]


def test_lines_to_paragraphs_single_line():
    paras = pl.lines_to_paragraphs([(60, 100, 200, 110, "only line")])
    assert paras == ["only line"]


def test_lines_to_paragraphs_empty():
    assert pl.lines_to_paragraphs([]) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_pdf_layout.py -q`
Expected: FAIL — `AttributeError: module 'pdf_layout' has no attribute 'join_lines'`

- [ ] **Step 3: 写实现**

追加到 `skills/bpr/scripts/fetch/pdf_layout.py`:

```python
import statistics

GAP_FACTOR = 1.3        # 行距 > 中位行距 × 此值 → 段落边界

CJK_RE = re.compile(r"[　-〿一-鿿＀-￯]")


def _is_cjk(ch):
    return bool(CJK_RE.match(ch))


def join_lines(prev, nxt):
    """拼接相邻两行。

    - 行尾 '-' 且下行以小写字母开头 → 去连字符直接拼(PDF 换行断词)
    - 行尾 '-' 且下行非小写      → 保留连字符,直接拼不补空格(Sino-US 这类复合专名)
    - 任一侧是 CJK               → 不补空格
    - 其余                       → 补一个空格
    """
    if not prev:
        return nxt
    if not nxt:
        return prev
    if prev.endswith("-"):
        if nxt[:1].islower() and nxt[:1].isascii():
            return prev[:-1] + nxt
        return prev + nxt
    if _is_cjk(prev[-1]) or _is_cjk(nxt[0]):
        return prev + nxt
    return prev + " " + nxt


def lines_to_paragraphs(lines, gap_factor=GAP_FACTOR):
    """5 元组行列表(已按阅读顺序)→ 段落字符串列表。

    段落边界两种:
      1) 相邻行 y 间距 > 中位行距 × gap_factor
      2) y 回跳(delta <= 0)= 换栏或换页,强制断段
    """
    if not lines:
        return []
    if len(lines) == 1:
        return [lines[0][4]]

    deltas = []
    for i in range(len(lines) - 1):
        d = lines[i + 1][1] - lines[i][1]
        if d > 0:
            deltas.append(d)
    median = statistics.median(deltas) if deltas else 0.0
    limit = median * gap_factor if median else float("inf")

    paragraphs = []
    current = lines[0][4]
    for i in range(1, len(lines)):
        delta = lines[i][1] - lines[i - 1][1]
        if delta <= 0 or delta > limit:
            paragraphs.append(current)
            current = lines[i][4]
        else:
            current = join_lines(current, lines[i][4])
    paragraphs.append(current)
    return paragraphs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_pdf_layout.py -q`
Expected: PASS,18 passed

- [ ] **Step 5: 提交**

```bash
cd ~/dev/bpr-pdf-input
git commit -- skills/bpr/scripts/fetch/pdf_layout.py skills/bpr/tests/test_pdf_layout.py -m "feat(pdf): 断词拼接与段落组装"
```

---

### Task 4: `extract_pdf.py` — 访问性探测与 text_ratio

**Files:**
- Create: `skills/bpr/scripts/fetch/extract_pdf.py`
- Create: `skills/bpr/tests/test_extract_pdf.py`

**Interfaces:**
- Consumes: `pdf_layout`(Task 1–3)
- Produces:
  - `is_pdf(path) -> bool` — 读前 5 字节判 `%PDF`
  - `page_has_text(page, min_chars=MIN_PAGE_CHARS) -> bool`
  - `text_ratio(doc) -> float` — 有效文字页数 / 总页数
  - `detect_mode(ratio) -> str` — `"text"` / `"mixed"` / `"scanned"`
  - `probe_access(doc) -> str` — `"ok"` / `"perm_locked"` / `"scanned"`
  - `PdfInputError(Exception)` — 带 `exit_code` 属性的自定义异常

- [ ] **Step 1: 写失败的测试**

创建 `skills/bpr/tests/test_extract_pdf.py`:

```python
from __future__ import annotations

import pathlib
import sys

import fitz
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import extract_pdf as ep
from pdf_fixtures import build_report_pdf


def test_is_pdf_true_for_real_pdf(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=4)
    assert ep.is_pdf(p) is True


def test_is_pdf_false_for_text_file(tmp_path):
    p = tmp_path / "not.pdf"
    p.write_text("just text, despite the extension")
    assert ep.is_pdf(p) is False


def test_text_ratio_is_page_level_not_char_level(tmp_path):
    """1 页长正文 + 4 页空白 → ratio 应为 0.2(页级),而非被长正文稀释。"""
    doc = fitz.open()
    page = doc.new_page()
    for i in range(40):
        page.insert_text((60, 60 + i * 15), f"a fairly long line of body text number {i}",
                         fontsize=10)
    for _ in range(4):
        doc.new_page()
    p = tmp_path / "mixed.pdf"
    doc.save(str(p))
    doc.close()

    d = fitz.open(p)
    ratio = ep.text_ratio(d)
    d.close()
    assert ratio == pytest.approx(0.2)


def test_text_ratio_all_text_pages(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    d = fitz.open(p)
    ratio = ep.text_ratio(d)
    d.close()
    assert ratio == pytest.approx(1.0)


def test_detect_mode_thresholds():
    assert ep.detect_mode(1.0) == "text"
    assert ep.detect_mode(0.8) == "text"
    assert ep.detect_mode(0.5) == "mixed"
    assert ep.detect_mode(0.2) == "scanned"
    assert ep.detect_mode(0.0) == "scanned"


def test_probe_access_ok_for_normal_pdf(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=4)
    d = fitz.open(p)
    assert ep.probe_access(d) == "ok"
    d.close()


def test_probe_access_reports_scanned_for_blank_pages(tmp_path):
    """无文字且无字体 → scanned。

    (perm_locked 的另一侧无法用 fitz 合成——需要「有字体却取不到文字」,
     合成不出来。该分支靠 Task 10 的真研报实测覆盖,此处不假造。)
    """
    doc = fitz.open()
    doc.new_page()          # 纯空白页:无文字、无字体
    p = tmp_path / "blank.pdf"
    doc.save(str(p))
    doc.close()

    d = fitz.open(p)
    assert ep.probe_access(d) == "scanned"
    d.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'extract_pdf'`

- [ ] **Step 3: 写实现**

创建 `skills/bpr/scripts/fetch/extract_pdf.py`:

```python
"""PDF → 干净正文 + 元数据。BPR INGEST 阶段的本地 PDF 入口。

用法:
    extract_pdf.py <path.pdf> --workdir <dir> [--no-truncate] [--tables img|md]

产物(写入 workdir):
    body.txt       干净正文,段落间空行,无页码污染
    pages.jsonl    每页一条 {page, text, source}
    metadata.json  7 键,与 extract_metadata.py 同形
    tables.json    表格 bbox 单一真源,给 extract_pdf_images.py 读

阶段 1 不含 OCR:遇到无文字层的 PDF 会明确报错并指向 ocr_pdf.py(阶段 3)。
"""
from __future__ import annotations

import sys

import fitz

MIN_PAGE_CHARS = 50        # 该页去空白后 ≥ 此字符数 → 算「有效文字页」
TEXT_RATIO_HI = 0.8        # ≥ 此值 → 纯文字层
TEXT_RATIO_LO = 0.2        # ≤ 此值 → 扫描件


class PdfInputError(Exception):
    """输入不可用。exit_code 供 main() 决定退出码。"""

    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


def is_pdf(path):
    """靠 magic 判,不靠扩展名——扩展名会骗人。"""
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def page_has_text(page, min_chars=MIN_PAGE_CHARS):
    return len(page.get_text().strip()) >= min_chars


def text_ratio(doc):
    """有效文字页数 / 总页数。

    刻意用页级而非字符级:要回答的问题是「哪些页需要 OCR」,
    字符比例会被一页长正文稀释掉十页空白图。
    """
    if doc.page_count == 0:
        return 0.0
    return sum(1 for page in doc if page_has_text(page)) / doc.page_count


def detect_mode(ratio):
    if ratio >= TEXT_RATIO_HI:
        return "text"
    if ratio <= TEXT_RATIO_LO:
        return "scanned"
    return "mixed"


def probe_access(doc):
    """区分「扫描件」与「被权限锁住的文字层」。

    研报很爱设禁止复制。两者都取不到文字,但成因不同:
      有字体却取不到文字 → 权限锁(perm_locked)
      既无字体又无文字   → 真扫描件(scanned)
    混报会让人以为是文件质量问题而非权限问题。
    """
    has_text = any(page_has_text(page) for page in doc)
    if has_text:
        return "ok"
    has_fonts = any(page.get_fonts() for page in doc)
    return "perm_locked" if has_fonts else "scanned"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: PASS,7 passed

- [ ] **Step 5: 提交**

```bash
cd ~/dev/bpr-pdf-input
git add skills/bpr/scripts/fetch/extract_pdf.py skills/bpr/tests/test_extract_pdf.py
git commit -- skills/bpr/scripts/fetch/extract_pdf.py skills/bpr/tests/test_extract_pdf.py -m "feat(pdf): 访问性探测与页级 text_ratio"
```

---

### Task 5: `extract_pdf.py` — 元数据策略链

**Files:**
- Modify: `skills/bpr/scripts/fetch/extract_pdf.py`(追加)
- Modify: `skills/bpr/tests/test_extract_pdf.py`(追加)

**Interfaces:**
- Consumes: Task 4 的 `PdfInputError`
- Produces:
  - `parse_pdf_date(raw) -> str` 或 `None` — `D:YYYYMMDD...` → `YYYY-MM-DD`
  - `is_junk_title(text) -> bool`
  - `cover_max_font_text(page) -> str` 或 `None`
  - `find_cover_date(text) -> str` 或 `None` — 支持 `2026年7月15日` / `2026年7月` / `2026-07-15` / `July 2026`
  - `find_org_name(text) -> str` 或 `None`
  - `slugify_org(name) -> str`
  - `build_metadata(doc, pdf_path) -> tuple` — 返回 `(meta_dict, confidence_dict)`,`meta_dict` 恒 7 键

- [ ] **Step 1: 写失败的测试**

追加到 `skills/bpr/tests/test_extract_pdf.py`:

```python
def test_parse_pdf_date_handles_timezone_suffix():
    assert ep.parse_pdf_date("D:20260801093000+08'00'") == "2026-08-01"


def test_parse_pdf_date_returns_none_for_empty():
    assert ep.parse_pdf_date("") is None
    assert ep.parse_pdf_date(None) is None


def test_is_junk_title_rejects_word_export_artifacts():
    assert ep.is_junk_title("Microsoft Word - draft.doc") is True
    assert ep.is_junk_title("untitled") is True
    assert ep.is_junk_title("report.pdf") is True
    assert ep.is_junk_title("中国AI算力产业深度报告") is False


def test_cover_max_font_text_picks_largest_span(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    d = fitz.open(p)
    assert ep.cover_max_font_text(d[0]) == "中国AI算力产业深度报告"
    d.close()


def test_find_cover_date_chinese_full():
    assert ep.find_cover_date("发布日期 2026年7月15日 中金公司") == "2026-07-15"


def test_find_cover_date_chinese_year_month_only():
    """只有年月 → 补 01 日。"""
    assert ep.find_cover_date("2026年7月 行业深度") == "2026-07-01"


def test_find_cover_date_iso():
    assert ep.find_cover_date("published 2026-07-15") == "2026-07-15"


def test_find_cover_date_english_month_year():
    assert ep.find_cover_date("July 2026 Industry Outlook") == "2026-07-01"


def test_find_cover_date_returns_none_when_absent():
    assert ep.find_cover_date("no date at all here") is None


def test_find_org_name_matches_research_institution():
    assert ep.find_org_name("中金公司研究部\n某某分析师") == "中金公司研究部"
    assert ep.find_org_name("Morgan Stanley Research\nequity") == "Morgan Stanley Research"


def test_slugify_org_ascii_and_cjk():
    assert ep.slugify_org("Morgan Stanley Research") == "morgan-stanley-research"
    # CJK 无法音译,退回 pdf 兜底 slug,不产出乱码
    assert ep.slugify_org("中金公司研究部") == "pdf"


def test_build_metadata_cover_date_beats_creation_date(tmp_path):
    """核心断言:封面印的日期必须赢过 PDF CreationDate。

    一份 2026-07-15 发布的研报被重新导出,CreationDate 会变成 2026-08-01。
    用 CreationDate 会让时间线错位,正是 ingest.md:321 要防的事。
    """
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5, creation_date="D:20260801093000+08'00'")
    d = fitz.open(p)
    meta, conf = ep.build_metadata(d, p)
    d.close()
    assert meta["date"] == "2026-07-15"
    assert meta["source"] == "pdf:cover-text"


def test_build_metadata_falls_back_to_creation_date(tmp_path):
    """封面无日期时才用 CreationDate,且 source 要说清楚。"""
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5, cover=False,
                     creation_date="D:20260801093000+08'00'")
    d = fitz.open(p)
    meta, conf = ep.build_metadata(d, p)
    d.close()
    assert meta["date"] == "2026-08-01"
    assert meta["source"] == "pdf:info-creationdate"
    assert conf["date"] == "low"


def test_build_metadata_rejects_junk_info_title(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5, title="Microsoft Word - draft.doc")
    d = fitz.open(p)
    meta, conf = ep.build_metadata(d, p)
    d.close()
    assert meta["title"] == "中国AI算力产业深度报告"


def test_build_metadata_always_has_exactly_seven_keys(tmp_path):
    """键集恒定是下游零改动的前提。"""
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    d = fitz.open(p)
    meta, _ = ep.build_metadata(d, p)
    d.close()
    assert set(meta) == {"date", "title", "author", "publication",
                         "source_slug", "canonical", "source"}


def test_build_metadata_canonical_is_absolute_path(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    d = fitz.open(p)
    meta, _ = ep.build_metadata(d, p)
    d.close()
    assert meta["canonical"] == str(p.resolve())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: FAIL — `AttributeError: module 'extract_pdf' has no attribute 'parse_pdf_date'`

- [ ] **Step 3: 写实现**

追加到 `skills/bpr/scripts/fetch/extract_pdf.py`(文件顶部 import 区加 `import json`、`import pathlib`、`import re`):

```python
PDF_DATE_RE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")

JUNK_TITLE_RE = re.compile(
    r"(microsoft word|^untitled$|\.docx?$|\.pdf$|^\s*$)", re.IGNORECASE)

ORG_TAIL_RE = re.compile(
    r"^.{2,40}?(研究部|研究所|研究院|证券|Research|Capital|Institute)\s*$",
    re.IGNORECASE | re.MULTILINE)

CN_DATE_FULL_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
CN_DATE_YM_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
EN_MONTH_YEAR_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{4})\b", re.IGNORECASE)

EN_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

FALLBACK_SLUG = "pdf"


def parse_pdf_date(raw):
    """PDF /Info 的 D:YYYYMMDDHHmmSS+TZ → YYYY-MM-DD。"""
    match = PDF_DATE_RE.match(raw or "")
    if not match:
        return None
    return "{}-{}-{}".format(*match.groups())


def is_junk_title(text):
    """Word 导出残留 / 文件名当标题 → 一律弃。"""
    return bool(JUNK_TITLE_RE.search((text or "").strip()))


def cover_max_font_text(page):
    """封面上字号最大的那段文字,通常就是报告标题。"""
    best_size, best_text = 0.0, None
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if text and span["size"] > best_size:
                    best_size, best_text = span["size"], text
    return best_text


def find_cover_date(text):
    """从封面文本里找发布日期。仅有年月时补 01 日。"""
    match = CN_DATE_FULL_RE.search(text)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    match = ISO_DATE_RE.search(text)
    if match:
        return "{}-{}-{}".format(*match.groups())
    match = CN_DATE_YM_RE.search(text)
    if match:
        y, m = match.groups()
        return f"{y}-{int(m):02d}-01"
    match = EN_MONTH_YEAR_RE.search(text)
    if match:
        name, year = match.groups()
        return f"{year}-{EN_MONTHS[name.lower()]:02d}-01"
    return None


def find_org_name(text):
    """找发布机构:整行以「研究部/研究所/研究院/证券/Research/Capital/Institute」结尾。"""
    match = ORG_TAIL_RE.search(text or "")
    return match.group(0).strip() if match else None


def slugify_org(name):
    """机构名 → kebab slug。CJK 无法音译,退回兜底 slug,绝不产出乱码或空串。"""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or FALLBACK_SLUG


def build_metadata(doc, pdf_path):
    """返回 (meta, confidence)。meta 恒 7 键,与 extract_metadata.py 同形。

    date 策略链刻意把 CreationDate 排在封面文本之后:CreationDate 记的是
    「这个 PDF 文件何时生成」,重新导出一次就会变成今天。
    """
    info = doc.metadata or {}
    cover = doc[0] if doc.page_count else None
    cover_text = cover.get_text() if cover is not None else ""

    confidence = {}

    info_title = (info.get("title") or "").strip()
    if info_title and not is_junk_title(info_title):
        title, title_src, confidence["title"] = info_title, "pdf:info-title", "high"
    else:
        title = cover_max_font_text(cover) if cover is not None else None
        title_src = "pdf:cover-maxfont" if title else "pdf:none"
        confidence["title"] = "medium" if title else "low"

    org = find_org_name(cover_text) or (info.get("author") or "").strip() or None
    confidence["publication"] = "high" if org else "low"

    date = find_cover_date(cover_text)
    if date:
        date_src, confidence["date"] = "pdf:cover-text", "high"
    else:
        date = parse_pdf_date(info.get("creationDate"))
        date_src = "pdf:info-creationdate" if date else "pdf:none"
        confidence["date"] = "low"

    slug = slugify_org(org)
    confidence["source_slug"] = "medium" if slug != FALLBACK_SLUG else "low"

    meta = {
        "date": date,
        "title": title,
        "author": (info.get("author") or "").strip() or None,
        "publication": org,
        "source_slug": slug,
        "canonical": str(pathlib.Path(pdf_path).resolve()),
        # source 只报最关键的那条策略(date),与 extract_metadata.py 语义一致
        "source": date_src if date else title_src,
    }
    return meta, confidence
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: PASS,23 passed

- [ ] **Step 5: 提交**

```bash
cd ~/dev/bpr-pdf-input
git commit -- skills/bpr/scripts/fetch/extract_pdf.py skills/bpr/tests/test_extract_pdf.py -m "feat(pdf): 元数据策略链,封面日期优先于 CreationDate"
```

---

### Task 6: `extract_pdf.py` — 表格 bbox 单一真源与正文剔除

**Files:**
- Modify: `skills/bpr/scripts/fetch/extract_pdf.py`(追加)
- Modify: `skills/bpr/tests/test_extract_pdf.py`(追加)
- Modify: `skills/bpr/tests/pdf_fixtures.py`(追加 `build_pdf_with_table`)

**Interfaces:**
- Consumes: Task 4 的 `PdfInputError`
- Produces:
  - `collect_tables(doc) -> list` — 元素为 `{"page": int, "index": int, "bbox": list, "markdown": str}`,`bbox` 为 4 元素 list(JSON 友好)
  - `table_anchor(page_no, index) -> str` — 返回 `"[[table:p{page}-{index}]]"`
  - `strip_table_lines(lines, tables_on_page) -> tuple` — 返回 `(kept_lines, anchors_inserted)`,把落在表格 bbox 内的行替换成一个锚记

- [ ] **Step 1: 追加 fixture**

追加到 `skills/bpr/tests/pdf_fixtures.py`:

```python
def build_pdf_with_table(path, npages=4):
    """含一个 3x3 网格表的 PDF,表格在第 1 页正文中部。"""
    doc = fitz.open()
    for pno in range(npages):
        page = doc.new_page(width=A4_W, height=A4_H)
        page.insert_text((60, 120), "Some body text above the table", fontsize=11)
        if pno == 0:
            x0, y0, cw, ch = 60, 200, 150, 30
            for r in range(4):
                page.draw_line(fitz.Point(x0, y0 + r * ch),
                               fitz.Point(x0 + 3 * cw, y0 + r * ch))
            for c in range(4):
                page.draw_line(fitz.Point(x0 + c * cw, y0),
                               fitz.Point(x0 + c * cw, y0 + 3 * ch))
            for r in range(3):
                for c in range(3):
                    page.insert_text((x0 + c * cw + 6, y0 + r * ch + 20),
                                     f"r{r}c{c}", fontsize=9)
        page.insert_text((60, 400), "Body text below the table", fontsize=11)
    doc.save(str(path))
    doc.close()
```

- [ ] **Step 2: 写失败的测试**

追加到 `skills/bpr/tests/test_extract_pdf.py`(顶部 import 改成 `from pdf_fixtures import build_report_pdf, build_pdf_with_table`):

```python
def test_collect_tables_finds_grid_table(tmp_path):
    p = tmp_path / "t.pdf"
    build_pdf_with_table(p)
    d = fitz.open(p)
    tables = ep.collect_tables(d)
    d.close()
    assert len(tables) == 1
    entry = tables[0]
    assert entry["page"] == 1
    assert entry["index"] == 0
    assert len(entry["bbox"]) == 4
    assert "r0c0" in entry["markdown"]


def test_collect_tables_bbox_is_json_serialisable(tmp_path):
    """bbox 必须是 list 而非 fitz.Rect —— tables.json 要能被 json.dump。"""
    import json
    p = tmp_path / "t.pdf"
    build_pdf_with_table(p)
    d = fitz.open(p)
    tables = ep.collect_tables(d)
    d.close()
    json.dumps(tables)          # 不抛异常即通过
    assert all(isinstance(t["bbox"], list) for t in tables)


def test_table_anchor_format():
    assert ep.table_anchor(1, 0) == "[[table:p1-0]]"


def test_strip_table_lines_replaces_table_text_with_single_anchor():
    """表格区域的行必须从正文剔除并留一个锚记。

    不剔除的话,表格既成了图、它那份乱序文字层又留在正文里,
    会同时污染 TL;DR 和翻译。
    """
    lines = [
        (60, 120, 300, 132, "Some body text above the table"),
        (66, 210, 100, 222, "r0c0"),
        (216, 210, 250, 222, "r0c1"),
        (60, 400, 300, 412, "Body text below the table"),
    ]
    tables = [{"page": 1, "index": 0, "bbox": [60, 200, 510, 290], "markdown": "|x|"}]
    kept, anchors = ep.strip_table_lines(lines, tables)
    texts = [l[4] for l in kept]
    assert texts == ["Some body text above the table",
                     "[[table:p1-0]]",
                     "Body text below the table"]
    assert anchors == 1


def test_strip_table_lines_noop_when_no_tables():
    lines = [(60, 120, 300, 132, "only body")]
    kept, anchors = ep.strip_table_lines(lines, [])
    assert kept == lines
    assert anchors == 0
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: FAIL — `AttributeError: module 'extract_pdf' has no attribute 'collect_tables'`

- [ ] **Step 4: 写实现**

追加到 `skills/bpr/scripts/fetch/extract_pdf.py`:

```python
def collect_tables(doc):
    """表格 bbox 的单一真源,写进 tables.json 给 extract_pdf_images.py 读。

    刻意不让两个脚本各跑一次 find_tables():两次调用的 bbox 未必一致,
    锚点会错位。
    """
    out = []
    for page_no, page in enumerate(doc, start=1):
        try:
            finder = page.find_tables()
        except Exception:          # find_tables 对畸形页会抛,跳过该页而非整体失败
            continue
        for index, table in enumerate(finder.tables):
            out.append({
                "page": page_no,
                "index": index,
                "bbox": [float(v) for v in table.bbox],
                "markdown": table.to_markdown(),
            })
    return out


def table_anchor(page_no, index):
    return f"[[table:p{page_no}-{index}]]"


def _inside(line, bbox):
    """行中心是否落在 bbox 内。用中心而非完全包含,容忍 1-2pt 的边界溢出。"""
    x0, y0, x1, y1 = bbox
    cx, cy = (line[0] + line[2]) / 2.0, (line[1] + line[3]) / 2.0
    return x0 <= cx <= x1 and y0 <= cy <= y1


def strip_table_lines(lines, tables_on_page):
    """把落在表格 bbox 内的行换成一个锚记。返回 (kept_lines, anchors_inserted)。"""
    if not tables_on_page:
        return lines, 0

    kept, seen, anchors = [], set(), 0
    for line in lines:
        hit = None
        for table in tables_on_page:
            if _inside(line, table["bbox"]):
                hit = table
                break
        if hit is None:
            kept.append(line)
            continue
        key = (hit["page"], hit["index"])
        if key in seen:
            continue                    # 同一表格的后续行直接丢
        seen.add(key)
        anchors += 1
        kept.append((line[0], line[1], line[2], line[3],
                     table_anchor(hit["page"], hit["index"])))
    return kept, anchors
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: PASS,28 passed

- [ ] **Step 6: 提交**

```bash
cd ~/dev/bpr-pdf-input
git add skills/bpr/tests/pdf_fixtures.py
git commit -- skills/bpr/scripts/fetch/extract_pdf.py skills/bpr/tests/test_extract_pdf.py skills/bpr/tests/pdf_fixtures.py -m "feat(pdf): 表格 bbox 单一真源与正文剔除留锚"
```

---

### Task 7: `extract_pdf.py` — 免责声明截断(带报告)

**Files:**
- Modify: `skills/bpr/scripts/fetch/extract_pdf.py`(追加)
- Modify: `skills/bpr/tests/test_extract_pdf.py`(追加)

**Interfaces:**
- Consumes: 无(纯函数)
- Produces:
  - `find_disclaimer_page(page_texts) -> int` 或 `None` — 入参为 `[(page_no, text), ...]`,返回免责声明起始页号

- [ ] **Step 1: 写失败的测试**

追加到 `skills/bpr/tests/test_extract_pdf.py`:

```python
def test_find_disclaimer_page_detects_tail_section():
    pages = [
        (1, "正文第一页 讲行业规模"),
        (2, "正文第二页 讲竞争格局"),
        (3, "免责声明\n本报告仅供参考,不构成投资建议"),
        (4, "分析师承诺\n本人具有中国证券业协会授予的证券投资咨询执业资格"),
    ]
    assert ep.find_disclaimer_page(pages) == 3


def test_find_disclaimer_page_english():
    pages = [
        (1, "Body page one"),
        (2, "Disclaimer\nThis report is for information purposes only"),
    ]
    assert ep.find_disclaimer_page(pages) == 2


def test_find_disclaimer_page_ignores_early_mention():
    """正文前半段提到「免责声明」(如页脚提示语)不算,只认尾部三分之一。"""
    pages = [
        (1, "请务必阅读正文之后的免责声明部分"),
        (2, "正文第二页"),
        (3, "正文第三页"),
        (4, "正文第四页"),
        (5, "正文第五页"),
        (6, "正文第六页"),
    ]
    assert ep.find_disclaimer_page(pages) is None


def test_find_disclaimer_page_returns_none_when_absent():
    pages = [(1, "body one"), (2, "body two"), (3, "body three")]
    assert ep.find_disclaimer_page(pages) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: FAIL — `AttributeError: module 'extract_pdf' has no attribute 'find_disclaimer_page'`

- [ ] **Step 3: 写实现**

追加到 `skills/bpr/scripts/fetch/extract_pdf.py`:

```python
DISCLAIMER_RE = re.compile(
    r"^\s*(免责声明|评级说明|分析师承诺|分析师声明|重要声明|法律声明|"
    r"Disclaimer|Disclosures?|Important\s+Disclosures?)\s*$",
    re.IGNORECASE | re.MULTILINE)

DISCLAIMER_TAIL_FRACTION = 2.0 / 3.0    # 只在尾部三分之一里找


def find_disclaimer_page(page_texts):
    """返回免责声明起始页号,没有则 None。

    page_texts: [(page_no, text), ...]

    只认尾部三分之一:研报每页页脚都写「请务必阅读正文之后的免责声明部分」,
    在正文前半段命中一定是那句提示语,截了会吃掉真正文。
    """
    total = len(page_texts)
    if total < 2:
        return None
    threshold = total * DISCLAIMER_TAIL_FRACTION
    for position, (page_no, text) in enumerate(page_texts, start=1):
        if position <= threshold:
            continue
        if DISCLAIMER_RE.search(text or ""):
            return page_no
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: PASS,32 passed

- [ ] **Step 5: 提交**

```bash
cd ~/dev/bpr-pdf-input
git commit -- skills/bpr/scripts/fetch/extract_pdf.py skills/bpr/tests/test_extract_pdf.py -m "feat(pdf): 尾部免责声明截断,只认尾三分之一"
```

---

### Task 8: `extract_pdf.py` — CLI 与产物写出(端到端)

**Files:**
- Modify: `skills/bpr/scripts/fetch/extract_pdf.py`(追加 `run` / `main`)
- Modify: `skills/bpr/tests/test_extract_pdf.py`(追加端到端测试)

**Interfaces:**
- Consumes: Task 1–7 的全部函数
- Produces:
  - `run(pdf_path, workdir, truncate=True, tables_mode="img") -> dict` — 返回报告 dict,含 `mode` / `pages` / `paragraphs` / `hf_dropped` / `tables` / `table_anchors` / `truncated_from` / `truncated_pages` / `meta` / `confidence`
  - `main(argv=None) -> int` — 退出码:0 成功 / 2 输入非法 / 3 需要 OCR(阶段 3)

- [ ] **Step 1: 写失败的测试**

追加到 `skills/bpr/tests/test_extract_pdf.py`:

```python
def test_run_writes_four_artifacts(tmp_path):
    import json
    pdf = tmp_path / "r.pdf"
    build_report_pdf(pdf, npages=5)
    work = tmp_path / "w"
    report = ep.run(pdf, work)

    assert (work / "body.txt").exists()
    assert (work / "pages.jsonl").exists()
    assert (work / "metadata.json").exists()
    assert (work / "tables.json").exists()

    meta = json.loads((work / "metadata.json").read_text(encoding="utf-8"))
    assert set(meta) == {"date", "title", "author", "publication",
                         "source_slug", "canonical", "source"}
    assert report["mode"] == "text"


def test_run_body_has_no_header_footer_residue(tmp_path):
    pdf = tmp_path / "r.pdf"
    build_report_pdf(pdf, npages=5)
    work = tmp_path / "w"
    ep.run(pdf, work)
    body = (work / "body.txt").read_text(encoding="utf-8")
    assert "中金公司研究部" not in body
    assert "免责声明" not in body
    assert "共 5 页" not in body


def test_run_body_has_no_page_number_pollution(tmp_path):
    """body.txt 必须干净;页码信息只进 pages.jsonl。"""
    pdf = tmp_path / "r.pdf"
    build_report_pdf(pdf, npages=5)
    work = tmp_path / "w"
    ep.run(pdf, work)
    body = (work / "body.txt").read_text(encoding="utf-8")
    assert "[[page" not in body


def test_run_pages_jsonl_one_record_per_page(tmp_path):
    import json
    pdf = tmp_path / "r.pdf"
    build_report_pdf(pdf, npages=5)
    work = tmp_path / "w"
    ep.run(pdf, work)
    records = [json.loads(l) for l in
               (work / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 5
    assert records[0]["page"] == 1
    assert records[0]["source"] == "text"


def test_run_reports_dropped_header_footer_count(tmp_path):
    """所有丢内容的行为都必须可被审计。"""
    pdf = tmp_path / "r.pdf"
    build_report_pdf(pdf, npages=5)
    work = tmp_path / "w"
    report = ep.run(pdf, work)
    assert report["hf_dropped"] >= 2


def test_run_raises_for_non_pdf(tmp_path):
    p = tmp_path / "fake.pdf"
    p.write_text("not a pdf")
    with pytest.raises(ep.PdfInputError) as excinfo:
        ep.run(p, tmp_path / "w")
    assert excinfo.value.exit_code == 2


def test_run_raises_for_scanned_pdf_pointing_at_phase3(tmp_path):
    """阶段 1 不含 OCR:无文字层必须明确报错,绝不静默产出空正文。"""
    doc = fitz.open()
    for _ in range(4):
        doc.new_page()
    p = tmp_path / "blank.pdf"
    doc.save(str(p))
    doc.close()

    with pytest.raises(ep.PdfInputError) as excinfo:
        ep.run(p, tmp_path / "w")
    assert excinfo.value.exit_code == 3
    assert "ocr_pdf.py" in str(excinfo.value)


def test_main_returns_zero_on_success(tmp_path, capsys):
    pdf = tmp_path / "r.pdf"
    build_report_pdf(pdf, npages=5)
    code = ep.main([str(pdf), "--workdir", str(tmp_path / "w")])
    assert code == 0
    out = capsys.readouterr().out
    assert "body.txt" in out


def test_main_returns_two_for_non_pdf(tmp_path, capsys):
    p = tmp_path / "fake.pdf"
    p.write_text("nope")
    code = ep.main([str(p), "--workdir", str(tmp_path / "w")])
    assert code == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: FAIL — `AttributeError: module 'extract_pdf' has no attribute 'run'`

- [ ] **Step 3: 写实现**

追加到 `skills/bpr/scripts/fetch/extract_pdf.py`(顶部 import 区加 `import argparse`,并加 `import pdf_layout as layout`):

```python
def run(pdf_path, workdir, truncate=True, tables_mode="img"):
    """解析 PDF,把产物写进 workdir。返回报告 dict。"""
    pdf_path = pathlib.Path(pdf_path)
    if not is_pdf(pdf_path):
        raise PdfInputError(f"不是 PDF 文件(magic 非 %PDF-): {pdf_path}", exit_code=2)

    doc = fitz.open(str(pdf_path))
    try:
        if doc.needs_pass:
            raise PdfInputError(
                f"PDF 已加密: {pdf_path}。请先解密或提供密码。", exit_code=2)

        access = probe_access(doc)
        ratio = text_ratio(doc)
        mode = detect_mode(ratio)

        if access == "perm_locked":
            raise PdfInputError(
                f"文字层被权限锁(有字体但取不到文字): {pdf_path}。"
                f"需要 OCR —— 走 scripts/fetch/ocr_pdf.py(阶段 3,尚未实现)。",
                exit_code=3)
        if mode == "scanned":
            raise PdfInputError(
                f"无文字层(text_ratio={ratio:.2f},疑似扫描件): {pdf_path}。"
                f"需要 OCR —— 走 scripts/fetch/ocr_pdf.py(阶段 3,尚未实现)。",
                exit_code=3)

        need_ocr_pages = [i + 1 for i, page in enumerate(doc)
                          if not page_has_text(page)]
        if mode == "mixed" and need_ocr_pages:
            raise PdfInputError(
                f"混合模式:第 {need_ocr_pages} 页无文字层,需要 OCR 补齐 —— "
                f"走 scripts/fetch/ocr_pdf.py(阶段 3,尚未实现)。"
                f"跳过这些页会静默丢内容,故不继续。",
                exit_code=3)

        drop_set = layout.find_repeated_hf(doc)
        tables = collect_tables(doc) if tables_mode == "img" else []
        tables_by_page = {}
        for entry in tables:
            tables_by_page.setdefault(entry["page"], []).append(entry)

        page_records, page_texts, anchors_total = [], [], 0
        for page_no, page in enumerate(doc, start=1):
            lines = layout.page_lines(page, drop_set)
            lines, anchors = strip_table_lines(lines, tables_by_page.get(page_no, []))
            anchors_total += anchors
            paragraphs = layout.lines_to_paragraphs(lines)
            text = "\n\n".join(paragraphs)
            page_records.append({"page": page_no, "text": text, "source": "text"})
            page_texts.append((page_no, text))

        cut_at = find_disclaimer_page(page_texts) if truncate else None
        truncated_pages = 0
        if cut_at is not None:
            truncated_pages = len(page_texts) - cut_at + 1
            page_texts = [pt for pt in page_texts if pt[0] < cut_at]

        body = "\n\n".join(text for _, text in page_texts if text).strip() + "\n"
        meta, confidence = build_metadata(doc, pdf_path)
        total_pages = doc.page_count
    finally:
        doc.close()

    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "body.txt").write_text(body, encoding="utf-8")
    with open(workdir / "pages.jsonl", "w", encoding="utf-8") as fh:
        for record in page_records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    (workdir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (workdir / "tables.json").write_text(
        json.dumps(tables, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "mode": mode,
        "text_ratio": round(ratio, 3),
        "pages": total_pages,
        "chars": len(body),
        "hf_dropped": len(drop_set),
        "hf_texts": sorted(drop_set),
        "tables": len(tables),
        "table_anchors": anchors_total,
        "truncated_from": cut_at,
        "truncated_pages": truncated_pages,
        "meta": meta,
        "confidence": confidence,
        "workdir": str(workdir),
    }


def _print_report(report):
    """所有「丢了内容」的行为都要在这里说出来。静默丢弃是头号禁忌。"""
    print(f"模式         {report['mode']}(text_ratio={report['text_ratio']})")
    print(f"页数         {report['pages']}")
    print(f"正文         {report['chars']} 字符 → {report['workdir']}/body.txt")
    print(f"剔除页眉页脚  {report['hf_dropped']} 条")
    for text in report["hf_texts"]:
        print(f"             · {text}")
    print(f"表格         {report['tables']} 个,正文留锚 {report['table_anchors']} 处"
          f" → {report['workdir']}/tables.json")
    if report["truncated_from"] is not None:
        print(f"⚠ 已截断     从第 {report['truncated_from']} 页起共 "
              f"{report['truncated_pages']} 页(命中免责声明类标题)。"
              f"若误截请加 --no-truncate 重跑")
    print()
    print("元数据(请确认,有误直接告诉我改哪一项):")
    print(f"  {'字段':<14}{'候选值':<34}{'来源':<26}置信度")
    for key in ("title", "publication", "date", "source_slug", "canonical"):
        value = report["meta"].get(key)
        source = report["meta"]["source"] if key == "date" else (
            "local-path" if key == "canonical" else "derived")
        conf = report["confidence"].get(key, "—")
        print(f"  {key:<14}{str(value):<34}{source:<26}{conf}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PDF → 干净正文 + 元数据(BPR INGEST 本地 PDF 入口)")
    parser.add_argument("pdf")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--no-truncate", action="store_true",
                        help="不截断尾部免责声明")
    parser.add_argument("--tables", choices=("img", "md"), default="img",
                        help="img=表格当图(默认,剔正文留锚) md=表格转 markdown 留在正文")
    args = parser.parse_args(argv)

    try:
        report = run(args.pdf, args.workdir,
                     truncate=not args.no_truncate, tables_mode=args.tables)
    except PdfInputError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return exc.exit_code

    _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/test_extract_pdf.py -q`
Expected: PASS,41 passed

- [ ] **Step 5: 跑全量测试**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/ -q`
Expected: PASS,59 passed(现有 21 + layout 18 + extract 41 中新增部分;实际数字以运行结果为准,只要 0 failed)

- [ ] **Step 6: 手动驱动一次真实路径**(不能只靠单测就报完成)

```bash
cd ~/dev/bpr-pdf-input/skills/bpr
/usr/bin/python3 - <<'PY'
import pathlib, sys
sys.path.insert(0, "tests")
from pdf_fixtures import build_report_pdf
build_report_pdf(pathlib.Path("/tmp/bpr-demo.pdf"), npages=6)
PY
/usr/bin/python3 scripts/fetch/extract_pdf.py /tmp/bpr-demo.pdf --workdir /tmp/bpr-demo-w
echo "--- body.txt ---"
cat /tmp/bpr-demo-w/body.txt
echo "--- metadata.json ---"
cat /tmp/bpr-demo-w/metadata.json
```

Expected:报告里 `模式 text`、`剔除页眉页脚 2 条`、元数据表里 `date` 为 `2026-07-15` 且来源 `pdf:cover-text`;`body.txt` 无「中金公司研究部」「免责声明」「共 6 页」。

- [ ] **Step 7: 提交**

```bash
cd ~/dev/bpr-pdf-input
git commit -- skills/bpr/scripts/fetch/extract_pdf.py skills/bpr/tests/test_extract_pdf.py -m "feat(pdf): CLI 与产物写出,无文字层明确报错指向阶段 3"
```

---

### Task 9: 文档接线

**Files:**
- Modify: `skills/bpr/references/ingest.md`(输入模式判定表 + `:37` 行 + 新增一节)
- Modify: `skills/bpr/SKILL.md`(流水线表第 1 行 + 错误处理节)
- Modify: `skills/bpr/references/lessons-learned.md`(新增 L5)

**Interfaces:**
- Consumes: Task 8 的 CLI 形状(`extract_pdf.py <pdf> --workdir W [--no-truncate] [--tables img|md]`)与退出码语义
- Produces: 无代码接口

- [ ] **Step 1: `ingest.md` 输入模式判定表加一行**

在「输入模式判定」表格(现有四行 SRT / Transcript with timestamps / Plain transcript / Blog-Essay)之后加:

```markdown
| **本地 PDF** | `.pdf` 文件路径(研报 / 白皮书 / 书籍章节) | ✗ 全部跳过 | `{publication} · Report · {YYYY-MM-DD}` |
```

并在判定逻辑列表末尾加一条:

```markdown
- 输入是本地 `.pdf` 路径 → **本地 PDF 模式**(走 `scripts/fetch/extract_pdf.py`,渲染上等同 blog / essay 模式)
```

- [ ] **Step 2: `ingest.md` 改 PDF 链接那一行**

把现有那行(`| PDF 链接 | 让用户先下载到本地,再 /bpr <文件路径> |`)改成:

```markdown
| PDF 链接 | 让用户先下载到本地,再 `/bpr <文件路径>` → 走下面「本地 PDF 一站式流程」 |
```

- [ ] **Step 3: `ingest.md` 新增「本地 PDF 一站式流程」一节**

放在「小宇宙 / Bilibili → 飞书妙记 一站式流程」之后:

```markdown
### 本地 PDF 一站式流程

**Step A · 解析**

```bash
WORKDIR=$(mktemp -d /tmp/bpr-pdf-XXXX)
python3 scripts/fetch/extract_pdf.py "<path.pdf>" --workdir "$WORKDIR"
```

产物:
- `body.txt` — 干净正文(已剥跨页重复的页眉页脚、已接行尾断词、双栏已按栏序拉直)
- `pages.jsonl` — 每页一条 `{page, text, source}`,底档,查错字定位到页
- `metadata.json` — 7 键,与 `extract_metadata.py` 同形
- `tables.json` — 表格 bbox 单一真源,阶段 2 的 `extract_pdf_images.py` 读它

**退出码**:`0` 成功 · `2` 输入非法(非 PDF / 已加密)· `3` 需要 OCR(无文字层或权限锁,走阶段 3 的 `ocr_pdf.py`)。

**Step B · 元数据确认(必做,不要跳)**

脚本会打一张「字段 / 候选值 / 来源 / 置信度」表。**发布日期必须来自封面正文,不是 PDF 的 CreationDate**——CreationDate 记的是文件何时生成,一份旧研报被重新导出就会变成今天,正好违反本文档「绝不静默用今天」那条。

看到 `source` 为 `pdf:info-creationdate` 或 `pdf:none` 时,主动问用户要真实发布日期。

**Step C · 截断与丢弃都要复核**

脚本会报「剔除页眉页脚 N 条」「已截断从第 X 页起共 N 页」。研报尾部的免责声明该截,但**若截掉的页数明显偏多,加 `--no-truncate` 重跑**再人工判断。

**Step D · 喂给正常流程**

把 `body.txt` 当 essay 正文输入,`metadata.json` 供 hero kicker 与文件名。之后 PREP 按 CJK 占比自动选中文浓缩 / 英文双语,与其他来源一致。

> **表格**:默认 `--tables img`,表格文本从 `body.txt` 剔除并留 `[[table:pN-i]]` 锚记,由阶段 2 抽成图填回。想要 markdown 表格用 `--tables md`。
```

- [ ] **Step 4: `SKILL.md` 流水线表第 1 行补脚本**

把 INGEST 行的 reference 列改成:

```
`references/ingest.md`(URL 处理 / 发布日期 / 文件名规则)· `scripts/fetch/*`(含 `extract_pdf.py` 本地 PDF)
```

- [ ] **Step 5: `SKILL.md` 错误处理节补三条**

在「错误处理」列表里加:

```markdown
- 本地 PDF 无文字层 / 文字层被权限锁:`extract_pdf.py` 退出码 3,需 OCR(阶段 3)。**不要**跳过这些页继续,会静默丢内容。
- 本地 PDF > 200 页:询问是否分 part。
- 本地 PDF 报「已截断 N 页」:复核是否误截真正文,必要时 `--no-truncate` 重跑。
```

- [ ] **Step 6: `lessons-learned.md` 新增 L5**

```markdown
- **L5 PDF 分栏只能在 line 级做**:`page.get_text("blocks")` 会把**同一基线上的左右栏文字合并进同一个 block**,栏在 block 内部就已经糊在一起——任何 block 级的 x 判据都拿不到栏边界,而且 block 级的「通栏」判据会把所有合并后的正文块误判成通栏。必须用 `get_text("dict")` 的 `blocks[].lines[]`(每行带 bbox)。
  另:**研报图表大多是矢量而非位图**,`page.get_images()` 会静默返回空(Wind / Excel 导出的图在 PDF 里是填充矩形与 path)。必须靠 `get_drawings()` 的 bbox 聚类 + `get_pixmap(clip=bbox)` 区域截图。
  两条都是 2026-08-03 实测结论,见 `docs/superpowers/specs/2026-08-03-bpr-pdf-input-design.md`。
```

- [ ] **Step 7: 确认没弄坏测试**

Run: `cd skills/bpr && /usr/bin/python3 -m pytest tests/ -q`
Expected: PASS,0 failed

- [ ] **Step 8: 提交**

```bash
cd ~/dev/bpr-pdf-input
git commit -- skills/bpr/references/ingest.md skills/bpr/SKILL.md skills/bpr/references/lessons-learned.md -m "docs(pdf): 本地 PDF 流程接线,记 L5 分栏与矢量图两条硬规则"
```

---

### Task 10: 真研报实测与发版

**Files:**
- Modify: `.claude-plugin/marketplace.json:9`、`.claude-plugin/marketplace.json:16`、`.claude-plugin/plugin.json:4`

**Interfaces:**
- Consumes: Task 1–9 全部
- Produces: 版本 1.7.0

- [ ] **Step 1: 拿 Ken 的真 PDF 实跑**

向 Ken 要一份真实研报路径(文字层的,不要扫描件——扫描件属阶段 3),然后:

```bash
cd ~/dev/bpr-pdf-input/skills/bpr
WORKDIR=$(mktemp -d /tmp/bpr-real-XXXX)
/usr/bin/python3 scripts/fetch/extract_pdf.py "<Ken 给的路径>" --workdir "$WORKDIR"
echo "=== body.txt 前 60 行 ==="
head -60 "$WORKDIR/body.txt"
echo "=== 末 20 行(看截断对不对) ==="
tail -20 "$WORKDIR/body.txt"
echo "=== metadata.json ==="
cat "$WORKDIR/metadata.json"
```

**逐项人工核对,把结论如实报给 Ken**:

1. 页眉页脚是否剔净(搜机构名和「请务必阅读」)
2. 双栏是否被拉直(有没有「左栏半句 + 右栏半句」黏在一行)
3. 发布日期是否来自封面而非 CreationDate
4. 截断起点是否真的是免责声明(不是真正文)
5. 表格锚记数量与 `tables.json` 条数是否一致

任何一项不对 → **不要 bump 版本**,回到对应 Task 修,并把实测输出贴给 Ken。

- [ ] **Step 2: 跑一次完整 bpr 流程出 HTML**

用 `$WORKDIR/body.txt` 走完 PREP → STRUCTURE →(中文 CLEAN / 英文 TRANSLATE)→ RENDER,确认:
- essay 版型正常(不渲染 speaker / turn / timestamp)
- hero kicker 用的是封面日期
- 文件名第一段是封面日期

RENDER 阶段暂时**没有图**(阶段 2 才做),`[[table:pN-i]]` 锚记会以字面量出现在正文里——这是预期的,在报告里说明,不要当 bug 修。

- [ ] **Step 3: bump 三处版本号**

```bash
cd ~/dev/bpr-pdf-input
/usr/bin/python3 - <<'PY'
import pathlib, re
for rel, count in ((".claude-plugin/marketplace.json", 2),
                   (".claude-plugin/plugin.json", 1)):
    p = pathlib.Path(rel)
    s = p.read_text(encoding="utf-8")
    new, n = re.subn(r'"version": "1\.6\.3"', '"version": "1.7.0"', s)
    assert n == count, f"{rel}: 期望替换 {count} 处,实际 {n} 处"
    p.write_text(new, encoding="utf-8")
    print(f"{rel}: {n} 处已 bump")
PY
grep -n '"version"' .claude-plugin/marketplace.json .claude-plugin/plugin.json
```

Expected:`marketplace.json` 两行、`plugin.json` 一行,全部 `1.7.0`。

> **漏一处会静默不发版**——上一个 commit `c8c91f3` 正是为补漏而生。断言 `n == count` 就是为了让漏改直接报错而不是静默通过。

- [ ] **Step 4: 提交并推分支**

```bash
cd ~/dev/bpr-pdf-input
git commit -- .claude-plugin/marketplace.json .claude-plugin/plugin.json -m "chore(release): 1.7.0 本地 PDF 输入(阶段 1)"
git push -u origin feat/pdf-input
```

- [ ] **Step 5: 向 Ken 汇报,明确标注验证边界**

按 CLAUDE.md §8,报告必须分清:
- **实测过的**:单测数量、真研报解析的五项人工核对结果、完整流程出 HTML 的观察
- **未实测的**:扫描件路径(阶段 3 未实现)、图表落地(阶段 2 未实现)、`--tables md` 分支(若本轮没跑)

不要把「接线完成」说成「验证通过」。

---

## Self-Review

**1. Spec coverage** — 逐节核对:

| Spec 章节 | 覆盖任务 |
|---|---|
| 三档探测 / `text_ratio` 页级定义 | Task 4 |
| 机制 ① 分栏(line 级修正版) | Task 2 |
| 机制 ② 页眉页脚 + 短文档守卫 | Task 1 |
| 机制 ③ 断词与段落边界 | Task 3 |
| 机制 ④ 免责声明截断 + 必须报告 | Task 7 |
| 表格默认当图 + `tables.json` 单一真源 + 剔正文留锚 | Task 6 |
| 元数据策略链 + CreationDate 降级 + 仅年份补 01-01 | Task 5 |
| 7 键形状 + `source` / `canonical` 重新解释 | Task 5 |
| 元数据确认交互 | Task 8(`_print_report`) |
| 产物 body.txt / pages.jsonl / metadata.json / tables.json | Task 8 |
| 错误处理表(非 PDF / 加密 / 权限锁 / 需 OCR / 截断报告) | Task 4 + Task 8 |
| 文档四处改动 | Task 9(`render.md` 那处属阶段 2,见下) |
| 发版三处 bump | Task 10 |
| 测试(fixture 合成、date 优先级、键集一致) | Task 1–8 |

**已知的有意缺口(非遗漏):**

- **`render.md` 的 enrich 注记**留到阶段 2 —— 那一节讲的是 `extract_pdf_images.py`,阶段 1 没有这个脚本,现在写等于写一条指向不存在文件的引用。
- **`> 200 页询问分 part`** 只写进了 `SKILL.md` 的错误处理(Task 9 Step 5)作为流程规则,没做成脚本里的硬检查。理由:脚本是被 LLM 调用的,分不分 part 是流程决策而非脚本职责;而且 200 页的 PDF 解析本身不会失败。
- **`--tables md` 分支**在 Task 6 实现里是「`tables_mode != "img"` 时不收集表格」,即表格文本自然留在正文里。`find_tables().to_markdown()` 的结果已存进 `tables.json` 的 `markdown` 字段,但阶段 1 不把它插回 `body.txt`。真正的 markdown 回填留给阶段 2 一起做(那时才有图 / 表两条路的取舍)。**这是缩水,已在此明示**:阶段 1 的 `--tables md` 只是「不剔除表格文本」,不是「表格变成漂亮 markdown」。

**2. Placeholder scan** — 已检查:无 TBD / TODO;每个代码步骤都有可运行的完整代码块;每个测试步骤都有真实断言;没有「参照 Task N」式的省略(Task 3 与 Task 6 的重复 import 说明都写全了)。

**3. Type consistency** — 已核对跨任务的签名与形状:

- `body_lines` / `page_lines` 全程返回 **5 元组** `(x0, y0, x1, y1, text)`;`strip_table_lines`(Task 6)构造替换行时也保持 5 元组;`lines_to_paragraphs`(Task 3)按 `l[1]` 取 y0、`l[4]` 取文本 —— 一致。
- `hf_lines` 返回 **已归一化的 str**,`find_repeated_hf` 因此直接 `update`,`page_lines` 里再对正文行做 `norm_hf(l[4])` 后比对 —— 一致。
- `collect_tables` 的条目键 `page` / `index` / `bbox` / `markdown`,在 `strip_table_lines` 里用 `table["bbox"]`、`hit["page"]`、`hit["index"]`,在 `run` 里用 `entry["page"]` 分组 —— 一致。
- `build_metadata` 返回 `(meta, confidence)` 二元组,`run` 解包成 `meta, confidence`,`_print_report` 读 `report["meta"]` / `report["confidence"]` —— 一致。
- `PdfInputError.exit_code` 在 `run` 里赋 2 / 3,`main` 里 `return exc.exit_code`,测试断言 2 / 3 —— 一致。
- `find_disclaimer_page` 入参是 `[(page_no, text)]`,`run` 里传的 `page_texts` 正是这个形状 —— 一致。
