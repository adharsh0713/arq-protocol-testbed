# Milestone 1 Report - Protocol and ARQ Correctness

**Status:** Passed local unit-test gate. Receiver/proxy integration is intentionally deferred to Milestone 2.

## Work completed

### Configuration

- Added a validated `RuntimeConfig` model and `load_config()` function in `config.py`.
- Added environment settings for timeout, retry count, chunk size, window, sender/receiver/proxy ports, random seed, and all DATA/ACK fault dimensions including reordering.
- Changed the localhost default timeout from 1 second to 50 milliseconds.
- Validated protocol names, positive window/chunk/timeout, port ranges, retry count, fault probabilities, and non-negative delays.
- Added `MAX_PAYLOAD=60,000` and an explicit maximum transfer-size calculation based on the 32-bit DATA/END sequence semantics.

### Packet layer

- Preserved the existing 11-byte `!IBHI` big-endian header.
- Preserved CRC32 coverage over sequence, type, length, and payload.
- Added encode/decode field checks, maximum payload enforcement, DATA non-empty enforcement, and empty ACK/END payload enforcement.
- Changed packet representation to report payload length rather than payload contents.

### Sender algorithms

- Stop-and-Wait uses a monotonic deadline per packet attempt. Invalid, stale, duplicate, or foreign datagrams do not reset that deadline.
- Go-Back-N now slides after every valid cumulative ACK, keeps one deadline on `base`, and retransmits the current outstanding suffix after timeout.
- Selective Repeat now stores only unacknowledged active-window state, uses per-packet deadlines, checks deadlines after every receive path, and removes timer state on ACK.
- Sender functions accept timeout/retry/window arguments. Sender passes the process configuration explicitly and closes its socket in `finally`. END control retransmission also uses the same monotonic-deadline approach.

### Tests and supporting records

- Replaced malformed/misplaced ARQ test code with focused sender tests.
- Added tests for packet layout, all header-byte corruption, every truncated header length, payload limits, invalid field combinations, random-input robustness, and packet representation.
- Added validated-configuration tests.
- Added the four-milestone plan, test plan, repository hygiene checklist, six research questions/hypotheses, design decision record, and technical review answer guide.
- Removed the unnecessary repository-root `__init__.py` and added `pytest.ini` so both pytest invocation styles discover project modules from the root.

## Verification performed

| Check | Result |
|---|---|
| `pytest -q` | 50 passed |
| `python -m pytest -q` | 50 passed |
| `python -m compileall -q .` | Passed |
| Packet header corruption tests | Passed for all 11 header bytes |
| Packet truncation tests | Passed for lengths 0 through 10 |
| Random packet-input test | 10,000 deterministic byte strings; no exception other than expected `ValueError` |
| Go-Back-N sliding test | New packet sent after cumulative ACK opens a slot |
| Malformed/foreign traffic deadline tests | Timeout values decrease against one deadline for all three senders |
| Go-Back-N timeout test | Outstanding packets retransmitted from base |
| Selective Repeat timer test | Only the packet whose deadline expires is retransmitted in the controlled test |

Tests ran in the provided Linux container using Python 3.13. Windows behavior, especially UDP `ConnectionResetError` and socket address reuse, has not been verified in this environment.

## Known remaining work

These are not M1 failures; they are explicit later-milestone items:

- Receiver still binds and runs at import time; it must become testable in M2.
- Receiver currently writes directly to its final output and lacks idle timeout/transactional cleanup; M2.
- Proxy delay remains blocking; reordering, ACK duplication, seeded per-injector RNG, directional counters, and graceful shutdown are not implemented yet; M2.
- Existing metrics still use wall-clock time and fixed file paths; M3.
- Existing runner still uses fixed sleeps, has no run isolation/tiers/workers, and does not record all failed attempts; M3.
- Full test-file matrix, experiment results, final plots, six required release documents, CI, diagrams, and release are M3/M4.

## Gate decision

**M1 is complete.** The packet and sender foundation is stable enough to support the receiver and deterministic proxy refactor. No full benchmark should be run yet: the checklist's proxy and receiver blockers still invalidate fault-model and end-to-end results.
