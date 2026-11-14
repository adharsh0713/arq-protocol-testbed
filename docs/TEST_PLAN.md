# Reliable UDP - Test Plan

## Test execution policy

- Run `pytest -q` and `python -m pytest -q` from the repository root; both are supported.
- The default suite excludes tests marked `slow`. Full experiment matrices are never part of pytest.
- Tests must assert behavior rather than print observations.
- Use deterministic seeds, temporary directories and fake sockets for unit tests; use real loopback UDP processes only for integration.
- Every successful end-to-end transfer must assert byte-count and SHA-256 equality.
- Every runner attempt, including setup and transfer failures, must be represented in the result CSV.

## Test layers and status

| Layer | Coverage | Location | Status |
|---|---|---|---|
| Configuration | Defaults, valid overrides, invalid ranges, independent ports and reorder delay | `test_config.py` | Passing |
| Packet | Binary layout, CRC, invalid fields, truncation, corruption, oversize and deterministic malformed-input corpus | `protocol/test_packet.py` | Passing |
| Sender ARQ | ACK filtering, deadlines, retry behavior, GBN window boundaries/sliding, SR timers and cleanup | `algorithms/test_*.py` | Passing |
| Receiver | Ordering, SR buffer/window, duplicate handling, premature/repeated END, idle failure, partial-file cleanup and chunk boundaries | `receiver/test_receiver.py` | Passing |
| Fault injector | Fixed-seed loss, corruption, duplication, delay and reordering decisions/counters | `network/test_fault.py`, `network/test_loss.py` | Passing |
| Proxy | Bidirectional forwarding, combined faults, queue release order, sender routing, stats and shutdown | `network/test_proxy.py` | Passing |
| Fixture generator | Deterministic three text files, valid PNG, valid WAV and SHA-256 manifest | `scripts/test_make_test_files.py` | Passing |
| Result schema | Exact header, unique fields, failed-row persistence and rejection of unknown fields | `experiments/test_results.py` | Passing |
| Analysis | Failure-aware aggregation, median/IQR, directional fault comparison and plot creation | `experiments/test_analysis.py` | Passing |
| Integration | Real sender/receiver/proxy processes for all three protocols with seeded bidirectional faults and SHA-256 | `experiments/test_end_to_end.py` | Passing |

## Packet-layer cases

- DATA/ACK/END encode-decode round trips and the 11-byte `!IBHI` header.
- CRC coverage of sequence, type, declared length and payload.
- Truncation at lengths 0 through 10, every header byte corrupted, payload corruption, declared-length mismatch and trailing bytes.
- Oversize payloads and invalid type/sequence/field combinations.
- 10,000 deterministic random byte strings: valid Packet or `ValueError`, never an unrelated exception.
- ACK/END empty-payload and DATA chunk constraints.

## Sender ARQ cases

- Matching, stale, duplicate, out-of-range, corrupt, malformed and foreign-source ACKs.
- Monotonic deadline behavior under unrelated traffic and retry exhaustion.
- Stop-and-Wait DATA and END retransmission.
- GBN ACK at `base`, ACK at `next_seq - 1`, window-full boundary, outside-window ACKs, sliding after cumulative ACK and timeout resend of outstanding suffix.
- SR individual ACK handling, expired-packet retransmission, current-window state cleanup and duplicate ACK behavior.

## Receiver cases

1. In-order DATA is written once and in sequence.
2. Duplicate DATA is not written twice.
3. GBN discards out-of-order DATA and re-ACKs last in-order sequence.
4. SR buffers only valid in-window DATA and releases a contiguous prefix when a gap closes.
5. Packets at `expected - 1`, `expected`, `expected + W - 1` and `expected + W` follow the specified boundary behavior.
6. Premature END or END with unresolved buffered data is rejected; valid END is ACKed and repeated END is re-ACKed during linger.
7. Corrupt or malformed datagrams do not mutate receiver state.
8. Empty files, short files, exact chunk multiples and a short final chunk complete correctly.
9. Expected file size and SHA-256 are checked before final output is published.
10. Success atomically renames `.part`; abort and idle timeout remove `.part` and leave no misleading final file.

## Fault injector and proxy cases

For both DATA/END and ACK directions:

- Zero-fault forwarding preserves bytes.
- Fixed seeds reproduce loss, corruption, duplication and reorder-hold decisions.
- Isolated tests verify each fault and exact counters; combined faults are a separate case.
- Delay uses release-time scheduling rather than blocking `sleep()`.
- A selected reorder hold can result in a later-arriving datagram overtaking the held datagram.
- Actual reorder delivery counters are distinct from scheduled reorder holds.
- ACK duplication is injected and counted in the ACK direction.
- Proxy shutdown flushes final metrics, drains queued copies and releases the socket.

## End-to-end integration tests

The fast suite launches receiver, proxy and sender as separate processes for Stop-and-Wait, Go-Back-N and Selective Repeat. It uses a seeded bidirectional combination of loss, corruption, delay, duplication and reordering, then verifies:

- sender and receiver exit successfully;
- effective configuration reports match across all three processes;
- received output exists and exact byte count matches;
- source and received SHA-256 values are identical;
- proxy counters show both directions observed traffic.

The three process-level cases complete in under 10 seconds combined in the validation environment. Longer size/fault matrices belong to the experiment runner.

The `slow` group is separately verified and contains nine additional process-level scenarios (baseline, loss, and combined faults for each protocol) and nine file-boundary transfers (empty, smaller than one chunk, and exact chunk multiple for each protocol). These tests are excluded from the default CI time budget but remain part of the full regression suite.

## Experiment-runner and results assertions

- Smoke/quick/full task counts are 6/36/905; `--dry-run` must report these counts without launching child processes.
- Each attempted run gets a unique run ID, output directory, port pair and process-specific metrics path.
- Each run uses `sys.executable`, explicit READY synchronization and deterministic seed assignment before filters.
- Sender, receiver and proxy effective configurations must match.
- A failure row is persisted for process startup errors, timeouts, retry exhaustion and integrity errors.
- Required source hashes, received hashes, byte counts, sender/receiver metrics, realized fault counts, seed and environment metadata are persisted when available.
- Throughput is blank unless verified; a failed run remains in the success-rate denominator.
- Concurrent runs do not share metric files or result writer buffers.

## Analysis and plots

- Group only matched configurations.
- Report attempts, verified successes and success rate for every group.
- Calculate median, Q1, Q3 and IQR using verified runs only; never turn a failure into a zero performance value.
- Compare configured and realized fault measurements per direction, with delay's configured seconds kept distinct from its realized delayed-packet event fraction.
- Distinguish scheduled reordering from observed out-of-order delivery.
- Generate plots from the input CSV with one command; do not pool unmatched files/windows or infer missing matrices.

## CI and M4 release checks

- GitHub Actions installs pinned dependencies, runs the fast suite, and executes the smoke tier on push and pull request.
- Confirm CI passes in the target repository.
- Before release, run the full matrix with the frozen schema/methodology, regenerate summaries/plots, and audit every benchmark claim against the CSV.
- Full benchmark outputs, documentation, license, diagrams, demo and v1.0 tag remain M4 deliverables.
