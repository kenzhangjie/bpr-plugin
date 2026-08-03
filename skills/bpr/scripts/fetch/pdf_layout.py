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
