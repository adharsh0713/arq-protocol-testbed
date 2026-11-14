# Reliable UDP — ARQ Protocol Testbed

[![Tests and smoke matrix](https://github.com/adharsh0713/reliable-udp/actions/workflows/tests.yml/badge.svg)](https://github.com/adharsh0713/reliable-udp/actions/workflows/tests.yml)

Reliable UDP is an experimental testbed for implementing and comparing three Automatic Repeat reQuest (ARQ) strategies over UDP: **Stop-and-Wait, Go-Back-N, and Selective Repeat**. A deterministic localhost proxy injects packet loss, corruption, delay, duplication, and reordering independently into DATA and ACK traffic. Every experiment records its seed, effective configuration, proxy counters, process metrics, outcome, and file-integrity evidence.

> **Research status (13 November 2026):** The implementation and test/experiment framework are complete. The current committed result set is a six-transfer smoke run. It verifies that all three protocols transfer the test file under the smoke conditions; it is not sufficient to confirm or reject the six research hypotheses. The pre-registered 905-attempt full matrix remains the final research gate. This project is an educational ARQ testbed, not a replacement for TCP or QUIC.

## Problem and objective

UDP provides datagram delivery without built-in guarantees of reliable, in-order application delivery. This project implements three classic ARQ strategies above UDP and studies their behavior under controlled packet faults. The objective is to understand **when each ARQ strategy recovers efficiently and what it costs**, not to build a production transport protocol.

## Research questions

1. How do completion time and retransmissions grow with packet loss?
2. When does a larger sender/receiver window improve throughput?
3. How do Go-Back-N and Selective Repeat compare under packet reordering?
4. How closely do configured fault rates match realized rates?
5. How sensitive are outcomes to retransmission timeout selection?
6. Do all three protocols deliver byte-identical files under combined faults?

The hypotheses, controlled conditions, and required outputs are in [RESEARCH_QUESTIONS.md](docs/RESEARCH_QUESTIONS.md) and [EXPERIMENT_METHODOLOGY.md](docs/EXPERIMENT_METHODOLOGY.md). The current evidence status is in [BENCHMARKS.md](docs/BENCHMARKS.md); predictions are not presented as findings.

## Protocols and packet format

| Protocol | ACK behavior | Recovery behavior |
|---|---|---|
| Stop-and-Wait | ACK confirms one DATA sequence | Retransmits the current DATA packet after timeout |
| Go-Back-N | Cumulative ACK through the latest in-order sequence | Retransmits the outstanding suffix beginning at `base` |
| Selective Repeat | Individual ACK for each accepted in-window sequence | Retransmits only expired, unacknowledged DATA packets |

The fixed packet header is 11 bytes (`!IBHI`, big-endian): sequence `u32`, packet type `u8`, payload length `u16`, CRC32 `u32`. CRC covers sequence, type, length, and payload. The default chunk size is 4,096 bytes. See [PROTOCOL_SPEC.md](docs/PROTOCOL_SPEC.md) and [packet/ARQ diagrams](docs/DIAGRAMS.md).

## Architecture

```text
Source file
    |
    v
Sender — Stop-and-Wait / Go-Back-N / Selective Repeat
    |
    | DATA / END
    v
Seeded DATA fault injector -> scheduled-delivery queue
    |
    v
Receiver — protocol checks, SR buffer, .part file, integrity verification
    |
    | ACK
    v
Seeded ACK fault injector -> scheduled-delivery queue
    |
    +-----------------------------------------------> Sender
```

The runner launches sender, proxy, and receiver as separate local processes. Each attempt gets isolated ports, output paths, metrics files, logs, and a reproducible seed. The receiver publishes the final file only after END and configured integrity checks. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install pinned dependencies:

```bash
python -m pip install -r requirements.txt
```

Generate deterministic transfer fixtures (the five fixtures and their SHA-256 manifest are included in the repository):

```bash
python scripts/make_test_files.py
```

## Run and test

Run the fast suite, including three real sender/proxy/receiver loopback transfers:

```bash
python -m pytest -q
```

Run longer integration tests separately:

```bash
python -m pytest -m slow -q
```

Run the six-transfer correctness smoke tier:

```bash
python -m experiments.runner --tier smoke --workers 1
```

Run the development tier:

```bash
python -m experiments.runner --tier quick --workers 1
```

Run the full pre-registered research matrix (905 attempts):

```bash
python -m experiments.runner --tier full --workers 1
```

Inspect the planned matrix without launching processes:

```bash
python -m experiments.runner --tier full --dry-run
```

Run selected parts of a tier with repeatable filters:

```bash
python -m experiments.runner --tier full --matrix reordering --protocol go_back_n --protocol selective_repeat
python -m experiments.runner --tier full --file medium.txt --matrix loss
```

Use one worker for the cleanest timing comparisons. Two are supported; higher parallelism can cause CPU contention and distort measurements. The full matrix is deliberately excluded from pytest and CI.

## Metrics and results

The CSV schema is frozen in `experiments/results.py`. Each attempted run has a row, including failures. It records:

- Completion time, verified throughput, DATA retransmissions, and END retries.
- Encoded bytes sent, unique DATA delivered, duplicate/corrupt arrivals, and recovery timing.
- Source/received byte counts and SHA-256 values.
- Configured and realized loss, corruption, duplication, delay, and reordering for DATA and ACK directions.
- Seed, protocol parameters, Python version, OS, machine, and Git commit when available.

After a run, analysis generates median, quartiles, IQR, success-rate summaries, configured-versus-realized fault comparisons, and plots from verified data:

```bash
python -m experiments.analysis
```

Current result CSV and summary files are under `data/results/`; figures and `plots_manifest.json` are under `docs/graphs/`. See [BENCHMARKS.md](docs/BENCHMARKS.md) before interpreting them.

## Repository map

```text
algorithms/       Stop-and-Wait, Go-Back-N, Selective Repeat
protocol/         Packet format, CRC and control-packet handling
sender/           Sender entry point and metrics
receiver/         Testable receiver and atomic output handling
network/          Seeded fault injection and scheduled UDP proxy
experiments/      Runner, metrics schema, analysis, plots and tests
scripts/          Deterministic fixture generation and packaging
 data/test_files/  Small/medium/large text, PNG, WAV and manifest
data/results/     Committed CSV summaries; per-run outputs are generated
 docs/            Specification, architecture, research, limitations and release docs
```

## Limitations and positioning

The model uses localhost UDP sockets. It does not implement bandwidth limiting, queue capacity, congestion control, correlated loss, adaptive RTO, encryption, authentication, replay protection, or multiple simultaneous transfers. Python scheduling and host load affect small latency measurements. A configured fault probability is not guaranteed to be the realized fraction in a finite run.

Use TCP for a conventional reliable ordered byte stream with mature congestion and flow control. Use QUIC when multiplexed streams, integrated TLS, user-space transport evolution, or connection migration are relevant. This project is a controlled ARQ learning/research testbed only. See [LIMITATIONS.md](docs/LIMITATIONS.md).

## Milestones and release status

- M1 — Packet and ARQ correctness: complete.
- M2 — Receiver and fault-injection proxy: complete.
- M3 — Tests and experimental framework: complete.
- M4 — Research interpretation and release: documentation and release preparation are present; the 905-attempt full matrix, final research answers, demo recording, and published `v1.0` tag remain gated.

See [MILESTONE_4_REPORT.md](docs/MILESTONE_4_REPORT.md) and [RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).
