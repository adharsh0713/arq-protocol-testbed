# Milestone 6 — Independent Validation & Final Release Readiness

**Date:** 14 November 2026  
**Status:** Corrected benchmark analysis and structural validation complete; final v1.0 release gate remains blocked by provenance and missing per-run evidence.

## 1. Why Milestone 6 exists

The original `IMPLEMENTATION_PLAN.md` defined four implementation milestones, ending with documentation, full research, and v1.0 release preparation. The later Milestone 5 evidence-audit report recorded that a complete 905-row canonical research CSV had not been available in the persisted package at that time. The subsequently uploaded `results(1).zip` supplies that full CSV export. Milestone 6 is an explicit follow-on validation/release-readiness milestone, not a claim that the original four-milestone plan had a pre-existing M6 definition.

This milestone has four goals:

1. Independently audit the uploaded raw CSV against the frozen 905-attempt design.
2. Recompute aggregate and configured-versus-realized fault summaries from raw rows.
3. Correct research analyses to follow the registered RQ definitions and matched-configuration rules.
4. Establish whether the evidence is sufficient for the v1.0 release gate.

## 2. Input archive and evidence boundary

Input: `results(1).zip` (SHA-256: `48d3f4f2c92480f49742f7ecc43c546903963a17f9c1adbf46829e5dec73eab5`). It contains exactly four files:

- `experiment_results.csv`
- `aggregated_results.csv`
- `fault_rate_comparison.csv`
- `README.md`

The raw CSV contains 911 records: 905 `full` attempts and six `smoke` attempts. The six smoke attempts are excluded from full-tier RQ inference. The uploaded README says the individual per-run output folders/process reports are excluded from this summary archive. Fixture binaries and their manifest are also absent. The original benchmark rows record Python 3.13.15 on Windows 11; this Milestone 6 analysis was independently run in Python 3.13.5 on Linux using pandas 2.2.3, NumPy 2.3.5, SciPy 1.17.0 and Matplotlib 3.10.8.

## 3. Independent audit results

### 3.1 Counts and identity

| Check | Result |
|---|---:|
| Raw records | 911 |
| Full-tier attempts | 905 |
| Smoke attempts | 6 |
| Full-tier verified successes | 858 |
| Full-tier failures | 47 |
| Full-tier success rate | 94.8% |
| Unique run IDs | 911 |
| Duplicate run IDs | 0 |
| Unique full-tier seeds | 905 |
| Unique full-tier task combinations | 905 |
| CSV columns | 87, with no duplicate names |

The full-tier seeds are unique and sequential by timestamp, from 20261113 through 20262017, consistent with the registered base seed and stable task ordinal convention.

### 3.2 Registered matrix counts

| Matrix | Expected | Observed | Result |
|---|---:|---:|---|
| Loss | 200 | 200 | Pass |
| Delay | 140 | 140 | Pass |
| Reordering | 200 | 200 | Pass |
| Corruption | 100 | 100 | Pass |
| Duplication | 100 | 100 | Pass |
| Timeout | 90 | 90 | Pass |
| Combined | 75 | 75 | Pass |
| **Total** | **905** | **905** | **Pass** |

### 3.3 Design/configuration checks

The audit validates registered probability/delay levels, protocol/window allocations, repetition counts, file names/sizes, 4,096-byte chunk size, 15 maximum retries, 50 ms timeout for non-timeout matrices, isolated-fault zeros, timeout-matrix 10% symmetric loss, combined-fault settings, and DATA/ACK symmetry. Every registered-design check passed.

### 3.4 Integrity and failure accounting

All **858 successful full-tier rows** record matching source/received SHA-256 values, matching expected/received byte counts, and true `hash_verified` / `integrity_verified` flags. All 47 failed attempts remain represented with an error and blank throughput. The archive lacks the actual fixture files, so this audit checks the integrity fields within the CSV but does not independently rehash the original source fixtures.

Failures by matrix:

| Matrix | Failures |
|---|---:|
| Delay | 24 |
| Reordering | 12 |
| Loss | 6 |
| Combined | 3 |
| Corruption | 1 |
| Timeout | 1 |
| Duplication | 0 |
| **Total** | **47** |

