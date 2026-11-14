"""Audit the documentation and evidence required for a Reliable UDP v1.0 release."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.results import validate_schema
EXPECTED_MATRIX_COUNTS = {
    "loss": 200,
    "delay": 140,
    "reordering": 200,
    "corruption": 100,
    "duplication": 100,
    "timeout": 90,
    "combined": 75,
}
REQUIRED_DOCS = (
    "PROTOCOL_SPEC.md",
    "FAULT_MODEL.md",
    "EXPERIMENT_METHODOLOGY.md",
    "ARCHITECTURE.md",
    "BENCHMARKS.md",
    "LIMITATIONS.md",
    "DIAGRAMS.md",
    "MILESTONE_4_REPORT.md",
    "RELEASE_CHECKLIST.md",
    "DEMO_SCRIPT.md",
    "DESIGN_DECISIONS.md",
    "INTERVIEW_PREPARATION.md",
)


def audit_docs(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_DOCS:
        path = root / "docs" / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"Missing or empty document: docs/{relative}")
    for relative in ("README.md", "LICENSE", "CHANGELOG.md"):
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"Missing or empty root file: {relative}")
    return errors


def audit_results(csv_path: Path, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if not csv_path.is_file():
        return [f"Missing full experiment CSV: {csv_path}"]
    try:
        validate_schema(csv_path)
    except Exception as exc:
        return [f"CSV schema validation failed: {exc}"]

    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != sum(EXPECTED_MATRIX_COUNTS.values()):
        errors.append(
            f"Expected {sum(EXPECTED_MATRIX_COUNTS.values())} attempts, found {len(rows)}"
        )
    counts = Counter(row.get("fault_matrix", "") for row in rows)
    if dict(counts) != EXPECTED_MATRIX_COUNTS:
        errors.append(f"Matrix counts mismatch: expected {EXPECTED_MATRIX_COUNTS}, found {dict(counts)}")

    seeds = [row.get("seed", "") for row in rows]
    if len(seeds) != len(set(seeds)):
        errors.append("Run seeds are not unique")

    for row in rows:
        status = row.get("status", "")
        verified = row.get("hash_verified", "").strip().lower() in {"true", "1", "yes"}
        if status == "success" and not verified:
            errors.append(f"Success row is not integrity-verified: {row.get('run_id')}")
            break
        if status == "failed" and row.get("throughput", "").strip():
            errors.append(f"Failed row has a throughput value: {row.get('run_id')}")
            break
        if status not in {"success", "failed"}:
            errors.append(f"Unknown run status in row: {row.get('run_id')}")
            break

    results_dir = csv_path.parent
    for filename in ("aggregated_results.csv", "fault_rate_comparison.csv"):
        if not (results_dir / filename).is_file():
            errors.append(f"Missing analysis output: {results_dir / filename}")

    manifest_path = root / "docs" / "graphs" / "plots_manifest.json"
    if not manifest_path.is_file():
        errors.append("Missing docs/graphs/plots_manifest.json")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for filename in manifest.get("plots", []):
                if not (manifest_path.parent / filename).is_file():
                    errors.append(f"Manifest plot is missing: docs/graphs/{filename}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid plots manifest: {exc}")

    if any(row.get("status") == "failed" for row in rows):
        errors.append("One or more full-matrix attempts failed; review failures before release")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-only", action="store_true", help="Check release documents without requiring the full matrix")
    parser.add_argument("--csv", type=Path, default=ROOT / "data/results/experiment_results.csv")
    args = parser.parse_args()

    errors = audit_docs()
    if not args.docs_only:
        errors.extend(audit_results(args.csv))
    if errors:
        print("RELEASE NOT READY")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Documentation preflight passed." if args.docs_only else "Full v1.0 evidence gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
