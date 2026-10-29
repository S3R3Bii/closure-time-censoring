"""Offline replay from public aggregate counts, with exact freeze and source-certificate binding."""

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from config import ROOT


def main():
    freeze = json.loads((ROOT / "results/CODE_FREEZE.json").read_text())
    for name, digest in freeze["sha256"].items():
        payload = (ROOT / name).read_bytes()
        if not name.endswith(".gz"):
            payload = payload.replace(b"\r\n", b"\n")
        assert hashlib.sha256(payload).hexdigest() == digest, name
    cert = json.loads((ROOT / "results/INDEPENDENT_SOURCE_CHECK.json").read_text())
    manifest = json.loads((ROOT / "data/source/manifest.json").read_text())
    assert (
        cert["status"] == "PASS"
        and cert["public_aggregate_sha256"] == manifest["public_aggregate_sha256"]
    )
    assert (
        cert["public_manifest_sha256"]
        == hashlib.sha256(
            (ROOT / "data/source/manifest.json").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
    )
    targets = [
        "data/timing_cells.csv",
        "results/source_panels.csv",
        "results/SOURCE_CHECK.json",
    ]
    for phase in ["development", "evaluation"]:
        targets.extend(
            [
                f"results/{phase}_{suffix}.csv"
                for suffix in ["settings", "curves", "summary"]
            ]
        )
        targets.extend(
            [
                f"results/{phase.upper()}_{suffix}.json"
                for suffix in ["CHECK", "INDEPENDENT_CHECK"]
            ]
        )
    count = 0
    with tempfile.TemporaryDirectory(prefix="closure-replay-") as temp:
        out = Path(temp)
        for name in ["src", "data"]:
            shutil.copytree(ROOT / name, out / name)
        (out / "results").mkdir()
        for command in [
            ["ingest.py"],
            ["analysis.py", "development"],
            ["verify_metrics.py", "development"],
            ["analysis.py", "evaluation"],
            ["verify_metrics.py", "evaluation"],
        ]:
            subprocess.run(
                [sys.executable, str(out / "src" / command[0]), *command[1:]],
                check=True,
                capture_output=True,
                text=True,
            )
        for name in targets:
            if name.endswith(".csv"):
                with (ROOT / name).open(encoding="utf-8", newline="") as f:
                    left = list(csv.DictReader(f))
                with (out / name).open(encoding="utf-8", newline="") as f:
                    right = list(csv.DictReader(f))
                assert left == right, name
                count += sum(len(r) for r in left)
            else:
                assert json.loads((ROOT / name).read_text()) == json.loads(
                    (out / name).read_text()
                ), name
                count += 1
    result = {
        "status": "PASS",
        "exact_csv_fields_or_json_documents": count,
        "frozen_dependencies": len(freeze["sha256"]),
        "scope": "Isolated source aggregation, all 144 settings, all survival steps and independent SQL/integer/decimal reconstruction; no network or private originals required",
        "source_original_limit": "Private-original reconciliation is a retained hash-bound certificate; public replay cannot independently access unpublished request identifiers/timestamps",
    }
    (ROOT / "results/REPRODUCTION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
