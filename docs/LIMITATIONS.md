# Limitations and Appropriate Use

## 1. Experimental status

Reliable UDP is an educational testbed for comparing three ARQ strategies over UDP. It is not a general-purpose transport, a TCP alternative, a QUIC implementation, or a production-ready file-transfer service.

## 2. Network model

The proxy injects packet-level faults in a localhost process environment. It does not model:

- Link bandwidth limits or queue capacity.
- Congestion control or competing flows.
- Correlated/burst loss or realistic error distributions.
- Physical propagation delay, route changes, jitter distributions, or multi-hop scheduling.
- NAT traversal, path MTU discovery, or realistic WAN middleboxes.

The delay setting is fixed per datagram, with an optional extra hold for selected reorder events. The reordering mechanism is a controlled queue approximation, not a router implementation.

## 3. Protocol scope

- No congestion-control algorithm or bandwidth cap is implemented.
- Retransmission timeout is fixed per experiment; there is no adaptive RTO estimator.
- The 32-bit sequence space does not wrap.
- A proxy and receiver each support one active sender/transfer at a time.
- There is no session negotiation, authentication, encryption, or replay protection across transfers.
- CRC32 detects accidental corruption and is not a cryptographic integrity/authentication mechanism.
- The receiver's size/chunk-boundary/hash verification is strongest when the runner supplies source metadata.

## 4. Measurement limits

- Python scheduling and interpreter overhead affect sub-millisecond observations.
- Concurrent workers compete for CPU and can distort timing matrices; one or two workers are recommended.
- Small files contain few packets, so realized fault rates can differ noticeably from configured probabilities.
- Ten repetitions are used for headline loss/reordering points and five for other full-matrix points; these remain finite samples, not universal guarantees.
- Results describe the tested implementation, runtime, machine and localhost setup only.

## 5. When to use existing transports

Use **TCP** for a general reliable, ordered byte stream when kernel-managed congestion control, retransmission, flow control and broad interoperability are desired. Use **QUIC** when application requirements include user-space transport evolution, multiplexed streams, integrated TLS security, and connection migration support. This project should be used to study ARQ state machines and controlled recovery trade-offs, not to replace either transport.


## 6. Current evidence status

The committed CSV in this release candidate is a six-attempt smoke run: all three protocols at 0% and 20% matched DATA/ACK loss, with one trial per point on the 8 KiB `small.txt` fixture. It is not the pre-registered 905-attempt full matrix. Consequently, RQ1–RQ6 are currently **inconclusive**. The smoke measurements in `BENCHMARKS.md` must not be used to rank protocols, claim speedups, or make general reliability claims.

## 7. Release boundary

The documentation and release-candidate packaging are prepared, but the final research gate remains open until the complete matrix is executed, analyzed, and reviewed. A video storyboard is provided; no demo recording is included. The project workspace does not publish a GitHub tag or release.
