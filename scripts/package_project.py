"""Create a clean source ZIP while retaining deterministic transfer fixtures."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    "node_modules", "build", "dist", "runs", "received",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}
EXCLUDED_FILES = {".DS_Store", "Thumbs.db"}
CURATED_RESULT_FILES = {"README.md", "experiment_results.csv", "aggregated_results.csv", "fault_rate_comparison.csv"}


def create_archive(destination: Path) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or path.name in EXCLUDED_FILES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED_DIRS for part in relative.parts):
                continue
            if relative.parts[:2] == ("data", "results"):
                if len(relative.parts) != 3 or path.name not in CURATED_RESULT_FILES:
                    continue
            # Keep figures generated from the included CSV; omit only transient plots manifests are handled normally.
            if path.resolve() == destination:
                continue
            archive.write(path, relative.as_posix())
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=ROOT.parent / "Reliable_UDP_Project.zip")
    args = parser.parse_args()
    archive = create_archive(args.output)
    print(f"Archive created: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
