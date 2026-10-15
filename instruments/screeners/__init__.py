"""Mental-health screening questionnaires with published cut-offs.

  depression  short: PHQ-9            long: PHQ-9 + DASS-42 depression items
  anxiety     short: GAD-7            long: GAD-7 + DASS-42 anxiety items
  dass        short: DASS-21          long: DASS-42
  ocd         short: OCI-R            long: OCI-R + DOCS

All share one item bank and one set of texts (texts/<lang>.json). Scores are raw sums
compared with the official severity ranges, so no sex or age is needed.
"""

import json
from html import escape as _escape
from pathlib import Path

from core import charts
from core.draw import SERIES
from core.engine import Form, Instrument, Report
from core.i18n import LANGS, num, t
from core.pdf import Document, today

DATA = Path(__file__).resolve().parent
escape = lambda s: _escape(s, quote=False)

DASS_D = [3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42]
DASS_A = [2, 4, 7, 9, 15, 19, 20, 23, 25, 28, 30, 36, 40, 41]
DASS_S = [1, 6, 8, 11, 12, 14, 18, 22, 27, 29, 32, 33, 35, 39]
DASS_21 = [22, 2, 3, 4, 42, 6, 41, 12, 40, 10, 39, 8, 26, 35, 28, 31, 17, 18, 25, 20, 38]   # DASS-21 order
OCI_SUB = {"washing": [5, 11, 17], "checking": [2, 8, 14], "ordering": [3, 9, 15],
           "obsessing": [6, 12, 18], "hoarding": [1, 7, 13], "neutralizing": [4, 10, 16]}
DOCS_DIMS = "CRUS"

PHQ = [f"phq{i}" for i in range(1, 10)]
GAD = [f"gad{i}" for i in range(1, 8)]
OCI = [f"oci{i}" for i in range(1, 19)]
DOCS = [f"docs_{d}{q}" for d in DOCS_DIMS for q in range(1, 6)]
dass = lambda ns: [f"dass{n}" for n in ns]

# measure -> items (full version), severity ranges (upper score, band), text family, colour
MEASURES = {
    "phq9": (PHQ, [(4, "minimal"), (9, "mild"), (14, "moderate"), (19, "moderately_severe"), (27, "severe")],
             "depression", SERIES[6]),
    "gad7": (GAD, [(4, "minimal"), (9, "mild"), (14, "moderate"), (21, "severe")], "anxiety", SERIES[0]),
    "dass_d": (dass(DASS_D), [(9, "normal"), (13, "mild"), (20, "moderate"), (27, "severe"), (42, "extremely_severe")],
               "depression", SERIES[6]),
    "dass_a": (dass(DASS_A), [(7, "normal"), (9, "mild"), (14, "moderate"), (19, "severe"), (42, "extremely_severe")],
               "anxiety", SERIES[0]),
    "dass_s": (dass(DASS_S), [(14, "normal"), (18, "mild"), (25, "moderate"), (33, "severe"), (42, "extremely_severe")],
               "stress", SERIES[1]),
    "oci": (OCI, [(20, "below"), (72, "above")], "ocd", SERIES[2]),
    "docs": (DOCS, [(20, "below"), (80, "above")], "ocd", SERIES[2]),
}
SEEK_HELP = {"moderate", "moderately_severe", "severe", "extremely_severe", "above"}
SEVERE = {"moderately_severe", "severe", "extremely_severe"}
ICON = {"minimal": "🟢", "normal": "🟢", "below": "🟢", "mild": "🟡", "moderate": "🟠",
        "moderately_severe": "🔴", "severe": "🔴", "extremely_severe": "🔴", "above": "🟠"}


def _scale_of(item_id):
    return "docs" if item_id.startswith("docs") else "".join(ch for ch in item_id if ch.isalpha())


