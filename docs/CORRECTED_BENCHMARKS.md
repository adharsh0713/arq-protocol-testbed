# Reliable UDP — Corrected Benchmark Findings

**Dataset:** `results(1).zip`  
**Population:** 905 full-tier attempts; six smoke attempts excluded from research inference.  
**Analysis rule:** failures remain in success-rate denominators; successful-run time/throughput summaries are reported separately.

## Overall benchmark

| Matrix | Attempts | Successes | Failures | Success rate |
|---|---:|---:|---:|---:|
| DATA/ACK loss | 200 | 194 | 6 | 97.0% |
| DATA/ACK delay | 140 | 116 | 24 | 82.9% |
| DATA/ACK reordering | 200 | 188 | 12 | 94.0% |
| DATA/ACK corruption | 100 | 99 | 1 | 99.0% |
| DATA/ACK duplication | 100 | 100 | 0 | 100.0% |
| Timeout sensitivity | 90 | 89 | 1 | 98.9% |
| Combined faults | 75 | 72 | 3 | 96.0% |
| **Total** | **905** | **858** | **47** | **94.8%** |

All 858 successful records have recorded matching source/received SHA-256 values, matching byte counts, and true hash/integrity flags. The uploaded archive does not include fixture files, so the fixture bytes themselves could not be independently hashed in this follow-up audit.

## RQ1 — How do completion time and retransmissions grow with packet loss for each protocol?

**Status: Supported within the tested localhost conditions.**

The loss matrix has 10 repetitions per matched protocol/window/rate. Results were grouped by protocol **and** sender window, not pooled across different windows.

At 20% DATA/ACK loss:

| Protocol / window | Verified successes | Median completion time | Median DATA retransmissions |
|---|---:|---:|---:|
| Stop-and-Wait / 1 | 10/10 | 2.638 s | 40.5 |
| Go-Back-N / 4 | 10/10 | 1.130 s | 69 |
| Go-Back-N / 16 | 10/10 | 0.961 s | 214 |
| Selective Repeat / 4 | 9/10 | 1.451 s | 38 |
| Selective Repeat / 16 | 6/10 | 0.682 s | 40.5 |

Across successful attempts within each matched protocol/window series, Spearman correlations between configured loss and completion time range from **0.938 to 0.967**; loss and DATA retransmissions range from **0.949 to 0.975**. These are exploratory monotonic associations and should not be read as protocol-independent causal effect estimates.

**Interpretation:** higher loss is consistently associated with longer completion time and more retransmissions. Larger windows do not automatically improve delivery reliability: Selective Repeat at window 16 had only 6/10 successes at 20% loss, while Go-Back-N retained 10/10 in this particular matrix. Report the success rate alongside the successful-run medians.

Full table: `outputs/rq1_loss_by_protocol_window.csv`. Correlations: `outputs/rq1_loss_correlations.csv`.

## RQ2 — When does a larger sender window help as delay increases?

**Status: Conditional support; timing interaction is material.**

This is the corrected RQ2: symmetric one-way DATA and ACK delay at 0, 5, 20, and 50 ms, with window 1/4/16 where the protocol supports it. Each point has five attempts. Window 1 is the only Stop-and-Wait condition.

Selected median successful-run throughput, MB/s (decimal):

| Protocol / window | 0 ms | 5 ms | 20 ms | 50 ms |
|---|---:|---:|---:|---:|
| Go-Back-N / 1 | 12.42 | 0.175 | 0.076* | —* |
| Go-Back-N / 4 | 15.78 | 0.484 | 0.244 | 0.128 |
| Go-Back-N / 16 | 16.35 | 2.024 | 0.653 | 0.339 |
| Selective Repeat / 1 | 9.90 | 0.162 | 0.064 | 0.034 |
| Selective Repeat / 4 | 13.59 | 0.570 | 0.284 | 0.136 |
| Selective Repeat / 16 | 16.19 | 1.809 | 0.632 | 0.329 |
| Stop-and-Wait / 1 | 12.27 | 0.129 | 0.065 | 0.033 |