The nested exception text in the 47 failure records contains **35 `TimeoutError`** cases and **12 `BlockingIOError`** cases (non-blocking socket receive). The observed failure stack categories are a diagnostic signal, not a full root-cause analysis: the process reports, exact source revision and fixture bundle are absent, so these errors could not be reproduced or traced to a source line during this milestone. They must be investigated before v1.0.

### 3.5 Recomputed aggregate tables

`aggregated_results.csv` contains 147 groups (141 full-tier and six smoke groups). The analysis package recalculates attempts, verified successes, success rate, median, Q1, Q3 and IQR for completion time, throughput and retransmissions from the run-level data. All 147 rows reconcile within floating-point rounding.

`fault_rate_comparison.csv` contains 40 groups. Its observed run counts and mean/median/Q1/Q3 realized rates were recalculated from raw telemetry. All 40 rows reconcile within floating-point rounding.

Machine-readable results are in `outputs/audit.json`; the audit script reports 13/15 release checks passing. The two blocked checks are exact source commit provenance and per-run process reports.

## 4. Corrected research findings

The registered RQ2 is **delay × sender-window size**. This was not what the earlier M5 report analyzed. RQ1/RQ3 need to retain window distinctions; RQ6 must be split by fixture file. M6 regenerates all research tables and figures with those matching conditions.

### RQ1 — Packet loss

Higher DATA/ACK loss was associated with longer completion time and more retransmissions. For each protocol/window series, loss-to-completion Spearman ρ was 0.938–0.967 and loss-to-retransmission ρ was 0.949–0.975. At 20% loss, Go-Back-N W4 and W16 completed 10/10 each; Selective Repeat W4 completed 9/10 and W16 6/10; Stop-and-Wait completed 10/10. The result supports the loss-degradation hypothesis, but the success-rate drop for SR at larger windows is important and must not be hidden by successful-run medians.

See `outputs/rq1_loss_by_protocol_window.csv` and `outputs/rq1_loss_correlations.csv`.

### RQ2 — Delay × window

At 5, 20 and 50 ms one-way delay in both directions, window 16 had higher successful-run median throughput than window 4 for both GBN and SR. At 20 ms, W16/W4 throughput ratios were 2.68× for GBN and 2.22× for SR. At 50 ms they were 2.64× and 2.41× respectively. But success rates vary: GBN W1 at 50 ms completed 0/5; GBN W4 4/5; GBN W16 5/5. SR W4 and W16 completed 4/5 each at 50 ms.

Conclusion: larger windows help throughput in the tested delayed conditions, but the fixed 50 ms retransmission timeout confounds interpretation. A one-way delay of 50 ms in each direction implies about 100 ms round-trip delay, longer than the fixed timeout. These localhost results do not identify a physical BDP optimum.

See `outputs/rq2_delay_by_protocol_window.csv` and `outputs/rq2_window_tests.csv`.

### RQ3 — Reordering

Selective Repeat was more resilient than GBN in the tested reordering matrix. At 20% reorder and W4, SR had 10/10 successes and 0.684 MB/s median throughput versus GBN's 10/10 and 0.268 MB/s (2.55×, p=0.000183). At W16, SR had 10/10 and 1.435 MB/s versus GBN's 4/10 and 0.267 MB/s (5.38×, p=0.001998). GBN W16's median retransmissions reached 150.5, versus 2.5 for SR W16. These comparisons support the expected cost of GBN discarding out-of-order packets and retransmitting a suffix.

See `outputs/rq3_reordering_by_protocol_window.csv` and `outputs/rq3_protocol_tests.csv`.

### RQ4 — Configured versus realized fault rates

Across probability-based loss, corruption, duplication and reordering summary cells in DATA and ACK directions, mean absolute deviation between configured probability and realized mean was about **0.43 percentage points**. For non-zero delay settings, all observed packets were assigned non-zero delay; delay remains a duration (seconds), not a probability. At 20% configured reordering, around 19–20% of packets were scheduled for extra hold, whereas about 12% of forwarded copies were observed arriving out of order.

