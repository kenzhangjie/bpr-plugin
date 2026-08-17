from __future__ import annotations

import pathlib
import sys

import fitz
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import extract_pdf as ep
from pdf_fixtures import (build_band_content_pdf, build_pdf_with_blank_pages,
                          build_pdf_with_disclaimer, build_pdf_with_table,
                          build_report_pdf, unicode_font_path)


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


def test_is_junk_title_rejects_export_tool_default_titles():
    """R2:飞书等导出工具的默认标题('Docs'/'无标题'…)必须一律弃,整串精确匹配。"""
    assert ep.is_junk_title("Docs") is True
    assert ep.is_junk_title("无标题") is True
    assert ep.is_junk_title("Untitled Document") is True
    assert ep.is_junk_title("韩国 UGC 平台内容审核风险说明") is False
    # 含 "Docs" 但不是整串精确匹配,不能被误杀
    assert ep.is_junk_title("Google Docs 使用指南") is False


def test_cover_max_font_text_picks_largest_span(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5)
    d = fitz.open(p)
    assert ep.cover_max_font_text(d[0]) == "中国AI算力产业深度报告"
    d.close()


def test_cover_max_font_text_joins_multi_span_line(tmp_path):
    """实测('韩国 UGC 平台内容审核风险说明.pdf'):中英混排的标题因字体切换被
    fitz 拆成多个 span('韩国 ' / 'UGC ' / '报告标题'),但它们仍是同一行
    (同一 bbox y 区间)。cover_max_font_text 必须返回整行拼接后的文本,
    不能只返回其中一个 span。

    用不同 fontname 的相邻 insert_text 调用重现这个切分:同字体、相邻位置
    的两次调用会被 fitz 合并成单 span(实测验证过),换字体才会真正切出多
    span 但仍归为一行——这与真实 PDF 里 CJK/Latin 字体切换的成因一致。
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 200), "韩国 ", fontsize=20, fontname="china-s")
    page.insert_text((110, 200), "UGC ", fontsize=20, fontname="helv")
    page.insert_text((160, 200), "报告标题", fontsize=20, fontname="china-s")
    p = tmp_path / "multispan.pdf"
    doc.save(str(p))
    doc.close()

    d = fitz.open(p)
    # 前提断言:确实被切成了多个 span,而非我们要验证的行为本身。
    line = d[0].get_text("dict")["blocks"][0]["lines"][0]
    assert len(line["spans"]) == 3
    assert ep.cover_max_font_text(d[0]) == "韩国 UGC 报告标题"
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


def test_build_metadata_source_reports_pdf_none_when_date_missing(tmp_path):
    """封面无日期 + 无 CreationDate + 有标题 → source 必须是 pdf:none。

    回落成 title 的命中策略(pdf:cover-maxfont)会让 ingest.md 那条
    「看到 pdf:none / pdf:info-creationdate 就主动问用户要真实日期」的守卫
    在最需要问的场景下不触发,直接踩「绝不静默用今天」的硬规则。
    """
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5, cover_date=False, creation_date="")
    d = fitz.open(p)
    meta, conf = ep.build_metadata(d, p)
    d.close()
    assert meta["date"] is None
    assert meta["title"] == "中国AI算力产业深度报告"      # 标题确实抓到了
    assert meta["source"] == "pdf:none"
    assert conf["date"] == "low"


def test_build_metadata_rejects_junk_info_title(tmp_path):
    p = tmp_path / "r.pdf"
    build_report_pdf(p, npages=5, title="Microsoft Word - draft.doc")
    d = fitz.open(p)
    meta, conf = ep.build_metadata(d, p)
    d.close()
    assert meta["title"] == "中国AI算力产业深度报告"


def test_cover_max_font_text_strips_zero_width_chars(tmp_path):
    """真实 PDF 实测暴露('韩国 UGC 平台内容审核风险说明.pdf'):标题行尾带
    U+200B(飞书等导出工具常见)。cover_max_font_text 自己拼行文本,没有走
    pdf_layout._iter_lines 那条已有的零宽字符剔除,原样漏进了标题。
    """
    font = unicode_font_path()
    if font is None:
        pytest.skip("本机找不到能保留零宽字符编码的 Unicode 字体,跳过")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="F0", fontfile=font)
    page.insert_text((60, 200), "真实标题​", fontsize=20, fontname="F0")
    p = tmp_path / "zw.pdf"
    doc.save(str(p))
    doc.close()

    d = fitz.open(p)
    assert ep.cover_max_font_text(d[0]) == "真实标题"
    d.close()


def test_build_metadata_excludes_cross_page_watermark_from_title(tmp_path):
    """缺陷 A 回归钉:水印字号比真标题大、且跨页(此处每页)重复,不能被当成标题。

    实测('韩国 UGC 平台内容审核风险说明.pdf',22 页):品牌水印 52.6pt 出现在
    22/22 页,真标题 25.5pt 只在封面出现 0 次跨页重复。修复前 cover_max_font_text
    只看字号最大,必然选中水印——此断言在修复前会失败,断言值是 "WATERMARK"。
    """
    doc = fitz.open()
    for pno in range(5):
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 400), "WATERMARK", fontsize=40)
        if pno == 0:
            page.insert_text((60, 200), "真实报告标题", fontsize=20, fontname="china-s")
    p = tmp_path / "watermark.pdf"
    doc.save(str(p))
    doc.close()

    d = fitz.open(p)
    meta, conf = ep.build_metadata(d, p)
    d.close()
    assert meta["title"] == "真实报告标题"


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


def test_run_raises_when_text_mode_still_has_pages_without_text(tmp_path):
    """TEXT_RATIO_HI=0.8 允许 20% 的页完全没有文字层却仍判 "text"。

    「正文有文字层、图表页/附录页是整页扫描图」正是研报最常见形态。
    这些页 pages.jsonl 为空、body 里被 if text 跳过、stdout 全程无提示——
    需要 OCR 的判断必须与 mode 解耦。
    """
    p = tmp_path / "img.pdf"
    build_pdf_with_blank_pages(p, npages=20, blank_pages=(17, 18, 19))
    with pytest.raises(ep.PdfInputError) as excinfo:
        ep.run(p, tmp_path / "w")
    assert excinfo.value.exit_code == 3
    msg = str(excinfo.value)
    assert "17" in msg and "18" in msg and "19" in msg
    assert "ocr_pdf.py" in msg


def test_run_reports_actual_hf_lines_dropped(tmp_path):
    """模式条数 ≠ 实际删除行数,两者都要报。"""
    pdf = tmp_path / "b.pdf"
    build_band_content_pdf(pdf, npages=5)
    work = tmp_path / "w"
    report = ep.run(pdf, work)
    # 每页一条页眉 + 一条页脚 × 5 页 = 10 行
    assert report["hf_dropped"] == 2
    assert report["hf_lines_dropped"] == 10


def test_run_keeps_band_content_out_of_thin_air(tmp_path):
    """端到端:带内的非重复真正文必须出现在 body.txt 里。"""
    pdf = tmp_path / "b.pdf"
    build_band_content_pdf(pdf, npages=5)
    work = tmp_path / "w"
    ep.run(pdf, work)
    body = (work / "body.txt").read_text(encoding="utf-8")
    assert "unique top beta" in body
    assert "unique bottom beta" in body
    assert "REPEATED HEADER LINE" not in body
    assert "REPEATED FOOTER LINE" not in body


def test_run_body_not_gutted_by_reversed_drop_filter(tmp_path):
    """drop_set 若拿去过滤正文区,同模板的正文行会跨页归一成同串而被整体删空。"""
    doc = fitz.open()
    for pno in range(5):
        page = doc.new_page(width=595, height=842)
        for i in range(38):
            page.insert_text((60, 90 + i * 18),
                             f"body line {i} page {pno + 1} of running report text",
                             fontsize=9)
    pdf = tmp_path / "tmpl.pdf"
    doc.save(str(pdf))
    doc.close()

    work = tmp_path / "w"
    report = ep.run(pdf, work)
    body = (work / "body.txt").read_text(encoding="utf-8")
    assert len(body.strip()) > 1000
    assert "body line 0 page 1" in body
    assert report["hf_lines_dropped"] == 0


def test_run_short_document_skips_hf_detection_and_says_so(tmp_path, capsys):
    """页数 < HF_MIN_PAGES 时跳过重复检测,且必须在 stdout 说清楚未删任何行。"""
    pdf = tmp_path / "b.pdf"
    build_band_content_pdf(pdf, npages=2)
    code = ep.main([str(pdf), "--workdir", str(tmp_path / "w")])
    assert code == 0
    out = capsys.readouterr().out
    assert str(ep.layout.HF_MIN_PAGES) in out
    assert "跳过" in out
    body = (tmp_path / "w" / "body.txt").read_text(encoding="utf-8")
    assert "unique top alpha" in body
    assert "REPEATED HEADER LINE" in body      # 不敢判定就不删


def test_run_truncation_actually_shortens_body_and_is_reported(tmp_path, capsys):
    pdf = tmp_path / "d.pdf"
    build_pdf_with_disclaimer(pdf, npages=6)

    full = ep.run(pdf, tmp_path / "full", truncate=False)
    assert full["truncated_from"] is None
    assert full["truncated_pages"] == 0

    code = ep.main([str(pdf), "--workdir", str(tmp_path / "cut")])
    assert code == 0
    out = capsys.readouterr().out
    assert "已截断" in out and "第 5 页" in out

    cut_body = (tmp_path / "cut" / "body.txt").read_text(encoding="utf-8")
    full_body = (tmp_path / "full" / "body.txt").read_text(encoding="utf-8")
    assert len(cut_body) < len(full_body)
    assert "免责声明" in full_body
    assert "免责声明" not in cut_body


def test_run_no_truncate_flag_keeps_disclaimer(tmp_path, capsys):
    pdf = tmp_path / "d.pdf"
    build_pdf_with_disclaimer(pdf, npages=6)
    code = ep.main([str(pdf), "--workdir", str(tmp_path / "w"), "--no-truncate"])
    assert code == 0
    out = capsys.readouterr().out
    assert "已截断" not in out
    body = (tmp_path / "w" / "body.txt").read_text(encoding="utf-8")
    assert "免责声明" in body


def test_run_table_anchor_end_to_end(tmp_path):
    """tables_by_page 分组 → strip_table_lines → body 里出现锚记。"""
    import json
    pdf = tmp_path / "t.pdf"
    build_pdf_with_table(pdf, npages=4)
    work = tmp_path / "w"
    report = ep.run(pdf, work)

    assert report["tables"] == 1
    assert report["table_anchors"] == 1
    body = (work / "body.txt").read_text(encoding="utf-8")
    assert "[[table:p1-0]]" in body
    assert "r0c0" not in body           # 表格文字层已从正文剔除
    tables = json.loads((work / "tables.json").read_text(encoding="utf-8"))
    assert len(tables) == 1 and tables[0]["page"] == 1


def test_run_tables_md_mode_keeps_table_text_and_writes_no_bbox(tmp_path):
    """--tables md:不采 bbox、不留锚,表格原始文字留在正文里。"""
    import json
    pdf = tmp_path / "t.pdf"
    build_pdf_with_table(pdf, npages=4)
    work = tmp_path / "w"
    report = ep.run(pdf, work, tables_mode="md")

    assert report["tables"] == 0
    assert report["table_anchors"] == 0
    body = (work / "body.txt").read_text(encoding="utf-8")
    assert "[[table:" not in body
    assert "r0c0" in body
    assert json.loads((work / "tables.json").read_text(encoding="utf-8")) == []


def test_main_tables_md_flag_wires_through(tmp_path, capsys):
    pdf = tmp_path / "t.pdf"
    build_pdf_with_table(pdf, npages=4)
    code = ep.main([str(pdf), "--workdir", str(tmp_path / "w"), "--tables", "md"])
    assert code == 0
    body = (tmp_path / "w" / "body.txt").read_text(encoding="utf-8")
    assert "r0c0" in body
    assert "[[table:" not in body