`*` Go-Back-N/window 1 at 20 ms had only 2/5 successful attempts; at 50 ms it had 0/5, so there is no valid throughput sample at 50 ms. Go-Back-N/window 4 at 50 ms had 4/5 successes. Other detailed success counts are in `outputs/rq2_delay_by_protocol_window.csv`.

At 5, 20, and 50 ms, window 16 had higher median throughput than window 4 for both sliding-window protocols. At 20 ms, Go-Back-N W16 vs W4 throughput was 2.68× (5/5 successes in both); Selective Repeat was 2.22× (5/5 vs 4/5). At 50 ms, the ratios were 2.64× for Go-Back-N (5/5 vs 4/5) and 2.41× for Selective Repeat (4/5 vs 4/5). Mann–Whitney comparisons use successful runs only, with very small cells, and are exploratory without multiplicity correction.

**Critical limitation:** retransmission timeout remained fixed at 50 ms. Because the same one-way delay is applied to DATA and ACK paths, configured 50 ms each direction implies a nominal 100 ms round trip, exceeding the timeout. At 20 ms each direction, nominal round-trip delay is already about 40 ms, leaving little room for host scheduling. Therefore the trend is a window/timeout interaction in this emulator; it is not clean evidence of a physical bandwidth-delay-product optimum. Do not extrapolate an optimal window or a real-link BDP from this result.

Full table: `outputs/rq2_delay_by_protocol_window.csv`. Pairwise exploratory tests: `outputs/rq2_window_tests.csv`.

## RQ3 — How do Go-Back-N and Selective Repeat compare under packet reordering?

**Status: Strong support for Selective Repeat resilience in this tested workload.**

Results are split by the registered sender window. At 20% reordering:

| Protocol / window | Verified successes | Median throughput | Median DATA retransmissions |
|---|---:|---:|---:|
| Go-Back-N / 4 | 10/10 | 0.268 MB/s | 43 |
| Go-Back-N / 16 | 4/10 | 0.267 MB/s | 150.5 |
| Selective Repeat / 4 | 10/10 | 0.684 MB/s | 2.5 |
| Selective Repeat / 16 | 10/10 | 1.435 MB/s | 2.5 |
| Stop-and-Wait / 1 | 9/10 | 0.314 MB/s | 3 |

At matched window 4, Selective Repeat throughput was **2.55×** Go-Back-N (Mann–Whitney p = 0.000183, successful runs only). At window 16 it was **5.38×**, with 10/10 Selective Repeat successes versus 4/10 Go-Back-N (p = 0.001998). The contrast is consistent with GBN discarding later packets after a gap and retransmitting the outstanding suffix, while SR buffers/acknowledges valid in-window packets.

At configured 20% reordering, the mean proportion selected for additional hold was 19.38% on DATA and 20.44% on ACK. Mean actual out-of-order delivery fractions were lower: 12.13% DATA and 11.91% ACK. A scheduled hold is not the same event as an observed overtaking delivery.

Full table: `outputs/rq3_reordering_by_protocol_window.csv`. Protocol comparisons: `outputs/rq3_protocol_tests.csv`.

## RQ4 — Do configured fault probabilities correspond to realized fault rates?

**Status: Supported for probability faults; delay and reordering need separate units.**

The 40-row configured-versus-realized summary was recomputed from raw rows and reconciles. Across the probability-based fault rows (loss, corruption, duplication and reordering in both directions and all configured levels), mean absolute deviation of realized means from configured probabilities was **0.43 percentage points**.

The configured delay is expressed in seconds. At every non-zero delay setting (5, 20 and 50 ms), 100% of observed DATA and ACK datagrams were assigned non-zero delay; zero delay produced 0%. This is an event fraction, not a probability value to compare numerically against milliseconds.

At configured 20% reorder probability, roughly 19–20% of packets were selected for extra hold, but only roughly 12% of forwarded copies were observed arriving out of order. This distinction is preserved in the fault model.

The corruption matrix completed 99/100 attempts; duplication completed 100/100. Each successful transfer met its recorded integrity checks.