See the five RQ4 output tables in `outputs/`.

### RQ5 — Timeout sensitivity

Completion-time medians increased monotonically with the configured timeout over 10 ms to 1 s. Spearman timeout/completion ρ was 0.923 (GBN), 0.969 (SR), and 0.987 (Stop-and-Wait). The preregistered hypothesis predicted a U-shaped time/timeout relationship; the observed medians did not show the predicted U shape. Because the archive does not provide a direct validated spurious-retransmission count and each point has five attempts, the U-shaped optimum hypothesis is **inconclusive**, not confirmed or refuted. No production timeout recommendation should be made from this test.

See `outputs/rq5_timeout_by_protocol.csv` and `outputs/rq5_timeout_correlations.csv`.

### RQ6 — Combined faults and integrity

The combined matrix recorded 72/75 completed attempts (96%). Each of the 72 completed transfers passed recorded byte-count and SHA-256 integrity checks. Three failed attempts were all for the 1 MiB large file: two GBN and one SR. By protocol, success was 25/25 for Stop-and-Wait, 23/25 for GBN, and 24/25 for SR. By file, the only incomplete groups were GBN large 3/5 and SR large 4/5.

The supported statement is **all completed, verified transfers were byte-identical**. It is not “all attempts delivered successfully.”

See `outputs/rq6_combined_by_file.csv`.

## 5. Corrected research answer register

| RQ | Corrected status | Defensible conclusion |
|---|---|---|
| RQ1 — Loss vs time/retransmissions | Supported | Higher loss is associated with longer completion and more DATA retransmissions; success rate varies by protocol/window. |
| RQ2 — Delay × window | Conditional support | Larger windows improve successful-run throughput at tested delay levels, but the fixed 50 ms timeout confounds interpretation. |
| RQ3 — GBN vs SR under reordering | Strong support | SR is more resilient than GBN at higher reordering in this workload, especially at window 16. |
| RQ4 — Configured vs realized faults | Supported with metric distinctions | Probability fault summaries track configuration closely; delay and reorder-hold metrics require distinct units/denominators. |
| RQ5 — Timeout sensitivity | U-shape inconclusive | Completion-time medians rise with timeout; the hypothesized U-shaped optimum was not demonstrated. |
| RQ6 — Integrity under combined faults | Integrity supported for successful attempts | All 72 completed transfers passed recorded integrity checks, but 3/75 attempts failed. |

## 6. Analysis artifacts generated

- Seven figures under `outputs/figures/`.
- Matrix and protocol success summaries.
- RQ1 loss-by-protocol/window and correlation tables.
- RQ2 delay-by-protocol/window and paired-window test tables.
- RQ3 reordering-by-protocol/window and GBN/SR tests.
- RQ4 corruption, duplication, probability-calibration, delay-event and reorder-delivery tables.
- RQ5 timeout summary and correlation tables.
- RQ6 combined-fault per-file/protocol table.
- Audit JSON and analysis manifest.

## 7. Provenance and release decision

The uploaded result ZIP contains no per-run process JSON/logs or fixture binaries/manifest. More importantly, `git_commit` is `unknown` on all 905 full-tier rows. The ZIP hash identifies the uploaded export but cannot be converted into a Git commit. We will not infer or fabricate a commit.

The dataset is structurally complete and internally reconcilable; exact source revision and raw process provenance remain unverified. The source tree was not provided with this input, so M6 did not run its pytest suite, compile step, release verifier, or CI. No demo recording or GitHub release was performed.

**Decision: Milestone 6's independent analysis/audit deliverable is complete. Reliable UDP is still a release candidate, not a verified v1.0 release.** See `docs/RELEASE_READINESS.md` for the precise remaining gate.

## 8. Reproduction

From this package root:

```bash
pip install -r requirements.txt
python scripts/audit_benchmark.py --input input --output outputs/audit.json
python -m analysis.analyze_full_matrix --input input --output outputs
```

This reproduces the audit, tables and figures from the supplied CSV records. It does not rerun the network experiments or recreate per-run reports absent from the input archive.
