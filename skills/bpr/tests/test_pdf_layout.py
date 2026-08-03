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
