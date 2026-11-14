# Protocol and Architecture Diagrams

These diagrams describe the implemented experimental protocol. The sequence diagrams show a representative lost DATA packet and recovery; they are explanatory traces, not a claim about a measured benchmark run.

## 1. Packet format

```text
Offset      0              4       5               7                   11
            |--------------|-------|---------------|-------------------|------>
Field       sequence       type    payload_length  CRC32               payload
Width       4 bytes        1 byte  2 bytes         4 bytes             N bytes
            unsigned u32   u8      unsigned u16    unsigned u32        bytes

+----------------------+--------+----------------+--------------------+-------------+
| sequence (4 bytes)   | type   | length (2 B)   | CRC32 (4 bytes)    | payload (N) |
+----------------------+--------+----------------+--------------------+-------------+
|<----------------------------- fixed 11-byte header ---------------->|<-- data -->|
```

All fields are big-endian. Packet types are DATA=0, ACK=1, END=2. The CRC input is sequence + type + length + payload; the CRC field is not included in its own checksum.

## 2. Process architecture

```mermaid
flowchart LR
    F[Source file] --> S[Sender / ARQ strategy]
    S -->|DATA, END| P[UDP fault proxy]
    P --> DI[Seeded DATA injector]
    DI --> Q[Scheduled delivery heap]
    Q --> R[Receiver]
    R -->|ACK| P
    P --> AI[Seeded ACK injector]
    AI --> S
    R --> T[.part file]
    T -->|END + size + SHA-256 pass| O[Atomic final output]
    E[Experiment runner] --> S
    E --> P
    E --> R
    E --> C[CSV / run metrics]
    C --> A[Analysis / plots]
```

## 3. Stop-and-Wait — DATA loss and timeout recovery

```mermaid
sequenceDiagram
    participant S as Sender
    participant P as Fault proxy
    participant R as Receiver
    S->>P: DATA(seq=0)
    P->>R: DATA(seq=0)
    R-->>P: ACK(0)
    P-->>S: ACK(0)
    S->>P: DATA(seq=1)
    Note over P,R: DATA(seq=1) is dropped
    S->>S: Deadline expires
    S->>P: Retransmit DATA(seq=1)
    P->>R: DATA(seq=1)
    R-->>P: ACK(1)
    P-->>S: ACK(1)
    S->>P: DATA(seq=2)
```

## 4. Go-Back-N — lost packet and suffix retransmission

```mermaid
sequenceDiagram
    participant S as Sender
    participant P as Fault proxy
    participant R as Receiver
    S->>P: DATA(0), DATA(1), DATA(2)
    P->>R: DATA(0)
    Note over P,R: DATA(1) is dropped
    P->>R: DATA(2)
    R-->>P: ACK(0)
    P-->>S: ACK(0)
    R->>R: Discard out-of-order DATA(2)
    S->>S: Base timer expires at seq=1
    S->>P: Retransmit DATA(1), DATA(2)
    P->>R: DATA(1)
    R-->>P: ACK(1)
    P-->>S: ACK(1)
    P->>R: DATA(2)
    R-->>P: ACK(2)
    P-->>S: ACK(2)
```

## 5. Selective Repeat — buffer out-of-order data and recover one packet

```mermaid
sequenceDiagram
    participant S as Sender
    participant P as Fault proxy
    participant R as Receiver
    S->>P: DATA(0), DATA(1), DATA(2)
    P->>R: DATA(0)
    Note over P,R: DATA(1) is dropped
    P->>R: DATA(2)
    R-->>P: ACK(0)
    P-->>S: ACK(0)
    R->>R: Buffer DATA(2)
    R-->>P: ACK(2)
    P-->>S: ACK(2)
    S->>S: Timer for seq=1 expires
    S->>P: Retransmit DATA(1)
    P->>R: DATA(1)
    R->>R: Write seq=1 then buffered seq=2 in order
    R-->>P: ACK(1)
    P-->>S: ACK(1)
```

## 6. Diagram interpretation

- Go-Back-N uses a cumulative ACK and discards out-of-order DATA; a gap can cause retransmission of the outstanding suffix.
- Selective Repeat ACKs valid in-window packets individually and buffers them until the missing earlier sequence arrives.
- Stop-and-Wait has only one in-flight DATA packet, so there is no multi-packet receive reordering within its sender window.
- The proxy's scheduled queue implements controlled fault injection; it is not a physical router or bandwidth-limited network.
