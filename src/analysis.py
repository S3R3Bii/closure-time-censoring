"""Exact finite-cohort calculations under the fixed reconstructed observation rules."""

import argparse
import csv
from collections import defaultdict
from fractions import Fraction
from config import ROOT, CUTOFF_OFFSETS, ENDPOINTS, HORIZONS, phase
from source import save_json


def observations(cells, cutoff, endpoint):
    out = []
    for r in cells:
        n = int(r["count"])
        c = cutoff - (int(r["created_day"]) - 1)
        delay = r["closure_delay_cell"]
        t = int(delay) if delay.isdigit() else None
        if endpoint == "closed_status_and_date" and r["status_category"] != "closed":
            t = None
        event = t is not None and t <= c
        out.append((n, t, c, t if event else c, event))
    return out


def curve(obs, last_day=45):
    survival = Fraction(1)
    steps = []
    for d in range(last_day + 1):
        risk = sum(n for n, t, c, x, e in obs if x >= d)
        events = sum(n for n, t, c, x, e in obs if x == d and e)
        censors = sum(n for n, t, c, x, e in obs if x == d and not e)
        if risk:
            assert survival is not None
            survival *= Fraction(risk - events, risk)
        elif survival != 0:
            survival = None
        steps.append((d, risk, events, censors, survival))
    return steps


def restricted_mean(steps, tau):
    parts = [s for d, r, e, c, s in steps if d < tau]
    assert len(parts) == tau
    return sum(parts, Fraction()) if all(s is not None for s in parts) else None


def metrics(obs, steps, tau):
    total = sum(r[0] for r in obs)
    done = sum(n for n, t, c, x, e in obs if e)
    benchmark = Fraction(
        sum(n * (min(t, tau) if t is not None else tau) for n, t, c, x, e in obs), total
    )
    lower = Fraction(sum(n * min(x, tau) for n, t, c, x, e in obs), total)
    upper = Fraction(
        sum(n * (min(x, tau) if e else tau) for n, t, c, x, e in obs), total
    )
    naive = (
        Fraction(sum(n * min(t, tau) for n, t, c, x, e in obs if e), done)
        if done
        else None
    )
    raw = Fraction(sum(n * t for n, t, c, x, e in obs if e), done) if done else None
    rmst = restricted_mean(steps, tau)
    assert lower <= benchmark <= upper
    return {
        "eligible_rows": total,
        "observed_events": done,
        "censored_rows": total - done,
        "benchmark": benchmark,
        "completed_capped": naive,
        "completed_uncapped": raw,
        "rmst": rmst,
        "lower_bound": lower,
        "upper_bound": upper,
        "completed_abs_error": abs(naive - benchmark) if naive is not None else None,
        "rmst_abs_error": abs(rmst - benchmark) if rmst is not None else None,
        "rmst_status": "ESTIMABLE" if rmst is not None else "NOT_ESTIMABLE",
        "rmst_within_bounds": (
            "UNDEFINED" if rmst is None else str(lower <= rmst <= upper)
        ),
    }


def pack(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, Fraction) or v is None:
            out[k + "_exact"] = "NA" if v is None else str(v)
            out[k] = "NA" if v is None else format(float(v), ".17g")
        else:
            out[k] = v
    return out


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def exact(row, k):
    return None if row[k + "_exact"] == "NA" else Fraction(row[k + "_exact"])


def run(which):
    cells = list(
        csv.DictReader((ROOT / "data/timing_cells.csv").open(encoding="utf-8"))
    )
    panels = defaultdict(list)
    for r in cells:
        a, m = r["agency"], int(r["month"])
        if phase(a, m) == which:
            panels[a, m].append(r)
    output = []
    curves = []
    for (agency, month), rows in sorted(panels.items()):
        for cutoff in CUTOFF_OFFSETS:
            for endpoint in ENDPOINTS:
                base = {
                    "agency": agency,
                    "month": month,
                    "phase": which,
                    "cutoff": cutoff,
                    "endpoint": endpoint,
                }
                obs = observations(rows, cutoff, endpoint)
                steps = curve(obs)
                for d, r, e, c, s in steps:
                    curves.append(
                        pack(
                            {
                                **base,
                                "day": d,
                                "at_risk": r,
                                "events": e,
                                "censors": c,
                                "survival": s,
                            }
                        )
                    )
                for tau in HORIZONS:
                    output.append(
                        pack({**base, "tau": tau, **metrics(obs, steps, tau)})
                    )
    summaries = []
    for cutoff in CUTOFF_OFFSETS:
        for endpoint in ENDPOINTS:
            for tau in HORIZONS:
                subset = [
                    r
                    for r in output
                    if r["cutoff"] == cutoff
                    and r["endpoint"] == endpoint
                    and r["tau"] == tau
                ]
                paired = [
                    r
                    for r in subset
                    if exact(r, "rmst") is not None
                    and exact(r, "completed_capped") is not None
                ]
                n = len(paired)
                km = [exact(r, "rmst_abs_error") for r in paired]
                nv = [exact(r, "completed_abs_error") for r in paired]
                summaries.append(
                    pack(
                        {
                            "phase": which,
                            "cutoff": cutoff,
                            "endpoint": endpoint,
                            "tau": tau,
                            "panels": len(subset),
                            "paired_estimable_panels": n,
                            "rmst_wins": sum(k < v for k, v in zip(km, nv)),
                            "completed_wins": sum(v < k for k, v in zip(km, nv)),
                            "ties": sum(k == v for k, v in zip(km, nv)),
                            "rmst_mae": sum(km, Fraction()) / n if n else None,
                            "completed_mae": sum(nv, Fraction()) / n if n else None,
                            "rmst_outside_bounds": sum(
                                r["rmst_within_bounds"] == "False" for r in subset
                            ),
                        }
                    )
                )
    write_csv(ROOT / f"results/{which}_settings.csv", output)
    write_csv(ROOT / f"results/{which}_curves.csv", curves)
    write_csv(ROOT / f"results/{which}_summary.csv", summaries)
    save_json(
        ROOT / f"results/{which.upper()}_CHECK.json",
        {
            "status": "COMPUTED_PENDING_INDEPENDENT_CHECK",
            "phase": which,
            "panels": len(panels),
            "settings": len(output),
            "curve_steps": len(curves),
            "caveat": "Synthetic cutoffs on later captured records; no historical-vintage or true-resolution claim",
        },
    )
    print(
        f"{which}: {len(panels)} panels, {len(output)} settings, {len(curves)} curve steps"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["development", "evaluation"])
    a = p.parse_args()
    run(a.phase)
