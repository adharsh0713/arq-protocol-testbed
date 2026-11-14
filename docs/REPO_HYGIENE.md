# Reliable UDP - Repository Hygiene Checklist

## Current source layout

```text
reliable-udp/
├── algorithms/          # Stop-and-Wait, Go-Back-N, Selective Repeat and ARQ tests
├── protocol/            # Packet format, CRC, timers, control messages and config tests
├── sender/              # Sender CLI and sender-side metrics
├── receiver/            # Import-safe receiver, integrity checks and receiver tests
├── network/             # Seeded fault injectors, UDP proxy and fault/proxy tests
├── experiments/         # Metrics, tiered runner, frozen CSV, analysis, plots and E2E tests
├── scripts/             # Deterministic fixture generator and packaging utility
├── data/
│   ├── test_files/      # Deterministic text, PNG, WAV fixtures and manifest
│   └── results/         # Curated final CSV/aggregates tracked; per-run JSON/logs ignored
├── docs/
│   ├── graphs/          # CSV-derived figures plus plots manifest
│   └── *.md             # Specifications, method, decisions, plans and reports
├── .github/workflows/   # Fast-test and smoke CI workflow
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

Tests are kept beside their owning package rather than duplicated in a separate top-level `tests/` directory. The root `test_config.py` holds shared-configuration tests so pytest discovers them from both supported invocations.

## Source-control rules

- Commit source, tests, deterministic fixture files and generator, pinned requirements, documentation, and selected verified research evidence.
- Do not commit virtual environments, Python caches, pytest/coverage caches, temporary `.part` files, logs, editor state, machine-specific paths, credentials, or runtime result directories.
- `data/test_files/` is deterministic project test input and is tracked. `data/results/` retains the curated `experiment_results.csv`, `aggregated_results.csv`, and `fault_rate_comparison.csv`; bulky per-run directories remain ignored and are preserved separately when needed.
- Generated figures must be tied to the committed source CSV, listed in `docs/graphs/plots_manifest.json`, and reproducible with `python -m experiments.analysis`; do not commit plots generated from stale or unverified data.
- Each experiment writes to a unique run directory. Sender, receiver and proxy do not share metrics filenames across concurrent runs.

## Cleanup and hygiene status

| Item | Action taken | Status |
|---|---|---|
| Root empty `__init__.py` | Removed during M1 | Complete |
| `docs/architecture.md` | Removed obsolete empty lowercase file; required `ARCHITECTURE.md` exists | Complete |
| `docs/experiment_results.md` | Removed obsolete empty lowercase file; final `BENCHMARKS.md` remains M4 because full data is not yet available | Complete / M4 evidence pending |
| `experiments/plots.py` | Implemented reproducible CSV-based plots | Complete |
| `experiments/launcher.py` | Removed duplicate/broken entry point | Complete |
| Root `create_zip.py` | Replaced by `scripts/package_project.py` | Complete |
| Root/package init files | Retained only where Python package semantics/tests require them; removed empty root initializer | Complete |
| `requirements.txt` | Pinned pytest, pandas, matplotlib and numpy versions | Complete |
| Print-only fault tests | Replaced by seeded assertion-based tests | Complete |
| README | Rewritten against current commands, source layout and supported experiment tiers | Complete |
| Deterministic fixtures | Generated text, PNG and WAV files plus SHA-256 manifest | Complete |
| Per-run metrics and outputs | Unique IDs, ports and sender/receiver/proxy JSON paths | Complete |
| Result artifacts | Curated CSV/aggregate/fault table and CSV-derived figures tracked; run directories ignored | Complete for smoke evidence; full-matrix evidence pending |
| License and repository metadata | MIT license and suggested description/topics prepared | Complete / external metadata update pending |
| Verified benchmark CSV and plots | Smoke CSV and five plots committed; full matrix remains unrun | M4 evidence pending |
| Demo and tagged v1.0 release | Script prepared; recording and GitHub publication remain release gates | M4 |

## Local quality gates

Run from the repository root:

```bash
python -m compileall -q .
pytest -q
python -m pytest -q
python -m experiments.runner --tier smoke
```

The default pytest configuration excludes tests marked `slow`. Three process-level loopback tests are part of the fast suite; the full benchmark is deliberately not a pytest test.

Before v1.0:

- Run and retain the full pre-registered matrix only after schema and methodology are frozen.
- Re-run analysis from the final CSV and verify every output plot is reproducible.
- Confirm all required release documents and protocol/architecture/sequence diagrams exist and are non-empty.
- Run README quick-start commands from a clean environment on supported platforms.
- Inspect `git status --short` and `git diff --check` in the actual Git checkout.
- Confirm the v1.0 tag does not precede the Definition of Done.

## Milestone gates

- **M1:** packet, configuration and ARQ sender correctness.
- **M2:** testable receiver, deterministic fault injectors and queued proxy.
- **M3:** 100-test fast suite (18 extended tests separately marked `slow`), deterministic fixtures, loopback E2E coverage, frozen 87-column result schema, smoke/quick/full tiers, failure-aware analysis, plots and CI workflow.
- **M4:** full verified evidence, final conclusions, release assets and v1.0.
