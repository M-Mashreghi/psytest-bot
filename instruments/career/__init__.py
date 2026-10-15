"""Career interests: Holland's RIASEC types from the O*NET Interest Profiler Short Form (60 items).

Each item is rated 1 (strongly dislike) to 5 (strongly like); an area score is the sum of its
10 items scored 0 to 4 (0 to 40). The Holland code is the three highest areas.
Used under the O*NET Tools Developer License (translated and adapted; see the attribution text).
"""

from html import escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import LANGS, num, t
from core.pdf import Document, today

AREAS = "RIASEC"
COLOR = dict(zip(AREAS, SERIES))
ICON = {"R": "🔧", "I": "🔬", "A": "🎨", "S": "🤝", "E": "📈", "C": "🗂"}
LEVEL_ICON = {"low": "🔵", "average": "⚪", "high": "🟠"}


class Career(Instrument):
    id = "career"
    category = "eq_talent"
    forms = {"short": Form("short", 60, 10)}
    data_dir = Path(__file__).resolve().parent

    def items(self, form):
        cache = self.__dict__.setdefault("_items", {})
        if form not in cache:
            cache[form] = [{**x, "n": k + 1,
                            "text": {l: self.texts(l)["items"][x["id"]] for l in LANGS},
                            "prompt": {l: self.texts(l)["test"]["prompt"] for l in LANGS}}
                           for k, x in enumerate(self._json("items.json")["items"])]
        return cache[form]

    def choices(self, form, item, lang):
        return self.texts(lang)["choices"]

    def score(self, form, answers, profile):
        its = self.items(form)
        if set(answers) != {x["n"] for x in its}:
            raise ValueError("every item must be answered exactly once")
        sums = {a: 0 for a in AREAS}
        for x in its:
            v = int(answers[x["n"]])
            if not 1 <= v <= 5:
                raise ValueError(f"answer out of range for item {x['n']}")
            sums[x["area"]] += v - 1
        ranked = sorted(AREAS, key=lambda a: (-sums[a], AREAS.index(a)))
        return {"form": form, "areas": {a: {"score": s, "level": "low" if s <= 13 else "high" if s >= 27 else "average"}
                                        for a, s in sums.items()},
                "code": "".join(ranked[:3]), "flat": max(sums.values()) - min(sums.values()) < 8}

    # --- presentation ----------------------------------------------------
    def summary_line(self, result, lang):
        tx = self.texts(lang)
        sep = "، " if lang in ("fa", "ar") else ", "
        return f"{result['code']} · " + sep.join(tx["areas"][a]["name"] for a in result["code"])

    def chart(self, result, lang):
        tx = self.texts(lang)
        axes = [(f"{tx['areas'][a]['name']} ({a})", result["areas"][a]["score"],
                 num(lang, result["areas"][a]["score"])) for a in AREAS]
        return charts.radar(tx["test"]["chart_title"], tx["test"]["chart_subtitle"], axes, lang, vmax=40,
                            color=COLOR[result["code"][0]])

    def chart_bars(self, result, lang):
        tx = self.texts(lang)
        order = sorted(AREAS, key=lambda a: -result["areas"][a]["score"])
        rows = [(f"{a} · {tx['areas'][a]['name']}", result["areas"][a]["score"], num(lang, result["areas"][a]["score"]),
                 tx["levels"][result["areas"][a]["level"]], COLOR[a]) for a in order]
        return charts.bars(tx["test"]["code"] + ": " + result["code"], tx["test"]["code_about"], rows, lang, vmax=40)

    def code_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        lines = [f"🧭 <b>{escape(test['code'])}: {result['code']}</b>", escape(test["code_about"]), ""]
        if result["flat"]:
            lines += [escape(test["flat"]), ""]
        for a in result["code"]:
            info = tx["areas"][a]
            sep = "، " if lang in ("fa", "ar") else ", "
            lines += [f"{ICON[a]} <b>{a} · {escape(info['name'])}</b> ({escape(info['nickname'])}) · "
                      f"{num(lang, result['areas'][a]['score'])}/{num(lang, 40)}",
                      escape(info["about"]),
                      f"<i>{escape(test['careers'])}: {escape(sep.join(info['careers']))}</i>", ""]
        return "\n".join(lines).rstrip()

    def scores_message(self, result, lang):
        tx = self.texts(lang)
        test = tx["test"]
        lines = [f"<b>{escape(test['scores'])}</b>", ""]
        for a in sorted(AREAS, key=lambda a: -result["areas"][a]["score"]):
            r = result["areas"][a]
            lines.append(f"{ICON[a]} <b>{escape(tx['areas'][a]['name'])}</b>: {num(lang, r['score'])}/{num(lang, 40)} · "
                         f"{LEVEL_ICON[r['level']]} {tx['levels'][r['level']]}")
        lines += ["", f"<i>{escape(test['attribution'])}</i>", t(lang, "disclaimer")]
        return "\n".join(lines)

    def build_pdf(self, result, lang, pngs):
        tx = self.texts(lang)
        test = tx["test"]
        doc = Document(lang, test["title"], t(lang, "pdf_footer"))
        doc.cover(test["about"], [f"{t(lang, 'pdf_date')}: {today(lang)}",
                                  f"{t(lang, 'pdf_form')}: {num(lang, 60)} {t(lang, 'pdf_questions')}"])
        doc.image(pngs[0], width=860)
        doc.page_break()
        doc.heading(f"{test['code']}: {result['code']}", COLOR[result["code"][0]])
        doc.paragraph(test["code_about"], 21, "#52514e")
        if result["flat"]:
            doc.paragraph(test["flat"], 21)
        sep = "، " if lang in ("fa", "ar") else ", "
        for a in sorted(AREAS, key=lambda a: -result["areas"][a]["score"]):
            info, r = tx["areas"][a], result["areas"][a]
            doc.subheading(f"{a} · {info['name']} ({info['nickname']}): {num(lang, r['score'])}/{num(lang, 40)}", COLOR[a])
            doc.paragraph(info["about"], 21)
            doc.paragraph(f"{test['careers']}: {sep.join(info['careers'])}", 20, "#52514e")
        doc.page_break()
        doc.image(pngs[1], width=900)
        doc.paragraph(test["attribution"], 17, "#52514e")
        doc.paragraph(t(lang, "disclaimer_plain"), 18, "#52514e")
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        pngs = [self.chart(result, lang), self.chart_bars(result, lang)]
        rep = Report(charts=pngs, messages=[self.code_message(result, lang), self.scores_message(result, lang)])
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, pngs)
        return rep


career = Career()
