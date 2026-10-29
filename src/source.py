"""Minimal official source projection; only privacy-preserving aggregate bins are public."""

from collections import Counter
from datetime import datetime, date
import csv, gzip, io, json
from config import FIELDS


def parse_record(row, capture_date):
    assert set(row) <= set(FIELDS), "Unexpected field in minimal response"
    key = row.get("unique_key")
    assert isinstance(key, str) and key.strip(), "Missing ID"
    created = row.get("created_date")
    assert isinstance(created, str) and created
    try:
        c = datetime.fromisoformat(created)
    except (ValueError, TypeError):
        raise AssertionError("Unparseable creation")
    assert (
        c.tzinfo is None
        and c.year == 2026
        and c.month in [4, 5, 6, 7]
        and 1 <= c.day <= 28
    ), "Creation cohort mismatch"
    agency = row.get("agency")
    assert agency in ["DOT", "DEP", "DSNY"]
    status = row.get("status", "")
    assert isinstance(status, str)
    status_category = (
        "missing"
        if not status.strip()
        else "closed" if status.strip().casefold() == "closed" else "other"
    )
    close = row.get("closed_date", "")
    assert isinstance(close, str)
    quality = "eligible"
    delay = "missing"
    if close:
        try:
            t = datetime.fromisoformat(close)
        except (ValueError, TypeError):
            quality = "unparseable_closure"
        else:
            if t.tzinfo is not None:
                quality = "timezone_closure"
            elif t < c:
                quality = "closure_before_creation"
            elif t.date() > capture_date:
                quality = "closure_after_capture"
            else:
                elapsed = (t.date() - c.date()).days
                delay = str(elapsed) if elapsed <= 45 else "gt45"
    cell = (agency, str(c.month), str(c.day), delay, status_category, quality)
    return key, cell


def aggregate(rows, capture_date):
    seen = set()
    bins = Counter()
    for row in rows:
        key, cell = parse_record(row, capture_date)
        assert key not in seen, "Duplicate source ID"
        seen.add(key)
        bins[cell] += 1
    return bins


def write_bins(path, bins):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "agency",
            "month",
            "created_day",
            "closure_delay_cell",
            "status_category",
            "quality",
            "count",
        ]
    )
    for key, n in sorted(bins.items()):
        w.writerow([*key, n])
    path.write_bytes(gzip.compress(buf.getvalue().encode("utf-8"), mtime=0))


def read_bins(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_json(path, obj):
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
