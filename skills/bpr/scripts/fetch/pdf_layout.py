"""PDF 版面层 · 纯函数,零 IO。

为什么全程在 line 级而不是 block 级:fitz 的 get_text("blocks") 会把同一基线上
的左右栏文字合并进同一个 block,栏在 block 内部就已经糊在一起,任何 block 级的
x 判据都拿不到栏边界(2026-08-03 实测)。见 references/lessons-learned.md L8。
"""
from __future__ import annotations

import re
import statistics
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
