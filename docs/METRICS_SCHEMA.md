# Metrics and Results CSV Schema

The canonical ordered CSV header is `experiments/results.py::FIELDS`. Do not reorder, rename, remove, or repurpose a column after starting the full matrix. Add new metrics by versioning the schema and documenting the change before a new benchmark series.

## Run identity and environment

| Field | Meaning |
|---|---|
| `run_id` | Unique run directory and CSV identity |
| `timestamp_utc` | Run start timestamp in UTC |
| `tier`, `fault_matrix`, `trial` | Tier and matrix point/repetition |
| `seed` | Per-run deterministic seed |
| `status`, `error` | `success` only after all completion/integrity checks; otherwise `failed` and an error description |
| `protocol`, `file_name`, `file_size` | Protocol and source file metadata |
| `window`, `chunk_size`, `timeout`, `max_retries` | Protocol parameters used by the attempt |
| `git_commit`, `python_version`, `os`, `machine_name` | Execution environment metadata |

## Configured faults

`data_*` parameters apply to sender-to-receiver DATA/END direction. `ack_*` parameters apply to receiver-to-sender ACK direction.

| Fields | Meaning |
|---|---|
| `*_loss_rate` | Probability an incoming datagram is dropped |
| `*_corruption_rate` | Probability the incoming datagram is bit-corrupted |
| `*_delay` | Fixed base delay in seconds |
| `*_duplicate_rate` | Probability the incoming datagram produces a second copy |
| `*_reorder_rate` | Probability an incoming datagram receives an additional hold |
| `*_reorder_delay` | Additional hold in seconds for a selected reorder packet |

## Sender metrics

| Field | Definition |
|---|---|
| `completion_time` | First DATA send to END ACK using `time.perf_counter()`; empty files start at first END send |
| `throughput` | Source bytes / completion time; blank for failed/unverified attempts |
| `retransmissions` | DATA retransmission sends; END retries excluded |
| `end_retries` | Retransmitted END packets |
| `total_bytes_sent` | Encoded bytes sent for DATA and END, headers and retries included; ACK bytes excluded |
| `data_packets_sent` | All DATA transmissions, including retries |
| `control_packets_sent` | All END transmissions |
| `acks_received` | Valid ACK datagrams accepted by the sender |
| `duplicate_acks_received` | Duplicate/stale ACK datagrams observed by sender logic |
| `retransmitted_packets` | Unique DATA sequences retransmitted at least once |
| `recovery_samples` | Number of retransmitted sequences subsequently ACKed |
| `recovery_time_mean`, `recovery_time_max` | First-send-to-successful-ACK latency for recovered retransmitted packets |
| `duplicate_acks_for_retransmitted_packets` | Unique retransmitted sequences observed with a subsequent duplicate ACK |

## Receiver metrics

| Field | Definition |
|---|---|
| `unique_data_received` | Unique DATA sequence payloads accepted (including SR buffered packets) |
| `unique_data_delivered` | Unique DATA payloads written in order to the partial file |
| `data_arrivals` | Valid decoded DATA arrivals, including duplicates |
| `duplicate_arrivals` | Duplicate DATA packets observed |
| `corrupt_discarded` | Malformed, truncated or CRC-invalid datagrams discarded |
| `out_of_window_discarded` | DATA rejected because it is outside the receiver's valid sequence/window range |
| `invalid_chunk_discarded` | DATA rejected because its length does not match the configured chunk size and expected final-chunk boundary |
| `bytes_received` | Payload bytes written to the partial file |
| `received_size` | Final received file size |
| `source_sha256`, `received_sha256` | Expected source digest and computed received digest |
| `hash_verified` | Runner-level result requiring both byte-count and SHA-256 equality |
| `integrity_verified` | Receiver-level integrity result; `null` if source expectations were not provided |
| `acks_sent` | Receiver ACK transmissions |

## Proxy counts and realized rates

For each direction, the CSV has `data_*` or `ack_*` count/rate fields. Counts:

- `packets_seen`: incoming original datagrams observed by the injector.
- `packets_dropped`: incoming datagrams intentionally dropped.
- `packets_corrupted`: incoming datagrams modified before forwarding.
- `packets_duplicated`: incoming datagrams for which an additional copy was scheduled.
- `packets_delayed`: incoming datagrams assigned a nonzero base or reorder delay.
- `reorder_scheduled`: incoming datagrams assigned the additional reorder hold.
- `packets_forwarded`: copies actually delivered to the destination.
- `packets_reordered`: delivered copies observed arriving behind a later original arrival order.

Realized rates use the corresponding incoming-packet denominator, except `*_realized_reorder_delivery_rate`, which is out-of-order delivered copies divided by forwarded copies. `*_realized_reorder_rate` is the rate at which incoming packets were selected for additional hold. Both are retained because scheduling an extra hold does not guarantee an overtaking event.

## Configured-versus-realized fault comparison output

`fault_rate_comparison.csv` is produced beside the aggregate summary. It contains one row per available fault-matrix, direction, and configured setting, with these columns:

| Field | Meaning |
|---|---|
| `fault_matrix` | Isolated fault family (`loss`, `corruption`, `duplication`, `delay`, or `reordering`) |
| `direction` | `data` or `ack`; directions are never pooled |
| `configured_value` | Configured probability or base delay value |
| `configured_unit` | `probability` for event probabilities; `seconds` for configured base delay |
| `observed_runs`, `attempted_runs` | Runs with realized telemetry and all attempts in the group |
| `realized_event_rate_mean`, `median`, `q1`, `q3` | Distribution of realized event fractions across runs |

For the delay matrix, the configured quantity is a duration in seconds while the realized quantity is the fraction of incoming packets assigned non-zero delay. They are deliberately labelled with different units and must not be subtracted or treated as measurements of the same quantity. Reordering also retains both `*_realized_reorder_rate` (selected for extra hold) and `*_realized_reorder_delivery_rate` (observed arriving out of order).

## Missing values and failed attempts

A value is blank when a process did not produce it or the metric is undefined. Do not replace missing process metrics with zero. A failed run remains in the CSV with `status=failed`, error text, the settings known before launch, and whatever partial process metrics were successfully flushed. `throughput` is blank unless the final transfer is verified.

## Aggregated summary

`experiments/analysis.py` groups rows by tier, matrix, protocol, file, window, chunk size, timeout, and configured fault settings. It reports `attempt_count`, `success_count`, `success_rate`, and median/Q1/Q3/IQR for completion time, throughput and retransmissions over verified successes only. This keeps failure accounting separate from performance distributions.
