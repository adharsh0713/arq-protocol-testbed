# Reliable UDP Experimental Protocol Specification

**Version:** Experimental v1 specification (Milestones 1–3)  
**Status:** The protocol is an educational ARQ testbed, not TCP, QUIC, or a production transport.

## 1. Packet format

All header fields are unsigned and big-endian. The fixed header is 11 bytes and uses Python's `struct` format `!IBHI`.

```text
Byte offset  Size  Field             Meaning
-----------  ----  ----------------  ---------------------------------
0            4     sequence          Unsigned 32-bit sequence number
4            1     packet_type       DATA=0, ACK=1, END=2
5            2     payload_length    Unsigned 16-bit payload byte count
7            4     crc32             CRC32 over sequence/type/length/payload
11           N     payload           N bytes, where N = payload_length
```

```text
+----------------------+------------+------------------+--------------------+---------+
| sequence (4 bytes)   | type (1)   | length (2)       | CRC32 (4)          | payload |
+----------------------+------------+------------------+--------------------+---------+
|<------------------------------ 11-byte header ----------------------->|<- N bytes ->|
```

The CRC input is the concatenation of the first seven semantic header bytes (`sequence`, `type`, and `length`) and the payload. The CRC field itself is excluded. CRC32 is computed with `zlib.crc32(data) & 0xffffffff`.

## 2. Packet types and field rules

| Type | Value | Payload | Sequence meaning |
|---|---:|---|---|
| DATA | 0 | Non-empty; at most `CHUNK_SIZE` bytes and never above `MAX_PAYLOAD` | Zero-based data-chunk index |
| ACK | 1 | Must be empty | Acknowledged DATA sequence, or END sequence for final confirmation |
| END | 2 | Must be empty | Number of DATA chunks / next expected sequence |

`MAX_PAYLOAD` is 60,000 bytes. The default `CHUNK_SIZE` is 4,096 bytes and must be between 1 and `MAX_PAYLOAD`; header plus payload must remain under the UDP datagram limit.

The sender splits a file into full `CHUNK_SIZE` chunks and at most one shorter final chunk. An empty file has no DATA packets and sends END with sequence 0. When the runner supplies `EXPECTED_FILE_SIZE`, the receiver validates the sequence-specific expected chunk length and rejects DATA packets outside the expected chunk count. When no source size is supplied, the receiver can enforce only non-empty payloads no larger than the configured chunk size; final size integrity cannot be established from the packet stream alone.

## 3. Sequence space

Sequence values are unsigned 32-bit integers from 0 through `2^32 - 1`. Sequence numbers do not wrap. The sender refuses a file whose chunk count and following END sequence cannot fit in this range.

The maximum DATA packet count is `2^32 - 1`; the largest DATA sequence in that transfer is `2^32 - 2`, and END uses sequence `2^32 - 1`. With 4,096-byte chunks, the maximum accepted source size is `4096 × (2^32 - 1)` bytes (approximately 16 TiB).

## 4. ACK semantics by protocol

### Stop-and-Wait

- At most one DATA packet is outstanding.
- ACK `n` confirms DATA sequence `n` was accepted in order and written once.
- Duplicate DATA below the receiver's next expected sequence is re-ACKed but not written again.
- Future DATA is not acknowledged.
- A timeout retransmits the current DATA packet. A monotonic deadline is not extended by malformed, foreign, or stale datagrams.

### Go-Back-N

- The sender maintains the outstanding interval `[base, next_seq)` and never exceeds its configured window.
- ACK `n` is cumulative: every DATA sequence up to and including `n` has arrived in order.
- The receiver discards out-of-order DATA and re-ACKs the last in-order sequence when one exists.
- The sender slides the window as each valid cumulative ACK advances `base`.
- One timer is associated with `base`; it restarts when `base` advances. On expiry, the sender retransmits the outstanding suffix beginning at `base`.

### Selective Repeat

- The sender maintains independent outstanding-packet timers and removes packet state after ACK.
- The receiver accepts and buffers DATA only in `[expected_sequence, expected_sequence + window_size)`.
- ACK `n` confirms only DATA sequence `n` was received or buffered.
- DATA below `expected_sequence` is already delivered and may be re-ACKed.
- DATA at or above the upper receive-window boundary is ignored and must not be ACKed.
- Buffered data is written in order once the gap at `expected_sequence` is filled.

## 5. END handshake

After all DATA packets are acknowledged, the sender transmits END with sequence equal to the number of DATA chunks. END has an empty payload and is subject to the DATA-direction proxy faults.

The receiver accepts END only if its next expected sequence equals the END sequence and the Selective Repeat receive buffer is empty. If source size/hash expectations are configured, integrity checks happen before final publication and before the END ACK is sent.

On success:

1. Flush and close `<output>.part`.
2. Compare expected and received byte count and SHA-256 when expectations are supplied.
3. Atomically rename the `.part` file to the final output path.
4. Send ACK with the END sequence.
5. Linger for a bounded interval and re-ACK duplicate END packets, allowing recovery if the first END ACK was lost.

If END is premature or integrity verification fails, the receiver does not confirm successful completion and removes the partial file. The linger duration is derived from the configured timeout, retry count, and a margin rather than a fixed magic constant.

## 6. Retry and failure rules

`MAX_RETRIES` is the maximum number of retransmissions after the initial send. When the retry budget is exhausted, the sender raises `TimeoutError`. Stop-and-Wait retries the current packet; Go-Back-N retries the outstanding suffix; Selective Repeat retries only expired outstanding packets. END retries are measured separately from DATA retransmissions.

The receiver has an idle timeout and writes an explicit terminal status to its metrics report. Failed/aborted transfers remove `.part` output and release buffered data.

## 7. Integrity and security

CRC32 is for accidental packet corruption detection, not authenticity. SHA-256 and byte-count checks validate the reconstructed file against source metadata supplied by the experiment runner. No encryption, authentication, replay protection across sessions, congestion control, adaptive RTO, or handshake-based peer authentication is implemented.

## 8. Scope statement

This is an experimental ARQ protocol over UDP for studying Stop-and-Wait, Go-Back-N, and Selective Repeat under controlled faults. It is not TCP and is not a secure, congestion-controlled, interoperable, or production transport.
