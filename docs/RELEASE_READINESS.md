# Reliable UDP — v1.0 Release Readiness Gate

## Decision

**Status: Release candidate only — v1.0 release gate not passed.**

The supplied 905-attempt CSV export passes structural, registered-matrix, integrity-record, and derived-table reconciliation checks. It is suitable for a corrected research interpretation with the limitations documented in `MILESTONE_6_REPORT.md`. It is not enough to establish exact source provenance or independently replay the original benchmark.

## Gate results

| Gate | Status | Evidence / reason |
|---|---|---|
| 905 full-tier attempts | Pass | 905 full rows plus six smoke rows in raw CSV |
| Registered matrix counts | Pass | 200/140/200/100/100/90/75 |
| Registered parameter levels and windows | Pass | Machine-checked against methodology |
| Repetition counts | Pass | Ten for loss/reordering points; five for remaining points |
| Run IDs and task uniqueness | Pass | 911 unique IDs; 905 unique full task combinations |
| Sequential seed policy | Pass | Unique sequential full seeds, ordered by timestamp |
| Successful-transfer integrity records | Pass | 858/858 source/received hash, byte count and flags agree |
| Failure retention | Pass | 47 failed rows retained with errors and blank throughput |
| Aggregate CSV reconciliation | Pass | 147/147 aggregate rows recomputed from raw data |
| Fault-rate CSV reconciliation | Pass | 40/40 configured/realized rows recomputed from raw data |
| Correct RQ2 analysis | Pass | Delay × window matrix analyzed; earlier wrong RQ2 grouping superseded |
| Exact source Git commit | **Blocked** | All 905 rows contain `git_commit=unknown` |
| Per-run process reports/logs | **Blocked** | Not included in uploaded ZIP; the ZIP README says per-run output folders are excluded. Failure text includes 35 `TimeoutError` and 12 `BlockingIOError` cases, which cannot be independently traced without those reports/source. |
| Fixture binary/manifest replay | **Blocked** | Fixture files and manifest are not in uploaded ZIP; cannot independently hash original source fixtures |
| Clean-checkout code/test reproduction | **Not verified** | Project source tree / exact Git checkout was not included in this input archive |
| CI workflow execution | **Not verified** | No live repository/CI run was available in the supplied evidence |
| 2–3 minute demo video | **Not complete** | Existing project checklist records a storyboard, not a recorded video |
| GitHub v1.0 tag/release | **Not complete** | Requires repository access and all release gates |

## Machine audit

Run:

```bash
python scripts/audit_benchmark.py --input input --output outputs/audit.json
```

The structural/design audit reports **13/15 checks passed**. The two non-passing checks are intentional blockers: known commit provenance and per-run process reports. The strict release form may be invoked with:

```bash
python scripts/audit_benchmark.py \
  --input input \
  --output outputs/audit_release_gate.json \
  --require-known-commit \
  --require-per-run-reports \
  --require-fixtures
```

That strict invocation is expected to fail on the current uploaded archive. Do not edit the source `git_commit` column to insert a guessed commit. The real source revision must be recovered from the machine/repository that ran the experiments, or the full matrix must be rerun from a known Git checkout with commit metadata written into every row.

## Required work before v1.0

1. Recover the exact source checkout and Git commit used for the 905 runs, if it still exists. Otherwise rerun the registered full matrix from a committed checkout.
2. Preserve each run directory: sender, receiver, and proxy metrics JSON; stdout/stderr or process logs; final output status; input fixture and manifest hash; effective config; and run ID.
3. Add the fixture binaries/manifest to a separate reproducibility bundle or provide an immutable verified fixture archive.
4. Re-run the full structural and integrity audit against the canonical dataset and the per-run evidence. Do not pool the current data with any rerun unless source revision, task identity, seeds, and parameters are proven identical.
5. From a clean checkout, run fast tests, slow integration tests, smoke tier, `compileall`, and release verifier; preserve CI output.
6. Record and review the planned 2–3 minute demo.
7. Only after all gates pass, tag and publish `v1.0` and attach canonical CSV, analysis outputs, and demo.

## Scope boundary

This is an experimental ARQ testbed. It is not a TCP/QUIC replacement or a production transport; congestion control, adaptive RTO, bandwidth caps, Wireshark dissector, and TCP/QUIC performance comparison remain explicitly out of v1.0 scope per the implementation plan.
