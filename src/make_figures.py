"""Three original source-backed figures; finite-panel comparisons, no sampling inference."""

import csv
import calendar
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
from config import ROOT


def read(name):
    with (ROOT / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def label(r):
    return r["agency"] + " " + calendar.month_abbr[int(r["month"])]


def build():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "svg.fonttype": "none",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    rows = read("results/evaluation_settings.csv")
    primary = [
        r
        for r in rows
        if r["cutoff"] == "35" and r["endpoint"] == "date_only" and r["tau"] == "28"
    ]
    keys = [(r["agency"], r["month"]) for r in primary]
    fig1, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
    y = np.arange(len(primary))
    for i, r in enumerate(primary):
        (line,) = ax.plot(
            [float(r["lower_bound"]), float(r["upper_bound"])],
            [i, i],
            color="#9ca3af",
            lw=5,
            solid_capstyle="round",
            label="Observation bounds" if i == 0 else None,
        )
        line.set_gid("bounds-" + str(i))
    for field, color, marker, title in [
        ("benchmark", "#111827", "|", "Later-record benchmark"),
        ("completed_capped", "#b45309", "o", "Completed cases only"),
        ("rmst", "#0369a1", "D", "Censoring-aware RMST"),
    ]:
        art = ax.scatter(
            [float(r[field]) for r in primary],
            y,
            s=75 if field == "benchmark" else 37,
            c=color,
            marker=marker,
            label=title,
            zorder=3,
        )
        art.set_gid(field)
    ax.set_yticks(y, [label(r) for r in primary])
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.set_xlabel("28-day restricted recorded closure time (calendar days)")
    ax.set_title(
        "The completed-case summary omits unfinished requests", loc="left", pad=14
    )
    ax.grid(axis="x", alpha=0.18)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    figures = [("primary_comparison", fig1)]

    curve_rows = read("results/evaluation_curves.csv")
    fig2, axes = plt.subplots(
        2, 4, figsize=(8, 4.6), sharex=True, sharey=True, layout="constrained"
    )
    for ax, key in zip(axes.flat, keys):
        part = [
            r
            for r in curve_rows
            if (r["agency"], r["month"]) == key
            and r["cutoff"] == "35"
            and r["endpoint"] == "date_only"
            and int(r["day"]) <= 28
        ]
        (line,) = ax.step(
            [int(r["day"]) for r in part],
            [float(r["survival"]) for r in part],
            where="post",
            color="#0369a1",
            lw=1.8,
        )
        line.set_gid("curve-" + key[0] + "-" + key[1])
        ax.set_title(label(part[0]), fontsize=11, loc="left")
        ax.set_xlim(0, 28)
        ax.set_ylim(0, 1)
        ax.set_xticks([0, 7, 14, 21, 28])
        ax.grid(alpha=0.17)
    fig2.supxlabel("Calendar days since request creation", fontsize=11)
    fig2.supylabel("Estimated fraction without recorded closure", fontsize=11)
    fig2.suptitle(
        "All eight held panels under the primary observation rule",
        x=0.05,
        ha="left",
        fontsize=13,
    )
    figures.append(("survival_overview", fig2))

    settings = [
        (str(c), e, str(t))
        for t in [7, 14, 28]
        for c in [35, 45]
        for e in ["date_only", "closed_status_and_date"]
    ]
    matrix = np.array(
        [
            [
                float(
                    next(
                        r
                        for r in rows
                        if (r["agency"], r["month"]) == key
                        and (r["cutoff"], r["endpoint"], r["tau"]) == setting
                    )["rmst_abs_error"]
                )
                - float(
                    next(
                        r
                        for r in rows
                        if (r["agency"], r["month"]) == key
                        and (r["cutoff"], r["endpoint"], r["tau"]) == setting
                    )["completed_abs_error"]
                )
                for key in keys
            ]
            for setting in settings
        ]
    )
    limit = max(abs(matrix.min()), abs(matrix.max()))
    fig3, ax = plt.subplots(figsize=(8, 6.3), layout="constrained")
    image = ax.imshow(
        matrix,
        cmap="RdBu_r",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit),
        aspect="auto",
    )
    image.set_gid("all_error_differences")
    ax.set_xticks(
        range(8), [label(r).replace(" ", "\n") for r in primary], fontsize=10.5
    )
    ax.set_yticks(
        range(12),
        [
            f"{t}d | +{c} | " + ("Date" if e == "date_only" else "Closed + date")
            for c, e, t in settings
        ],
        fontsize=10.5,
    )
    for i in range(12):
        for j in range(8):
            ax.text(
                j,
                i,
                f"{matrix[i,j]:.2f}",
                ha="center",
                va="center",
                fontsize=10,
                color="white" if abs(matrix[i, j]) > limit * 0.6 else "#111827",
            )
    for boundary in [3.5, 7.5]:
        ax.axhline(boundary, color="white", lw=2)
    ax.set_title(
        "Every held endpoint / cutoff / horizon comparison", loc="left", pad=14
    )
    ax.set_ylabel("Horizon | cutoff from cohort start | endpoint", fontsize=10)
    bar = fig3.colorbar(
        image, ax=ax, orientation="horizontal", fraction=0.065, pad=0.08
    )
    bar.set_label(
        "RMST absolute error − completed-case absolute error (days)\nNegative values favor RMST within this reconstruction",
        fontsize=10,
    )
    figures.append(("error_sensitivity", fig3))
    return figures


def main():
    for name, fig in build():
        fig.savefig(
            ROOT / f"figures/{name}.pdf",
            metadata={
                "CreationDate": None,
                "ModDate": None,
                "Creator": "Study05 reproducible Python figure",
            },
        )
        fig.savefig(ROOT / f"figures/{name}.svg")
        fig.savefig(ROOT / f"figures/{name}.png", dpi=150)
        svg = ROOT / f"figures/{name}.svg"
        svg.write_bytes(
            (
                "\n".join(
                    line.rstrip()
                    for line in svg.read_text(encoding="utf-8").splitlines()
                )
                + "\n"
            ).encode()
        )
        plt.close(fig)
    print("Created three original PDF/SVG/PNG figures")


if __name__ == "__main__":
    main()
