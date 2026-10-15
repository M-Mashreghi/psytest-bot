"""Reusable chart images (PNG bytes) for test results, in any of the six languages."""

import math

from core.draw import BAND, GRID, INK, INK_2, INK_3, SERIES, Canvas
from core.i18n import num


def _header(c, title, subtitle, pad):
    c.text_start(pad, pad, title, 40, INK, "Bold")
    y = pad + 62
    if subtitle:
        y = c.paragraph(pad, y, subtitle, 22, c.w - 2 * pad, INK_2) + 6
    return y


def radar(title, subtitle, axes, lang, band=None, band_label=None, vmax=100, color=SERIES[0], size=1080):
    """axes: list of (label, value, value_text). Values 0..vmax plotted clockwise from the top."""
    pad = 56
    c = Canvas(size, size, lang)
    top = _header(c, title, subtitle, pad)
    legend_h = 50 if band else 0
    cx, cy = size / 2, (top + size - legend_h) / 2 + 10
    n_axes = len(axes)
    r = min(size / 2 - (190 if n_axes <= 5 else 225), (size - legend_h - top) / 2 - (90 if n_axes <= 5 else 115))
    n = len(axes)
    ang = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]
    sx = -1 if c.rtl else 1   # right-to-left languages go counter-clockwise

    def pt(i, v):
        return cx + sx * r * v / vmax * math.cos(ang[i]), cy + r * v / vmax * math.sin(ang[i])

    if band:
        c.polygon([pt(i, band[1]) for i in range(n)], fill=BAND)
        c.polygon([pt(i, band[0]) for i in range(n)], fill="#fcfcfb")
    for ring in (25, 50, 75, 100):
        c.polygon([pt(i, ring * vmax / 100) for i in range(n)], outline=GRID, width=1.5)
    for i in range(n):
        c.line([(cx, cy), pt(i, vmax)], GRID, 1.5)
    poly = [pt(i, max(v, vmax * 0.02)) for i, (_, v, _) in enumerate(axes)]
    fill = Canvas.blend(color, "#fcfcfb", 0.25)
    c.polygon(poly, fill=fill, outline=color, width=3)
    for x, y in poly:
        c.circle(x, y, 7, color, outline="#fcfcfb", width=2)
    for ring in (25, 50, 75):
        x, y = pt(0, ring * vmax / 100)
        label = ring * vmax / 100
        c.text(x + 6, y, num(lang, int(label)) if label == int(label) else str(label), 15, INK_3, anchor="lm")

    for i, (label, v, vtext) in enumerate(axes):
        x, y = pt(i, vmax * 1.13)
        ca = sx * math.cos(ang[i])
        h = "m" if abs(ca) < 0.3 else ("l" if ca > 0 else "r")
        lines = c.wrap(label, 24, 230, "SemiBold")
        dy = -len(lines) * 30 if math.sin(ang[i]) < -0.3 else (0 if math.sin(ang[i]) > 0.3 else -len(lines) * 15)
        for k, ln in enumerate(lines):
            c.text(x, y + dy + k * 30, ln, 24, INK, "SemiBold", h + "a")
        c.text(x, y + dy + len(lines) * 30 + 2, vtext, 26, color, "Bold", h + "a")

    if band and band_label:
        y = size - pad + 4
        c.rect(c.x(pad), y - 12, c.x(pad + 28), y + 12, BAND, 4)
        c.text_start(pad + 40, y, band_label, 20, INK_2, v="m")
    return c.png()


