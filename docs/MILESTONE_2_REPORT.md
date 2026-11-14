# Milestone 2 Report - Receiver and Fault-Injection Network

**Completion date:** 2026-11-13  
**Milestone status:** Complete  
**Scope:** Receiver lifecycle, file integrity, deterministic bidirectional fault injection, proxy scheduling, and focused unit tests.

## 1. Summary

Milestone 2 converted the receiver from an import-time script into an explicit `Receiver` class and replaced the proxy's blocking, partial fault-injection logic with a seeded, queue-based bidirectional proxy.

The receiver now rejects premature END packets, handles protocol-specific receiver windows, prevents duplicate writes, removes partial files after failure, and only publishes the final output after a valid END. When the runner supplies source size and SHA-256 values, the receiver checks both before acknowledging END and publishing the file.

The proxy now implements loss, corruption, delay, duplication, and reordering independently in both directions. It records configured settings and realized event counters, periodically persists statistics, and supports graceful shutdown with queued-delivery draining.

## 2. Implementation changes

### Receiver

- Removed module-level socket creation, bind, file open, and receive loop. Importing `receiver.receiver` no longer binds a port or starts a transfer.
- Added a `Receiver` class with an injectable socket, explicit configuration, output path, metrics path, expected source size/hash, idle timeout, and END-ACK linger.
- Added a monotonic idle deadline. Invalid, foreign, or unrelated datagrams do not extend the idle deadline.
- Pinned the transfer to its first DATA/END sender address; foreign addresses are ignored.
- Implemented the protocol-specific receive behaviors:
  - Stop-and-Wait accepts the expected sequence, re-ACKs already accepted sequences, and does not ACK future sequences.
  - Go-Back-N writes only the expected sequence and sends a cumulative ACK for the last in-order packet when appropriate.
  - Selective Repeat buffers only `[expected_sequence, expected_sequence + window_size)`, ACKs only in-window or already delivered packets, and drains contiguous buffered data in order.
- Writes to `<output>.part`, flushes and `fsync`s before finalization, checks expected size/hash when provided, and atomically publishes with `os.replace` only after successful checks.
- Deletes the partial file and clears the receive buffer on idle timeout, integrity failure, or receiver error.
- Re-ACKs repeated END packets during a bounded linger interval derived from timeout/retry settings plus a margin.
- Writes a per-run receiver metrics JSON atomically. It includes expected/received byte counts and SHA-256 values, integrity status, DATA arrivals, unique acceptance/delivery, duplicates, corrupt discards, ACK count, and terminal status.

### Fault injector and proxy

- Replaced global `random` usage with one `random.Random` instance per injector. DATA uses the base seed; ACK uses a deterministic XOR-derived seed.
- Added reordering and explicit reorder-hold parameters for DATA and ACK independently.
- Unified the DATA and ACK processing paths so both support loss, corruption, delay, duplication, and reordering.
- Replaced `time.sleep()` delay with a release-time min-heap. The socket timeout is set to the next delivery deadline, so the loop can continue receiving while delayed packets wait.
- Counts actual out-of-order releases separately from packets merely selected for a reorder hold.
- Pins one sender, accepts ACK only from the configured receiver endpoint, and rejects unexpected senders.
- Persists effective configuration, seed, per-direction counters, realized rates, malformed input count, unexpected sender count, and pending queue size to an atomic JSON file.
- Added periodic stats flushing and a local shutdown datagram. The proxy drains scheduled deliveries, persists final stats, and closes its socket.
- Uses exclusive UDP socket binding where the platform supports `SO_EXCLUSIVEADDRUSE`; `SO_REUSEADDR` is not enabled.

## 3. Test coverage and validation

### Automated tests

The full default suite now contains **86 passing tests** after Milestone 2's additional configuration and receiver/proxy coverage.

Commands:

```bash
pytest -q
python -m pytest -q
python -m compileall -q .
```

Coverage includes:

- Receiver import safety and socket injection.
- Stop-and-Wait, Go-Back-N, and Selective Repeat acceptance/ACK behavior.
- Selective Repeat lower/upper window boundaries and out-of-window ACK suppression.
- In-order release of buffered SR packets.
- Duplicate and corrupt datagrams, foreign sender rejection, premature END, and END re-ACK.
- Empty-file completion, integrity mismatch, atomic output, and `.part` cleanup.
- Receive-buffer cleanup after successful and aborted transfers.
- Seeded injector repeatability and exact loss/corruption/delay/duplication/reordering decisions.
- Each supported fault in both DATA and ACK directions.
- Proxy zero-fault forwarding, ACK duplication, queue scheduling, actual reorder counting, invalid input, sender pinning, stats persistence, and shutdown signaling.

