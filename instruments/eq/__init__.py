"""Emotional intelligence: WLEIS (short) and WLEIS + Schutte SSEIT (long).

WLEIS: 16 items, 4 subscales of 4, 7-point agreement. SSEIT: 33 items (5, 28, 33 reversed),
5-point agreement. There are no international norms, so levels are anchored to the answer
scale: an average answer below "neutral" is low, above "somewhat agree" is high.
"""

from html import escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import LANGS, num, t
from core.pdf import Document, today

SUBS = ["SEA", "OEA", "UOE", "ROE"]
COLOR = dict(zip(SUBS, SERIES))
OVERALL_COLOR, SSEIT_COLOR = SERIES[6], SERIES[4]
POINTS = {"wleis": 7, "sseit": 5}
CUTS = {"wleis": (4.0, 5.5), "sseit": (3.0, 4.0)}   # mean answer: below first = low, above second = high
LEVEL_ICON = {"low": "🔵", "average": "⚪", "high": "🟠"}


def _fmt(lang, x):
    s = f"{x:.1f}"
    return num(lang, int(s.split(".")[0])) + ("٫" if lang in ("fa", "ar") else ".") + num(lang, int(s.split(".")[1]))


class EQ(Instrument):
    id = "eq"
    category = "eq_talent"
    forms = {"short": Form("short", 16, 4), "long": Form("long", 49, 10)}
    data_dir = Path(__file__).resolve().parent

    def items(self, form):
        cache = self.__dict__.setdefault("_items", {})
        if form not in cache:
            bank = self._json("items.json")["items"]
            if form == "short":
                bank = [x for x in bank if x["scale"] == "wleis"]
            cache[form] = [{**x, "n": k + 1,
                            "text": {l: self.texts(l)["items"][x["id"]] for l in LANGS},
                            "prompt": {l: self.texts(l)["test"]["prompt"] for l in LANGS}}
                           for k, x in enumerate(bank)]
        return cache[form]

    def choices(self, form, item, lang):
        return self.texts(lang)["scales"][item["scale"]]

    def score(self, form, answers, profile):
        its = self.items(form)
        if set(answers) != {x["n"] for x in its}:
            raise ValueError("every item must be answered exactly once")
        vals = {"wleis": {s: [] for s in SUBS}, "sseit": []}
        for x in its:
            a = int(answers[x["n"]])
            if not 1 <= a <= POINTS[x["scale"]]:
                raise ValueError(f"answer out of range for item {x['n']}")
            if x["scale"] == "wleis":
                vals["wleis"][x["sub"]].append(a)
            else:
                vals["sseit"].append(a if x["keyed"] == "plus" else POINTS["sseit"] + 1 - a)

        def scale(mean, which):
            lo, hi = CUTS[which]
            return {"mean": round(mean, 2), "pct": round((mean - 1) / (POINTS[which] - 1) * 100),
                    "level": "low" if mean < lo else "high" if mean > hi else "average"}

        subs = {s: scale(sum(v) / len(v), "wleis") for s, v in vals["wleis"].items()}
        all_w = [a for v in vals["wleis"].values() for a in v]
        result = {"form": form, "subs": subs, "overall": scale(sum(all_w) / len(all_w), "wleis")}
        if form == "long":
            result["sseit"] = {**scale(sum(vals["sseit"]) / len(vals["sseit"]), "sseit"), "total": sum(vals["sseit"])}
        return result

    # --- presentation ----------------------------------------------------
    def summary_line(self, result, lang):
        tx = self.texts(lang)
        o = result["overall"]
        return f"{_fmt(lang, o['mean'])}/{num(lang, 7)} · {tx['levels'][o['level']]}"

    def chart(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        rows = [(tx["subscales"][s]["name"], r["pct"], f"{_fmt(lang, r['mean'])}/{num(lang, 7)}", "", COLOR[s])
                for s, r in result["subs"].items()]
        o = result["overall"]
        rows.append((test["overall"], o["pct"], f"{_fmt(lang, o['mean'])}/{num(lang, 7)}", "", OVERALL_COLOR))
        if "sseit" in result:
            r = result["sseit"]
            rows.append((test["sseit"], r["pct"], f"{_fmt(lang, r['mean'])}/{num(lang, 5)}", "", SSEIT_COLOR))
        return charts.bars(test["chart_title"], test["chart_subtitle"], rows, lang)

    def _ranked(self, result):
        return sorted(SUBS, key=lambda s: -result["subs"][s]["mean"])

    def scores_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        o = result["overall"]
        lines = [f"<b>{escape(test['scores'])}</b>", ""]
        for s in SUBS:
            r = result["subs"][s]
            lines.append(f"{LEVEL_ICON[r['level']]} <b>{escape(tx['subscales'][s]['name'])}</b>: "
                         f"{_fmt(lang, r['mean'])}/{num(lang, 7)} · {tx['levels'][r['level']]}")
        lines.append(f"{LEVEL_ICON[o['level']]} <b>{escape(test['overall'])}</b>: {_fmt(lang, o['mean'])}/{num(lang, 7)} · "
                     f"{tx['levels'][o['level']]}")
        if "sseit" in result:
            r = result["sseit"]
            lines.append(f"{LEVEL_ICON[r['level']]} <b>{escape(test['sseit'])}</b>: {num(lang, r['total'])}/{num(lang, 165)} · "
                         f"{tx['levels'][r['level']]}")
        lines += ["", escape(tx["overall_texts"][o["level"]])]
        if "sseit" in result:
            lines += ["", escape(test["agree"] if abs(result["sseit"]["pct"] - o["pct"]) <= 15 else test["disagree"])]
        return "\n".join(lines)

    def detail_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        ranked = self._ranked(result)
        lines = []
        for s in SUBS:
            r, info = result["subs"][s], tx["subscales"][s]
            lines += [f"<b>{escape(info['name'])}</b> · {tx['levels'][r['level']]}", escape(info[r["level"]]), ""]
        best, dev = ranked[0], ranked[-1]
        lines += [f"💪 <b>{escape(test['strongest'])}</b>: {escape(tx['subscales'][best]['name'])}",
                  f"🌱 <b>{escape(test['develop'])}</b>: {escape(tx['subscales'][dev]['name'])}",
                  f"💡 <b>{escape(test['tips'])}</b>: {escape(tx['subscales'][dev]['tip'])}", "",
                  f"<i>{escape(test['note'])}</i>", t(lang, "disclaimer")]
        return "\n".join(lines)

    def build_pdf(self, result, lang, png):
        tx = self.texts(lang)
        test = tx["test"]
        form = self.forms[result["form"]]
        doc = Document(lang, test["title"], t(lang, "pdf_footer"))
        doc.cover(test["about"], [f"{t(lang, 'pdf_date')}: {today(lang)}",
                                  f"{t(lang, 'pdf_form')}: {num(lang, form.n_items)} {t(lang, 'pdf_questions')}"])
        doc.image(png, width=900)
        doc.paragraph(tx["overall_texts"][result["overall"]["level"]], 22)
        doc.page_break()
        for s in SUBS:
            r, info = result["subs"][s], tx["subscales"][s]
            doc.subheading(f"{info['name']}: {_fmt(lang, r['mean'])}/{num(lang, 7)} · {tx['levels'][r['level']]}", COLOR[s])
            doc.paragraph(info["about"], 20, "#52514e")
            doc.paragraph(info[r["level"]], 21)
            doc.paragraph(f"{test['tips']}: {info['tip']}", 20, "#52514e")
        doc.paragraph(test["note"], 18, "#52514e")
        doc.paragraph(t(lang, "disclaimer_plain"), 18, "#52514e")
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        png = self.chart(result, lang)
        rep = Report(charts=[png], messages=[self.scores_message(result, lang), self.detail_message(result, lang)])
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, png)
        return rep


eq = EQ()