def bars(title, subtitle, rows, lang, color=SERIES[0], band=None, band_label=None, vmax=100, width=1080, headline=None,
         compact=False, legend=None):
    """Horizontal bars. rows: list of (label, value, value_text, note[, color]). headline: (big_text, small_text).
    compact: label and bar on one line, for long lists. legend: [(color, label)] for per-row colours."""
    pad, row_h = 56, (58 if compact else 96)
    head_extra = 90 if headline else 0
    probe = Canvas(width, 10, lang)
    sub_lines = len(probe.wrap(subtitle, 22, width - 2 * pad)) if subtitle else 0
    top_guess = pad + 62 + sub_lines * 33 + 6
    legend_h = 0
    if legend:
        lx, legend_h = pad, 40
        for _, lab in legend:
            w = 34 + probe.measure(lab, 20) + 30
            if lx + w > width - pad:
                lx, legend_h = pad, legend_h + 36
            lx += w
    height = int(top_guess + head_extra + len(rows) * row_h + (60 if band else 0) + legend_h + pad + 30)
    c = Canvas(width, height, lang)
    y = _header(c, title, subtitle, pad)
    if headline:
        big, small = headline
        c.text_start(pad, y + 4, big, 54, color, "Bold")
        bw = c.measure(big, 54, "Bold")
        c.text_start(pad + bw + 18, y + 30, small, 24, INK_2, "SemiBold")
        y += head_extra
    y += 18
    track0, track1 = pad, width - pad - 110
    for row in rows:
        label, v, vtext, note = row[:4]
        col = row[4] if len(row) > 4 else color
        if compact:
            tr0 = pad + 330
            size = 22
            while size > 15 and c.measure(label, size, "SemiBold") > 315:
                size -= 1
            c.text_start(pad, y + 15, label, size, INK, "SemiBold", v="m")
            by = y + 2
        else:
            tr0 = track0
            c.text_start(pad, y, label, 24, INK, "SemiBold")
            if note:
                c.text_end(width - pad, y + 2, note, 20, INK_2)
            by = y + 42
        c.rect(c.x(tr0), by, c.x(track1), by + 26, "#f1f0ec", 6)
        if band:
            bx0 = tr0 + (track1 - tr0) * band[0] / vmax
            bx1 = tr0 + (track1 - tr0) * band[1] / vmax
            c.rect(c.x(bx0), by, c.x(bx1), by + 26, "#e2e1db")
        x1 = tr0 + (track1 - tr0) * max(v, vmax * 0.015) / vmax
        c.rect(c.x(tr0), by, c.x(x1), by + 26, col, 6)
        c.text_start(x1 + 14, by + 13, vtext, 24, INK, "Bold", v="m")
        y += row_h
    if band and band_label:
        y += 8
        c.rect(c.x(pad), y, c.x(pad + 28), y + 22, "#e2e1db", 4)
        c.text_start(pad + 40, y + 11, band_label, 20, INK_2, v="m")
    if legend:
        y += 14
        lx = pad
        for col, lab in legend:
            w = 34 + c.measure(lab, 20) + 30
            if lx + w > width - pad:
                lx, y = pad, y + 36
            c.rect(c.x(lx), y, c.x(lx + 22), y + 22, col, 4)
            c.text_start(lx + 32, y + 11, lab, 20, INK_2, v="m")
            lx += w
    return c.png()


def _diamond(c, x, y, r, fill, ring="#fcfcfb"):
    c.polygon([(x, y - r - 3), (x + r + 3, y), (x, y + r + 3), (x - r - 3, y)], fill=ring)
    c.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill)


def _pct(lang, v):
    return num(lang, round(v)) + ("٪" if lang in ("fa", "ar") else "%")