Outputs: `outputs/rq4_probability_fault_realization.csv`, `outputs/rq4_delay_event_rates.csv`, `outputs/rq4_reordering_hold_vs_delivery.csv`, `outputs/rq4_corruption_outcomes.csv`, and `outputs/rq4_duplication_outcomes.csv`.

## RQ5 — How sensitive are results to timeout selection?

**Status: The simple monotonic association is supported; the preregistered U-shaped optimum is inconclusive.**

Timeout points were 10, 25, 50, 100, 250, and 1,000 ms, at 10% symmetric DATA/ACK loss with five attempts per protocol/point. Median completion time rose as timeout increased for all protocols. At 1,000 ms, medians were 6.095 s (GBN), 9.152 s (SR), and 13.182 s (Stop-and-Wait). At 10 ms, SR completed 4/5 attempts; GBN and Stop-and-Wait completed 5/5.

Spearman timeout/completion correlations were 0.923 (GBN), 0.969 (SR), and 0.987 (Stop-and-Wait), computed from successful attempts. The preregistered hypothesis predicted a U-shaped relationship from competing spurious-timeout and loss-recovery effects. The observed medians did not show a U shape across this sweep. However, the current archived metrics do not provide a direct validated count of spurious retransmissions, and each point has only five attempts. Therefore no general or production timeout recommendation follows.

Full tables: `outputs/rq5_timeout_by_protocol.csv` and `outputs/rq5_timeout_correlations.csv`.

## RQ6 — Do completed transfers remain byte-identical under combined faults?

**Status: Integrity requirement met for completed attempts; completion reliability is not 100%.**

The combined-fault matrix contains 75 attempts (25 per protocol), of which 72 completed and passed the recorded byte-count, SHA-256, and integrity checks. Three attempts failed, all on the 1 MiB `large.txt` fixture: two Go-Back-N and one Selective Repeat attempt.

| Protocol | Attempts | Verified successes | Success rate |
|---|---:|---:|---:|
| Stop-and-Wait | 25 | 25 | 100% |
| Go-Back-N | 25 | 23 | 92% |
| Selective Repeat | 25 | 24 | 96% |
| **Total** | **75** | **72** | **96%** |

The file/protocol table shows 5/5 successes for all protocol/file pairs except large text: Go-Back-N 3/5 and Selective Repeat 4/5. Stop-and-Wait completed all five large-file attempts. Do not phrase this as “all transfers succeeded”; the accurate claim is that all completed, verified transfers were byte-identical.

Full table: `outputs/rq6_combined_by_file.csv`.

## Limitations that apply to all questions

- The measurement environment is localhost UDP on Windows 11 / Python 3.13.15; it does not establish behavior on WAN paths.
- The archive does not contain per-run process logs/metrics JSON or source fixture binaries/manifest.
- All full-tier `git_commit` values are `unknown`, so the 905 rows are not bound to an exact source revision.
- Successful-run performance statistics exclude failures; report success rates alongside them to expose selection effects.
- Five/ten repetitions per cell are limited, and many comparisons are exploratory; multiple-testing correction was not applied.
- The timeout-vs-delay interaction complicates RQ2 interpretation.


## Failure diagnostics from recorded error text

The 47 failure rows contain nested `TimeoutError` text in 35 cases and `BlockingIOError` text in 12 cases (non-blocking socket receive). The matrix/protocol breakdown is retained in `outputs/failure_diagnostics.csv`. This is a log-text classification only; without the original per-run reports and source revision, it is not sufficient to assign a definitive code-level root cause.

## Corrected answer register

| RQ | Status |
|---|---|
| RQ1 — Loss vs completion/retransmissions | Supported |
| RQ2 — Delay × sender window | Conditional support; fixed-timeout confound |
| RQ3 — GBN vs SR under reordering | Strong support for SR in this workload |
| RQ4 — Configured vs realized faults | Supported for probability faults; delay/reorder units kept separate |
| RQ5 — Timeout sensitivity | U-shaped optimum inconclusive |
| RQ6 — Combined-fault integrity | All successful transfers verified; 3/75 failures remain |
