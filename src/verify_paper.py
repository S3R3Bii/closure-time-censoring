"""Verify all manuscript tables and claims, approved bytes and bounded PDF safety."""

import csv
import hashlib
import json
import re
import unicodedata
from pypdf import PdfReader
from config import ROOT


def read(name):
    with (ROOT / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    scope = json.loads((ROOT / "paper/PUBLICATION_SCOPE.json").read_text())
    assert (
        scope["scope"] == "independent-program-study"
        and scope["formal_submission_target"] is False
        and len(scope["public_files"]) == 5
    )
    for n, h in scope["public_files"].items():
        assert hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h, n
    tex = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    checks = 0

    def require(text):
        nonlocal checks
        assert text in tex, text
        checks += 1

    certs = {
        name: json.loads((ROOT / f"results/{name}.json").read_text())
        for name in [
            "SOURCE_CHECK",
            "INDEPENDENT_SOURCE_CHECK",
            "DEVELOPMENT_INDEPENDENT_CHECK",
            "EVALUATION_INDEPENDENT_CHECK",
            "REPRODUCTION",
            "FIGURE_CHECK",
        ]
    }
    assert all(r["status"] == "PASS" for r in certs.values())
    source = read("results/source_panels.csv")
    settings = read("results/evaluation_settings.csv")
    summaries = read("results/evaluation_summary.csv")
    mon = {"4": "Apr", "5": "May", "6": "Jun", "7": "Jul"}
    assert len(source) == 12 and len(settings) == 96 and len(summaries) == 12
    for r in source:
        require(
            " & ".join(
                [
                    r["agency"],
                    mon[r["month"]],
                    r["phase"].capitalize(),
                    f"{int(r['source_rows']):,}",
                    r["quarantined_rows"],
                    f"{int(r['eligible_rows']):,}",
                ]
            )
        )
    assert sum(int(r["source_rows"]) for r in source) == 273641
    assert sum(int(r["quarantined_rows"]) for r in source) == 195
    assert sum(int(r["date_present_status_not_closed"]) for r in source) == 392
    assert sum(int(r["closed_status_date_missing"]) for r in source) == 1
    primary = [
        r
        for r in settings
        if (r["cutoff"], r["endpoint"], r["tau"]) == ("35", "date_only", "28")
    ]
    for r in primary:
        require(
            " & ".join(
                [
                    r["agency"] + " " + mon[r["month"]],
                    f"{int(r['eligible_rows']):,}",
                    f"{100*int(r['censored_rows'])/int(r['eligible_rows']):.1f}\\%",
                    *[
                        f"{float(r[k]):.3f}"
                        for k in ["benchmark", "completed_capped", "rmst"]
                    ],
                    f"[{float(r['lower_bound']):.3f}, {float(r['upper_bound']):.3f}]",
                ]
            )
        )
    for r in summaries:
        require(
            " & ".join(
                [
                    r["tau"],
                    r["cutoff"],
                    "Date" if r["endpoint"] == "date_only" else "Closed + date",
                    f"{float(r['rmst_mae']):.4f}",
                    f"{float(r['completed_mae']):.4f}",
                    r["rmst_wins"] + " / " + r["paired_estimable_panels"],
                ]
            )
        )
        assert (
            r["paired_estimable_panels"],
            r["rmst_wins"],
            r["completed_wins"],
            r["ties"],
            r["rmst_outside_bounds"],
        ) == ("8", "8", "0", "0", "0")
        if r["tau"] == "7" or (r["cutoff"] == "45" and r["tau"] == "14"):
            assert r["rmst_mae_exact"] == "0"
    r = next(
        r
        for r in summaries
        if (r["cutoff"], r["endpoint"], r["tau"]) == ("35", "date_only", "28")
    )
    for key in ["rmst_mae", "completed_mae"]:
        require(f"{float(r[key]):.3f}")
    r = next(r for r in primary if r["agency"] == "DOT" and r["month"] == "7")
    for key in ["benchmark", "completed_capped", "rmst"]:
        require(f"{float(r[key]):.3f}")
    d = certs["DEVELOPMENT_INDEPENDENT_CHECK"]
    e = certs["EVALUATION_INDEPENDENT_CHECK"]
    for n in [
        certs["INDEPENDENT_SOURCE_CHECK"]["selected_field_checks"],
        certs["INDEPENDENT_SOURCE_CHECK"]["normalized_aggregate_scalar_checks"],
        d["exact_scalar_checks"] + e["exact_scalar_checks"],
        d["reported_float_checks"] + e["reported_float_checks"],
        d["independent_decimal_checks"] + e["independent_decimal_checks"],
        certs["REPRODUCTION"]["exact_csv_fields_or_json_documents"],
        certs["FIGURE_CHECK"]["plotted_values"],
    ]:
        require(f"{n:,}")
    for phrase in [
        "273,446",
        "273,641",
        "195",
        "392",
        "twenty-dependency freeze",
        "inputs were not blinded",
        "not historical dashboard exports",
        "not verified problem resolution",
        "not a guarantee of unbiasedness",
        "not verified and can fail",
        "not asserted to be sharp",
        "R execution is not claimed",
        "zero errors do not test recovery",
        "finite-cohort bounds",
        "all 96",
    ]:
        require(phrase)
    commands = [
        "python -m pip install -r requirements.txt",
        "python -m unittest discover -s tests -v",
        "python src/check_reproduction.py",
        "python src/verify_figures.py",
        "python src/verify_paper.py",
        "python src/verify_public_package.py",
    ]
    for command in commands:
        require(command)
    reader = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(reader.pages) == 8 and not reader.is_encrypted
    pages = [
        unicodedata.normalize("NFKC", p.extract_text() or "") for p in reader.pages
    ]
    headings = [
        "Decision and verified finding",
        "1. Source, partitions and quality accounting",
        "2. Fixed estimand and independent computation",
        "3. The primary held comparison",
        "4. Survival curves and what early agreement means",
        "5. Every held sensitivity result",
        "6. Complete summaries, interpretation and next evidence",
        "7. Reproduction and independent evidence",
    ]
    for text, title in zip(pages, headings):
        assert title in re.sub(r"\s+", " ", text), title
    normalized = re.sub(r"\s+", " ", " ".join(pages))
    for command in commands:
        assert command in normalized
        checks += 1
    for number in ["273,641", "273,446", "0.033", "1.689", "97,920", "1,368,205"]:
        assert number in normalized
        checks += 1
    assert not re.search(
        r"(?:[Cc]:\\[Uu]sers\\|/[Uu]sers/|/[Hh]ome/|github_pat_|ghp_[A-Za-z0-9]{20,})",
        normalized,
    )
    pdf_count = 0
    for name in scope["public_files"]:
        if not name.endswith(".pdf"):
            continue
        doc = PdfReader(ROOT / name)
        assert not doc.is_encrypted and not doc.attachments
        catalog = doc.trailer["/Root"]
        assert not any(k in catalog for k in ["/AA", "/AcroForm", "/Collection"])
        names = catalog.get("/Names", {})
        names = names.get_object() if hasattr(names, "get_object") else names
        assert "/JavaScript" not in names
        if "/OpenAction" in catalog:
            assert isinstance(catalog["/OpenAction"], list)
        for page in doc.pages:
            assert "/AA" not in page
            for ref in page.get("/Annots", []):
                annotation = ref.get_object()
                assert "/AA" not in annotation
                action = annotation.get("/A")
                if action:
                    action = action.get_object()
                    assert action["/S"] in ["/URI", "/GoTo"]
                    if action["/S"] == "/URI":
                        assert str(action["/URI"]).startswith("https://")
        pdf_count += 1
    for name in ["primary_comparison", "survival_overview", "error_sensitivity"]:
        assert (ROOT / f"paper/images/{name}.pdf").read_bytes() == (
            ROOT / f"figures/{name}.pdf"
        ).read_bytes()
    result = {
        "status": "PASS",
        "manuscript_pages": 8,
        "numeric_table_and_text_checks": checks,
        "public_file_hashes_checked": 5,
        "pdfs_checked": pdf_count,
        "scope": "All12source rows,8primary rows,12summary rows; headline/check-count/qualification/command support; rendered headings and numeric text; approved exact bytes and bounded private-path/token scan",
        "pdf_security": "No active code, attachments, forms or additional actions; ordinary HTTPS links/navigation only. Rendered readability checked separately.",
    }
    (ROOT / "results/PAPER_CHECK.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
