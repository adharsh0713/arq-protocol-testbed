# Milestone 4 — Research Interpretation and Release Preparation

**Date:** 13 November 2026  
**Status:** Documentation and release-candidate preparation completed; final research/release gate remains open.

## 1. Objective

Milestone 4 converts the implemented ARQ testbed into an auditable research artifact: run the frozen 905-attempt matrix, interpret all six research questions from verified evidence, finalize diagrams/limitations, and prepare a v1.0 release.

## 2. Completed in this workspace

- Rebuilt the Milestone 3 source archive from its exact project contents and independently extracted/tested it: 100 passed, 18 slow tests deselected.
- Executed a fresh six-attempt smoke matrix on the M4 working tree. All six transfers succeeded and passed the runner's byte-count, SHA-256, and effective-configuration checks.
- Retained the smoke `experiment_results.csv` (87 columns), aggregate summary, fault-rate comparison, per-run process reports, and five plots.
- Completed packet-format, architecture, and three ARQ loss/recovery sequence diagrams in `DIAGRAMS.md`.
- Added `BENCHMARKS.md` with measured smoke observations and an explicit inconclusive answer register for RQ1–RQ6.
- Completed protocol specification, architecture, fault model, methodology, limitations, design decisions, technical interview answers, README, changelog, MIT license, repository metadata, and demo storyboard.
- Added a v1.0 release checklist and `scripts/verify_release.py` so the final evidence gate is machine-checkable.
- Updated packaging rules to retain the curated CSV/aggregate/fault table and generated figures while excluding bulky per-run execution folders.

## 3. Smoke observations

| Protocol | 0% matched DATA/ACK loss | 20% matched DATA/ACK loss | Integrity |
|---|---:|---:|---|
| Stop-and-Wait | 0.002423 s; 0 DATA retransmissions | 0.153023 s; 3 DATA retransmissions | 2/2 verified |
| Go-Back-N | 0.003005 s; 0 DATA retransmissions | 0.102469 s; 2 DATA retransmissions | 2/2 verified |
| Selective Repeat | 0.002769 s; 0 DATA retransmissions | 0.151551 s; 1 DATA retransmission | 2/2 verified |

Each point has one trial and uses the 8 KiB `small.txt` fixture. These values are smoke instrumentation observations only and are not used to infer a protocol winner.

## 4. Research status

The pre-registered full matrix contains 905 attempts: loss 200, delay 140, reordering 200, corruption 100, duplication 100, timeout 90, and combined faults 75. It has **not** been executed in this workspace. Accordingly:

- RQ1 — inconclusive.
- RQ2 — inconclusive.
- RQ3 — inconclusive.
- RQ4 — inconclusive.
- RQ5 — inconclusive.
- RQ6 — inconclusive.

The measured smoke observations and reason for each inconclusive status are in `BENCHMARKS.md`. The full run command is `python -m experiments.runner --tier full --workers 1`.

## 5. Validation

| Validation | Result |
|---|---|
| M4 working-tree fast suite | 102 passed, 18 slow tests deselected (7.85 s) |
| Milestone 3 archive extracted and tested | 100 passed, 18 deselected |
| M4 smoke run | 6/6 successful, 0 failures |
| Source/received byte counts and SHA-256 | Verified by runner for all six smoke runs |
| Analysis pipeline | Aggregate CSV, fault comparison CSV, five plots, manifest generated |
| `python -m experiments.runner --tier full --dry-run` | 905 planned attempts, correct matrix breakdown |
| `python -m compileall -q .` | Passed |
| `python scripts/verify_release.py --docs-only` | Passed after documentation completion |

The full repeated-trial research matrix, final research conclusions, and complete `v1.0` evidence gate remain outstanding.

## 6. External release items not represented as complete

- The 905-attempt full matrix and final data/plots have not been run.
- No two-to-three-minute demo video has been recorded; `DEMO_SCRIPT.md` is the recording storyboard.
- No GitHub tag or Release has been pushed. The source workspace does not perform publication without repository access.

The project is therefore packaged as a **release candidate**, not represented as a completed v1.0 publication. See `RELEASE_CHECKLIST.md` for the remaining gates.
