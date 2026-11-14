# Reliable UDP - Research Questions and Answer Register

## Research positioning

This project is a controlled testbed for studying the behavior and trade-offs of three ARQ strategies over UDP. It is not a general-purpose transport protocol and does not claim to replace TCP or QUIC.

The hypotheses below are reasoned predictions from ARQ design. They are not experimental findings. The M3 runner implements the pre-registered 905-attempt full matrix; the full matrix has not yet been executed. During M4, every question will be classified as **confirmed**, **refuted**, or **inconclusive** using measured results.

## Questions and hypotheses

### RQ1 - How do completion time and retransmissions grow with packet loss for each protocol?

- **Hypothesis:** Stop-and-Wait pays a full timeout serially for each lost packet because it has no overlap. SR should retransmit approximately the packets whose individual delivery/ACKs failed. GBN can retransmit packets that arrived after the first missing packet, so its retransmission count can grow with the outstanding window.
- **Experiment:** Sweep DATA loss with all other faults disabled. Compare all three protocols on matched files, equal chunk size, equal timeout, equal retry limit, and windows 1, 4, and 16 (Stop-and-Wait has an effective window of 1). Use at least five repetitions per standard point and ten for headline comparisons.
- **Outputs:** Completion time vs loss, verified throughput vs loss, retransmissions vs loss, and success rate for each configuration.
- **Answer rule:** Report actual medians/IQR and trial counts. State the file size, window, timeout, seed policy, and success rate. Do not generalize across unmatched configurations.

### RQ2 - When does a larger window help?

- **Hypothesis:** With negligible added delay, larger windows may provide little benefit. As delay increases, pipelining should improve utilization until the in-flight window covers the effective bandwidth-delay product; further increases should flatten and may add overhead.
- **Experiment:** Sweep one-way data/ACK delay with window sizes 1, 4, and 16. Keep chunk size, timeout policy, retry limit, file and injected faults matched. Treat Stop-and-Wait as window 1.
- **Outputs:** Verified throughput vs window size, with a separate series for each delay level; completion time as a supporting metric.
- **Answer rule:** Identify the measured point where gains flatten for each delay; explain that localhost emulation does not reproduce a physical link's bandwidth-delay product exactly.

### RQ3 - How do Go-Back-N and Selective Repeat compare under reordering?

- **Hypothesis:** GBN discards out-of-order packets and may retransmit an entire outstanding suffix after a gap. SR can buffer valid in-window packets and ACK them individually, so it should be less sensitive to reordering. Stop-and-Wait has only one in-flight DATA packet and should be largely unaffected by DATA reordering.
- **Experiment:** Run a reordering-rate sweep as an isolated fault, in both configured directions where applicable. Keep loss, corruption, delay, and duplication disabled. Use matched file/timeout/chunk/retry settings and ten repetitions for the headline result.
- **Outputs:** Completion time, throughput, retransmissions, recovery time and success rate vs configured and realized reorder counts/rates.
- **Answer rule:** Explain the result with observed queue counters and sender retransmissions. Distinguish injected reordering from reordering naturally caused by the host scheduler.

### RQ4 - Do configured fault rates match realized rates?

- **Hypothesis:** Over large packet counts, realized rates should approach configured probabilities. Small files will show greater run-to-run variation because each packet changes the percentage substantially.
- **Experiment:** For each fault, compare configured probability with proxy counters over repeated runs and multiple packet counts. Keep each fault isolated for the primary calibration table.
- **Outputs:** Configured-vs-realized table for loss, corruption, duplication, delay events and scheduled reordering, reported separately for DATA and ACK. The configured delay is a duration in seconds; the realized delay measurement is a fraction of incoming packets assigned non-zero delay, so units are labelled separately. Actual out-of-order delivery is reported separately from reorder holds.
- **Answer rule:** Use actual observed counts, not configured rates, when describing what happened in a particular transfer. Explain finite-sample variation.

### RQ5 - How sensitive are results to timeout selection?

- **Hypothesis:** Completion time should be U-shaped against timeout: a very short timeout may cause retransmission before delayed ACKs arrive; a long timeout makes genuine loss expensive to recover from.
- **Experiment:** Sweep timeout from 10 ms to 1 s at 10% DATA loss, one fixed file, window 4 (Stop-and-Wait remains window 1), and all other faults disabled. Use repeated seeds and keep other protocol parameters matched.
- **Outputs:** Completion time, throughput, retransmissions, spurious-retransmission count, and success rate vs timeout.
- **Answer rule:** Identify the measured best region for this localhost setup only. Do not claim the chosen value is suitable for the public internet.

