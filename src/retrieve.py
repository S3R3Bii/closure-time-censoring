"""Sequential publicAPI capture with version/count guards; originals remain private."""

import argparse, hashlib, json, time
from datetime import datetime, date, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from config import ROOT, AGENCIES, MONTHS, FIELDS
from source import aggregate, write_bins, save_json

META = "https://data.cityofnewyork.us/api/views/erm2-nwe9.json"
BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"


def get(url):
    with urlopen(
        Request(url, headers={"User-Agent": "IndependentServiceClosureResearch/1.0"}),
        timeout=90,
    ) as response:
        assert response.status == 200
        data = response.read()
    return data, json.loads(data)


def where(month, agency):
    return f"created_date >= '2026-{month:02d}-01T00:00:00' AND created_date < '2026-{month:02d}-29T00:00:00' AND agency='{agency}'"


def query(params):
    return BASE + "?" + urlencode(params)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("originals", type=Path)
    p.add_argument("--capture-date", required=True)
    a = p.parse_args()
    raw = a.originals.resolve()
    assert not raw.is_relative_to(ROOT)
    raw.mkdir(parents=True, exist_ok=False)
    capture = date.fromisoformat(a.capture_date)
    assert (
        capture == datetime.now(timezone.utc).date()
    ), "Capture date must match this UTC retrieval day"
    data, meta = get(META)
    (raw / "metadata-before.json").write_bytes(data)
    version = meta["rowsUpdatedAt"]
    pages = []
    panels = []
    allrows = []
    save_json(
        raw / "CAPTURE_PROGRESS.json",
        {
            "state": "STARTED",
            "source_rows_updated_at": version,
            "capture_date": a.capture_date,
            "pages": pages,
            "panels": panels,
        },
    )
    for month in MONTHS:
        for agency in AGENCIES:
            url = query({"$select": "count(*) as n", "$where": where(month, agency)})
            count_bytes, count = get(url)
            total = int(count[0]["n"])
            assert 100 <= total <= 100000
            name = f"count-{month:02d}-{agency}-before.json"
            (raw / name).write_bytes(count_bytes)
            panels.append(
                {
                    "month": month,
                    "agency": agency,
                    "expected_rows": total,
                    "count_url": url,
                    "count_original": name,
                    "count_sha256": hashlib.sha256(count_bytes).hexdigest(),
                }
            )
            previous = None
            rows = []
            for offset in range(0, total, 5000):
                url = query(
                    {
                        "$select": ",".join(FIELDS),
                        "$where": where(month, agency),
                        "$order": "unique_key ASC",
                        "$limit": 5000,
                        "$offset": offset,
                    }
                )
                payload, part = get(url)
                assert len(part) == min(5000, total - offset)
                name = f"{month:02d}-{agency}-{offset:05d}.json"
                (raw / name).write_bytes(payload)
                for row in part:
                    assert row["agency"] == agency and row["created_date"].startswith(
                        f"2026-{month:02d}-"
                    )
                    key = row["unique_key"]
                    assert (
                        previous is None or key > previous
                    ), "Unstable sorted pagination"
                    previous = key
                rows.extend(part)
                pages.append(
                    {
                        "month": month,
                        "agency": agency,
                        "offset": offset,
                        "rows": len(part),
                        "url": url,
                        "original_file": name,
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "captured_utc": datetime.now(timezone.utc).isoformat(),
                    }
                )
                save_json(
                    raw / "CAPTURE_PROGRESS.json",
                    {
                        "state": "CAPTURING",
                        "source_rows_updated_at": version,
                        "capture_date": a.capture_date,
                        "pages": pages,
                        "panels": panels,
                    },
                )
                time.sleep(0.15)
            assert len(rows) == total
            allrows.extend(rows)
            print(
                json.dumps(
                    {
                        "month": month,
                        "agency": agency,
                        "captured_source_rows": len(rows),
                    }
                ),
                flush=True,
            )
    final = []
    for panel in panels:
        data, count = get(panel["count_url"])
        assert int(count[0]["n"]) == panel["expected_rows"]
        name = f"count-{panel['month']:02d}-{panel['agency']}-after.json"
        (raw / name).write_bytes(data)
        final.append(
            {
                "month": panel["month"],
                "agency": panel["agency"],
                "original_file": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "rows": int(count[0]["n"]),
            }
        )
    data, after = get(META)
    (raw / "metadata-after.json").write_bytes(data)
    assert after["rowsUpdatedAt"] == version, "Source changed;do not silentlyrefresh"
    bins = aggregate(allrows, capture)
    out = ROOT / "data/source/aggregate_cells.csv.gz"
    write_bins(out, bins)
    manifest = {
        "source": "NYC311erm2-nwe9",
        "source_url": BASE,
        "source_rows_updated_at": version,
        "capture_date": a.capture_date,
        "fields_requested": FIELDS,
        "total_rows": len(allrows),
        "aggregate_cells": len(bins),
        "metadata_before_sha256": hashlib.sha256(
            (raw / "metadata-before.json").read_bytes()
        ).hexdigest(),
        "metadata_after_sha256": hashlib.sha256(data).hexdigest(),
        "pages": pages,
        "panels": panels,
        "final_counts": final,
        "public_aggregate_file": out.relative_to(ROOT).as_posix(),
        "public_aggregate_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "privacy": "NoID,exacttimestamp,location,problem,descriptionorrawstatus published;0–45daycells exact andlaterdates pooledgt45",
        "version_limit": "Stablemetadata/counts areboundedcaptureevidence,nottransactionalorhistoricalvintageproof",
    }
    save_json(ROOT / "data/source/manifest.json", manifest)
    save_json(
        raw / "CAPTURE_PROGRESS.json",
        {
            "state": "COMPLETE",
            "source_rows_updated_at": version,
            "total_rows": len(allrows),
            "public_manifest_sha256": hashlib.sha256(
                (ROOT / "data/source/manifest.json").read_bytes()
            ).hexdigest(),
        },
    )
    print(
        json.dumps(
            {
                "status": "CAPTURED",
                "rows": len(allrows),
                "aggregate_cells": len(bins),
                "source_version": version,
            }
        )
    )


if __name__ == "__main__":
    main()
