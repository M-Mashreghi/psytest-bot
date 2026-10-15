"""DISC-style behaviour profile built from open Big Five (IPIP-NEO) facets.

There is no public-domain DISC questionnaire, so each DISC style is scored from the
IPIP-NEO facets that describe it, using Johnson's norms for the person's sex and age:

  D  Dominance          assertiveness +, cooperation -, achievement-striving +
  I  Influence          friendliness +, gregariousness +, cheerfulness +
  S  Steadiness         cooperation +, anger -, excitement-seeking -
  C  Conscientiousness  orderliness +, cautiousness +, dutifulness +

Each style's T-score is the mean of its signed facet T-scores, turned into a percentile.
Short form: those facets' items from the IPIP-NEO-120 (44 items).
Long form: the same facets from the IPIP-NEO-300 (110 items).
"""

import math
from html import escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import num, t
from core.pdf import Document, today
from instruments.neo import scoring as neo_scoring

ORDER = "DISC"
# Conventional DISC colours, taken from the chart palette: red, yellow, green, blue.
COLOR = {"D": SERIES[7], "I": SERIES[3], "S": SERIES[2], "C": SERIES[0]}
ICON = {"D": "🔴", "I": "🟡", "S": "🟢", "C": "🔵"}
LEVEL_ICON = {"low": "🔵", "average": "⚪", "high": "🟠"}
FACETS = {
    "D": [("E", 3, 1), ("A", 4, -1), ("C", 4, 1)],
    "I": [("E", 1, 1), ("E", 2, 1), ("E", 6, 1)],
    "S": [("A", 4, 1), ("N", 2, -1), ("E", 5, -1)],
    "C": [("C", 2, 1), ("C", 6, 1), ("C", 3, 1)],
}
VERSION = {"short": 120, "long": 300}
BAND = (31, 69)


def _pct_of_t(t_score):
    return max(1, min(99, round(50 * (1 + math.erf((t_score - 50) / 10 / math.sqrt(2))))))


