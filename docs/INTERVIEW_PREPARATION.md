# Reliable UDP - Technical Review and Interview Preparation

These are concise model answers to the review questions implied by the project checklist. Replace generic statements with measured values only after Milestone 3 has produced verified results.

## 1. What problem does the project solve?

UDP is a datagram transport and does not itself provide the ordered, reliable byte stream implemented by TCP. This project adds a small ARQ layer over UDP and compares three ways to recover from missing packets: Stop-and-Wait, Go-Back-N, and Selective Repeat. Its purpose is to study their behavior under controlled faults, not to provide a production transport.

## 2. Why not just use TCP?

For an application that needs a general reliable byte stream, TCP is the appropriate choice. Reimplementing reliability is normally unnecessary and would omit mature congestion control, flow control, connection management, and extensive operational experience. The project's purpose is experimental: by implementing ARQ directly, we can isolate how ACK policy, sender windows, buffering, loss, and reordering affect transfer behavior. QUIC is another production option when its UDP-based, user-space transport and multiplexed streams are useful. This project is not a TCP/QUIC replacement.

## 3. What is the bandwidth-delay product (BDP), and how does it relate to window size?

The bandwidth-delay product is the amount of data that can be in flight during one round-trip interval:

`BDP (bytes) = bottleneck bandwidth (bytes/second) × RTT (seconds)`

A window with fewer bytes in flight than the BDP can leave a path underutilized while waiting for ACKs. In a simplified fixed-chunk model, a rough window target is `ceil(BDP / chunk_size)`. Once the window covers the effective in-flight requirement, increasing it further should not proportionally improve throughput. On localhost, host scheduling, socket processing and the absence of a controlled physical bottleneck make this relationship less clean than on a real link.

## 4. Why does Selective Repeat need a receiver buffer?

SR accepts and acknowledges valid packets that arrive within the receive window even when an earlier packet is missing. It must retain those out-of-order payloads until the missing sequence arrives, then write the now-contiguous prefix in order. Without that buffer, individually acknowledging out-of-order packets would confirm data that the receiver could not safely reconstruct in order.

## 5. What does Go-Back-N cost under reordering?

The GBN receiver accepts the next expected sequence and discards packets above it. If packet `k` is missing but `k+1`, `k+2`, and later packets arrive first, those later packets are discarded. When the sender's base timer expires, it retransmits from `k` onward. Thus, reordering can create retransmissions of packets that were already transmitted successfully but discarded by the receiver.

## 6. Cumulative ACK versus individual ACK

In this project's GBN semantics, ACK `n` means every DATA sequence through `n` has arrived in order. The sender can advance its base to `n+1`. In SR, an ACK identifies an individual accepted sequence, allowing the sender to release that packet while retaining state for any earlier missing sequence. This project uses individual ACK packets for SR; it does not implement TCP's selective-acknowledgement option format.

## 7. How should timeout estimation work?

A sender needs an RTO (retransmission timeout) long enough to avoid retransmitting packets/ACKs that are merely delayed, but short enough to recover promptly after loss. Production transports estimate RTT and its variation rather than selecting one universal fixed timeout. This project's v1.0 scope uses a configurable fixed timeout so the protocols can be compared under matched parameters. RQ5 measures how sensitive the results are to this choice; adaptive RTO is explicitly out of scope.

## 8. Why is one timer used for GBN and multiple timers for SR?

GBN retransmits the outstanding suffix when the oldest unacknowledged packet times out, so a timer on `base` is sufficient. SR retransmits packets independently; each unacknowledged packet therefore needs its own send timestamp/deadline and retry count. ACKed SR state must be removed so the cost depends on the active window, not the entire transfer history.

## 9. Why are configured and realized fault rates different?

The configured rate is a probability applied independently to eligible packet arrivals. A finite transfer samples that probability only a limited number of times, so the observed fraction can differ, especially for small files. The proxy must record actual event counts; the runner reports both requested rates and observed counts instead of labelling the configuration as though it were the measured outcome.

## 10. Why use SHA-256 if packets already have CRC32?

CRC32 detects accidental corruption of individual packets and helps discard damaged datagrams before the ARQ logic processes them. SHA-256 compares the complete source and reconstructed files after the transfer. They operate at different levels: per-packet error detection versus end-to-end file-integrity verification. Neither provides peer authentication in this project.

## 11. How do measured localhost results differ from textbook expectations?

Textbook ARQ models often assume a simplified link with specified propagation delay, bandwidth, independent loss, and negligible host processing overhead. This testbed runs sender, proxy and receiver as processes on one machine. Its measurements include Python scheduling, socket queues, process startup and timer granularity; its injected delay/reordering is a software model. Therefore, results are useful for controlled relative comparisons within the recorded setup, not as direct predictions of WAN performance.

