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
