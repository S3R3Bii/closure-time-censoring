"""Validate all aggregate bins and retain complete quality/endpoint accounting."""

from collections import Counter
from datetime import date
import hashlib, json, csv
from config import (
    ROOT,
    AGENCIES,
    MONTHS,
    QUALITY_CAP_NUMERATOR,
    QUALITY_CAP_DENOMINATOR,
    phase,
)
from source import read_bins, save_json


def main():
    m = json.loads((ROOT / "data/source/manifest.json").read_text())
    path = ROOT / m["public_aggregate_file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == m["public_aggregate_sha256"]
    rows = read_bins(path)
    assert len(rows) == m["aggregate_cells"]
    totals = Counter()
    bad = Counter()
    cells = set()
    coherence = Counter()
    eligible = []
    for r in rows:
        a = r["agency"]
        month = int(r["month"])
        day = int(r["created_day"])
        n = int(r["count"])
        key = tuple(
            r[k]
            for k in [
                "agency",
                "month",
                "created_day",
                "closure_delay_cell",
                "status_category",
                "quality",
            ]
        )
        assert key not in cells
        cells.add(key)
        assert a in AGENCIES and month in MONTHS and 1 <= day <= 28 and n > 0
        assert r["status_category"] in ["closed", "other", "missing"]
        totals[a, month] += n
        assert (
            r["closure_delay_cell"] in ["missing", "gt45"]
            or r["closure_delay_cell"].isdigit()
            and 0 <= int(r["closure_delay_cell"]) <= 45
        )
        assert r["quality"] in [
            "eligible",
            "unparseable_closure",
            "timezone_closure",
            "closure_before_creation",
            "closure_after_capture",
        ]
        if r["quality"] != "eligible":
            assert r["closure_delay_cell"] == "missing"
            bad[a, month] += n
            continue
        eligible.append(r)
        coherence[a, month, "date_present_status_not_closed"] += n * (
            r["closure_delay_cell"] != "missing" and r["status_category"] != "closed"
        )
        coherence[a, month, "closed_status_date_missing"] += n * (
            r["closure_delay_cell"] == "missing" and r["status_category"] == "closed"
        )
    summaries = []
    for panel in m["panels"]:
        key = panel["agency"], panel["month"]
        total = totals[key]
        quarantine = bad[key]
        assert total == panel["expected_rows"]
        assert (
            100 <= total - quarantine
            and quarantine * QUALITY_CAP_DENOMINATOR <= total * QUALITY_CAP_NUMERATOR
        ), "Fixedqualitygatefailed"
        latest_creation = date(2026, panel["month"], 28)
        assert (date.fromisoformat(m["capture_date"]) - latest_creation).days >= 28
        summaries.append(
            {
                "agency": key[0],
                "month": key[1],
                "phase": phase(*key),
                "source_rows": total,
                "quarantined_rows": quarantine,
                "eligible_rows": total - quarantine,
                **{
                    label: coherence[key + (label,)]
                    for label in [
                        "date_present_status_not_closed",
                        "closed_status_date_missing",
                    ]
                },
            }
        )
    assert sum(totals.values()) == m["total_rows"] and len(summaries) == 12
    # Publicinputcontains onlyprivacybins;allsourcequalityoutcomes areexplicit.
    with (ROOT / "data/timing_cells.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(eligible[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(eligible)
    with (ROOT / "results/source_panels.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(summaries)
    cert = {
        "status": "PASS",
        "source_rows": m["total_rows"],
        "aggregate_source_cells": len(rows),
        "eligible_timing_cells": len(eligible),
        "panels": 12,
        "quarantined_rows": sum(bad.values()),
        "quality_cap": "Atmost0.5percent closure-quality exclusionsperpanel;IDs/creation/cohortfailuresnotallowed",
        "maturity": "Allcohortlatestcreationdatesatleast28calendar daysbeforecapture",
        "held_inputs_not_blinded": True,
        "no_held_analysis_metrics_computed": True,
    }
    save_json(ROOT / "results/SOURCE_CHECK.json", cert)
    print(json.dumps(cert))


if __name__ == "__main__":
    main()
