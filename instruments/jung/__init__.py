"""Jungian 16-type personality (an open alternative to the MBTI).

Short form: the 32 Open Extended Jungian Type Scales (OEJTS 1.2) pairs, answered on a
5-point scale between the two poles.
Long form: the same 32 pairs plus 48 IPIP-NEO-120 items from the Big Five facets that
track each preference, scored against Johnson's norms. The two measurements are averaged
and shown side by side, so the user can see whether they agree.
"""

import math
from html import escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import LANGS, num, t
from core.pdf import Document, today
from instruments.neo import scoring as neo_scoring

DATA = Path(__file__).resolve().parent
DIMS = ["EI", "SN", "TF", "JP"]
POLES = {"EI": "EI", "SN": "SN", "TF": "FT", "JP": "JP"}   # (left pole, right pole) letters; left = E/S/F/J
COLOR = dict(zip(DIMS, SERIES))
ICON = {"EI": "⚡", "SN": "🔭", "TF": "⚖️", "JP": "🗓"}
# Big Five facets (domain, facet number) that measure each dimension, and which pole they point to.
FACETS = {
    "EI": ([("E", 1), ("E", 2), ("E", 3)], "left"),     # friendliness, gregariousness, assertiveness -> E
    "SN": ([("O", 1), ("O", 4), ("O", 5)], "right"),    # imagination, adventurousness, intellect -> N
    "TF": ([("A", 6), ("A", 3), ("O", 3)], "left"),     # sympathy, altruism, emotionality -> F
    "JP": ([("C", 2), ("C", 5), ("C", 6)], "left"),     # orderliness, self-discipline, cautiousness -> J
}
N_PAIRS = 32


