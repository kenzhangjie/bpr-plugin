from __future__ import annotations

import pathlib
import sys

import fitz
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import extract_pdf as ep
from pdf_fixtures import build_report_pdf, build_pdf_with_table


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


def test_collect_tables_skips_malformed_page_with_warning(tmp_path, monkeypatch, capsys):
    """畸形页的 find_tables() 抛异常时,该页被跳过但 stderr 有告警。"""
    p = tmp_path / "t.pdf"
    build_pdf_with_table(p, npages=2)
    d = fitz.open(p)

    # 让第 2 页的 find_tables() 抛 RuntimeError
    orig_find_tables = fitz.Page.find_tables
    call_count = [0]

    def patched_find_tables(self):
        call_count[0] += 1
        if call_count[0] == 2:  # 第 2 页(1-indexed 第 2 页是 0-indexed 第 1 页)
            raise RuntimeError("boom")
        return orig_find_tables(self)

    monkeypatch.setattr(fitz.Page, "find_tables", patched_find_tables)

    tables = ep.collect_tables(d)
    d.close()

    # 验证:
    # (a) 函数不抛异常
    assert tables is not None
    # (b) 第 1 页的表格在结果里,第 2 页没有(被跳过了)
    assert len(tables) == 1
    assert tables[0]["page"] == 1
    # (c) stderr 有告警,含页号与异常类型
    captured = capsys.readouterr()
    assert "2" in captured.err
    assert "RuntimeError" in captured.err


def test_collect_tables_reraises_attribute_error(tmp_path, monkeypatch):
    """AttributeError 不被吞,照常抛出(编程错误)。"""
    p = tmp_path / "t.pdf"
    build_pdf_with_table(p, npages=1)
    d = fitz.open(p)

    def boom_find_tables(self):
        raise AttributeError("find_tables method missing")

    monkeypatch.setattr(fitz.Page, "find_tables", boom_find_tables)

    with pytest.raises(AttributeError):
        ep.collect_tables(d)

    d.close()


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