class Screener(Instrument):
    category = "mental"
    demographics = ()
    data_dir = DATA

    def __init__(self, test_id, forms, plan):
        self.id = test_id
        self.forms = forms
        self.plan = plan          # form -> (item ids, measures)

    # --- texts -----------------------------------------------------------
    def texts(self, lang):
        if not (DATA / "texts" / f"{lang}.json").exists():
            lang = "en"
        return self._json(f"texts/{lang}.json")

    def _test(self, lang):
        return self.texts(lang)["tests"][self.id]

    def title(self, lang):
        return self._test(lang)["title"]

    def short_title(self, lang):
        return self._test(lang)["short_title"]

    def about(self, lang):
        return self._test(lang)["about"]

    def instructions(self, lang):
        return self._test(lang)["instructions"]

    # --- items -----------------------------------------------------------
    def _item_text(self, item_id, lang):
        tx = self.texts(lang)
        if item_id.startswith("docs"):
            return tx["docs"]["questions"][int(item_id[-1]) - 1]
        return tx["items"][item_id]

    def _prompt(self, item_id, lang):
        tx = self.texts(lang)
        stem = tx["scales"][_scale_of(item_id)]["stem"]
        if item_id.startswith("docs"):
            return f"{tx['docs']['dims'][item_id[5]]}\n\n{stem}"
        return stem

    def items(self, form):
        cache = self.__dict__.setdefault("_items", {})
        if form not in cache:
            cache[form] = [{"n": k + 1, "id": iid,
                            "text": {l: self._item_text(iid, l) for l in LANGS},
                            "prompt": {l: self._prompt(iid, l) for l in LANGS}}
                           for k, iid in enumerate(self.plan[form][0])]
        return cache[form]

    def choices(self, form, item, lang):
        tx = self.texts(lang)
        if item["id"].startswith("docs"):
            return tx["docs"]["choices"][int(item["id"][-1]) - 1]
        return tx["scales"][_scale_of(item["id"])]["choices"]

    # --- scoring ---------------------------------------------------------
    def score(self, form, answers, profile):
        its = self.items(form)
        if set(answers) != {x["n"] for x in its}:
            raise ValueError("every item must be answered exactly once")
        val = {}
        for x in its:
            v = int(answers[x["n"]]) - 1
            if not 0 <= v <= len(self.choices(form, x, "en")) - 1:
                raise ValueError(f"answer out of range for item {x['n']}")
            val[x["id"]] = v
        result = {"form": form, "measures": {}, "answers": val}
        for m in self.plan[form][1]:
            full, cuts, _, _ = MEASURES[m]
            present = [i for i in full if i in val]
            score = round(sum(val[i] for i in present) * len(full) / len(present))   # DASS-21 counts double
            band = next(b for hi, b in cuts if score <= hi)
            result["measures"][m] = {"score": score, "max": cuts[-1][0], "band": band}
        if "phq9" in val:
            result["item9"] = val["phq9"]
        if "oci1" in val:
            result["oci_sub"] = {k: sum(val[f"oci{i}"] for i in ns) for k, ns in OCI_SUB.items()}
        if "docs_C1" in val:
            result["docs_sub"] = {d: sum(val[f"docs_{d}{q}"] for q in range(1, 6)) for d in DOCS_DIMS}
        return result

    # --- presentation ----------------------------------------------------
    def _value_text(self, lang, m, r, chart=False):
        tx = self.texts(lang)
        sep = "–" if chart and lang in ("fa", "ar") else "·"   # in Vazirmatn a middle dot looks like a Persian zero
        return f"{num(lang, r['score'])} / {num(lang, r['max'])} {sep} {tx['bands'][r['band']]}"

    def summary_line(self, result, lang):
        tx = self.texts(lang)
        return " · ".join(f"{tx['measures'][m]['short']} {num(lang, r['score'])} ({tx['bands'][r['band']]})"
                          for m, r in result["measures"].items())

    def chart_severity(self, result, lang):
        tx = self.texts(lang)
        rows = [{"label": tx["measures"][m]["name"], "score": r["score"], "max": r["max"],
                 "cuts": MEASURES[m][1], "value_text": self._value_text(lang, m, r, chart=True), "color": MEASURES[m][3]}
                for m, r in result["measures"].items()]
        rep = tx["report"]
        return charts.severity(rep["severity_title"], rep["severity_subtitle"], rows, lang)

    def chart_sub(self, result, lang, which):
        tx = self.texts(lang)
        rep, subs = tx["report"], tx["subscales"][which]
        scores = result[f"{which}_sub"]
        vmax = 12 if which == "oci" else 20
        order = sorted(scores, key=lambda k: -scores[k])
        rows = [(subs[k]["name"], scores[k], f"{num(lang, scores[k])} / {num(lang, vmax)}", "", SERIES[2]) for k in order]
        return charts.bars(rep[f"subscales_{which}"], rep["subscales_subtitle"], rows, lang, vmax=vmax)

    def _levels(self, result):
        out = []
        for m, r in result["measures"].items():
            cuts = [b for _, b in MEASURES[m][1]]
            out.append(cuts.index(r["band"]) / (len(cuts) - 1))
        return out

    def results_message(self, result, lang):
        tx = self.texts(lang)
        rep = tx["report"]
        lines = [f"<b>{escape(self.title(lang))}</b>", ""]
        shown = set()
        for m, r in result["measures"].items():
            info = tx["measures"][m]
            lines.append(f"{ICON[r['band']]} <b>{escape(info['name'])}</b>: {self._value_text(lang, m, r)}")
            key = (MEASURES[m][2], r["band"])
            if key not in shown:
                lines.append(escape(tx["band_texts"][key[0]][key[1]]))
                shown.add(key)
            lines.append("")
        if self.plan[result["form"]][1] != self.plan["short"][1] and self.id != "dass":
            lv = self._levels(result)
            lines += [rep["agree"] if max(lv) - min(lv) <= 0.35 else rep["disagree"], ""]
        lines.append(f"<i>{escape(rep['screening_note'])}</i>")
        return "\n".join(lines)

    def subscales_message(self, result, lang, which):
        tx = self.texts(lang)
        subs, scores = tx["subscales"][which], result[f"{which}_sub"]
        vmax = 12 if which == "oci" else 20
        lines = [f"<b>{escape(tx['report'][f'subscales_{which}'])}</b>", ""]
        for k in sorted(scores, key=lambda k: -scores[k]):
            lines.append(f"• <b>{escape(subs[k]['name'])}</b> {num(lang, scores[k])}/{num(lang, vmax)}: "
                         f"{escape(subs[k]['about'])}")
        return "\n".join(lines)

    def next_steps(self, result, lang):
        rep = self.texts(lang)["report"]
        need = any(r["band"] in SEEK_HELP for r in result["measures"].values())
        lines = [f"<b>{escape(rep['next_steps'])}</b>", "", escape(rep["self_care"])]
        if need:
            lines += ["", escape(rep["seek_help"])]
        return "\n".join(lines)

    def alerts(self, result, lang):
        rep = self.texts(lang)["report"]
        if result.get("item9", 0) > 0:
            return [rep["item9_alert"] + "\n\n" + t(lang, "crisis_lines")]
        if any(r["band"] in SEVERE for r in result["measures"].values()):
            extra = "\n\n" + t(lang, "crisis_lines") if result["measures"].get("phq9", {}).get("band") == "severe" else ""
            return [rep["severe_alert"] + extra]
        return []

    def build_pdf(self, result, lang, pngs):
        tx = self.texts(lang)
        rep = tx["report"]
        form = self.forms[result["form"]]
        doc = Document(lang, self.title(lang), t(lang, "pdf_footer"))
        doc.cover(self.about(lang), [f"{t(lang, 'pdf_date')}: {today(lang)}",
                                     f"{t(lang, 'pdf_form')}: {num(lang, form.n_items)} {t(lang, 'pdf_questions')}"])
        for alert in self.alerts(result, lang):
            doc.paragraph(alert.replace("<b>", "").replace("</b>", ""), 21, "#b3261e", "SemiBold")
        doc.image(pngs[0], width=900)
        for m, r in result["measures"].items():
            info = tx["measures"][m]
            doc.subheading(f"{info['name']}: {self._value_text(lang, m, r, chart=True)}", MEASURES[m][3])
            doc.paragraph(info["about"], 20, "#52514e")
            doc.paragraph(tx["band_texts"][MEASURES[m][2]][r["band"]], 21)
        for which, png in zip([w for w in ("oci", "docs") if f"{w}_sub" in result], pngs[1:]):
            doc.page_break()
            doc.image(png, width=900)
            subs, scores = tx["subscales"][which], result[f"{which}_sub"]
            for k in sorted(scores, key=lambda k: -scores[k]):
                doc.subheading(f"{subs[k]['name']}: {num(lang, scores[k])}")
                doc.paragraph(subs[k]["about"], 20, "#52514e")
        doc.page_break()
        doc.heading(rep["next_steps"])
        doc.paragraph(rep["self_care"], 21)
        if any(r["band"] in SEEK_HELP for r in result["measures"].values()):
            doc.paragraph(rep["seek_help"], 21)
        doc.paragraph(rep["screening_note"], 19, "#52514e")
        # every answer, so a professional can go through them
        doc.page_break()
        doc.heading(f"{num(lang, form.n_items)} {t(lang, 'pdf_questions')}")
        for x in self.items(result["form"]):
            v = result["answers"][x["id"]]
            doc.paragraph(f"{num(lang, x['n'])}. {x['text'][lang]}", 18, weight="SemiBold")
            doc.paragraph(f"{self.choices(result['form'], x, lang)[v]} ({num(lang, v)})", 18, "#52514e")
        return doc.bytes()

    def report(self, result, lang, with_pdf=True):
        pngs = [self.chart_severity(result, lang)]
        msgs = [self.results_message(result, lang)]
        for which in ("oci", "docs"):
            if f"{which}_sub" in result:
                pngs.append(self.chart_sub(result, lang, which))
                msgs.append(self.subscales_message(result, lang, which))
        msgs.append(self.next_steps(result, lang))
        rep = Report(charts=pngs, messages=msgs, alerts=self.alerts(result, lang))
        if with_pdf:
            rep.pdf = self.build_pdf(result, lang, pngs)
        return rep


depression = Screener("depression", {"short": Form("short", 9, 3), "long": Form("long", 23, 7)},
                      {"short": (PHQ, ["phq9"]), "long": (PHQ + dass(DASS_D), ["phq9", "dass_d"])})
anxiety = Screener("anxiety", {"short": Form("short", 7, 2), "long": Form("long", 21, 6)},
                   {"short": (GAD, ["gad7"]), "long": (GAD + dass(DASS_A), ["gad7", "dass_a"])})
dass_test = Screener("dass", {"short": Form("short", 21, 5), "long": Form("long", 42, 10)},
                     {"short": (dass(DASS_21), ["dass_d", "dass_a", "dass_s"]),
                      "long": (dass(range(1, 43)), ["dass_d", "dass_a", "dass_s"])})
ocd = Screener("ocd", {"short": Form("short", 18, 5), "long": Form("long", 38, 12)},
               {"short": (OCI, ["oci"]), "long": (OCI + DOCS, ["oci", "docs"])})
