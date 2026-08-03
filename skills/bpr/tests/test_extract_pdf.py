from __future__ import annotations

import pathlib
import sys

import fitz
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fetch"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import extract_pdf as ep
from pdf_fixtures import build_report_pdf


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