def bipolar(title, subtitle, rows, lang, headline=None, legend=None, width=1080):
    """Two-pole preference bars (left pole at the reading start).

    rows: list of dicts with name, left, right (pole labels), value (0 = fully left, 100 = fully right),
          color, and optional markers [(value, "circle" | "diamond")].
    headline: (letters, colors, caption) drawn large and centred, e.g. a 16-type code.
    legend: [(shape, label)] explaining the markers.
    """
    pad, row_h = 56, 168
    probe = Canvas(width, 10, lang)
    sub_lines = len(probe.wrap(subtitle, 22, width - 2 * pad)) if subtitle else 0
    head_h = 190 if headline else 0
    height = int(pad + 62 + sub_lines * 33 + 6 + head_h + 20 + len(rows) * row_h + (60 if legend else 0) + pad)
    c = Canvas(width, height, lang)
    y = _header(c, title, subtitle, pad)
    if headline:
        letters, colors, caption = headline
        size = 112
        widths = [c.measure(ch, size, "Bold") for ch in letters]
        gap = 14
        x = width / 2 - (sum(widths) + gap * (len(letters) - 1)) / 2
        for ch, w, col in zip(letters, widths, colors):   # Latin code: always left to right
            c.text(x, y + 10, ch, size, col, "Bold", "la")
            x += w + gap
        c.text(width / 2, y + 150, caption, 30, INK_2, "SemiBold", "ma")
        y += head_h
    y += 20
    t0, t1 = pad + 10, width - pad - 10
    pos = lambda v: t0 + (t1 - t0) * v / 100
    for r in rows:
        v = r["value"]
        lean_right = v > 50
        c.text(width / 2, y, r["name"], 21, INK_3, "SemiBold", "ma")
        for side, label, strong in (("start", r["left"], not lean_right), ("end", r["right"], lean_right)):
            draw, x = (c.text_start, pad) if side == "start" else (c.text_end, width - pad)
            draw(x, y + 32, label, 27, INK if strong else INK_2, "Bold" if strong else "Regular")
        by = y + 84
        c.rect(c.x(t0), by - 11, c.x(t1), by + 11, "#f1f0ec", 11)
        has_markers = bool(r.get("markers"))
        fill = Canvas.blend(r["color"], "#fcfcfb", 0.45) if has_markers else r["color"]
        a, b = sorted((pos(50), pos(v)))
        if b - a >= 1:
            c.rect(c.x(a), by - 11, c.x(b), by + 11, fill, 0)
        c.line([(c.x(pos(50)), by - 20), (c.x(pos(50)), by + 20)], INK_3, 2)
        if has_markers:
            for mv, shape in r["markers"]:
                mx = c.x(pos(mv))
                if shape == "diamond":
                    _diamond(c, mx, by, 11, INK)
                else:
                    c.circle(mx, by, 11, INK, outline="#fcfcfb", width=3)
        else:
            c.circle(c.x(pos(v)), by, 14, r["color"], outline="#fcfcfb", width=4)
        c.text_start(pad, by + 26, _pct(lang, 100 - v), 22, INK if not lean_right else INK_3,
                     "Bold" if not lean_right else "Regular")
        c.text_end(width - pad, by + 26, _pct(lang, v), 22, INK if lean_right else INK_3,
                   "Bold" if lean_right else "Regular")
        y += row_h
    if legend:
        y += 6
        x = pad
        for shape, label in legend:
            cx = c.x(x + 12)
            if shape == "diamond":
                _diamond(c, cx, y + 14, 10, INK)
            else:
                c.circle(cx, y + 14, 10, INK)
            c.text_start(x + 34, y + 14, label, 21, INK_2, v="m")
            x += 34 + c.measure(label, 21) + 40
    return c.png()


