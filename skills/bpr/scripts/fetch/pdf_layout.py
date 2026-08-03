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


def content_lines(page):
    """该页**所有**非空行,不做任何剔除。返回 [(x0, y0, x1, y1, text)]。

    内容的唯一真源。产出正文一律从这里取行,再按 drop_set 精确过滤。
    """
    return list(_iter_lines(page))


def body_lines(page):
    """上下 8% 带外的行。**只供 find_gutter 做版式判定,不可用于产出正文。**

    带内也可能是真正文——页边距紧于 8%(A4 约 67pt)的 PDF 每页首尾都是正文。
    无条件剔整条带会静默吃掉这些行,踩「绝不静默丢内容」的头号禁忌。
    gutter 探测排除页眉页脚是有意的:它只影响启发式判断,不删任何内容。
    """
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
    """该页按阅读顺序排好的行,唯一的删除依据是 drop_set。

    行取自 content_lines(全量),因此:
      · 跨页重复的真页眉页脚(drop_set 由带内行推出)会被删 —— 过滤方向正确
      · 带内的非重复内容(真正文)被保留
      · drop_set 为空(页数 < HF_MIN_PAGES)时什么都不删,保守且正确

    双栏排序规则:以通栏行的 y 把页面切成 band,band 内先左栏(y 序)再右栏(y 序),
    通栏行本身排在其 band 之首。
    """
    lines = [l for l in content_lines(page) if norm_hf(l[4]) not in drop_set]
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
        # 下界取闭区间:y 恰好等于某通栏行 y0 的栏内行,双侧严格不等号会让它
        # 被两个 band 都排除,静默漏行。落在通栏行之后,阅读顺序仍正确。
        out.extend(sorted((l for l in left if lo <= l[1] < hi), key=lambda l: l[1]))
        out.extend(sorted((l for l in right if lo <= l[1] < hi), key=lambda l: l[1]))
    return out


GAP_FACTOR = 1.3        # 行距 > 中位行距 × 此值 → 段落边界
TALL_RATIO = 1.12       # 行高 > 页面中位行高 × 此值 → 高行(标题类)
#                         1.12 是刻意压到底的:12pt 标题 / 10.5pt 正文是研报里
#                         最小的字号差,这一档也要抓住。不要调大。

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

    段落边界三种:
      1) 相邻行 y 间距 > 中位行距 × gap_factor
      2) y 回跳(delta <= 0)= 换栏或换页,强制断段
      3) 高矮切换 = 标题类行与常规行的边界

    为什么需要第 3 条:垂直锚点用的是 bbox 的 y0,而 y0 被字号污染 —— 标题字号大,
    y0 被上抬,于是它「之前」的间距被压小(单栏:标题粘到上一段末尾),它落在
    band 边界时「之后」的间距被压小(双栏:标题粘到下一段开头);同时中位行距
    被标题前后的大间距抬高,limit 被推高,两条 delta 规则一起失灵。
    行高(y1 - y0)是字号的现成代理,不必改签名就能把标题揪出来。

    必须跟「页面中位行高」比,不能跟「相邻行行高」比:fitz 会把行尾 6.5pt 的
    脚注上标切成独立一行(行高 8.93),相邻比较会把一页均匀正文切成 5 段。
    跟中位比,矮行不触发,只有真标题(比中位高 12% 以上)才触发。
    """
    if not lines:
        return []
    if len(lines) == 1:
        return [lines[0][4]]

    heights = [l[3] - l[1] for l in lines]
    median_h = statistics.median(heights)
    tall = [h > median_h * TALL_RATIO for h in heights]

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
        if delta <= 0 or delta > limit or tall[i] != tall[i - 1]:
            paragraphs.append(current)
            current = lines[i][4]
        else:
            current = join_lines(current, lines[i][4])
    paragraphs.append(current)
    return paragraphs
