# Experiment Methodology

**Status:** Milestone 3 implementation specification. The full matrix has not yet been executed; no research hypothesis is marked confirmed or refuted in this document.

## 1. Purpose and experimental model

The experiment runner compares Stop-and-Wait, Go-Back-N, and Selective Repeat as ARQ strategies over localhost UDP. The sender transmits through one fault-injection proxy to one receiver. The proxy applies independent, seeded fault models to DATA/END and ACK traffic. The receiver writes to a temporary file and publishes a final file only after a valid END and configured integrity checks.

The experiment is a controlled software testbed. It does not reproduce physical bandwidth, congestion, correlated loss, route changes, or geographic latency.

## 2. Environment and controls

Every run records Python version, operating system, machine name, git commit (or `unknown` when the source is not in a Git checkout), UTC timestamp, seed, complete protocol configuration, and per-direction fault configuration.

Default controls:

| Parameter | Value | Notes |
|---|---:|---|
| Python | 3.10+ | CI uses Python 3.13 |
| Chunk size | 4,096 bytes | Same across protocols in a matched matrix |
| Timeout | 0.05 s | Environment override; fixed within each matrix point |
| Maximum retries | 15 | Same across protocols in a matched point |
| Windows | 1, 4, 16 | Stop-and-Wait is fixed at effective window 1 |
| Base seed | 20261113 | Each planned run gets base seed + one-based run ordinal - 1 |
| Workers | 1 by default | 1–2 recommended for timing; higher values risk CPU contention |

The runner starts receiver and proxy subprocesses through `sys.executable`, waits for explicit READY lines, assigns a distinct UDP port pair to each run, and gives each process unique metrics paths. Sender, receiver, and proxy each report their effective configuration. A run fails if these configurations disagree.

## 3. Deterministic fixture files

Run `python scripts/make_test_files.py` to regenerate the five fixtures. A fixed seed creates the same three text files on every run. The PNG is built with the standard library PNG chunk format, and the WAV is generated with Python's `wave` module. The generator writes `manifest.json` with sizes and SHA-256 hashes.

| File | Role |
|---|---|
| `small.txt` | Smoke and quick transfer |
| `medium.txt` | Main matched protocol matrices |
| `large.txt` | Large text transfer under combined faults |
| `image.png` | Binary image integrity |
| `audio.wav` | Small audio integrity |

## 4. Experiment tiers

The attempt counts below are determined from `build_tasks()` and can be checked without execution by using `--dry-run`.

| Tier | Attempts | Files | Purpose |
|---|---:|---|---|
| Smoke | 6 | `small.txt` | 3 protocols × 0% and 20% matched DATA/ACK loss; one trial |
| Quick | 36 | `small.txt`, `medium.txt` | 3 protocols × 3 loss levels × 2 files × 2 trials |
| Full | 905 | All five required fixtures | All fault matrices and research questions |

The full tier has the following breakdown:

| Matrix | Attempts | Configuration |
|---|---:|---|
| Loss (RQ1) | 200 | 0%, 5%, 10%, 20%; medium text; 10 trials; effective windows 1, 4, 16 |
| Delay (RQ2) | 140 | 0, 5, 20, 50 ms one-way delay in both directions; medium text; windows 1, 4, 16; 5 trials |
| Reordering (RQ3) | 200 | 0%, 5%, 10%, 20% in both directions; medium text; 10 trials |
| Corruption (RQ4) | 100 | 0%, 5%, 10%, 20% in both directions; medium text; 5 trials |
| Duplication (RQ4) | 100 | 0%, 5%, 10%, 20% in both directions; medium text; 5 trials |
| Timeout (RQ5) | 90 | 10, 25, 50, 100, 250, 1,000 ms at 10% DATA/ACK loss; 5 trials |
| Combined (RQ6) | 75 | All three protocols × five file types × five trials |

For loss and reordering headline results, the matrix uses ten repetitions. Other full-matrix points use five repetitions. The full matrix is intended as a long-running pre-release experiment, not as part of pytest.

## 5. Fault matrix isolation

Each isolated matrix changes one fault class in both directions and holds the other fault classes at zero:

- **Loss:** `DATA_LOSS_RATE` and `ACK_LOSS_RATE` use the same probability.
- **Corruption:** `DATA_CORRUPTION_RATE` and `ACK_CORRUPTION_RATE` use the same probability. Corruption can affect DATA, END, and ACK datagrams because the proxy operates on all decoded packet types by direction.
- **Delay:** `DATA_DELAY` and `ACK_DELAY` use the same fixed one-way delay.
- **Duplication:** `DATA_DUPLICATE_RATE` and `ACK_DUPLICATE_RATE` use the same probability.
- **Reordering:** `DATA_REORDER_RATE` and `ACK_REORDER_RATE` use the same probability. Selected packets get the configured additional reorder hold time.
- **Combined:** DATA and ACK sides both use 5% loss, 2% corruption, 5 ms base delay, 2% duplication and 2% reordering.

