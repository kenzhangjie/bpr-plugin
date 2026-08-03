from __future__ import annotations

import fitz

A4_W, A4_H = 595, 842


def build_report_pdf(path, npages=5, two_col=True, header=True, cover=True,
                     creation_date="D:20260801093000+08'00'",
                     title="Microsoft Word - draft.doc",
                     author="中金公司研究部"):
    """合成一份研报样子的 PDF。

    header=True  → 每页加相同页眉「中金公司研究部」+ 含页码的页脚
    two_col=True → 正文分左右两栏(x=60 / x=320)
    cover=True   → 第 1 页加 28pt 大标题与「2026年7月15日」
    """
    doc = fitz.open()
    for pno in range(npages):
        page = doc.new_page(width=A4_W, height=A4_H)
        if header:
            page.insert_text((60, 40), "中金公司研究部", fontsize=8, fontname="china-s")
            page.insert_text(
                (60, 810),
                f"请务必阅读正文之后的免责声明部分  第 {pno + 1} 页 共 {npages} 页",
                fontsize=8, fontname="china-s")
        if cover and pno == 0:
            page.insert_text((60, 200), "中国AI算力产业深度报告", fontsize=28, fontname="china-s")
            page.insert_text((60, 240), "2026年7月15日", fontsize=11, fontname="china-s")
        page.insert_text((60, 90), f"Heading {pno + 1} spanning the whole width here",
                         fontsize=16)
        for i in range(6):
            page.insert_text((60, 130 + i * 20), f"left p{pno + 1} line{i} text", fontsize=10)
            if two_col:
                page.insert_text((320, 130 + i * 20), f"right p{pno + 1} line{i} text",
                                 fontsize=10)
    doc.set_metadata({"title": title, "author": author, "creationDate": creation_date})
    doc.save(str(path))
    doc.close()
