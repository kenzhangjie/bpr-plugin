from __future__ import annotations

import pathlib
import sys

import fitz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pdf_layout as pl
import pytest

from pdf_fixtures import (build_band_content_pdf, build_bullet_everywhere_pdf,
                          build_pdf_with_zero_width_chars, build_report_pdf,
                          unicode_font_path)


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


def test_content_lines_keeps_everything_including_bands(tmp_path):
    """content_lines 是内容的唯一真源:一行都不许少。"""
    p = tmp_path / "b.pdf"
    build_band_content_pdf(p, npages=5)
    doc = fitz.open(p)
    texts = [l[4] for l in pl.content_lines(doc[1])]
    doc.close()
    assert "REPEATED HEADER LINE" in texts
    assert "REPEATED FOOTER LINE" in texts
    assert "unique top beta" in texts
    assert "unique bottom beta" in texts
    assert sum(1 for t in texts if t.startswith("middle body")) == 6


def test_page_lines_keeps_non_repeated_band_content(tmp_path):
    """回归钉:页边距紧于 8% 时,带内的真正文必须留下。

    设计只授权删「≥60% 页面重复」的行。无条件剔整条带会静默吃掉
    每页首尾的真正文——这是修复前必然失败的那条断言。
    """
    p = tmp_path / "b.pdf"
    build_band_content_pdf(p, npages=5)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    texts = [l[4] for l in pl.page_lines(doc[1], drop)]
    doc.close()
    assert "unique top beta" in texts
    assert "unique bottom beta" in texts


def test_page_lines_keeps_band_content_in_short_document(tmp_path):
    """2 页文档:样本不足跳过重复检测 → 一行都不许删,带内也一样。"""
    p = tmp_path / "b.pdf"
    build_band_content_pdf(p, npages=2)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    texts = [l[4] for l in pl.page_lines(doc[0], drop)]
    all_texts = [l[4] for l in pl.content_lines(doc[0])]
    doc.close()
    assert drop == set()
    assert len(texts) == len(all_texts)
    assert "unique top alpha" in texts
    assert "unique bottom alpha" in texts
    assert "REPEATED HEADER LINE" in texts     # 只 2 页,不敢判定,保守留下


def test_page_lines_drops_repeated_hf(tmp_path):
    """过滤方向必须对着「跨页重复的带内行」,而不是对着正文。"""
    p = tmp_path / "b.pdf"
    build_band_content_pdf(p, npages=5)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    texts = [l[4] for l in pl.page_lines(doc[1], drop)]
    doc.close()
    # 真页眉页脚(每页重复)确实不在结果里
    assert "REPEATED HEADER LINE" not in texts
    assert "REPEATED FOOTER LINE" not in texts
    # 只出现在单页的带内行仍在结果里
    assert "unique top beta" in texts


def test_page_lines_running_hf_filter_is_position_aware(tmp_path):
    """R1 回归钉:同一文本('•')既跨页重复出现在带内、也出现在正文区。

    过滤必须同时满足「位置落在带内」且「文本在 drop_set 里」才删——只看文本
    会把正文里同形的行也删掉(实测:'•' 被判成页眉模式后,239 行 '•' 被删,
    219 行来自正文区)。修复前此断言必然失败:带内、正文区的 '•' 会被一起删空。
    """
    if unicode_font_path() is None:
        pytest.skip("本机找不到能保留 '•' 编码的 Unicode 字体,跳过")
    p = tmp_path / "bullet.pdf"
    build_bullet_everywhere_pdf(p, npages=5)
    doc = fitz.open(p)
    drop = pl.find_repeated_hf(doc)
    assert "•" in drop     # 前提:'•' 确实被判成跨页重复的页眉模式
    texts = [l[4] for l in pl.page_lines(doc[1], drop)]
    doc.close()
    assert texts.count("•") == 1              # 带内那条被删,正文区那条保留
    assert "body bullet item 2" in texts       # 正文其余内容原样保留


def test_content_lines_strips_zero_width_chars(tmp_path):
    """R3 回归钉:零宽空格(飞书导出常见)不许原样进产出行文本。"""
    if unicode_font_path() is None:
        pytest.skip("本机找不到能保留零宽字符编码的 Unicode 字体,跳过")
    p = tmp_path / "zw.pdf"
    build_pdf_with_zero_width_chars(p)
    doc = fitz.open(p)
    texts = [l[4] for l in pl.content_lines(doc[0])]
    doc.close()
    assert texts
    assert all("​" not in t for t in texts)
    assert any("bodyline with zerowidth space" in t for t in texts)


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


def test_lines_to_paragraphs_isolates_heading_with_zero_whitespace():
    """标题上下留白为 0 时也必须独立成段。

    y0 当锚点时行距被字号污染:大字号标题的 y0 被上抬,它前后的 delta 被压小,
    两条 delta 规则全部失灵,标题就粘进相邻段落。行高(y1-y0)是字号的代理,
    跟「页面中位行高」比即可把标题揪出来。
    """
    lines = [
        (60, 100, 300, 112, "body line one"),       # 行高 12
        (60, 114, 300, 126, "body line two"),       # 行高 12
        (60, 128, 300, 144, "SECTION TITLE"),       # 行高 16 → 高行
        (60, 146, 300, 158, "body line three"),     # 行高 12
        (60, 160, 300, 172, "body line four"),      # 行高 12
    ]
    # 全部 delta 都 ≤ 中位行距 × 1.3,单靠间距规则一段都断不出来
    paras = pl.lines_to_paragraphs(lines)
    assert paras == ["body line one body line two",
                     "SECTION TITLE",
                     "body line three body line four"]


def test_lines_to_paragraphs_short_line_does_not_split():
    """矮行(脚注上标被 fitz 切成独立行)不得触发断段。

    这是「跟页面中位行高比」而不是「跟相邻行行高比」的原因:相邻比较会被
    上标坑成一页切五段。
    """
    lines = [
        (60, 100, 300, 112, "uniform line one"),    # 行高 12
        (60, 114, 300, 126, "uniform line two"),
        (300, 128, 306, 137, "1"),                  # 行高 9 → 矮行(上标)
        (60, 142, 300, 154, "uniform line three"),
        (60, 156, 300, 168, "uniform line four"),
    ]
    paras = pl.lines_to_paragraphs(lines)
    assert len(paras) == 1


def test_lines_to_paragraphs_single_line():
    paras = pl.lines_to_paragraphs([(60, 100, 200, 110, "only line")])
    assert paras == ["only line"]


def test_lines_to_paragraphs_empty():
    assert pl.lines_to_paragraphs([]) == []
