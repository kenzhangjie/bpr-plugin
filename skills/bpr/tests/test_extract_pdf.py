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
