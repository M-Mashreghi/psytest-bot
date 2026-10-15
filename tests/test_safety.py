"""Safety messages for the mental-health screenings."""

import instruments  # noqa: F401
from core import engine
from core.i18n import LANGS, t


def answers(inst, form, value, overrides=None):
    a = {x["n"]: value for x in inst.items(form)}
    a.update(overrides or {})
    return a


def test_self_harm_item_shows_helplines_in_every_language():
    inst = engine.get("depression")
    r = inst.score("short", answers(inst, "short", 1, {9: 2}), {})   # all "not at all" except item 9
    assert r["measures"]["phq9"]["band"] == "minimal" and r["item9"] == 1
    for lang in LANGS:
        alerts = inst.report(r, lang, with_pdf=False).alerts
        assert len(alerts) == 1 and t(lang, "crisis_lines") in alerts[0]


def test_no_alert_when_symptoms_are_low():
    for tid in ("depression", "anxiety", "dass", "ocd"):
        inst = engine.get(tid)
        for form in inst.forms:
            r = inst.score(form, answers(inst, form, 1), {})
            assert inst.report(r, "en", with_pdf=False).alerts == []


def test_severe_scores_alert_and_published_cutoffs():
    inst = engine.get("depression")
    r = inst.score("short", answers(inst, "short", 4, {9: 1}), {})
    assert r["measures"]["phq9"] == {"score": 24, "max": 27, "band": "severe"}
    assert inst.report(r, "en", with_pdf=False).alerts
    dass = engine.get("dass")
    r21 = dass.score("short", answers(dass, "short", 2), {})        # all 1s on DASS-21 -> 7 per scale, doubled
    assert {m: v["score"] for m, v in r21["measures"].items()} == {"dass_d": 14, "dass_a": 14, "dass_s": 14}
    assert r21["measures"]["dass_d"]["band"] == "moderate" and r21["measures"]["dass_s"]["band"] == "normal"
    ocd = engine.get("ocd")
    assert ocd.score("short", answers(ocd, "short", 2), {})["measures"]["oci"]["band"] == "below"   # 18
    assert ocd.score("short", answers(ocd, "short", 3), {})["measures"]["oci"]["band"] == "above"   # 36
