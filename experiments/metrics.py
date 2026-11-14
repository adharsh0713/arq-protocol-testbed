"""Sender-side metrics with consistent packet and recovery accounting."""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any


class Metrics:
    def __init__(self, protocol: str, effective_configuration: dict[str, Any] | None = None):
        self.protocol = protocol
        self.effective_configuration = effective_configuration or {}
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.data_packets_sent = 0
        self.control_packets_sent = 0
        self.packets_received = 0
        self.acks_sent = 0
        self.acks_received = 0
        self.retransmissions = 0
        self.end_retries = 0
        self.total_bytes_sent = 0
        self._first_send_at: dict[int, float] = {}
        self._retransmitted_sequences: set[int] = set()
        self._recovered_sequences: set[int] = set()
        self._duplicate_acked_retransmissions: set[int] = set()
        self._recovery_times: list[float] = []
        self.duplicate_acks_received = 0

    def _ensure_started(self) -> float:
        now = time.perf_counter()
        if self.start_time is None:
            self.start_time = now
        return now

    def start_timer(self) -> None:
        """Compatibility method; production timing starts on first DATA/END send."""
        self._ensure_started()

    def stop_timer(self) -> None:
        self.end_time = time.perf_counter()

    def data_packet_sent(self, sequence: int | None = None, encoded_bytes: int = 0) -> None:
        now = self._ensure_started()
        self.data_packets_sent += 1
        self.total_bytes_sent += encoded_bytes
        if sequence is not None:
            self._first_send_at.setdefault(sequence, now)

    def control_packet_sent(self, encoded_bytes: int = 0, *, retransmission: bool = False) -> None:
        self._ensure_started()
        self.control_packets_sent += 1
        self.total_bytes_sent += encoded_bytes
        if retransmission:
            self.end_retries += 1

    def packet_received(self) -> None:
        self.packets_received += 1

    def ack_sent(self) -> None:
        self.acks_sent += 1

    def _record_recovery(self, sequence: int, now: float) -> None:
        if sequence in self._retransmitted_sequences and sequence not in self._recovered_sequences:
            first_sent = self._first_send_at.get(sequence)
            if first_sent is not None:
                self._recovery_times.append(max(0.0, now - first_sent))
                self._recovered_sequences.add(sequence)

    def ack_received(self, sequence: int | None = None) -> None:
        self.acks_received += 1
        if sequence is not None:
            self._record_recovery(sequence, time.perf_counter())

    def cumulative_ack_received(self, first_sequence: int, last_sequence: int) -> None:
        """Record one cumulative ACK while resolving recovery for every covered packet."""
        self.acks_received += 1
        now = time.perf_counter()
        for sequence in range(first_sequence, last_sequence + 1):
            self._record_recovery(sequence, now)

    def duplicate_ack_received(self, sequence: int | None = None) -> None:
        self.duplicate_acks_received += 1
        if sequence is not None and sequence in self._retransmitted_sequences:
            self._duplicate_acked_retransmissions.add(sequence)

    def retransmission(self, sequence: int | None = None) -> None:
        self.retransmissions += 1
        if sequence is not None:
            self._retransmitted_sequences.add(sequence)

    def completion_time(self) -> float:
        if self.start_time is None or self.end_time is None:
            return 0.0
        return max(0.0, self.end_time - self.start_time)

    def throughput(self, file_size: int) -> float:
        duration = self.completion_time()
        return file_size / duration if duration > 0 else 0.0

    def report(self, file_size: int) -> dict[str, Any]:
        recovery_mean = statistics.fmean(self._recovery_times) if self._recovery_times else None
        recovery_max = max(self._recovery_times) if self._recovery_times else None
        return {
            "protocol": self.protocol,
            "effective_configuration": self.effective_configuration,
            "file_size": file_size,
            "data_packets_sent": self.data_packets_sent,
            "control_packets_sent": self.control_packets_sent,
            "packets_received": self.packets_received,
            "acks_sent": self.acks_sent,
            "acks_received": self.acks_received,
            "duplicate_acks_received": self.duplicate_acks_received,
            "retransmissions": self.retransmissions,
            "end_retries": self.end_retries,
            "total_bytes_sent": self.total_bytes_sent,
            "retransmitted_packets": len(self._retransmitted_sequences),
            "recovery_samples": len(self._recovery_times),
            "recovery_time_mean": recovery_mean,
            "recovery_time_max": recovery_max,
            "duplicate_acks_for_retransmitted_packets": len(self._duplicate_acked_retransmissions),
            "completion_time": self.completion_time(),
            "throughput": self.throughput(file_size),
        }

    def save_json(self, filename: str | os.PathLike[str], file_size: int) -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(f"{path}.tmp")
        temporary.write_text(json.dumps(self.report(file_size), indent=2), encoding="utf-8")
        os.replace(temporary, path)
