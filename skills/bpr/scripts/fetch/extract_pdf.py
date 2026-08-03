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

import argparse
import json
import pathlib
import re
import sys

import fitz

import pdf_layout as layout

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
        title, confidence["title"] = info_title, "high"
    else:
        title = cover_max_font_text(cover) if cover is not None else None
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
        # source 只报 date 的来源,与 extract_metadata.py 语义一致。
        # 无日期时 date_src 已是 "pdf:none",绝不回落成 title 的命中策略 ——
        # 回落会让 ingest.md「见 pdf:none / pdf:info-creationdate 就问用户要
        # 真实发布日期」的守卫在最需要问的场景下不触发。
        "source": date_src,
    }
    return meta, confidence


def collect_tables(doc):
    """表格 bbox 的单一真源,写进 tables.json 给 extract_pdf_images.py 读。

    刻意不让两个脚本各跑一次 find_tables():两次调用的 bbox 未必一致,
    锚点会错位。
    """
    out = []
    for page_no, page in enumerate(doc, start=1):
        try:
            finder = page.find_tables()
        except AttributeError:
            # AttributeError 标志编程错误(如未来重构时拼错方法名),不应吞掉
            raise
        except Exception as e:
            # 畸形页导致的异常:跳过该页并打告警到 stderr
            print(f"⚠ 第 {page_no} 页表格解析失败,已跳过该页表格({type(e).__name__})",
                  file=sys.stderr)
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

        # 刻意与 mode 解耦:TEXT_RATIO_HI=0.8 意味着最多 20% 的页可以完全没有
        # 文字层却仍被判成 "text"。而「正文有文字层、图表页/附录页是整页扫描图」
        # 恰恰是研报最常见形态,这些页会 pages.jsonl 为空、body 里被 if text
        # 跳过、stdout 全程无提示 —— 静默丢内容。
        need_ocr_pages = [i + 1 for i, page in enumerate(doc)
                          if not page_has_text(page)]
        if need_ocr_pages:
            raise PdfInputError(
                f"第 {need_ocr_pages} 页无文字层(mode={mode},"
                f"text_ratio={ratio:.2f}),需要 OCR 补齐 —— "
                f"走 scripts/fetch/ocr_pdf.py(阶段 3,尚未实现)。"
                f"跳过这些页会静默丢内容,故不继续。",
                exit_code=3)

        drop_set = layout.find_repeated_hf(doc)
        tables = collect_tables(doc) if tables_mode == "img" else []
        tables_by_page = {}
        for entry in tables:
            tables_by_page.setdefault(entry["page"], []).append(entry)

        page_records, page_texts, anchors_total = [], [], 0
        hf_lines_dropped = 0
        for page_no, page in enumerate(doc, start=1):
            # 如实统计:content_lines 是全量真源,与过滤后的差就是实际删掉的行数
            raw_count = len(layout.content_lines(page))
            lines = layout.page_lines(page, drop_set)
            hf_lines_dropped += raw_count - len(lines)
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
        "hf_dropped": len(drop_set),            # 模式条数
        "hf_texts": sorted(drop_set),
        "hf_lines_dropped": hf_lines_dropped,   # 实际删掉的行数,与上面含义不同
        "hf_detection_skipped": total_pages < layout.HF_MIN_PAGES,
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
    if report["hf_detection_skipped"]:
        print(f"页眉页脚     页数不足 {layout.HF_MIN_PAGES},"
              f"跳过页眉页脚重复检测(未删任何行)")
    else:
        print(f"剔除页眉页脚  {report['hf_dropped']} 条模式,"
              f"实际删除 {report['hf_lines_dropped']} 行")
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
                        help="img=表格当图(默认,剔正文留锚) md=保留表格原始文字于正文(阶段 1 暂不转 markdown)")
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