class Disc(Instrument):
    id = "disc"
    category = "personality"
    forms = {"short": Form("short", 44, 6), "long": Form("long", 110, 15)}
    demographics = ("sex", "age")
    data_dir = Path(__file__).resolve().parent

    def items(self, form):
        cache = self.__dict__.setdefault("_items", {})
        if form not in cache:
            wanted = {(d, f) for fs in FACETS.values() for d, f, _ in fs}
            src = [x for x in neo_scoring.items(VERSION[form]) if (x["domain"], x["facet"]) in wanted]
            cache[form] = [{**x, "n": k + 1, "src": x["n"]} for k, x in enumerate(src)]
            assert len(cache[form]) == self.forms[form].n_items
        return cache[form]

    def choices(self, form, item, lang):
        return self._json("../neo/choices.json")[lang]

    # --- scoring ---------------------------------------------------------
    def score(self, form, answers, profile):
        its = self.items(form)
        if set(answers) != {x["n"] for x in its}:
            raise ValueError("every item must be answered exactly once")
        raw = {}
        for x in its:
            a = int(answers[x["n"]])
            if not 1 <= a <= 5:
                raise ValueError(f"answer out of range for item {x['n']}")
            key = (x["domain"], x["facet"])
            raw[key] = raw.get(key, 0) + (a if x["keyed"] == "plus" else 6 - a)
        ng = neo_scoring.norm_group(VERSION[form], profile["sex"], profile["age"])
        styles = {}
        for s, facets in FACETS.items():
            ts = [neo_scoring._scale(raw[(d, f)], ng["facets"][d][f - 1])["t"] for d, f, _ in facets]
            t_score = 50 + sum(sign * (tf - 50) for (_, _, sign), tf in zip(facets, ts)) / len(ts)
            styles[s] = {"t": round(t_score, 1), "percentile": _pct_of_t(t_score),
                         "level": "low" if t_score < 45 else "high" if t_score > 55 else "average"}
        ranked = sorted(ORDER, key=lambda s: -styles[s]["t"])
        p = [styles[s]["percentile"] for s in ORDER]
        first, second = ranked[0], ranked[1]
        return {"form": form, "sex": profile["sex"], "age": profile["age"], "styles": styles,
                  "primary": first,
                  "secondary": second if styles[second]["percentile"] >= 60
                  and styles[first]["percentile"] - styles[second]["percentile"] <= 15 else None,
                  "balanced": max(p) - min(p) < 15}

    # --- presentation ----------------------------------------------------
    def _style_label(self, result, lang):
        tx = self.texts(lang)
        name = tx["styles"][result["primary"]]["name"]
        if result["secondary"]:
            return f"{result['primary']}{result['secondary'].lower()} · {name} + {tx['styles'][result['secondary']]['name']}"
        return f"{result['primary']} · {name}"

    def summary_line(self, result, lang):
        sc = result["styles"]
        scores = " ".join(f"{s} {num(lang, sc[s]['percentile'])}" for s in ORDER)
        return f"{self._style_label(result, lang)} ({scores})"

    def chart_wheel(self, result, lang):
        tx = self.texts(lang)
        sc = {s: result["styles"][s]["percentile"] for s in ORDER}
        quads = {k: (s, tx["styles"][s]["name"], num(lang, sc[s]), COLOR[s])
                 for k, s in (("tl", "D"), ("tr", "I"), ("br", "S"), ("bl", "C"))}
        point = (((sc["I"] + sc["S"]) - (sc["D"] + sc["C"])) / 200, ((sc["D"] + sc["I"]) - (sc["S"] + sc["C"])) / 200)
        test = tx["test"]
        return charts.quadrants(test["wheel_title"], test["wheel_subtitle"], quads, point,
                                (test["axis_fast"], test["axis_steady"], test["axis_task"], test["axis_people"]),
                                lang, primary={"D": "tl", "I": "tr", "S": "br", "C": "bl"}[result["primary"]])

    def chart_scores(self, result, lang):
        tx = self.texts(lang)
        rows = [(f"{s} · {tx['styles'][s]['name']}", result["styles"][s]["percentile"],
                 num(lang, result["styles"][s]["percentile"]), tx["levels"][result["styles"][s]["level"]], COLOR[s])
                for s in ORDER]
        return charts.bars(tx["test"]["chart_title"], tx["test"]["chart_subtitle"], rows, lang,
                           band=BAND, band_label=tx["test"]["band_label"])

    def overview_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        lines = [f"🧩 <b>{escape(test['primary'])}: {escape(self._style_label(result, lang))}</b>", ""]
        if result["balanced"]:
            lines += [escape(test["balanced"]), ""]
        lines.append(f"<b>{escape(test['scores'])}</b>")
        for s in ORDER:
            r = result["styles"][s]
            lines.append(f"{ICON[s]} <b>{escape(tx['styles'][s]['name'])}</b>: {num(lang, r['percentile'])} · "
                         f"{LEVEL_ICON[r['level']]} {tx['levels'][r['level']]}")
        lines += ["", f"<i>{escape(test['chart_subtitle'])}</i>"]
        return "\n".join(lines)

    def style_message(self, result, lang):
        tx = self.texts(lang)
        test, st = tx["test"], tx["styles"][result["primary"]]
        lines = [f"{ICON[result['primary']]} <b>{escape(st['name'])}</b> · <i>{escape(st['tagline'])}</i>", "",
                 escape(st["high"]), "", f"💪 <b>{escape(test['strengths'])}</b>"]
        lines += [f"• {escape(x)}" for x in st["strengths"]]
        lines += ["", f"⚠️ <b>{escape(test['challenges'])}</b>"]
        lines += [f"• {escape(x)}" for x in st["challenges"]]
        lines += ["", f"🚀 <b>{escape(test['motivators'])}</b>: {escape(st['motivators'])}",
                  f"🌧 <b>{escape(test['stress'])}</b>: {escape(st['stress'])}",
                  f"🤝 <b>{escape(test['work_with'])}</b>: {escape(st['work_with'])}"]
        return "\n".join(lines)

    def scores_message(self, result, lang):
        tx = self.texts(lang)
        lines = [f"<b>{escape(tx['test']['scores'])}</b>", ""]
        for s in ORDER:
            r, st = result["styles"][s], tx["styles"][s]
            lines += [f"{ICON[s]} <b>{escape(st['name'])}</b> {num(lang, r['percentile'])} · {tx['levels'][r['level']]}",
                      escape(st[r["level"]]), ""]
        lines += [f"<i>{escape(tx['test']['note'])}</i>", t(lang, "disclaimer")]
        return "\n".join(lines)

    def build_pdf(self, result, lang, wheel, scores):
        tx = self.texts(lang)
        test = tx["test"]
        form = self.forms[result["form"]]
        sex = {"M": t(lang, "sex_M"), "F": t(lang, "sex_F")}.get(result["sex"], t(lang, "sex_N"))
        doc = Document(lang, test["title"], t(lang, "pdf_footer"))
        doc.cover(test["about"], [
            f"{t(lang, 'pdf_date')}: {today(lang)}",
            f"{t(lang, 'pdf_form')}: {num(lang, form.n_items)} {t(lang, 'pdf_questions')}",
            f"{t(lang, 'pdf_norms')}: {sex}, {t(lang, 'pdf_age')} {num(lang, result['age'])}",
        ])
        doc.image(wheel, width=860)
        doc.page_break()
        p = result["primary"]
        st = tx["styles"][p]
        doc.heading(f"{test['primary']}: {self._style_label(result, lang)}", COLOR[p])
        if result["balanced"]:
            doc.paragraph(test["balanced"], 22)
        doc.paragraph(st["tagline"], 22, "#52514e", "SemiBold")
        doc.paragraph(st["high"], 23)
        for key in ("strengths", "challenges"):
            doc.subheading(test[key], COLOR[p])
            for x in st[key]:
                doc.paragraph(f"•  {x}", 21)
        for key in ("motivators", "stress", "work_with"):
            doc.subheading(test[key], COLOR[p])
            doc.paragraph(st[key], 21)
        doc.page_break()
        doc.image(scores, width=900)
        for s in ORDER:
            r, info = result["styles"][s], tx["styles"][s]
            doc.subheading(f"{info['name']}: {num(lang, r['percentile'])} · {tx['levels'][r['level']]}", COLOR[s])
            doc.paragraph(info["about"], 20, "#52514e")
            doc.paragraph(info[r["level"]], 21)
        doc.paragraph(test["note"], 18, "#52514e")
        doc.paragraph(t(lang, "disclaimer_plain"), 18, "#52514e")
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        wheel, scores = self.chart_wheel(result, lang), self.chart_scores(result, lang)
        rep = Report(charts=[wheel, scores], messages=[self.overview_message(result, lang),
                                                       self.style_message(result, lang),
                                                       self.scores_message(result, lang)])
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, wheel, scores)
        return rep


disc = Disc()