## 12. What are the project's limitations?

- Localhost emulation only; not a physical wide-area network.
- No bandwidth cap, congestion control, or correlated loss model.
- Fixed configurable timeout in v1.0; no adaptive RTO.
- One sender per proxy and one transfer per receiver in the declared test model.
- 32-bit sequence space without wraparound.
- Python timing and scheduling noise.
- CRC32 is not cryptographic authentication.
- Results apply only to the parameter sets and fault model recorded in the CSV/methodology.

## Final review rule

Do not quote a performance win, speedup, retransmission reduction, or reliability percentage until the final CSV and plot show the matched configurations, realized fault counts, successful-trial count, and success rate. The resume statement is written last from those verified values.

## Milestone 2 implementation questions

### 13. Why write to a `.part` file instead of the final output path?

A file written directly to its final name can look complete even when the sender crashes halfway through. The receiver therefore writes to a sibling `.part` file and publishes it with an atomic rename only after it has received a valid END and passed the configured size/hash checks. On idle timeout or integrity failure, it deletes the partial file. This prevents a failed transfer from leaving a believable completed output.

### 14. Why must the receiver verify byte count and SHA-256 before acknowledging END?

END only says that the sender believes it has sent all DATA sequences. It does not independently prove that the receiver reconstructed the intended source file. The runner knows the original file's size and hash, so it passes those values to the receiver. The receiver compares both values before sending the END ACK. If metadata is absent, the receiver can complete the ARQ handshake but reports `integrity_verified: null`; it does not claim source verification.

### 15. Why is the receiver idle timeout different from the sender's packet timeout?

A sender timeout controls when a packet is retried. The receiver idle timeout controls how long a receiver process waits without a valid packet before abandoning an incomplete transfer. The receiver uses a retry-derived timeout with a five-second minimum by default so a person or runner can start the remaining processes. It is configurable for automated tests. Invalid or foreign datagrams do not reset the receiver's monotonic idle deadline.

### 16. Why must Selective Repeat not ACK a packet above its receive window?

The receiver has not buffered that packet and cannot guarantee delivery. ACKing it could let the sender discard its only retransmission copy. The receiver ACKs sequences inside the active receive window and re-ACKs sequences below the lower edge because those have already been delivered. It ignores a sequence at or beyond `expected + window_size`.

### 17. Why use a priority queue instead of sleeping or creating one thread per delayed packet?

A sleep in the single receive loop blocks all other packet processing, including ACK forwarding. A thread per packet adds synchronization and lifecycle complexity. The min-heap stores each packet copy with a release timestamp, and the UDP socket timeout wakes the loop when the next item is due. One event loop can therefore keep receiving new traffic while delayed DATA or ACK copies wait.

### 18. How does the proxy create and measure reordering?

Each observed packet has an arrival-order number. If the seeded injector selects it, the proxy adds a direction-specific hold to its release time. A later-arriving packet can then be released first. The proxy increments `reorder_scheduled` when it applies the hold and `packets_reordered` when it actually releases a copy whose arrival order is older than a copy already delivered. These are different measurements: a scheduled hold does not guarantee an actual overtake.

### 19. Why are DATA and ACK random generators independent?

If both injectors use Python's global random generator, a DATA-side random draw changes the next ACK-side decision. That couples two fault streams and makes results sensitive to unrelated code paths. Each direction therefore owns a `random.Random` instance. The DATA injector uses the run seed; the ACK injector uses a deterministic XOR-derived seed. The seed and effective settings are saved in the proxy report.

### 20. Why persist statistics periodically and also shut the proxy down gracefully?

A process terminated immediately may never execute its final statistics dump. Periodic atomic writes preserve progress if the process fails unexpectedly. On normal completion, the runner sends a local shutdown datagram; the proxy drains already scheduled packet copies, writes final counters and closes the socket. The resulting JSON includes configuration, seed, per-direction counts, realized rates, and pending queue state.

### 21. What does this proxy still not model?

It models packet-level loss, one-bit corruption, fixed delay, duplication, and controlled reordering. It does not model bandwidth caps, correlated/burst loss, queue overflow, congestion control, multiple hops, or real WAN jitter. Therefore, its measurements compare ARQ implementations under a controlled localhost fault model; they are not forecasts for a production network.

## M2 review note

The process-level cases in `MILESTONE_2_REPORT.md` are correctness validations, not statistically adequate answers to RQ1-RQ6. Quote research conclusions only after the full repeated experiment matrix and analysis are complete.
