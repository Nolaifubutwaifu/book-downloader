"""Book -> PDF via fpdf2.

Produces a title page, one chapter per section with sidebar bookmarks (PDF
outline), and page numbers. Uses a system serif TTF when one exists so accented
characters render properly; otherwise falls back to the built-in Helvetica with
text coerced to cp1252.
"""

import datetime
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

# (regular, bold) candidates, best first. Any hit is used for the whole book.
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Georgia.ttf",
     "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Times New Roman.ttf",
     "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
    ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/georgiab.ttf"),
    ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
]

CP1252_FIXUPS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
})

# Symbols the bundled serif fonts (Georgia/Times) lack a glyph for, mapped to
# ASCII so they render instead of silently dropping. Applied on every path,
# since this is about the font, not the byte encoding.
SYMBOL_FIXUPS = str.maketrans({
    "\u2192": "->", "\u2190": "<-", "\u2191": "^", "\u2193": "v", "\u2194": "<->",
    "\u21d2": "=>", "\u21d0": "<=", "\u2022": "-", "\u00b7": "-",
    "\u00d7": "x", "\u00f7": "/", "\u2011": "-", "\u2012": "-", "\u2015": "-",
    "\u2033": '"', "\u2032": "'",
})


class _BookPDF(FPDF):
    footer_font = "helvetica"

    def footer(self):
        if self.page_no() == 1:
            return  # no page number on the title page
        self.set_y(-15)
        self.set_font(self.footer_font, size=9)
        self.set_text_color(120)
        self.cell(0, 10, str(self.page_no()), align="C")
        self.set_text_color(0)


def _find_font():
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists():
            return regular, (bold if Path(bold).exists() else regular)
    return None, None


def build_pdf(book):
    """Render a Book to PDF bytes."""
    pdf = _BookPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(22, 20, 22)

    regular, bold = _find_font()
    if regular:
        pdf.add_font("book", "", regular)
        pdf.add_font("book", "B", bold)
        family, unicode_ok = "book", True
    else:
        family, unicode_ok = "helvetica", False
    pdf.footer_font = family

    def txt(s):
        s = s.translate(SYMBOL_FIXUPS)
        if unicode_ok:
            return s
        s = s.translate(CP1252_FIXUPS)
        return s.encode("cp1252", "replace").decode("cp1252")

    pdf.set_title(book.title)
    if book.author:
        pdf.set_author(book.author)

    # ---- title page ----
    pdf.add_page()
    pdf.ln(60)
    pdf.set_font(family, "B", 30)
    pdf.multi_cell(0, 14, txt(book.title), align="C")
    if book.author:
        pdf.ln(6)
        pdf.set_font(family, "", 16)
        pdf.multi_cell(0, 9, txt(book.author), align="C")
    pdf.ln(30)
    pdf.set_font(family, "", 9)
    pdf.set_text_color(120)
    meta = f"Source: {book.source_url}\nDownloaded {datetime.date.today().isoformat()} with book-downloader"
    pdf.multi_cell(0, 5, txt(meta), align="C")
    pdf.set_text_color(0)

    # ---- chapters ----
    for chapter in book.chapters:
        pdf.add_page()
        pdf.start_section(txt(chapter.title))  # sidebar bookmark
        pdf.set_font(family, "B", 16)
        pdf.multi_cell(0, 8, txt(chapter.title))
        pdf.ln(4)
        pdf.set_font(family, "", 11)
        for block in chapter.blocks:
            pdf.multi_cell(0, 5.6, txt(block))
            if not chapter.verse:
                pdf.ln(2.2)

    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)


def build_pdf_to(book, path):
    Path(path).write_bytes(build_pdf(book))


def pdf_bytesio(book):
    return BytesIO(build_pdf(book))
