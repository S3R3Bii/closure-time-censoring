# Independent SQLite counts and integer/decimal survival arithmetic; no production import.
import argparse
import csv
import json
import math
import sqlite3
from decimal import Decimal, localcontext
from fractions import Fraction
from config import ROOT, phase


def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def verify(which):
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE cells(agency TEXT,month INT,created INT,delay TEXT,status TEXT,w INT)"
    )
    for r in rows(ROOT / "data/timing_cells.csv"):
        db.execute(
            "INSERT INTO cells VALUES(?,?,?,?,?,?)",
            (
                r["agency"],
                int(r["month"]),
                int(r["created_day"]),
                r["closure_delay_cell"],
                r["status_category"],
                int(r["count"]),
            ),
        )
    stored = rows(ROOT / f"results/{which}_settings.csv")
    curves = rows(ROOT / f"results/{which}_curves.csv")
    summaries = rows(ROOT / f"results/{which}_summary.csv")
    exact_checks = 0
    float_checks = 0
    decimal_checks = 0
    computed = []

    def check(row, key, value):
        nonlocal exact_checks, float_checks
        assert row[key + "_exact"] == ("NA" if value is None else str(value)), (
            which,
            key,
        )
        exact_checks += 1
        if value is None:
            assert row[key] == "NA"
        else:
            assert abs(float(row[key]) - float(value)) <= 1e-12, (which, key, "float")
        float_checks += 1

    with localcontext() as context:
        context.prec = 90
        for agency, month in db.execute(
            "SELECT DISTINCT agency,month FROM cells ORDER BY agency,month"
        ).fetchall():
            if phase(agency, month) != which:
                continue
            for cutoff in [35, 45]:
                for endpoint in ["date_only", "closed_status_and_date"]:
                    db.execute("DROP TABLE IF EXISTS observed")
                    # The query constructs the endpoint and observation independently of Python's generator.
                    db.execute(
                        """CREATE TEMP TABLE observed AS
                        WITH panel AS (
                          SELECT w, ?-created+1 AS censor,
                            CASE WHEN delay IN ('missing','gt45') OR (?='closed_status_and_date' AND status!='closed')
                              THEN NULL ELSE CAST(delay AS INTEGER) END AS closure
                          FROM cells WHERE agency=? AND month=?
                        )
                        SELECT *, CASE WHEN closure IS NOT NULL AND closure<=censor THEN 1 ELSE 0 END AS event,
                          CASE WHEN closure IS NOT NULL AND closure<=censor THEN closure ELSE censor END AS observed
                        FROM panel""",
                        (cutoff, endpoint, agency, month),
                    )
                    subset = [
                        r
                        for r in curves
                        if r["agency"] == agency
                        and int(r["month"]) == month
                        and int(r["cutoff"]) == cutoff
                        and r["endpoint"] == endpoint
                    ]
                    assert len(subset) == 46
                    sn, sd = 1, 1
                    decimal_s = Decimal(1)
                    steps = []
                    decimal_steps = []
                    for day in range(46):
                        risk, event, censor = db.execute(
                            """SELECT
                          COALESCE(SUM(CASE WHEN observed>=? THEN w ELSE 0 END),0),
                          COALESCE(SUM(CASE WHEN observed=? AND event=1 THEN w ELSE 0 END),0),
                          COALESCE(SUM(CASE WHEN observed=? AND event=0 THEN w ELSE 0 END),0)
                          FROM observed""",
                            (day, day, day),
                        ).fetchone()
                        row = next(r for r in subset if int(r["day"]) == day)
                        for key, value in [
                            ("at_risk", risk),
                            ("events", event),
                            ("censors", censor),
                        ]:
                            assert int(row[key]) == value
                            exact_checks += 1
                        if risk:
                            assert sn is not None
                            sn *= risk - event
                            sd *= risk
                            g = math.gcd(sn, sd)
                            sn //= g
                            sd //= g
                            decimal_s *= Decimal(risk - event) / Decimal(risk)
                        elif sn != 0:
                            sn = None
                            sd = None
                            decimal_s = None
                        s = None if sn is None else Fraction(sn, sd)
                        check(row, "survival", s)
                        steps.append(s)
                        decimal_steps.append(decimal_s)
                        if s is not None:
                            assert abs(
                                Decimal(s.numerator) / Decimal(s.denominator)
                                - decimal_s
                            ) < Decimal("1e-70")
                            decimal_checks += 1
                    for tau in [7, 14, 28]:
                        row = next(
                            r
                            for r in stored
                            if r["agency"] == agency
                            and int(r["month"]) == month
                            and int(r["cutoff"]) == cutoff
                            and r["endpoint"] == endpoint
                            and int(r["tau"]) == tau
                        )
                        n, done, benchmark, lower, upper, capped, uncapped = db.execute(
                            """SELECT SUM(w),
                          SUM(CASE WHEN event=1 THEN w ELSE 0 END),
                          SUM(w*MIN(COALESCE(closure,?),?)), SUM(w*MIN(observed,?)),
                          SUM(w*CASE WHEN event=1 THEN MIN(observed,?) ELSE ? END),
                          SUM(CASE WHEN event=1 THEN w*MIN(closure,?) ELSE 0 END),
                          SUM(CASE WHEN event=1 THEN w*closure ELSE 0 END)
                          FROM observed""",
                            (tau, tau, tau, tau, tau, tau),
                        ).fetchone()
                        for key, value in [
                            ("eligible_rows", n),
                            ("observed_events", done),
                            ("censored_rows", n - done),
                        ]:
                            assert int(row[key]) == value
                            exact_checks += 1
                        rmst = (
                            sum(steps[:tau], Fraction())
                            if all(s is not None for s in steps[:tau])
                            else None
                        )
                        if rmst is not None:
                            assert abs(
                                sum(decimal_steps[:tau], Decimal())
                                - Decimal(rmst.numerator) / Decimal(rmst.denominator)
                            ) < Decimal("1e-70")
                            decimal_checks += 1
                        target = Fraction(benchmark, n)
                        lo = Fraction(lower, n)
                        hi = Fraction(upper, n)
                        naive = Fraction(capped, done) if done else None
                        values = {
                            "benchmark": target,
                            "completed_capped": naive,
                            "completed_uncapped": (
                                Fraction(uncapped, done) if done else None
                            ),
                            "rmst": rmst,
                            "lower_bound": lo,
                            "upper_bound": hi,
                            "completed_abs_error": (
                                abs(naive - target) if naive is not None else None
                            ),
                            "rmst_abs_error": (
                                abs(rmst - target) if rmst is not None else None
                            ),
                        }
                        for key, value in values.items():
                            check(row, key, value)
                        assert lo <= target <= hi
                        assert row["rmst_status"] == (
                            "ESTIMABLE" if rmst is not None else "NOT_ESTIMABLE"
                        )
                        within = "UNDEFINED" if rmst is None else str(lo <= rmst <= hi)
                        assert row["rmst_within_bounds"] == within
                        exact_checks += 3
                        computed.append(
                            {
                                "cutoff": cutoff,
                                "endpoint": endpoint,
                                "tau": tau,
                                **values,
                                "within": within,
                            }
                        )
        assert len(computed) == (48 if which == "development" else 96) and len(
            stored
        ) == len(computed)
        for row in summaries:
            subset = [
                r
                for r in computed
                if r["cutoff"] == int(row["cutoff"])
                and r["endpoint"] == row["endpoint"]
                and r["tau"] == int(row["tau"])
            ]
            paired = [
                r
                for r in subset
                if r["rmst"] is not None and r["completed_capped"] is not None
            ]
            n = len(paired)
            pairs = [(r["rmst_abs_error"], r["completed_abs_error"]) for r in paired]
            for key, value in [
                ("panels", len(subset)),
                ("paired_estimable_panels", n),
                ("rmst_wins", sum(k < v for k, v in pairs)),
                ("completed_wins", sum(v < k for k, v in pairs)),
                ("ties", sum(k == v for k, v in pairs)),
                ("rmst_outside_bounds", sum(r["within"] == "False" for r in subset)),
            ]:
                assert int(row[key]) == value
                exact_checks += 1
            check(
                row,
                "rmst_mae",
                sum((k for k, v in pairs), Fraction()) / n if n else None,
            )
            check(
                row,
                "completed_mae",
                sum((v for k, v in pairs), Fraction()) / n if n else None,
            )
    assert len(summaries) == 12
    cert = {
        "status": "PASS",
        "phase": which,
        "settings": len(computed),
        "curve_steps": len(curves),
        "exact_scalar_checks": exact_checks,
        "reported_float_checks": float_checks,
        "independent_decimal_checks": decimal_checks,
        "decimal_precision": 90,
        "decimal_tolerance": "1e-70",
        "reported_float_tolerance": "1e-12",
        "methods": "SQLite observation/risk/event/censor/benchmark sums; integer products reduced by gcd; separate high-precision decimal survival integration; complete setting/summary comparison",
        "limits": "Arithmetic verification of the declared captured-record reconstruction; independent-censoring assumptions and true resolution are not verified",
    }
    (ROOT / f"results/{which.upper()}_INDEPENDENT_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["development", "evaluation"])
    a = p.parse_args()
    verify(a.phase)
