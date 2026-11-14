# Milestone 3 — Test Suite and Experimental Framework Report

**Completion date:** 13 November 2026  
**Status:** Complete; the full pre-registered research matrix remains an M4 activity.

## 1. Objective

Milestone 3 turns the corrected sender, receiver, and fault-injection proxy into a reproducible experiment testbed. Every attempted transfer must have an isolated execution environment and a persistent result row; successful performance samples must be integrity-verified; failures must remain visible in success-rate calculations.

## 2. Implemented deliverables

### Deterministic test files

`scripts/make_test_files.py` creates the five required test inputs and a SHA-256 manifest:

| File | Type | Size / format |
|---|---|---|
| `small.txt` | Text | 8 KiB |
| `medium.txt` | Text | 256 KiB |
| `large.txt` | Text | 1 MiB |
| `image.png` | Binary image | Valid 128 × 96 RGB PNG |
| `audio.wav` | Audio | Mono, 16-bit, 8 kHz, one second |

Text content is generated with a local seeded random generator. PNG and WAV files use Python standard-library modules. The manifest records each fixture's size and SHA-256.

### End-to-end test suite

The default suite launches actual sender, receiver, and proxy processes concurrently for Stop-and-Wait, Go-Back-N, and Selective Repeat. All three transfers use seeded bidirectional loss, corruption, delay, duplication, and reordering. Each test checks process completion, matching effective configuration, output existence, exact byte count, and SHA-256 equality.

Longer integration coverage is marked `slow` and excluded from default CI. It comprises nine protocol/scenario transfers (baseline, loss, and combined faults for each protocol) and nine edge-case transfers (empty, sub-chunk, and exact-chunk files for each protocol). Both groups passed independently.

### Experiment runner and execution isolation

`python -m experiments.runner` provides three frozen tiers:

| Tier | Planned attempts | Purpose |
|---|---:|---|
| `smoke` | 6 | All protocols at 0% and 20% matched DATA/ACK loss |
| `quick` | 36 | Development loss sweep over small and medium text |
| `full` | 905 | Seven matrices covering the six research questions |

Filters include protocol, file, loss, and fault matrix. `--workers` controls concurrent runs; one or two workers are recommended for timing studies. `--dry-run` prints the planned attempt count and matrix breakdown without launching processes.

Each run receives a unique ID, a unique run directory, separate process metrics paths, its own output file, a separate UDP port pair, and a deterministic seed. The runner starts children using `sys.executable`, waits for READY messages, compares the effective configurations reported by all processes, and performs bounded cleanup. A result row is appended after each completed attempt, including failures and partial telemetry.

### Frozen metrics and analysis

The ordered 87-column CSV schema is defined in `experiments/results.py`. It includes run identity, seed, protocol parameters, configured faults in both directions, status/error, environment metadata, sender/receiver metrics, byte counts and hashes, and proxy fault counters/realized rates.

Metrics distinguish DATA retransmissions from END retries; count encoded DATA and END bytes including headers; record unique DATA delivery, duplicate/corrupt arrivals, and per-packet recovery time; and keep throughput blank for failed or unverified runs. Completion time uses `time.perf_counter()` and ends after the END acknowledgement. Receiver SHA-256 verification is reported separately.

The runner automatically calls the analysis pipeline after a tier finishes. Analysis retains failed attempts in the success-rate denominator, computes median, Q1, Q3, and IQR for verified performance samples, compares configured and realized DATA/ACK fault rates, and creates plots only for the matrices present in the CSV. Analysis can also be rerun independently with `python -m experiments.analysis`.

### CI and repository hygiene

`.github/workflows/tests.yml` installs the pinned dependencies, runs the default pytest suite, executes the smoke matrix, and uploads the smoke CSV as a workflow artifact. Longer process tests and the full research matrix are intentionally excluded from default pytest execution.

## 3. Validation performed

| Validation | Result |
|---|---|
| `python -m compileall -q .` | Passed |
| `python -m pytest -q` | 100 passed, 18 slow tests deselected (9.47 s) |
| `pytest -q` | 100 passed, 18 slow tests deselected (8.67 s) |
| Extended baseline/loss/combined loopback cases | 9 passed |
| Empty/sub-chunk/exact-chunk loopback cases | 9 passed |
| `smoke --dry-run`, `quick --dry-run`, `full --dry-run` | 6 / 36 / 905 planned attempts |
| Actual smoke matrix, one worker | 6 of 6 verified; 0 failures; 16.86 s |

The smoke matrix transferred the 8 KiB `small.txt` fixture through all three protocols at 0% and 20% symmetric DATA/ACK loss. All six runs had successful process completion, matching process configuration, matching source/received byte counts, and matching SHA-256 digests. Six per-run directories were created, with sender, receiver, and proxy reports. The result CSV has 87 columns and six rows. Analysis created six configuration-summary rows, a configured-versus-realized fault comparison, and five plots for the available loss matrix.

The smoke run is a correctness and instrumentation check. Its one-trial samples are not used to confirm or refute research hypotheses and should not be presented as final protocol-performance evidence.

## 4. Frozen full-matrix breakdown

| Matrix | Attempts |
|---|---:|
| Loss (RQ1) | 200 |
| Delay (RQ2) | 140 |
| Reordering (RQ3) | 200 |
| Corruption (RQ4) | 100 |
| Duplication (RQ4) | 100 |
| Timeout (RQ5) | 90 |
| Combined faults (RQ6) | 75 |
| **Total** | **905** |

The matrix and seed policy are detailed in [EXPERIMENT_METHODOLOGY.md](EXPERIMENT_METHODOLOGY.md). The full 905-attempt matrix has **not** been executed as part of M3. No benchmark conclusion or numerical answer to RQ1–RQ6 is claimed.

## 5. Exit-gate assessment

- [x] Deterministic small/medium/large text, PNG and WAV fixtures with manifest.
- [x] Fast unit and three-protocol process-level integration tests.
- [x] Extended `slow` integration coverage for baseline, loss, combined faults, and file-size boundaries.
- [x] Smoke/quick/full tiers, filters, seeds, worker control and dry-run planning.
- [x] Unique per-run directories, ports and process metrics paths; explicit readiness and bounded cleanup.
- [x] Frozen 87-column CSV with one row per attempted run and failure details.
- [x] Required sender, receiver, and per-direction proxy metrics.
- [x] Failure-aware median/IQR analysis, configured-versus-realized fault table, and reproducible plots.
- [x] CI workflow runs fast tests and the smoke tier.
- [ ] Full 905-attempt matrix and final research answers — **M4**.

## 6. Next milestone

Milestone 4 will run the frozen full matrix, preserve the complete CSV and plots, write `BENCHMARKS.md` with evidence-based answers to all six research questions, complete remaining diagrams and release documentation, prepare the demo, and create the tagged `v1.0` release only after the final Definition of Done is satisfied.
