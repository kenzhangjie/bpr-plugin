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

import json
import pathlib
import re
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