### Process-level loopback validation

Separate OS processes were launched for receiver, proxy, and sender. Transfers used a binary file, per-run output/metrics paths, and source size plus SHA-256 metadata.

| Protocol | Fault configuration | Bytes | Receiver status | Integrity |
|---|---|---:|---|---|
| Stop-and-Wait | No faults | 9,123 | completed | verified |
| Go-Back-N | No faults | 9,123 | completed | verified |
| Selective Repeat | No faults | 9,123 | completed | verified |
| Selective Repeat | 30% configured DATA reorder; 20% ACK duplication | 9,123 | completed | verified |

A second combined-fault validation used a 4,096-byte binary file and the same seed across the three protocol cases. Both directions used loss, corruption, delay, duplication, and reordering settings. Each protocol completed with exact byte equality and matching SHA-256:

| Protocol | Realized DATA drops | Realized ACK drops | DATA packets reordered | ACK packets reordered | Integrity |
|---|---:|---:|---:|---:|---|
| Stop-and-Wait | 2 | 1 | 0 | 0 | verified |
| Go-Back-N | 2 | 2 | 3 | 4 | verified |
| Selective Repeat | 2 | 1 | 3 | 1 | verified |

These are validation runs, not the project's final statistical benchmark. They demonstrate that the receiver/proxy process path works under the tested cases; they do not establish general performance rankings or research-question conclusions.

## 4. Configuration additions

| Variable | Default | Purpose |
|---|---:|---|
| `DATA_REORDER_DELAY` | `0.05` s | Additional hold for selected DATA/END datagrams |
| `ACK_REORDER_DELAY` | `0.05` s | Additional hold for selected ACK datagrams |
| `RECEIVER_IDLE_TIMEOUT` | `max(retry-derived timeout, 5 s)` | Maximum wait without a valid packet before receiver abort |
| `RECEIVER_METRICS_PATH` | `data/results/receiver_metrics.json` | Receiver's atomic metrics report |
| `PROXY_STATS_PATH` | `data/results/proxy_metrics.json` | Proxy's atomic fault statistics report |
| `PROXY_STATS_FLUSH_INTERVAL` | `100` | Periodic proxy stats flush interval in observed datagrams |
| `EXPECTED_FILE_SIZE` | unset | Expected source byte count supplied by the runner |
| `EXPECTED_FILE_SHA256` | unset | Expected source SHA-256 supplied by the runner |

When expected source size/hash are absent, the receiver can complete the ARQ transfer but reports `integrity_verified: null`; it does not claim end-to-end source verification. Milestone 3's runner must supply both values for benchmark runs and independently check the resulting receiver report.

## 5. Remaining scope

Milestone 2 does not complete the full experiment framework. Milestone 3 still needs the deterministic five-file fixture generator, a committed fast loopback integration suite, smoke/quick/full tiers, process readiness/cleanup helpers, per-run port and artifact isolation, the frozen result CSV schema, realized/configured fault comparisons in rows, complete sender/receiver/proxy metric merging, statistical summaries, and reproducible plots.

Windows-specific socket option and process behavior have not been verified in this environment. Linux process-level loopback validation passed.

## 6. Exit gate

| Milestone 2 criterion | Result |
|---|---|
| Receiver is import-safe and independently testable | PASS |
| Receiver uses atomic partial-file handling and idle timeout | PASS |
| END requires the expected contiguous sequence and empty SR buffer | PASS |
| Size/hash validation is available and reported | PASS |
| Receiver/proxy use centralized configuration | PASS |
| Faults operate independently in DATA and ACK directions | PASS |
| Delay is queue-scheduled rather than implemented with `sleep()` | PASS |
| Reordering can overtake and is counted when observed | PASS |
| Per-direction randomness is seeded and isolated | PASS |
| Proxy statistics are periodically and finally persisted | PASS |
| Local graceful shutdown drains pending scheduled deliveries | PASS |
| Focused unit suite and process-level loopback checks pass | PASS |

**Milestone 2 is complete.** The next milestone is the complete integration and experimental framework.
