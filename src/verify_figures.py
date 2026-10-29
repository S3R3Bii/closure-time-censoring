"""Inspect plotted artist coordinates against independently verified full output tables."""

import csv
import hashlib
import json
import numpy as np
import matplotlib.pyplot as plt
from config import ROOT
from make_figures import build


def read(name):
    with (ROOT / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    assert (
        json.loads((ROOT / "results/EVALUATION_INDEPENDENT_CHECK.json").read_text())[
            "status"
        ]
        == "PASS"
    )
    rows = read("results/evaluation_settings.csv")
    curves = read("results/evaluation_curves.csv")
    primary = [
        r
        for r in rows
        if (r["cutoff"], r["endpoint"], r["tau"]) == ("35", "date_only", "28")
    ]
    figures = build()
    checks = 0
    ax = figures[0][1].axes[0]
    for i, r in enumerate(primary):
        line = next(a for a in ax.lines if a.get_gid() == "bounds-" + str(i))
        assert np.allclose(
            line.get_xdata(),
            [float(r["lower_bound"]), float(r["upper_bound"])],
            rtol=0,
            atol=1e-12,
        )
        assert list(line.get_ydata()) == [i, i]
        checks += 2
    for key in ["benchmark", "completed_capped", "rmst"]:
        artist = next(a for a in ax.collections if a.get_gid() == key)
        assert np.allclose(
            artist.get_offsets(),
            [[float(r[key]), i] for i, r in enumerate(primary)],
            rtol=0,
            atol=1e-12,
        )
        checks += len(primary)
    for ax, r in zip(figures[1][1].axes, primary):
        selected = sorted(
            [
                v
                for v in curves
                if v["agency"] == r["agency"]
                and v["month"] == r["month"]
                and v["cutoff"] == "35"
                and v["endpoint"] == "date_only"
                and int(v["day"]) <= 28
            ],
            key=lambda v: int(v["day"]),
        )
        assert list(ax.lines[0].get_xdata()) == list(range(29))
        assert np.allclose(
            ax.lines[0].get_ydata(),
            [float(v["survival"]) for v in selected],
            rtol=0,
            atol=1e-12,
        )
        checks += 29
    matrix = figures[2][1].axes[0].images[0].get_array()
    assert matrix.shape == (12, 8)
    i = 0
    for tau in ["7", "14", "28"]:
        for cutoff in ["35", "45"]:
            for endpoint in ["date_only", "closed_status_and_date"]:
                for j, r in enumerate(primary):
                    v = next(
                        v
                        for v in rows
                        if all(
                            v[k] == value
                            for k, value in [
                                ("agency", r["agency"]),
                                ("month", r["month"]),
                                ("tau", tau),
                                ("cutoff", cutoff),
                                ("endpoint", endpoint),
                            ]
                        )
                    )
                    assert (
                        abs(
                            float(matrix[i, j])
                            - (
                                float(v["rmst_abs_error"])
                                - float(v["completed_abs_error"])
                            )
                        )
                        <= 1e-12
                    )
                    checks += 1
                i += 1
    for name, fig in figures:
        assert (ROOT / f"figures/{name}.pdf").read_bytes().startswith(b"%PDF-")
        assert "<svg" in (ROOT / f"figures/{name}.svg").read_text(encoding="utf-8")
        plt.close(fig)
    result = {
        "status": "PASS",
        "plotted_values": checks,
        "figure_hashes": {
            f"figures/{name}.{ext}": hashlib.sha256(
                (ROOT / f"figures/{name}.{ext}").read_bytes()
            ).hexdigest()
            for name, fig in figures
            for ext in ["pdf", "svg", "png"]
        },
        "scope": "All primary bounds/three point series, all 232 survival ordinates and all 96 held error differences checked on plotted artists against independently verified output tables; rendered readability checked separately",
    }
    (ROOT / "results/FIGURE_CHECK.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "plotted_values": checks}))


if __name__ == "__main__":
    main()
