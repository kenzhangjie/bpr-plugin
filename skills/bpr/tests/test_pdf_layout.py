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
