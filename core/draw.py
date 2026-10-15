"""Text and shape drawing with correct shaping for Latin, Cyrillic, Arabic, Persian and Devanagari.

Everything is drawn with Pillow's Raqm layout engine (HarfBuzz + FriBiDi), so
joined Arabic/Persian letters and Devanagari conjuncts render properly.
Images are drawn at 2x and downscaled for smooth edges.
"""

from functools import lru_cache
from pathlib import Path

import logging

from PIL import Image, ImageDraw, ImageFont, features

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
RTL = {"ar", "fa"}
SCALE = 2
LAYOUT = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
if LAYOUT == ImageFont.Layout.BASIC:
    logging.warning("Pillow was built without Raqm: Persian, Arabic and Hindi text in charts will not be shaped. "
                    "Install a recent Pillow wheel (pip install -U pillow).")

# Reference palette (dataviz skill), light surface.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8984"
GRID = "#e4e3df"
BAND = "#efeee9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def font_file(lang):
    return {"fa": "Vazirmatn.ttf", "ar": "Vazirmatn.ttf", "hi": "NotoSansDevanagari.ttf"}.get(lang, "NotoSans.ttf")


@lru_cache(maxsize=256)
def font(lang, size, weight="Regular"):
    f = ImageFont.truetype(str(FONTS / font_file(lang)), int(size * SCALE), layout_engine=LAYOUT)
    f.set_variation_by_name(weight)
    return f


class Canvas:
    """A drawing surface in logical pixels (internally SCALE x larger)."""

    def __init__(self, width, height, lang, bg=SURFACE):
        self.w, self.h, self.lang = width, height, lang
        self.rtl = lang in RTL
        self.img = Image.new("RGB", (width * SCALE, height * SCALE), bg)
        self.d = ImageDraw.Draw(self.img)

    # --- geometry -------------------------------------------------------
    def x(self, x):
        """Mirror an x coordinate for right-to-left layouts."""
        return self.w - x if self.rtl else x

    def rect(self, x0, y0, x1, y1, fill, radius=0):
        x0, x1 = sorted((x0, x1))
        box = [x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE]
        if radius:
            self.d.rounded_rectangle(box, radius * SCALE, fill=fill)
        else:
            self.d.rectangle(box, fill=fill)

    def line(self, pts, fill, width=1):
        self.d.line([(px * SCALE, py * SCALE) for px, py in pts], fill=fill, width=max(1, int(width * SCALE)))

    def polygon(self, pts, fill=None, outline=None, width=1):
        p = [(px * SCALE, py * SCALE) for px, py in pts]
        if fill:
            self.d.polygon(p, fill=fill)
        if outline:
            self.d.line(p + [p[0]], fill=outline, width=int(width * SCALE), joint="curve")

    def circle(self, cx, cy, r, fill, outline=None, width=0):
        self.d.ellipse([(cx - r) * SCALE, (cy - r) * SCALE, (cx + r) * SCALE, (cy + r) * SCALE],
                       fill=fill, outline=outline, width=int(width * SCALE))

    # --- text -----------------------------------------------------------
    def _dir(self, s):
        return "rtl" if self.rtl and any("؀" <= c <= "ۿ" for c in s) else None

    def measure(self, s, size, weight="Regular"):
        if self.rtl:
            s = s.replace("·", "–")
        f = font(self.lang, size, weight)
        return f.getlength(s, direction=self._dir(s) if LAYOUT == ImageFont.Layout.RAQM else None) / SCALE

    def text(self, x, y, s, size, color=INK, weight="Regular", anchor="la", halo=None, halo_width=4):
        """Draw text. anchor uses Pillow codes ('la' left-top, 'ra' right-top, 'ma' centre, 'lm' left-middle...).
        halo: an outline colour that keeps the text readable on top of marks."""
        if self.rtl:
            s = s.replace("·", "–")   # in Vazirmatn a middle dot looks like a Persian zero
        f = font(self.lang, size, weight)
        direction = self._dir(s) if LAYOUT == ImageFont.Layout.RAQM else None
        extra = {"stroke_width": int(halo_width * SCALE), "stroke_fill": halo} if halo else {}
        self.d.text((x * SCALE, y * SCALE), s, font=f, fill=color, anchor=anchor, direction=direction, **extra)

    def text_start(self, x, y, s, size, color=INK, weight="Regular", v="a"):
        """Text aligned to the reading-start edge at logical x (left in LTR, right in RTL)."""
        self.text(self.x(x), y, s, size, color, weight, ("r" if self.rtl else "l") + v)

    def text_end(self, x, y, s, size, color=INK, weight="Regular", v="a"):
        self.text(self.x(x), y, s, size, color, weight, ("l" if self.rtl else "r") + v)

    def wrap(self, s, size, max_w, weight="Regular"):
        lines, cur = [], ""
        for word in s.split():
            trial = f"{cur} {word}".strip()
            if cur and self.measure(trial, size, weight) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines

    def paragraph(self, x, y, s, size, max_w, color=INK, weight="Regular", leading=1.5):
        """Draw wrapped text from the reading-start edge; returns the y below it."""
        for ln in self.wrap(s, size, max_w, weight):
            self.text_start(x, y, ln, size, color, weight)
            y += size * leading
        return y

    def save(self, path=None, fmt="PNG"):
        out = self.img.resize((self.w, self.h), Image.LANCZOS) if SCALE != 1 else self.img
        if path:
            out.save(path, fmt)
        return out

    def png(self):
        import io
        buf = io.BytesIO()
        self.save().save(buf, "PNG", optimize=True)
        return buf.getvalue()


def _blend(fg, bg, alpha):
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a * alpha + c * (1 - alpha)):02x}" for a, c in zip(f, b))


Canvas.blend = staticmethod(_blend)


def bar_text(pct, width=10):
    """A text progress bar for chat messages."""
    filled = max(0, min(width, round(pct / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)
