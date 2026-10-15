"""IPIP-NEO scoring: raw sums -> T-scores against Johnson's norms -> percentiles.

Follows Johnson's IPIP-NEO procedure (reverse-key, sum per facet and domain,
T = 50 + 10 * (raw - mean) / sd). Percentiles use the exact normal CDF rather
than Johnson's cubic approximation.
"""

import json
import math
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent
DOMAINS = "NEOAC"
LOW_T, HIGH_T = 45, 55  # Johnson's cut-offs for low / average / high


@lru_cache
def items(version):
    return json.loads((DATA / f"items_{version}.json").read_text(encoding="utf-8"))


@lru_cache
def _norms():
    return json.loads((DATA / "norms.json").read_text(encoding="utf-8"))


def norm_group(version, sex, age):
    """Pick the norm group. Sex other than M/F averages the male and female norms."""
    v = _norms()["versions"][str(version)]
    if version == 120:
        band = "lt21" if age < 21 else "21-40" if age <= 40 else "41-60" if age <= 60 else "gt60"
    else:
        band = "lt21" if age < 21 else "gt20"
    if sex in ("M", "F"):
        return v["groups"][f"{sex}:{band}"]
    m, f = v["groups"][f"M:{band}"], v["groups"][f"F:{band}"]
    avg = lambda a, b: {"mean": (a["mean"] + b["mean"]) / 2, "sd": (a["sd"] + b["sd"]) / 2}
    return {
        "domains": {d: avg(m["domains"][d], f["domains"][d]) for d in DOMAINS},
        "facets": {d: [avg(x, y) for x, y in zip(m["facets"][d], f["facets"][d])] for d in DOMAINS},
    }


def _scale(raw, n):
    t = 50 + 10 * (raw - n["mean"]) / n["sd"]
    pct = 50 * (1 + math.erf((t - 50) / 10 / math.sqrt(2)))
    level = "low" if t < LOW_T else "high" if t > HIGH_T else "average"
    return {"raw": raw, "t": round(t, 1), "percentile": max(1, min(99, round(pct))), "level": level}


def score(version, answers, sex, age):
    """answers: {item number: 1..5 as chosen on the Very inaccurate..Very accurate scale}."""
    its = items(version)
    if set(answers) != {x["n"] for x in its}:
        raise ValueError("every item must be answered exactly once")
    raw_f = {d: [0] * 6 for d in DOMAINS}
    for x in its:
        a = int(answers[x["n"]])
        if not 1 <= a <= 5:
            raise ValueError(f"answer out of range for item {x['n']}")
        raw_f[x["domain"]][x["facet"] - 1] += a if x["keyed"] == "plus" else 6 - a

    ng = norm_group(version, sex, age)
    result = {"version": version, "sex": sex, "age": age, "domains": {}}
    for d in DOMAINS:
        dom = _scale(sum(raw_f[d]), ng["domains"][d])
        dom["facets"] = [_scale(raw_f[d][f], ng["facets"][d][f]) for f in range(6)]
        result["domains"][d] = dom
    return result
