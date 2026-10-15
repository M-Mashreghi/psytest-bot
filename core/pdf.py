"""A small flowing-layout PDF writer built on the same text engine as the charts.

Pages are rendered as A4 images (150 dpi) so every script is shaped correctly,
then bundled into one PDF.
"""

import io
from datetime import date

from PIL import Image

from core.draw import INK, INK_2, INK_3, GRID, Canvas
from core.i18n import num

W, H = 1240, 1754          # A4 at 150 dpi
MARGIN = 100


class Document:
    def __init__(self, lang, title, footer):
        self.lang, self.title, self.footer = lang, title, footer
        self.pages = []
        self._new_page()

    def _new_page(self):
        self.c = Canvas(W, H, self.lang, bg="#ffffff")
        self.pages.append(self.c)
        self.y = MARGIN
        if len(self.pages) > 1:
            self.c.text_start(MARGIN, 50, self.title, 16, INK_3)
            self.c.line([(MARGIN, 80), (W - MARGIN, 80)], GRID, 1)
            self.y = 120

    def _room(self, h):
        if self.y + h > H - MARGIN - 20:
            self._new_page()

    def cover(self, subtitle, meta_lines):
        c = self.c
        c.rect(0, 0, W, 14, "#2a78d6")
        self.y = 160
        for ln in c.wrap(self.title, 58, W - 2 * MARGIN, "Bold"):
            c.text_start(MARGIN, self.y, ln, 58, INK, "Bold")
            self.y += 80
        self.y += 10
        self.y = c.paragraph(MARGIN, self.y, subtitle, 26, W - 2 * MARGIN, INK_2) + 20
        for m in meta_lines:
            c.text_start(MARGIN, self.y, m, 22, INK_2)
            self.y += 36
        self.y += 30

    def heading(self, text, color=INK):
        self._room(140)
        self.y += 20
        for ln in self.c.wrap(text, 36, W - 2 * MARGIN, "Bold"):
            self.c.text_start(MARGIN, self.y, ln, 36, color, "Bold")
            self.y += 52
        self.y += 8

    def subheading(self, text, color=INK):
        self._room(90)
        self.y += 10
        self.c.text_start(MARGIN, self.y, text, 26, color, "SemiBold")
        self.y += 42

    def paragraph(self, text, size=22, color=INK, weight="Regular"):
        for ln in self.c.wrap(text, size, W - 2 * MARGIN, weight):
            self._room(size * 1.6)
            self.c.text_start(MARGIN, self.y, ln, size, color, weight)
            self.y += size * 1.6
        self.y += size * 0.6

    def image(self, png, width=W - 2 * MARGIN):
        img = Image.open(io.BytesIO(png)).convert("RGB")
        h = round(img.height * width / img.width)
        self._room(h + 20)
        img = img.resize((width * 2, h * 2), Image.LANCZOS)
        x = MARGIN
        self.c.img.paste(img, (x * 2, int(self.y * 2)))
        self.y += h + 24

    def page_break(self):
        self._new_page()

    def bytes(self):
        out = []
        total = len(self.pages)
        for i, c in enumerate(self.pages, start=1):
            c.text(W / 2, H - 55, f"{num(self.lang, i)} / {num(self.lang, total)}", 16, INK_3, anchor="ma")
            c.text_start(MARGIN, H - 55, self.footer, 16, INK_3)
            out.append(c.save())
        buf = io.BytesIO()
        out[0].save(buf, "PDF", save_all=True, append_images=out[1:], resolution=150, quality=88)
        return buf.getvalue()


def today(lang):
    d = date.today()
    return num(lang, f"{d.year}-{d.month:02d}-{d.day:02d}")