def _pairs():
    rows = []
    for line in (DATA / "oejts_pairs.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("|")
        texts = {lang: (f[2 + 2 * k], f[3 + 2 * k]) for k, lang in enumerate(["en", "ru", "ar", "hi", "fa", "fr"])}
        rows.append({"n": int(f[0]), "dim": f[1], "pair": texts})
    assert len(rows) == N_PAIRS
    return rows


def clarity(right):
    c = abs(right - 50) * 2
    return "slight" if c <= 25 else "moderate" if c <= 50 else "clear" if c <= 75 else "very_clear"


def _pct(lang, v):
    return num(lang, round(v)) + ("٪" if lang in ("fa", "ar") else "%")


class Jung(Instrument):
    id = "jung"
    category = "personality"
    forms = {"short": Form("short", 32, 7), "long": Form("long", 80, 15)}
    demographics = ("sex", "age")
    data_dir = DATA

    def needs(self, form):
        return self.demographics if form == "long" else ()

    # --- items -----------------------------------------------------------
    def items(self, form):
        cache = self.__dict__.setdefault("_items", {})
        if form not in cache:
            pairs = [{"n": p["n"], "kind": "pair", "dim": p["dim"],
                      "text": {l: f"🅰 {a}\n🅱 {b}" for l, (a, b) in p["pair"].items()},
                      "prompt": {l: self.texts(l)["test"]["pair_prompt"] for l in LANGS},
                      "pair": p["pair"]} for p in _pairs()]
            out = pairs
            if form == "long":
                wanted = {(d, f) for fs, _ in FACETS.values() for d, f in fs}
                ipip = [x for x in neo_scoring.items(120) if (x["domain"], x["facet"]) in wanted]
                out = pairs + [{**x, "n": N_PAIRS + k + 1, "kind": "ipip", "src": x["n"]} for k, x in enumerate(ipip)]
                assert len(out) == 80
            cache[form] = out
        return cache[form]

    def choices(self, form, item, lang):
        if item["kind"] == "ipip":
            return self._json("../neo/choices.json")[lang]
        tx = self.texts(lang)["test"]
        a, b = item["pair"][lang]
        return [f"🅰 {tx['much']}: {a}", f"🅰 {tx['bit']}: {a}", f"⚪ {tx['both']}",
                f"🅱 {tx['bit']}: {b}", f"🅱 {tx['much']}: {b}"]

    # --- scoring ---------------------------------------------------------
    def score(self, form, answers, profile):
        its = self.items(form)
        if set(answers) != {x["n"] for x in its}:
            raise ValueError("every item must be answered exactly once")
        sums = {d: 0 for d in DIMS}
        for x in its:
            if x["kind"] == "pair":
                sums[x["dim"]] += int(answers[x["n"]])     # 1 = fully left pole, 5 = fully right pole
        dims = {d: {"oejts": round((sums[d] - 8) / 32 * 100, 1)} for d in DIMS}
        result = {"form": form}
        if form == "long":
            result.update(sex=profile["sex"], age=profile["age"])
            ng = neo_scoring.norm_group(120, profile["sex"], profile["age"])
            raw = {}
            for x in its:
                if x["kind"] == "ipip":
                    a = int(answers[x["n"]])
                    key = (x["domain"], x["facet"])
                    raw[key] = raw.get(key, 0) + (a if x["keyed"] == "plus" else 6 - a)
            for d, (facets, pole) in FACETS.items():
                ts = [neo_scoring._scale(raw[(dom, f)], ng["facets"][dom][f - 1])["t"] for dom, f in facets]
                mean_t = sum(ts) / len(ts)
                p = 50 * (1 + math.erf((mean_t - 50) / 10 / math.sqrt(2)))
                dims[d]["ipip"] = round(p if pole == "right" else 100 - p, 1)
                dims[d]["facet_t"] = ts
        code = ""
        for d in DIMS:
            r = dims[d]
            r["value"] = round((r["oejts"] + r["ipip"]) / 2, 1) if "ipip" in r else r["oejts"]
            r["letter"] = POLES[d][1] if r["value"] >= 50 else POLES[d][0]
            r["clarity"] = clarity(r["value"])
            if "ipip" in r:
                r["agree"] = (r["oejts"] - 50) * (r["ipip"] - 50) >= 0
            code += r["letter"]
        result["type"] = code
        result["dims"] = dims
        return result

    # --- presentation ----------------------------------------------------
    def summary_line(self, result, lang):
        return f"{result['type']} · {self.texts(lang)['types'][result['type']]['name']}"

    def _rows(self, result, lang, markers=False):
        tx = self.texts(lang)
        rows = []
        for d in DIMS:
            r, info = result["dims"][d], tx["dims"][d]
            row = {"name": info["name"], "left": f"{info['left']} ({POLES[d][0]})", "right": f"{info['right']} ({POLES[d][1]})",
                   "value": r["value"], "color": COLOR[d]}
            if markers:
                row["markers"] = [(r["oejts"], "circle"), (r["ipip"], "diamond")]
            rows.append(row)
        return rows

    def chart_type(self, result, lang):
        tx = self.texts(lang)
        code = result["type"]
        return charts.bipolar(tx["test"]["chart_title"], tx["test"]["chart_subtitle"], self._rows(result, lang), lang,
                              headline=(code, [COLOR[d] for d in DIMS], tx["types"][code]["name"]))

    def chart_compare(self, result, lang):
        tx = self.texts(lang)["test"]
        return charts.bipolar(tx["compare_title"], tx["compare_subtitle"], self._rows(result, lang, markers=True),
                              lang, legend=[("circle", tx["src_oejts"]), ("diamond", tx["src_ipip"])])

    def _pole(self, result, lang, d):
        r, info = result["dims"][d], self.texts(lang)["dims"][d]
        right = r["value"] >= 50
        return (info["right"] if right else info["left"]), (r["value"] if right else 100 - r["value"]), \
            info["right_text" if right else "left_text"]

    def type_message(self, result, lang):
        tx = self.texts(lang)
        ty, test = tx["types"][result["type"]], tx["test"]
        lines = [f"🧭 <b>{result['type']} · {escape(ty['name'])}</b>", "", escape(ty["summary"]), "",
                 f"💪 <b>{escape(test['strengths'])}</b>"]
        lines += [f"• {escape(s)}" for s in ty["strengths"]]
        lines += ["", f"⚠️ <b>{escape(test['challenges'])}</b>"]
        lines += [f"• {escape(s)}" for s in ty["challenges"]]
        lines += ["", f"💼 <b>{escape(test['careers'])}</b>: {escape('، '.join(ty['careers']) if lang in ('fa', 'ar') else ', '.join(ty['careers']))}"]
        return "\n".join(lines)

    def preferences_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        lines = [f"<b>{escape(test['preferences'])}</b>", ""]
        disagree = []
        for d in DIMS:
            r = result["dims"][d]
            pole, strength, text = self._pole(result, lang, d)
            lines.append(f"{ICON[d]} <b>{escape(tx['dims'][d]['name'])}: {escape(pole)}</b> "
                         f"({_pct(lang, strength)} · {tx['clarity'][r['clarity']]})")
            lines += [escape(text), ""]
            if r.get("agree") is False:
                disagree.append(tx["dims"][d]["name"])
        if result["form"] == "long":
            sep = "، " if lang in ("fa", "ar") else ", "
            lines += [test["disagree"].format(dims=sep.join(disagree)) if disagree else test["agree"], ""]
        lines += [f"<i>{escape(test['trademark'])}</i>", t(lang, "disclaimer")]
        return "\n".join(lines)

    def build_pdf(self, result, lang, pngs):
        tx = self.texts(lang)
        test, ty = tx["test"], tx["types"][result["type"]]
        form = self.forms[result["form"]]
        doc = Document(lang, test["title"], t(lang, "pdf_footer"))
        meta = [f"{t(lang, 'pdf_date')}: {today(lang)}",
                f"{t(lang, 'pdf_form')}: {num(lang, form.n_items)} {t(lang, 'pdf_questions')}"]
        if result["form"] == "long":
            sex = {"M": t(lang, "sex_M"), "F": t(lang, "sex_F")}.get(result["sex"], t(lang, "sex_N"))
            meta.append(f"{t(lang, 'pdf_norms')}: {sex}, {t(lang, 'pdf_age')} {num(lang, result['age'])}")
        doc.cover(test["about"], meta)
        doc.image(pngs[0], width=900)
        doc.page_break()
        doc.heading(f"{result['type']} · {ty['name']}", COLOR["EI"])
        doc.paragraph(ty["summary"], 23)
        for key, items in (("strengths", ty["strengths"]), ("challenges", ty["challenges"]), ("careers", ty["careers"])):
            doc.subheading(test[key])
            for s in items:
                doc.paragraph(f"•  {s}", 21)
        doc.page_break()
        doc.heading(test["preferences"])
        for d in DIMS:
            r, info = result["dims"][d], tx["dims"][d]
            pole, strength, text = self._pole(result, lang, d)
            doc.subheading(f"{info['name']}: {pole} · {_pct(lang, strength)} · {tx['clarity'][r['clarity']]}", COLOR[d])
            doc.paragraph(text, 21)
        if len(pngs) > 1:
            doc.page_break()
            doc.image(pngs[1], width=900)
        doc.paragraph(test["trademark"], 18, "#52514e")
        doc.paragraph(t(lang, "disclaimer_plain"), 18, "#52514e")
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        pngs = [self.chart_type(result, lang)]
        if result["form"] == "long":
            pngs.append(self.chart_compare(result, lang))
        rep = Report(charts=pngs, messages=[self.type_message(result, lang), self.preferences_message(result, lang)])
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, pngs)
        return rep


jung = Jung()
