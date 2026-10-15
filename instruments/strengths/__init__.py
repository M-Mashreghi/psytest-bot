"""Character strengths: the 24 IPIP-VIA scales (public domain).

Long form: all 213 scored IPIP-VIA items. Short form: 4 items per strength (96), the first
three positively keyed and the first negatively keyed item of each scale, in the key's order.
Items are rated on the IPIP 5-point accuracy scale; a strength's score is its mean (1 to 5).
Strengths are ranked within the person's own profile (signature strengths = top 5), as VIA does.
"""

from html import escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import LANGS, num, t
from core.pdf import Document, today

VIRTUE_ORDER = ["wisdom", "courage", "humanity", "justice", "temperance", "transcendence"]
VCOLOR = dict(zip(VIRTUE_ORDER, SERIES))


def _fmt(lang, x):
    a, b = f"{x:.1f}".split(".")
    return num(lang, int(a)) + ("٫" if lang in ("fa", "ar") else ".") + num(lang, int(b))


class Strengths(Instrument):
    id = "strengths"
    category = "eq_talent"
    forms = {"short": Form("short", 96, 12), "long": Form("long", 213, 25)}
    data_dir = Path(__file__).resolve().parent

    @property
    def virtue_of(self):
        return {s: v for v, ss in self._json("virtues.json").items() for s in ss}

    def items(self, form):
        cache = self.__dict__.setdefault("_items", {})
        if form not in cache:
            data = self._json("items.json")
            keep = set(data["short"]) if form == "short" else None
            bank = [x for x in data["items"] if keep is None or x["id"] in keep]
            cache[form] = [{**x, "n": k + 1, "text": {l: self.texts(l)["items"][x["id"]] for l in LANGS}}
                           for k, x in enumerate(bank)]
            assert len(cache[form]) == self.forms[form].n_items
        return cache[form]

    def choices(self, form, item, lang):
        return self._json("../neo/choices.json")[lang]

    def score(self, form, answers, profile):
        its = self.items(form)
        if set(answers) != {x["n"] for x in its}:
            raise ValueError("every item must be answered exactly once")
        vals = {}
        for x in its:
            a = int(answers[x["n"]])
            if not 1 <= a <= 5:
                raise ValueError(f"answer out of range for item {x['n']}")
            vals.setdefault(x["scale"], []).append(a if x["keyed"] == "plus" else 6 - a)
        means = {s: round(sum(v) / len(v), 2) for s, v in vals.items()}
        order = sorted(means, key=lambda s: -means[s])     # stable: ties keep the key's order
        return {"form": form, "scores": means, "rank": order}

    # --- presentation ----------------------------------------------------
    def summary_line(self, result, lang):
        st = self.texts(lang)["strengths"]
        return ("، " if lang in ("fa", "ar") else ", ").join(st[s]["name"] for s in result["rank"][:3])

    def _row(self, result, lang, s):
        tx = self.texts(lang)
        v = self.virtue_of[s]
        return (tx["strengths"][s]["name"], result["scores"][s] - 1, _fmt(lang, result["scores"][s]),
                tx["virtues"][v], VCOLOR[v])

    def chart_top(self, result, lang):
        test = self.texts(lang)["test"]
        rows = [self._row(result, lang, s) for s in result["rank"][:5]]
        return charts.bars(test["top_title"], test["top_subtitle"], rows, lang, vmax=4)

    def chart_all(self, result, lang):
        tx = self.texts(lang)
        rows = [self._row(result, lang, s) for s in result["rank"]]
        legend = [(VCOLOR[v], tx["virtues"][v]) for v in VIRTUE_ORDER]
        return charts.bars(tx["test"]["chart_title"], tx["test"]["chart_subtitle"], rows, lang, vmax=4,
                           compact=True, legend=legend)

    def signature_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        lines = [f"⭐ <b>{escape(test['signature'])}</b>", escape(test["signature_about"]), ""]
        for k, s in enumerate(result["rank"][:5], 1):
            info = tx["strengths"][s]
            lines += [f"<b>{num(lang, k)}. {escape(info['name'])}</b> ({escape(tx['virtues'][self.virtue_of[s]])}) · "
                      f"{_fmt(lang, result['scores'][s])}",
                      escape(info["about"]), f"💡 <i>{escape(test['use_it'])}: {escape(info['tip'])}</i>", ""]
        return "\n".join(lines).rstrip()

    def all_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        lines = [f"<b>{escape(test['all'])}</b>", ""]
        for k, s in enumerate(result["rank"], 1):
            lines.append(f"{num(lang, k)}. {escape(tx['strengths'][s]['name'])} · {_fmt(lang, result['scores'][s])}")
        lines += ["", f"🌱 <b>{escape(test['lesser'])}</b>: "
                  + ("، " if lang in ("fa", "ar") else ", ").join(escape(tx["strengths"][s]["name"]) for s in result["rank"][-3:]),
                  escape(test["lesser_about"]), "", f"<i>{escape(test['note'])}</i>", t(lang, "disclaimer")]
        return "\n".join(lines)

    def build_pdf(self, result, lang, pngs):
        tx = self.texts(lang)
        test = tx["test"]
        form = self.forms[result["form"]]
        doc = Document(lang, test["title"], t(lang, "pdf_footer"))
        doc.cover(test["about"], [f"{t(lang, 'pdf_date')}: {today(lang)}",
                                  f"{t(lang, 'pdf_form')}: {num(lang, form.n_items)} {t(lang, 'pdf_questions')}"])
        doc.image(pngs[0], width=880)
        doc.page_break()
        doc.heading(test["signature"])
        doc.paragraph(test["signature_about"], 21, "#52514e")
        for k, s in enumerate(result["rank"][:5], 1):
            info, v = tx["strengths"][s], self.virtue_of[s]
            doc.subheading(f"{num(lang, k)}. {info['name']} ({tx['virtues'][v]})", VCOLOR[v])
            doc.paragraph(info["about"], 21)
            doc.paragraph(f"{test['use_it']}: {info['tip']}", 20, "#52514e")
        doc.page_break()
        doc.image(pngs[1], width=860)
        doc.paragraph(test["lesser_about"], 19, "#52514e")
        doc.paragraph(test["note"], 17, "#52514e")
        doc.paragraph(t(lang, "disclaimer_plain"), 17, "#52514e")
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        pngs = [self.chart_top(result, lang), self.chart_all(result, lang)]
        rep = Report(charts=pngs, messages=[self.signature_message(result, lang), self.all_message(result, lang)])
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, pngs)
        return rep


strengths = Strengths()