### RQ6 - Do all protocols deliver byte-identical files under combined faults?

- **Hypothesis:** Every successful transfer must be byte-identical; a failed transfer must be explicit and must not leave a final output file that looks complete.
- **Experiment:** Run a declared combined-fault matrix for all three protocols and all five required fixture types. Include loss, corruption, delay, duplication, and reordering within documented safe test ranges. Record every attempt, including exhausted retries and receiver timeouts.
- **Outputs:** Success rate, source/received byte counts, source/received SHA-256, failure category, and realized proxy counters.
- **Answer rule:** A success requires exact byte-count equality and matching SHA-256. A failed run is never silently omitted or described as delivered.

## Required metrics

| Metric | Definition used by the final experiment harness |
|---|---|
| Completion time | `perf_counter()` elapsed time from first DATA send to receipt of END ACK; SHA-256 verification is separate |
| Throughput | Source file bytes divided by completion time, emitted only for integrity-verified runs |
| DATA retransmissions | Number of retransmitted DATA packet sends under one definition across all protocols |
| END retries | Retransmitted END control packets, recorded separately from DATA retransmissions |
| Total bytes sent | Encoded bytes sent by the sender, including packet headers, for DATA and END |
| Unique DATA delivered | Receiver count incremented on first acceptance of each unique DATA sequence |
| DATA arrivals | Valid DATA arrivals, with duplicate arrivals and corrupt discards reported separately |
| Delivery integrity | Source/received byte counts and both SHA-256 values; success requires both comparisons to match |
| Recovery time | For each DATA packet that needed retransmission: time from first send to its successful ACK; report mean and maximum as specified in the checklist |
| Success rate | Successful verified runs divided by all attempts in the same configuration |
| Realized faults | Actual per-direction drop/corrupt/duplicate/delay/reorder counts from proxy telemetry |

## Common experimental controls

- The full matrix is pre-registered at 905 attempted transfers: loss 200, delay 140, reordering 200, corruption 100, duplication 100, timeout 90 and combined faults 75.
- Same Python/runtime environment, chunk size, timeout, retry limit, and fault configuration across the three protocols in a matched comparison.
- Record the exact effective configuration and a deterministic seed for every attempted run.
- Derive each run's seed from a documented base seed and run number.
- Use at least five repetitions for standard comparisons and ten for headline experiments.
- Use medians and IQR alongside success rate; do not present only means and standard deviations.
- Keep failures in the results dataset. Throughput is undefined for failed or unverified transfers.
- Separate loss, corruption, delay, duplication, and reordering matrices; add one combined-fault matrix.
- Report configured and realized fault rates side by side.
- Keep timing matrices at one or two workers to limit CPU contention; correctness matrices may use more workers.

## Research output checklist

Each RQ entry in `BENCHMARKS.md` must contain:

1. The exact question and pre-registered hypothesis.
2. Configuration and environment, including seed derivation and number of attempts.
3. A plot/table generated from the committed results CSV.
4. Number of successful and failed trials.
5. Median, IQR, and success rate for the matched configuration.
6. A conclusion: confirmed, refuted, or inconclusive.
7. A short explanation grounded in observed packet/fault counters.
8. Limitations specific to the result.

No numerical research conclusion is entered into this file until the corresponding full-matrix experiment has been run and verified. The six smoke-tier runs are a correctness gate only and do not count as RQ evidence.


## Milestone 4 answer register — current status

The current checked-in evidence is a six-run smoke matrix only. It is not sufficient for any research conclusion. The status of every research question therefore remains **inconclusive** until the 905-attempt full matrix is executed and analyzed.

| ID | Current status | Missing evidence |
|---|---|---|
| RQ1 | Inconclusive | Ten trials across all registered loss/window points on the matched medium fixture |
| RQ2 | Inconclusive | Delay × window sweep with five trials per configuration |
| RQ3 | Inconclusive | Reordering rates and windows with ten trials per headline point |
| RQ4 | Inconclusive | Corruption and duplication matrices, both directions, with observed proxy counters |
| RQ5 | Inconclusive | Six timeout values under matched 10% DATA/ACK loss with five trials per point |
| RQ6 | Inconclusive | Five fixtures × three protocols × five combined-fault trials |

Measured observations and their sample limitations are recorded in [BENCHMARKS.md](BENCHMARKS.md). Do not replace this status with a predicted answer.
