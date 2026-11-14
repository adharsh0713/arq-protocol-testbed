"""Testable UDP receiver for the experimental ARQ protocols."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from pathlib import Path
from typing import Any

import config
from config import RuntimeConfig
from protocol.packet import ACK, DATA, END, Packet

BUFFER_SIZE = 65_535


def _bind_udp_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
    try:
        if exclusive is not None:
            sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        sock.bind((host, port))
        return sock
    except Exception:
        sock.close()
        raise


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Receiver:
    """One-transfer receiver with injectable socket and filesystem paths.

    The final output path is never opened directly. Bytes are written to a
    sibling ``.part`` file and published with ``os.replace`` only after a valid
    END and optional source size/hash checks.
    """

    def __init__(
        self,
        settings: RuntimeConfig | None = None,
        *,
        sock: Any | None = None,
        output_file: str | os.PathLike[str] | None = None,
        metrics_path: str | os.PathLike[str] | None = None,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
        idle_timeout: float | None = None,
        end_ack_wait: float | None = None,
        quiet: bool = True,
    ) -> None:
        self.settings = settings or config.load_config()
        self.protocol = self.settings.protocol
        self.window_size = self.settings.window_size
        self.output_file = Path(output_file or self.settings.output_file)
        self.part_file = Path(f"{self.output_file}.part")
        self.metrics_path = Path(
            metrics_path
            or os.environ.get("RECEIVER_METRICS_PATH", "data/results/receiver_metrics.json")
        )
        if expected_size is not None and (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise ValueError("expected_size must be a non-negative integer")
        if expected_sha256 is not None:
            normalized_hash = expected_sha256.lower()
            if len(normalized_hash) != 64 or any(
                character not in "0123456789abcdef" for character in normalized_hash
            ):
                raise ValueError("expected_sha256 must be a 64-character hexadecimal digest")
            expected_sha256 = normalized_hash
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        margin = max(0.1, self.settings.timeout)
        self.idle_timeout = (
            self.settings.receiver_idle_timeout
            if idle_timeout is None else idle_timeout
        )
        self.end_ack_wait = (
            self.settings.timeout * (self.settings.max_retries + 1) + margin
            if end_ack_wait is None else end_ack_wait
        )
        if self.idle_timeout <= 0 or self.end_ack_wait <= 0:
            raise ValueError("Receiver timeouts must be positive")
        self.quiet = quiet
        self.sock = sock
        self._owns_socket = sock is None
        self.expected_sequence = 0
        self.receive_buffer: dict[int, bytes] = {}
        self._seen_sequences: set[int] = set()
        self._sender_address: tuple[str, int] | None = None
        self._file = None
        self._started_at = time.monotonic()
        self._stats: dict[str, Any] = {
            "protocol": self.protocol,
            "effective_configuration": self.settings.to_dict(),
            "packets_seen": 0,
            "data_arrivals": 0,
            "unique_data_received": 0,
            "unique_data_delivered": 0,
            "duplicate_arrivals": 0,
            "corrupt_discarded": 0,
            "out_of_window_discarded": 0,
            "invalid_chunk_discarded": 0,
            "acks_sent": 0,
            "bytes_received": 0,
            "expected_size": self.expected_size,
            "source_sha256": self.expected_sha256,
            "received_size": None,
            "received_sha256": None,
            "integrity_verified": None,
            "status": "running",
            "error": None,
        }

    def _log(self, message: str) -> None:
        if not self.quiet:
            print(message, flush=True)

    def _open(self) -> None:
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.part_file.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.part_file, "wb")
        if self.sock is None:
            self.sock = _bind_udp_socket(
                self.settings.receiver_host,
                self.settings.receiver_port,
            )
        if self._owns_socket:
            print(
                f"READY receiver {self.settings.receiver_host}:"
                f"{self.settings.receiver_port}",
                flush=True,
            )
        self._log(
            f"Receiver ready on {self.settings.receiver_host}:{self.settings.receiver_port}; "
            f"protocol={self.protocol}, window={self.window_size}"
        )

    def _send_ack(self, sequence: int, address: tuple[str, int]) -> None:
        packet = Packet(sequence, ACK, b"")
        self.sock.sendto(packet.encode(), address)
        self._stats["acks_sent"] += 1

    def _accept_sender(self, address: tuple[str, int]) -> bool:
        if self._sender_address is None:
            self._sender_address = address
            return True
        return address == self._sender_address

    def _write_payload(self, payload: bytes) -> None:
        self._file.write(payload)
        self._stats["bytes_received"] += len(payload)
        self._stats["unique_data_delivered"] += 1

    def _valid_data_chunk(self, packet: Packet) -> bool:
        """Validate sender chunk boundaries when the expected source size is known."""
        payload_length = len(packet.payload)
        if not 1 <= payload_length <= self.settings.chunk_size:
            return False
        if self.expected_size is None:
            return True
        chunk_size = self.settings.chunk_size
        expected_packets = (self.expected_size + chunk_size - 1) // chunk_size
        if packet.sequence >= expected_packets:
            return False
        expected_length = min(chunk_size, self.expected_size - packet.sequence * chunk_size)
        return payload_length == expected_length

    def _handle_data(self, packet: Packet, address: tuple[str, int]) -> None:
        sequence = packet.sequence

        if self.protocol == "stop_wait":
            if sequence == self.expected_sequence:
                self._seen_sequences.add(sequence)
                self._stats["unique_data_received"] += 1
                self._write_payload(packet.payload)
                self.expected_sequence += 1
                self._send_ack(sequence, address)
            elif sequence < self.expected_sequence:
                self._stats["duplicate_arrivals"] += 1
                self._send_ack(sequence, address)
            else:
                self._stats["out_of_window_discarded"] += 1
            return

        if self.protocol == "go_back_n":
            if sequence == self.expected_sequence:
                self._seen_sequences.add(sequence)
                self._stats["unique_data_received"] += 1
                self._write_payload(packet.payload)
                self.expected_sequence += 1
                self._send_ack(sequence, address)
            elif sequence < self.expected_sequence:
                self._stats["duplicate_arrivals"] += 1
                if self.expected_sequence > 0:
                    self._send_ack(self.expected_sequence - 1, address)
            else:
                self._stats["out_of_window_discarded"] += 1
                if self.expected_sequence > 0:
                    self._send_ack(self.expected_sequence - 1, address)
            return

        # Selective Repeat: acknowledge only data in the receive window or
        # already delivered data. Never ACK data beyond the window.
        if sequence < self.expected_sequence:
            self._stats["duplicate_arrivals"] += 1
            self._send_ack(sequence, address)
            return
        if sequence >= self.expected_sequence + self.window_size:
            self._stats["out_of_window_discarded"] += 1
            return

        if sequence in self.receive_buffer:
            self._stats["duplicate_arrivals"] += 1
        else:
            self.receive_buffer[sequence] = packet.payload
            self._seen_sequences.add(sequence)
            self._stats["unique_data_received"] += 1

        self._send_ack(sequence, address)
        while self.expected_sequence in self.receive_buffer:
            payload = self.receive_buffer.pop(self.expected_sequence)
            self._write_payload(payload)
            self.expected_sequence += 1

    def _finalize(self) -> bool:
        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()
        self._file = None

        received_size = self.part_file.stat().st_size
        received_hash = sha256_file(self.part_file)
        self._stats["received_size"] = received_size
        self._stats["received_sha256"] = received_hash

        size_ok = self.expected_size is None or received_size == self.expected_size
        hash_ok = self.expected_sha256 is None or received_hash == self.expected_sha256
        if not size_ok or not hash_ok:
            self._stats["integrity_verified"] = False
            self._stats["status"] = "integrity_failed"
            failures = []
            if not size_ok:
                failures.append(
                    f"size mismatch: expected {self.expected_size}, received {received_size}"
                )
            if not hash_ok:
                failures.append("SHA-256 mismatch")
            self._stats["error"] = "; ".join(failures)
            self._remove_partial()
            return False

        self._stats["integrity_verified"] = (
            True if self.expected_size is not None and self.expected_sha256 is not None else None
        )
        os.replace(self.part_file, self.output_file)
        self._stats["status"] = "completed"
        return True

    def _remove_partial(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None
        try:
            self.part_file.unlink(missing_ok=True)
        except OSError:
            pass

    def _write_metrics(self) -> None:
        self._stats.update({
            "expected_sequence": self.expected_sequence,
            "receive_buffer_remaining": len(self.receive_buffer),
            "elapsed_seconds": round(time.monotonic() - self._started_at, 6),
            "output_file": str(self.output_file),
        })
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(f"{self.metrics_path}.tmp")
        temporary.write_text(json.dumps(self._stats, indent=2), encoding="utf-8")
        os.replace(temporary, self.metrics_path)

    def _linger_for_end_retries(self, end_sequence: int) -> None:
        deadline = time.monotonic() + self.end_ack_wait
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.sock.settimeout(remaining)
            try:
                data, address = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                return
            except ConnectionResetError:
                continue

            try:
                packet = Packet.decode(data)
            except ValueError:
                self._stats["corrupt_discarded"] += 1
                continue
            if (
                packet.packet_type == END
                and packet.sequence == end_sequence
                and self._accept_sender(address)
            ):
                self._send_ack(end_sequence, address)

    def run(self) -> dict[str, Any]:
        """Receive exactly one transfer and return its terminal metrics."""
        try:
            self._open()
            idle_deadline = time.monotonic() + self.idle_timeout
            while True:
                remaining = idle_deadline - time.monotonic()
                if remaining <= 0:
                    self._stats["status"] = "idle_timeout"
                    self._stats["error"] = (
                        f"No valid datagram received for {self.idle_timeout:.3f}s"
                    )
                    break
                self.sock.settimeout(remaining)
                try:
                    data, address = self.sock.recvfrom(BUFFER_SIZE)
                except socket.timeout:
                    self._stats["status"] = "idle_timeout"
                    self._stats["error"] = (
                        f"No valid datagram received for {self.idle_timeout:.3f}s"
                    )
                    break
                except ConnectionResetError:
                    continue

                self._stats["packets_seen"] += 1
                try:
                    packet = Packet.decode(data)
                except ValueError:
                    self._stats["corrupt_discarded"] += 1
                    continue

                if packet.packet_type not in (DATA, END):
                    continue
                if not self._accept_sender(address):
                    self._stats["out_of_window_discarded"] += 1
                    continue
                idle_deadline = time.monotonic() + self.idle_timeout

                if packet.packet_type == DATA:
                    self._stats["data_arrivals"] += 1
                    if not self._valid_data_chunk(packet):
                        self._stats["invalid_chunk_discarded"] += 1
                        continue
                    self._handle_data(packet, address)
                    continue

                if packet.packet_type == END:
                    complete = (
                        packet.sequence == self.expected_sequence
                        and not self.receive_buffer
                    )
                    if not complete:
                        self._log(
                            f"Premature END rejected: sequence={packet.sequence}, "
                            f"expected={self.expected_sequence}"
                        )
                        continue

                    if not self._finalize():
                        break
                    self._send_ack(packet.sequence, address)
                    self._linger_for_end_retries(packet.sequence)
                    break

            if self._stats["status"] == "running":
                self._stats["status"] = "completed"
        except Exception as error:
            self._stats["status"] = "receiver_error"
            self._stats["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            if self._stats["status"] != "completed":
                self._stats["aborted_buffer_packets"] = len(self.receive_buffer)
                self.receive_buffer.clear()
            if self._file is not None or self._stats["status"] != "completed":
                self._remove_partial()
            self._write_metrics()
            if self._owns_socket and self.sock is not None:
                self.sock.close()
        return dict(self._stats)


def main() -> int:
    expected_size = os.environ.get("EXPECTED_FILE_SIZE")
    receiver = Receiver(
        expected_size=int(expected_size) if expected_size is not None else None,
        expected_sha256=os.environ.get("EXPECTED_FILE_SHA256"),
        metrics_path=os.environ.get(
            "RECEIVER_METRICS_PATH", "data/results/receiver_metrics.json"
        ),
        quiet=os.environ.get("QUIET", "1") == "1",
    )
    result = receiver.run()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
