# Reliable UDP - Four-Milestone Implementation Plan

## Current implementation status (2026-11-13)

| Milestone | Status | Evidence |
|---|---|---|
| M1 - Protocol and ARQ correctness | Complete | `docs/MILESTONE_1_REPORT.md`; packet/configuration/sender tests |
| M2 - Receiver and fault-injection network | Complete | `docs/MILESTONE_2_REPORT.md`; receiver/proxy tests and process-level loopback validation |
| M3 - Complete test suite and experimental framework | Complete | `docs/MILESTONE_3_REPORT.md`; 100 automated tests, six-run smoke matrix, concurrent loopback test, frozen 905-attempt full plan |
| M4 - Documentation, research and release | In progress — release candidate prepared | Required documents, diagrams, license, smoke evidence and packaging are present; 905-run matrix, final RQ answers, recording and published tag remain gated |

The current repository has a completed M1-M3 implementation and an M4 release candidate. It is not yet the v1.0 release: the 905-attempt full research matrix has not been run, so no RQ1-RQ6 performance conclusion is claimed.

## Project objective

Build a reproducible localhost testbed that implements and compares Stop-and-Wait, Go-Back-N (GBN), and Selective Repeat (SR) ARQ over UDP under controlled packet faults. The project studies reliability and ARQ trade-offs; it is not intended to replace TCP or QUIC.

The work is divided into four gated milestones. Tests are added with the component they validate rather than deferred to the final milestone.

## Milestone 1 - Protocol and ARQ correctness

**Purpose:** establish stable packet, configuration, timeout, and sender semantics before adding a more complex receiver or proxy.

### Scope

- Use one configuration module for protocol, window, chunk size, timeout, retry count, endpoint ports, seed, and all directional fault parameters.
- Preserve the 11-byte `!IBHI` packet header and CRC32 coverage of sequence, type, length, and payload.
- Validate packet type, sequence range, payload type/length, and the empty-payload rules for ACK and END.
- Define `MAX_PAYLOAD`; keep chunks below the maximum UDP datagram payload.
- Refuse files whose DATA packet count cannot be represented by the 32-bit END sequence.
- Use monotonic per-attempt deadlines so unrelated, stale, malformed, or duplicate datagrams cannot restart a sender timeout.
- Make timeout, window size, and retry count explicit sender parameters.
- Implement GBN sliding-window transmission with one timer on `base` and retransmission from `base` on timeout.
- Keep SR state limited to the current window and remove per-packet state as ACKs arrive.
- Repair misplaced ARQ tests and make both `pytest -q` and `python -m pytest -q` work from the repository root.

### Deliverables

- Hardened packet layer and centralized runtime configuration.
- Correct Stop-and-Wait, GBN, and SR sender implementations.
- Packet/configuration/sender unit tests, including boundary and malformed-input cases.
- This implementation plan, test plan, research-question register, repository hygiene checklist, and design decision record.

### Exit gate

- Unit tests pass on the supported Python runtime.
- Packet header size, field layout, CRC coverage, payload limits, and sequence limits are tested.
- GBN slides on cumulative ACK progress and resends the outstanding suffix on timeout.
- SR retransmits only expired unacknowledged packets and discards acknowledged state.
- Stale/foreign/invalid traffic cannot indefinitely postpone a timeout.

## Milestone 2 - Receiver and fault-injection network

**Purpose:** make the receiver independently testable and make the proxy's fault behavior faithful, observable, and reproducible.

### Scope

- Move receiver startup and socket operations out of module import time into a `Receiver` class or `run()` entry point.
- Add receiver protocol behavior tests using a fake socket.
- Write received data to `<output>.part`; atomically rename only after a valid END and integrity checks; remove partial output after failure or idle timeout.
- Add a receiver idle timeout and derive END-ACK linger from timeout/retry settings plus a documented margin.
- Count unique DATA deliveries, DATA arrivals, duplicates, and corrupt discards separately.
- Verify byte count and SHA-256 independently before marking a transfer successful.
- Move receiver, proxy, and sender endpoint settings to the shared config source.
- Replace blocking delay sleeps with a time-ordered delivery queue and socket timeout scheduling.
- Implement reordering by holding selected packets long enough for later packets to overtake them.
- Apply duplication on both DATA and ACK paths.
- Use one `random.Random(seed)` instance per directional injector; do not mutate Python's global random state.
- Collect per-direction seen/drop/corrupt/duplicate/delay/reorder counters and persist them during operation and at graceful shutdown.
- Add an explicit proxy shutdown message and process cleanup; reject or document unsupported second-sender behavior.

### Deliverables

- Testable receiver implementation and atomic output handling.
- Deterministic fault injector and queued-delivery proxy.
- `FAULT_MODEL.md` with fault definitions, configuration, seeding, counters, and exclusions.
- Receiver/proxy unit tests and isolated-fault deterministic tests.

### Exit gate

