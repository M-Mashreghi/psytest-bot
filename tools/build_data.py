"""Build the bot's data files (items, answer choices, norms) from the raw sources.

Run from the repo root:  python3 tools/build_data.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "sources"
OUT = ROOT / "instruments" / "neo"
LANGS = ["en", "ru", "ar", "hi", "fa", "fr"]
DOMAINS = "NEOAC"

# Fixes to the community 120-item translations (item number -> {lang: text}).
FIXES_120 = {
    "hi": {
        "Lose my temper": "अपना आपा खो देते हैं",
        "Trust what people say": "लोगों के कथनों पर विश्वास करते हैं",
    },
}


def norm_key(text):
    t = re.sub(r"[^a-z]", "", text.lower())
    return t.replace("rightandwrong", "rightorwrong")


def domain_facet(n):
    """Johnson's IPIP-NEO layout: items cycle through the 30 facets in order."""
    return DOMAINS[(n - 1) % 5], ((n - 1) // 5) % 6 + 1


def build_items():
    src120 = {l: json.loads((SRC / "b5-120-items" / l / "questions.json").read_text()) for l in LANGS}
    en120 = src120["en"]

    items120 = []
    by_text = {}
    for i, q in enumerate(en120):
        n = i + 1
        d, f = domain_facet(n)
        assert (q["domain"], q["facet"]) == (d, f), n
        text = {}
        for l in LANGS:
            t = src120[l][i]["text"].strip().rstrip(".")
            t = FIXES_120.get(l, {}).get(q["text"], t)
            text[l] = t
        item = {"n": n, "domain": d, "facet": f, "keyed": q["keyed"], "text": text}
        items120.append(item)
        by_text[norm_key(q["text"])] = item

    en300 = json.loads((SRC / "ipip300_en.json").read_text())["questions"]
    reversed300 = set(json.loads((SRC / "reversed300.json").read_text()))
    extra = {}
    for line in (SRC / "translations_300_extra.txt").read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        assert len(parts) == 6, line
        extra[int(parts[0])] = dict(zip(LANGS[1:], parts[1:]))

    items300 = []
    for q in en300:
        n = q["id"]
        d, f = domain_facet(n)
        keyed = "minus" if n in reversed300 else "plus"
        shared = by_text.get(norm_key(q["text"]))
        if shared:
            assert shared["keyed"] == keyed and (shared["domain"], shared["facet"]) == (d, f), n
            text = dict(shared["text"])
        else:
            text = {"en": q["text"].strip().rstrip("."), **extra[n]}
        items300.append({"n": n, "domain": d, "facet": f, "keyed": keyed, "text": text})

    assert len(items120) == 120 and len(items300) == 300
    for items, per in ((items120, 4), (items300, 10)):
        for d in DOMAINS:
            for f in range(1, 7):
                assert sum(1 for x in items if x["domain"] == d and x["facet"] == f) == per
        for x in items:
            assert all(x["text"].get(l) for l in LANGS), x["n"]
    return items120, items300


def build_norms():
    """Johnson's IPIP-NEO norms (means/SDs by sex and age band), via five-factor-e (MIT)."""
    sys.path.insert(0, str(SRC))
    import importlib.util

    spec = importlib.util.spec_from_file_location("jn", SRC / "johnson_norms_five_factor_e.py")
    code = (SRC / "johnson_norms_five_factor_e.py").read_text()
    # The file depends on its package only for validators and an unused import.
    code = code.replace("from ipipneo.model import NormCubic, NormScale\n", "")
    code = code.replace(
        "from ipipneo.utility import raise_if_age_is_invalid, raise_if_sex_is_invalid\n",
        "raise_if_age_is_invalid = raise_if_sex_is_invalid = lambda **k: True\n",
    )
    mod = type(sys)("jn")
    exec(compile(code, "jn", "exec"), mod.__dict__)
    Norm = mod.Norm

    def unpack(ns):
        out = {"domains": {}, "facets": {}}
        for k, d in enumerate("NEOAC"):
            out["domains"][d] = {"mean": ns[1 + k], "sd": ns[6 + k]}
            out["facets"][d] = [
                {"mean": ns[11 + 12 * k + f], "sd": ns[17 + 12 * k + f]} for f in range(6)
            ]
        return out

    bands = {
        "120": [("lt21", 18), ("21-40", 30), ("41-60", 50), ("gt60", 70)],
        "300": [("lt21", 18), ("gt20", 30)],
    }
    norms = {"source": "Johnson (2014) IPIP-NEO norms, as published in five-factor-e (MIT)", "versions": {}}
    for ver, bl in bands.items():
        v = {}
        for sex in ("M", "F"):
            for name, age in bl:
                v[f"{sex}:{name}"] = unpack(Norm(sex=sex, age=age, nquestion=int(ver))["ns"])
        norms["versions"][ver] = {"age_bands": [b[0] for b in bl], "groups": v}
    return norms


CHOICES = {
    "en": ["Very inaccurate", "Moderately inaccurate", "Neither accurate nor inaccurate", "Moderately accurate", "Very accurate"],
    "ru": ["Совсем не про меня", "Скорее не про меня", "Ни да, ни нет", "Скорее про меня", "Точно про меня"],
    "ar": ["لا ينطبق عليّ إطلاقاً", "لا ينطبق عليّ غالباً", "محايد", "ينطبق عليّ غالباً", "ينطبق عليّ تماماً"],
    "hi": ["बिल्कुल सही नहीं", "कुछ हद तक सही नहीं", "न सही, न गलत", "कुछ हद तक सही", "बिल्कुल सही"],
    "fa": ["اصلاً درباره من صدق نمی‌کند", "تا حدی صدق نمی‌کند", "نه درست نه نادرست", "تا حدی صدق می‌کند", "کاملاً درباره من صدق می‌کند"],
    "fr": ["Pas du tout moi", "Plutôt pas moi", "Ni l'un ni l'autre", "Plutôt moi", "Tout à fait moi"],
}


def main():
    items120, items300 = build_items()
    norms = build_norms()
    dump = lambda name, obj: (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    OUT.mkdir(exist_ok=True)
    dump("items_120.json", items120)
    dump("items_300.json", items300)
    dump("choices.json", CHOICES)
    dump("norms.json", norms)
    print("items_120:", len(items120), "items_300:", len(items300), "norm groups:",
          {k: len(v["groups"]) for k, v in norms["versions"].items()})


if __name__ == "__main__":
    main()
