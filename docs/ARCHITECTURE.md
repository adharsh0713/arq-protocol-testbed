# Reliable UDP Architecture

## 1. Components

| Component | Responsibility | Main files |
|---|---|---|
| Sender | Reads source, creates DATA chunks, selects an ARQ sender, performs END handshake, writes sender metrics | `sender/sender.py`, `algorithms/` |
| Packet layer | Encodes/decodes the fixed packet header and validates CRC/fields | `protocol/packet.py`, `protocol/crc.py` |
| ARQ implementations | Implements Stop-and-Wait, Go-Back-N, and Selective Repeat retransmission/ACK rules | `algorithms/stop_wait.py`, `algorithms/go_back_n.py`, `algorithms/selective_repeat.py` |
| Fault injector | Applies one set of seeded fault decisions to an incoming direction | `network/fault_injector.py` |
| Proxy | Routes DATA/END and ACK traffic through separate injectors and a release-time queue | `network/proxy.py` |
| Receiver | Applies protocol-specific acceptance rules, buffers SR packets, validates END/integrity, commits the output file | `receiver/receiver.py` |
| Experiment runner | Creates isolated process groups, assigns ports and paths, checks integrity/config consistency, records each attempt | `experiments/runner.py` |
| Analysis | Aggregates all attempt counts, computes verified-success performance distributions and creates plots | `experiments/analysis.py`, `experiments/plots.py` |

## 2. Process and port layout

For a manual local run, defaults are receiver UDP port 5000 and proxy UDP port 5001. The sender sends to the proxy. The proxy forwards DATA/END to the receiver and forwards ACK packets back to the sender's pinned source address.

```text
Sender process                 Proxy process                 Receiver process
127.0.0.1:<ephemeral>          127.0.0.1:5001                127.0.0.1:5000
       |                              |                              |
       |---------- DATA / END ------->|                              |
       |                              |---------- DATA / END ------->|
       |                              |<------------- ACK ------------|
       |<----------- ACK -------------|                              |
```

The experiment runner assigns a distinct receiver/proxy port pair to each attempt. It also assigns unique sender, receiver, and proxy metrics paths and a unique output file under that run's directory. This prevents parallel runs from sharing metrics filenames or overwriting received data.

The proxy supports one sender and one active transfer at a time. It pins the first valid DATA/END sender address and rejects datagrams from a second sender. The receiver process handles one transfer and exits after END ACK linger or idle failure.

## 3. DATA flow

1. Sender reads the source file in `CHUNK_SIZE` chunks and assigns sequence numbers starting at zero.
2. Each DATA packet is encoded with the 11-byte header and CRC32.
3. Sender sends the datagram to the proxy's UDP port.
4. The proxy identifies DATA direction, records the datagram, applies loss/corruption/duplication/delay/reordering decisions, and pushes scheduled copies into a min-heap ordered by release time.
5. The proxy forwards due copies to the receiver.
6. Receiver validates packet CRC and field constraints, applies the selected ARQ receiver rule, and writes only new in-order payload bytes to `<output>.part`.
7. Receiver sends ACK to the proxy. The proxy applies ACK-direction faults and forwards due copies to the sender.
8. Sender processes ACKs and updates its sliding/outstanding window or retransmission timers.

## 4. Completion flow

After all DATA has been acknowledged, sender transmits END using the next sequence value. Receiver accepts END only if all expected DATA is delivered and the SR buffer is empty. It flushes the temporary file, validates expected size and SHA-256 when supplied, atomically renames the file on success, and sends ACK for END. Duplicate END packets are re-ACKed during a bounded linger period.

The sender stops its completion timer after accepting the END ACK. The runner waits for receiver exit, requests graceful proxy shutdown, and lets the proxy drain scheduled deliveries and flush statistics. It then verifies both source/received file size and SHA-256 and checks that the sender, receiver, and proxy effective configurations are identical.

## 5. Fault scheduling and counters

DATA/END and ACK are separate fault directions with independent `random.Random` state. Each datagram can be dropped, corrupted, duplicated, assigned a base delay, or assigned an additional reorder hold. The proxy does not sleep in its receive loop. It wakes for the earliest queued release time, so one delayed packet does not block later incoming datagrams.

Proxy counters distinguish incoming packets from delivered copies. Reorder scheduling and actual out-of-order delivery are reported separately; a scheduled hold does not guarantee a later packet actually overtakes it.

## 6. Experiment lifecycle

Each attempt uses `sys.executable` to start receiver and proxy modules, waits for each process's READY line, starts the sender as a child process, then reads all process metrics reports. The result row includes run identity, exact configuration, seed, status/error, process metrics, proxy configured/realized faults, integrity metadata, and machine/runtime metadata.

Failed runs are appended to the same CSV as successful ones. The analysis groups by matched configuration, calculates success rate using all attempts, and calculates performance distributions only from verified successes.

## 7. Diagrams and scope

The packet field layout, architecture flowchart, and loss/recovery sequence diagrams for Stop-and-Wait, Go-Back-N, and Selective Repeat are maintained in [DIAGRAMS.md](DIAGRAMS.md). The protocol field semantics are authoritative in [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md). The current system is a localhost ARQ testbed and does not model congestion, link bandwidth limits, physical routing, or WAN behavior; see [LIMITATIONS.md](LIMITATIONS.md).
