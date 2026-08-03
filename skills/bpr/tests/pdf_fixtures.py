from __future__ import annotations

import fitz

A4_W, A4_H = 595, 842


def build_report_pdf(path, npages=5, two_col=True, header=True, cover=True,
                     creation_date="D:20260801093000+08'00'",
                     title="Microsoft Word - draft.doc",
                     author="中金公司研究部", cover_date=True):
    """合成一份研报样子的 PDF。

    header=True     → 每页加相同页眉「中金公司研究部」+ 含页码的页脚
    two_col=True    → 正文分左右两栏(x=60 / x=320)
    cover=True      → 第 1 页加 28pt 大标题(与 cover_date 控制的日期)
    cover_date=True → 封面印「2026年7月15日」;False 时封面有标题但无日期
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
            if cover_date:
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


def build_pdf_with_table(path, npages=4):
    """含一个 3x3 网格表的 PDF,表格在第 1 页正文中部。"""
    doc = fitz.open()
    for pno in range(npages):
        page = doc.new_page(width=A4_W, height=A4_H)
        page.insert_text((60, 120), "Some body text above the table", fontsize=11)
        if pno == 0:
            x0, y0, cw, ch = 60, 200, 150, 30
            for r in range(4):
                page.draw_line(fitz.Point(x0, y0 + r * ch),
                               fitz.Point(x0 + 3 * cw, y0 + r * ch))
            for c in range(4):
                page.draw_line(fitz.Point(x0 + c * cw, y0),
                               fitz.Point(x0 + c * cw, y0 + 3 * ch))
            for r in range(3):
                for c in range(3):
                    page.insert_text((x0 + c * cw + 6, y0 + r * ch + 20),
                                     f"r{r}c{c}", fontsize=9)
        page.insert_text((60, 400), "Body text below the table", fontsize=11)
    doc.save(str(path))
    doc.close()


# 页高 842 × 8% = 67.4 → y1 ≤ 67.4 落在上带;y0 ≥ 774.6 落在下带。
# 带内文字刻意用「不含数字的互异词」:norm_hf 会把数字替成 #,
# 若写成 "unique top p1" 则每页归一化后完全相同,反而是「真重复」该被删。
BAND_WORDS = ["alpha", "beta", "gamma", "delta", "epsilon",
              "zeta", "eta", "theta", "iota", "kappa"]


def build_band_content_pdf(path, npages=5, repeated_hf=True):
    """上下 8% 带内既有「每页重复的页眉页脚」,也有「每页互异的真正文」。

    用来钉住:带内的非重复内容必须保留,只有跨页重复的那两条才准删。
    """
    doc = fitz.open()
    for pno in range(npages):
        word = BAND_WORDS[pno % len(BAND_WORDS)]
        page = doc.new_page(width=A4_W, height=A4_H)
        if repeated_hf:
            page.insert_text((60, 30), "REPEATED HEADER LINE", fontsize=8)
            page.insert_text((60, 828), "REPEATED FOOTER LINE", fontsize=8)
        page.insert_text((60, 60), f"unique top {word}", fontsize=8)
        page.insert_text((60, 800), f"unique bottom {word}", fontsize=8)
        for i in range(6):
            page.insert_text((60, 200 + i * 16),
                             f"middle body {word} line {i} of running text",
                             fontsize=10)
    doc.save(str(path))
    doc.close()


def build_pdf_with_blank_pages(path, npages=20, blank_pages=(17, 18, 19)):
    """整页图/整页扫描的模拟:blank_pages 里的页没有文字层,其余正常。

    17/18/19 缺文字层 → ratio 0.85 → detect_mode 判 "text",
    正是「mode 是 text 却有页需要 OCR」这个静默丢内容的场景。
    """
    doc = fitz.open()
    for pno in range(1, npages + 1):
        page = doc.new_page(width=A4_W, height=A4_H)
        if pno in blank_pages:
            continue
        for i in range(8):
            page.insert_text((60, 120 + i * 16),
                             f"page {pno} body line {i} with plenty of text here",
                             fontsize=10)
    doc.save(str(path))
    doc.close()


def build_pdf_with_disclaimer(path, npages=6):
    """尾部两页是免责声明段,用来验证截断真的发生。"""
    doc = fitz.open()
    tail = npages - 2
    for pno in range(npages):
        page = doc.new_page(width=A4_W, height=A4_H)
        if pno >= tail:
            page.insert_text((60, 120), "免责声明", fontsize=14, fontname="china-s")
            for i in range(4):
                page.insert_text(
                    (60, 200 + i * 16),
                    "本报告仅供参考,不构成任何投资建议,请阅读全文后自行判断。",
                    fontsize=10, fontname="china-s")
        else:
            for i in range(10):
                page.insert_text((60, 120 + i * 16),
                                 f"body page {pno + 1} line {i} of running text",
                                 fontsize=10)
    doc.save(str(path))
    doc.close()