The timeout matrix varies timeout only; 10% DATA and ACK loss are applied while corruption, delay, duplication and reordering remain disabled. The combined matrix tests all five file types.

## 6. Seed and run isolation

The task list is generated in a stable order. The seed for task ordinal `n` is `base_seed + n - 1`. Filtering a tier is performed after its seeds are assigned, so filtering does not renumber the remaining tasks. DATA and ACK injectors own separate `random.Random` instances; ACK seed is deterministically derived from the run seed by the proxy. Reproduction requires the run's seed, effective configuration, project revision, and fault-injection implementation version.

Every attempt receives:

- Unique `run_id` and output directory.
- Unique sender, receiver, and proxy metrics JSON paths.
- A distinct receiver/proxy UDP port pair.
- A separate received output file.
- The seed and effective configuration stored in every process report where relevant and in the results CSV.

Processes are started with `sys.executable`. The runner checks READY output instead of sleeping fixed durations. The proxy receives a local shutdown datagram and drains scheduled deliveries before exit. Remaining processes are terminated, waited for, and killed only if necessary.

## 7. Metric definitions

See [METRICS_SCHEMA.md](METRICS_SCHEMA.md) for the result columns. Important definitions:

- **Completion time:** `time.perf_counter()` elapsed time from first DATA send through receipt of the END ACK. For an empty file, the timer begins with the first END send. Receiver-side SHA-256 verification is separate.
- **Throughput:** source file bytes divided by completion time. It is recorded only for a successful, integrity-verified transfer.
- **DATA retransmissions:** retransmitted DATA packet sends. END retransmissions are a separate `end_retries` metric.
- **Total sender bytes:** encoded DATA and END bytes actually sent, including packet headers and retries. ACK bytes are not included because they are sent by the receiver.
- **Unique DATA delivered:** DATA sequence payloads written once in order by the receiver. `unique_data_received` also captures unique buffered SR packets.
- **DATA arrivals:** valid decoded DATA arrivals; duplicates are separately counted. Corrupt/malformed discards are separate.
- **Recovery time:** for each DATA sequence that needed retransmission, time from first send to its successful ACK; report sample count, mean, and maximum.
- **Success:** sender succeeds, receiver status is completed, all three process configurations match, final file exists, byte counts match, and source/received SHA-256 hashes match.
- **Success rate:** verified successes divided by all attempts for the same configuration. Failed attempts remain in the denominator.
- **Realized fault rates:** derived from proxy telemetry and reported separately for DATA and ACK paths. The configured/realized table states the event denominator. Reorder scheduling rate and actual out-of-order delivery rate are both recorded.

No throughput value is written for a failed or unverified transfer.

## 8. CSV, aggregation and plotting

The exact ordered header lives in `experiments/results.py` and is checked with `validate_schema()`. It is frozen before the full run. Result rows are appended immediately after each completed attempt. Failures are also rows and have `status=failed` plus an explanatory `error`.

The experiment runner invokes this analysis automatically after a tier finishes. To regenerate summaries and plots later without repeating transfers, run:

```bash
python -m experiments.analysis
```

It reads only `data/results/experiment_results.csv` and produces:

- `data/results/aggregated_results.csv`: attempts, verified successes, success rate, median, Q1, Q3 and IQR for performance metrics.
- `data/results/fault_rate_comparison.csv`: configured versus realized rates for DATA and ACK loss/corruption/duplication/reordering.
- Plots under `docs/graphs/`: completion time, throughput and retransmissions vs loss; throughput vs window; completion time under reordering; three-protocol comparison; run-to-run variability; timeout sensitivity; combined-fault success rate.

Performance plots use verified successes only. The success-rate plot and grouped summary use all attempts. Overview plots use the matched `medium.txt` reference file and keep protocol/window labels separate; they do not pool different file sizes or windows into one line.

## 9. Statistical reporting rules

- Report number of attempted runs, successful verified runs, failed runs and success rate for every plotted configuration.
- Report median and interquartile range (Q1–Q3), not mean/std alone.
- Do not use throughput from an unverified result.
- Do not combine different file sizes, chunk sizes, timeouts, windows, or fault matrices in one comparison.
- For RQ1 and RQ3 headline conclusions, use the ten planned repetitions. For all other full-matrix points, use at least five.
- If too many trials fail to produce a stable comparison, label the result inconclusive rather than removing failures.

## 10. Threats to validity and limits

The proxy introduces packet-level effects on localhost. It has no bandwidth limiter, queue-capacity model, correlated loss, routing, congestion control, or physical propagation delay. `time.perf_counter()` improves local elapsed-time measurement but cannot remove OS scheduling and interpreter noise. A configured probability is sampled over finite packets and may differ markedly from the realized rate in small transfers. Parallel workers compete for CPU and can distort time. Findings must be scoped to this implementation, this runtime and these localhost conditions.
