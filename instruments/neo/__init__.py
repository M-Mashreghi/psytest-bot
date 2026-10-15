"""Big Five personality (IPIP-NEO-120 short form, IPIP-NEO-300 long form)."""

from html import escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import num, t
from core.pdf import Document, today

from . import scoring

ORDER = "OCEAN"
COLOR = dict(zip(ORDER, SERIES))   # fixed categorical slot per trait
ICON = {"O": "🎨", "C": "🎯", "E": "🎉", "A": "🤝", "N": "🌊"}
LEVEL_ICON = {"low": "🔵", "average": "⚪", "high": "🟠"}
BAND = (31, 69)                     # percentiles for T 45..55, Johnson's "average"
VERSION = {"short": 120, "long": 300}


class Neo(Instrument):
    id = "neo"
    category = "personality"
    forms = {"short": Form("short", 120, 15), "long": Form("long", 300, 40)}
    demographics = ("sex", "age")
    data_dir = Path(__file__).resolve().parent

    def items(self, form):
        return scoring.items(VERSION[form])

    def choices(self, form, item, lang):
        return self._json("choices.json")[lang]

    def score(self, form, answers, profile):
        r = scoring.score(VERSION[form], answers, profile["sex"], profile["age"])
        r["form"] = form
        return r

    def summary_line(self, result, lang):
        tx = self.texts(lang)
        return " · ".join(f"{ICON[d]} {num(lang, result['domains'][d]['percentile'])}" for d in ORDER)

    # --- charts ----------------------------------------------------------
    def chart_overview(self, result, lang):
        tx = self.texts(lang)
        axes = [(tx["domains"][d]["name"], result["domains"][d]["percentile"],
                 f"{num(lang, result['domains'][d]['percentile'])} – {tx['levels'][result['domains'][d]['level']]}")
                for d in ORDER]
        return charts.radar(tx["test"]["chart_title"], tx["test"]["chart_subtitle"], axes, lang,
                            band=BAND, band_label=tx["test"]["band_label"])

    def chart_domain(self, result, lang, d):
        tx = self.texts(lang)
        r = result["domains"][d]
        rows = [(f["name"], fr["percentile"], num(lang, fr["percentile"]), tx["levels"][fr["level"]])
                for f, fr in zip(tx["facets"][d], r["facets"])]
        return charts.bars(tx["domains"][d]["name"], tx["domains"][d]["tagline"], rows, lang, color=COLOR[d],
                           band=BAND, band_label=tx["test"]["band_label"],
                           headline=(num(lang, r["percentile"]), tx["levels"][r["level"]]))

    # --- texts -----------------------------------------------------------
    def overview_message(self, result, lang):
        tx = self.texts(lang)
        lines = [f"<b>{escape(tx['test']['chart_title'])}</b>", ""]
        for d in ORDER:
            r = result["domains"][d]
            lines.append(f"{ICON[d]} <b>{escape(tx['domains'][d]['name'])}</b>: {num(lang, r['percentile'])} · "
                         f"{LEVEL_ICON[r['level']]} {tx['levels'][r['level']]}")
        lines += ["", f"<i>{escape(tx['test']['chart_subtitle'])}</i>", t(lang, "disclaimer")]
        return "\n".join(lines)

    def domain_message(self, result, lang, d):
        tx = self.texts(lang)
        info, r = tx["domains"][d], result["domains"][d]
        lines = [
            f"{ICON[d]} <b>{escape(info['name'])}</b> · {LEVEL_ICON[r['level']]} <b>{tx['levels'][r['level']]}</b> "
            f"({t(lang, 'higher_than', p=r['percentile'])})",
            "",
            escape(info[r["level"]]),
            "",
        ]
        for f, fr in zip(tx["facets"][d], r["facets"]):
            text = f[fr["level"]] if fr["level"] in ("low", "high") else f["about"]
            lines.append(f"{LEVEL_ICON[fr['level']]} <b>{escape(f['name'])}</b> {num(lang, fr['percentile'])}: {escape(text)}")
        return "\n".join(lines)

    def build_pdf(self, result, lang, chart_overview, chart_domains):
        tx = self.texts(lang)
        form = self.forms[result["form"]]
        sex = {"M": t(lang, "sex_M"), "F": t(lang, "sex_F")}.get(result["sex"], t(lang, "sex_N"))
        doc = Document(lang, tx["test"]["title"], t(lang, "pdf_footer"))
        doc.cover(tx["test"]["about"], [
            f"{t(lang, 'pdf_date')}: {today(lang)}",
            f"{t(lang, 'pdf_form')}: {num(lang, form.n_items)} {t(lang, 'pdf_questions')}",
            f"{t(lang, 'pdf_norms')}: {sex}, {t(lang, 'pdf_age')} {num(lang, result['age'])}",
        ])
        doc.image(chart_overview, width=900)
        doc.paragraph(t(lang, "disclaimer_plain"), 18, "#52514e")
        for d, png in zip(ORDER, chart_domains):
            info, r = tx["domains"][d], result["domains"][d]
            doc.page_break()
            doc.heading(info["name"], COLOR[d])
            doc.paragraph(info["about"], 22, "#52514e")
            doc.subheading(f"{tx['levels'][r['level']]} · {t(lang, 'higher_than', p=r['percentile'])}", COLOR[d])
            doc.paragraph(info[r["level"]], 23)
            doc.image(png, width=880)
            for f, fr in zip(tx["facets"][d], r["facets"]):
                doc.subheading(f"{f['name']}: {num(lang, fr['percentile'])} · {tx['levels'][fr['level']]}")
                doc.paragraph(f["about"], 20, "#52514e")
                if fr["level"] in ("low", "high"):
                    doc.paragraph(f[fr["level"]], 21)
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        over = self.chart_overview(result, lang)
        doms = [self.chart_domain(result, lang, d) for d in ORDER]
        rep = Report(charts=[over] + doms,
                     messages=[self.overview_message(result, lang)] + [self.domain_message(result, lang, d) for d in ORDER])
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, over, doms)
        return rep


neo = Neo()
