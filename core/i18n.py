"""Bot UI strings in the six supported languages, plus number formatting."""

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LANGS = ["en", "ru", "ar", "hi", "fa", "fr"]
RTL = {"ar", "fa"}
_DIGITS = {"fa": "۰۱۲۳۴۵۶۷۸۹", "ar": "٠١٢٣٤٥٦٧٨٩"}


@lru_cache
def _ui():
    return json.loads((DATA / "ui.json").read_text(encoding="utf-8"))


def num(lang, n):
    """Write a number in the language's own digits (Persian and Arabic)."""
    s = str(n)
    digits = _DIGITS.get(lang)
    return s.translate(str.maketrans("0123456789", digits)) if digits else s


def t(lang, key, **kw):
    s = _ui()[lang].get(key) or _ui()["en"][key]
    return s.format(**{k: num(lang, v) if isinstance(v, int) else v for k, v in kw.items()})
