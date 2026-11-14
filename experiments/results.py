"""Frozen, append-only CSV schema for every attempted experiment run."""

from __future__ import annotations

import csv
import threading
from pathlib import Path
from typing import Any

RESULT_FILE = Path("data/results/experiment_results.csv")

FIELDS = [
    "run_id", "timestamp_utc", "tier", "fault_matrix", "trial", "seed",
    "status", "error", "protocol", "file_name", "file_size", "window",
    "chunk_size", "timeout", "max_retries",
    "data_loss_rate", "data_corruption_rate", "data_delay", "data_duplicate_rate",
    "data_reorder_rate", "data_reorder_delay", "ack_loss_rate", "ack_corruption_rate",
    "ack_delay", "ack_duplicate_rate", "ack_reorder_rate", "ack_reorder_delay",
    "completion_time", "throughput", "retransmissions", "end_retries",
    "total_bytes_sent", "data_packets_sent", "control_packets_sent", "acks_sent", "acks_received",
    "duplicate_acks_received", "retransmitted_packets", "recovery_samples",
    "recovery_time_mean", "recovery_time_max", "duplicate_acks_for_retransmitted_packets",
    "unique_data_received", "unique_data_delivered", "data_arrivals", "duplicate_arrivals",
    "corrupt_discarded", "out_of_window_discarded", "invalid_chunk_discarded", "bytes_received", "received_size",
    "source_sha256", "received_sha256", "hash_verified", "integrity_verified",
    "data_packets_seen", "data_packets_dropped", "data_packets_corrupted",
    "data_packets_duplicated", "data_packets_delayed", "data_reorder_scheduled",
    "data_packets_forwarded", "data_packets_reordered", "data_realized_loss_rate",
    "data_realized_corruption_rate", "data_realized_duplicate_rate", "data_realized_delay_rate",
    "data_realized_reorder_rate", "data_realized_reorder_delivery_rate", "ack_packets_seen", "ack_packets_dropped",
    "ack_packets_corrupted", "ack_packets_duplicated", "ack_packets_delayed",
    "ack_reorder_scheduled", "ack_packets_forwarded", "ack_packets_reordered",
    "ack_realized_loss_rate", "ack_realized_corruption_rate", "ack_realized_duplicate_rate",
    "ack_realized_delay_rate", "ack_realized_reorder_rate", "ack_realized_reorder_delivery_rate",
    "git_commit", "python_version", "os", "machine_name",
]

_write_lock = threading.Lock()


def save_result(result: dict[str, Any], path: str | Path = RESULT_FILE) -> None:
    """Append one attempted run; missing metrics remain empty, never fabricated as zero."""
    unknown = set(result) - set(FIELDS)
    if unknown:
        raise ValueError(f"Result contains fields outside frozen CSV schema: {sorted(unknown)}")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        write_header = not destination.exists() or destination.stat().st_size == 0
        with destination.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="raise")
            if write_header:
                writer.writeheader()
            writer.writerow({field: result.get(field, "") for field in FIELDS})
            handle.flush()


def validate_schema(path: str | Path = RESULT_FILE) -> None:
    """Fail if a result file does not use exactly the frozen field order."""
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
    if header != FIELDS:
        raise ValueError("Experiment CSV header does not match the frozen schema")