def quadrants(title, subtitle, quads, point, axes, lang, primary=None, width=1080):
    """A circle split into four styles (e.g. DISC) with a dot for the person.

    quads: dict with keys "tl", "tr", "br", "bl" -> (letter, name, value_text, color), in LTR orientation
           (right-to-left languages mirror left and right).
    point: (x, y) in -1..1, x toward the right-hand style pair, y upward.
    axes: (top, bottom, left, right) labels.
    """
    pad, R = 56, 290
    probe = Canvas(width, 10, lang)
    sub_lines = len(probe.wrap(subtitle, 22, width - 2 * pad)) if subtitle else 0
    top = pad + 62 + sub_lines * 33 + 6
    height = int(top + 60 + 2 * R + 60 + pad)
    c = Canvas(width, height, lang)
    _header(c, title, subtitle, pad)
    cx, cy = width / 2, top + 60 + R
    S = 2  # draw.SCALE
    side = {"tl": (-1, -1), "tr": (1, -1), "br": (1, 1), "bl": (-1, 1)}
    start = {(1, -1): 270, (1, 1): 0, (-1, 1): 90, (-1, -1): 180}
    px, py = point
    d = math.hypot(px, py)
    if d > 0.9:
        px, py = px * 0.9 / d, py * 0.9 / d
    if c.rtl:
        px = -px
    dot = (cx + px * R, cy - py * R)
    labels = []
    for key, (letter, name, vtext, color) in quads.items():
        sx, sy = side[key]
        if c.rtl:
            sx = -sx
        a0 = start[(sx, sy)]
        fill = Canvas.blend(color, "#fcfcfb", 0.42 if key == primary else 0.16)
        c.d.pieslice([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], a0, a0 + 90, fill=fill)
        # label block (centre ~ letter to value) placed where it is farthest from the dot
        spots = [(0.5, 0.45), (0.56, 0.3), (0.32, 0.6)]
        gap = lambda p: math.hypot(cx + sx * R * p[0] - dot[0], cy + sy * R * p[1] + 6 - dot[1])
        fx, fy = spots[0] if gap(spots[0]) > 120 else max(spots, key=gap)
        labels.append((cx + sx * R * fx, cy + sy * R * fy, letter, name, vtext, color, fill))
    c.line([(cx - R, cy), (cx + R, cy)], "#fcfcfb", 6)
    c.line([(cx, cy - R), (cx, cy + R)], "#fcfcfb", 6)
    c.circle(*dot, 17, INK, outline="#fcfcfb", width=5)
    for qx, qy, letter, name, vtext, color, fill in labels:
        c.text(qx, qy - 58, letter, 64, color, "Bold", "ma", halo=fill)
        c.text(qx, qy + 18, name, 24, INK, "SemiBold", "ma", halo=fill)
        c.text(qx, qy + 52, vtext, 22, INK_2, anchor="ma", halo=fill)
    t_, b_, l_, r_ = axes
    c.text(cx, cy - R - 16, t_, 21, INK_2, "SemiBold", "md")
    c.text(cx, cy + R + 16, b_, 21, INK_2, "SemiBold", "ma")
    for label, sx in ((l_, -1), (r_, 1)):
        if c.rtl:
            sx = -sx
        lines = c.wrap(label, 21, cx - R - pad - 14, "SemiBold")
        x = cx + sx * (R + 14)
        for k, ln in enumerate(lines):
            c.text(x, cy - 14 * len(lines) + 28 * k, ln, 21, INK_2, "SemiBold", ("l" if sx > 0 else "r") + "a")
    return c.png()


def severity(title, subtitle, rows, lang, width=1080):
    """Scores on official severity ranges.

    rows: list of dicts with label, score, max, cuts [(upper_score, band_label)], value_text, color.
    Each range is a segment of one hue, light (mild) to dark (severe); a marker shows the score.
    """
    pad, row_h = 56, 170
    probe = Canvas(width, 10, lang)
    sub_lines = len(probe.wrap(subtitle, 22, width - 2 * pad)) if subtitle else 0
    height = int(pad + 62 + sub_lines * 33 + 6 + 24 + len(rows) * row_h + pad - 20)
    c = Canvas(width, height, lang)
    y = _header(c, title, subtitle, pad) + 24
    t0, t1 = pad, width - pad
    for r in rows:
        mx = r["max"]
        pos = lambda s: t0 + (t1 - t0) * min(max(s, 0), mx) / mx
        c.text_start(pad, y, r["label"], 26, INK, "SemiBold")
        c.text_end(width - pad, y, r["value_text"], 26, INK, "Bold")
        by = y + 70
        lo, n = 0, len(r["cuts"])
        ticks = []
        for i, (hi, _) in enumerate(r["cuts"]):
            a, b = pos(max(lo - 0.5, 0)), pos(min(hi + 0.5, mx))
            alpha = 0.14 + 0.72 * (i / max(n - 1, 1))
            c.rect(c.x(a + (2 if i else 0)), by, c.x(b - (2 if i < n - 1 else 0)), by + 30,
                   Canvas.blend(r["color"], "#fcfcfb", alpha), 4)
            if i < n - 1:
                ticks.append((b, hi + 1))
            lo = hi + 1
        last = -999
        for x, v in [(t0, 0)] + ticks + [(t1, mx)]:
            if abs(x - last) >= 34:
                c.text(c.x(x), by + 40, num(lang, v), 17, INK_3, anchor="ma")
                last = x
        mxp = c.x(pos(r["score"]))
        c.polygon([(mxp - 13, by - 22), (mxp + 13, by - 22), (mxp, by - 4)], fill=INK)
        c.line([(mxp, by - 4), (mxp, by + 34)], INK, 3)
        y += row_h
    return c.png()