- Receiver and proxy tests pass, including window edges and all supported fault types in both directions.
- A fixed seed reproduces the same injected outcomes.
- Delay does not serialize all packets behind `sleep()`; reordering can be observed and counted.
- Receiver never leaves a partial file that looks like a successful completed transfer.
- Proxy statistics survive graceful shutdown and distinguish configured rates from realized counts.

## Milestone 3 - Complete test suite and experimental framework

**Purpose:** make correctness and performance claims reproducible and ensure failures are data, not silently discarded.

### Scope

- Generate small, medium, and large seeded text fixtures, a deterministic valid PNG, and a short deterministic WAV using standard-library modules.
- Build loopback end-to-end tests for all protocols with loss, duplication, and reordering; verify exact bytes and SHA-256.
- Mark longer tests with `@pytest.mark.slow`; keep the default suite fast.
- Add a smoke tier (small file, each protocol, zero and seeded loss), a quick tier, and a full research tier.
- Add protocol/file/loss/fault filters and per-run port/output/metrics isolation.
- Support configurable workers; use parallel workers for correctness matrices and one or two workers for timing matrices.
- Wait for explicit readiness rather than sleeping one second after process creation.
- Use `sys.executable`, verify ports, and reliably stop/wait/kill child processes.
- Write one CSV row for every attempted run, including startup failures, timeouts, retry exhaustion, and integrity failures.
- Freeze and document a schema containing run ID/status/error, seed, parameters, fault configuration and realized counts, environment, git commit, byte counts/hashes, and metrics.
- Use `time.perf_counter()` for elapsed time. Define completion time as first DATA send through END ACK; report SHA-256 verification separately.
- Record all required metrics: completion time, verified throughput, DATA retransmissions, END retries, total encoded bytes sent, unique DATA delivered, DATA arrivals/duplicates/corrupt discards, integrity values, and recovery time.
- Separate sender, receiver, and proxy reports and merge by field name.
- Report median and IQR, plus success rate for each configuration. Retain failed attempts in the denominator.
- Generate required plots from the verified CSV using one command; avoid plots that pool unmatched file/window configurations.

### Deliverables

- Reproducible test fixtures and a complete unit/integration suite.
- Smoke/quick/full experiment runner with isolated artifacts.
- Frozen results CSV schema, metrics JSON, aggregation, plots, and a one-command analysis entry point.
- `EXPERIMENT_METHODOLOGY.md`.

### Exit gate

- Fast tests pass by default and complete in seconds.
- Smoke tests transfer files through the actual UDP processes and verify SHA-256.
- Every attempted experiment appears in the CSV, including failed attempts.
- Fault counters, seeds, runtime environment, and effective config are present for every run.
- Analysis reports success rate, median, and IQR without silently discarding failures.
- Re-running the same seeded configuration reproduces the fault sequence.

## Milestone 4 - Documentation, research and release

**Purpose:** produce an auditable research artifact and a clean public repository from verified implementation and results.

### Scope

- Write the required documents: `PROTOCOL_SPEC.md`, `FAULT_MODEL.md`, `EXPERIMENT_METHODOLOGY.md`, `ARCHITECTURE.md`, `BENCHMARKS.md`, and `LIMITATIONS.md`.
- Maintain `DESIGN_DECISIONS.md`, `RESEARCH_QUESTIONS.md`, `TEST_PLAN.md`, and this plan.
- Rewrite README for a first-time reader: problem statement, research questions, architecture, quick start, test commands, measured headline result, benchmarks, and limitations.
- Correct stale/duplicate README content and remove unsupported performance claims.
- Add packet-format and process architecture diagrams, plus Stop-and-Wait, GBN, and SR sequence diagrams showing loss recovery.
- Store verified plots under `docs/graphs/` and raw experiment output under `data/results/`.
- Review the M3 GitHub Actions workflow and verify it on the target Git host.
- Review the pinned dependencies and clean-checkout setup documented in M3.
- Finish remaining release-only cleanup and verify no generated results or temporary files are committed.
- Add LICENSE, repository description/topics, and a 2-3 minute demo script.
- Prepare the v1.0 tag and attach CSV, plots, and demo only after all gates pass.

### Deliverables

- Complete documentation and diagrams.
- Verified research answers with figures and successful-trial counts.
- CI, license, clean repository tree, demo instructions, and release artifacts.

### Exit gate / Definition of Done

- All three protocols transfer all five required fixture types with matching byte counts and SHA-256 under every declared tested fault configuration.
- One command regenerates CSV analysis and plots.
- CSV includes seeds, configuration, realized faults, and failed runs.
- Fast tests and smoke tier pass in CI.
- Every README/BENCHMARKS claim maps to a CSV row or plot; unsupported claims are documented in LIMITATIONS.
- v1.0 is tagged only after the above conditions are met.

## Explicit v1.0 exclusions

Adaptive RTO, congestion control, bandwidth caps, a Wireshark dissector, and TCP/QUIC performance comparisons are outside v1.0. They may be proposed as future work after the controlled ARQ testbed is complete.
