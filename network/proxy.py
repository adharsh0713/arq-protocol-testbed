"""Bidirectional UDP fault-injection proxy with non-blocking delay scheduling."""

from __future__ import annotations

import heapq
import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from config import RuntimeConfig
from network.fault_injector import FaultInjector, ScheduledCopy
from protocol.packet import ACK, DATA, END, Packet

BUFFER_SIZE = 65_535
SHUTDOWN_DATAGRAM = b"\x00RELIABLE_UDP_PROXY_SHUTDOWN\x00"


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


@dataclass(frozen=True)
class Delivery:
    direction: str
    data: bytes
    destination: tuple[str, int]
    arrival_order: int


class FaultInjectionProxy:
    """Route sender DATA/END and receiver ACK datagrams through two injectors.

    Delayed datagrams are held in a min-heap and released when due. The receive
    loop wakes at the next delivery deadline, so one delayed packet never
    serializes traffic behind it.
    """

    def __init__(
        self,
        settings: RuntimeConfig | None = None,
        *,
        sock: Any | None = None,
        stats_path: str | os.PathLike[str] | None = None,
        quiet: bool = True,
        stats_flush_interval: int = 100,
    ) -> None:
        self.settings = settings or config.load_config()
        self.sock = sock or _bind_udp_socket(
            self.settings.proxy_host,
            self.settings.proxy_port,
        )
        self._owns_socket = sock is None
        self.receiver_address = (
            self.settings.receiver_ip,
            self.settings.receiver_port,
        )
        self.sender_address: tuple[str, int] | None = None
        self.stats_path = Path(
            stats_path
            or os.environ.get("PROXY_STATS_PATH", "data/results/proxy_metrics.json")
        )
        self.quiet = quiet
        self.stats_flush_interval = max(1, stats_flush_interval)
        self._processed_since_flush = 0
        self._queue: list[tuple[float, int, Delivery]] = []
        self._event_id = 0
        self._arrival_order = {"data": 0, "ack": 0}
        self._max_delivered_order = {"data": 0, "ack": 0}
        self.stopping = False
        self.invalid_datagrams = 0
        self.unexpected_senders = 0

        seed = self.settings.seed
        self.injectors = {
            "data": FaultInjector(
                loss_rate=self.settings.data_loss_rate,
                corruption_rate=self.settings.data_corruption_rate,
                delay=self.settings.data_delay,
                duplicate_rate=self.settings.data_duplicate_rate,
                reorder_rate=self.settings.data_reorder_rate,
                reorder_delay=self.settings.data_reorder_delay,
                seed=seed,
            ),
            "ack": FaultInjector(
                loss_rate=self.settings.ack_loss_rate,
                corruption_rate=self.settings.ack_corruption_rate,
                delay=self.settings.ack_delay,
                duplicate_rate=self.settings.ack_duplicate_rate,
                reorder_rate=self.settings.ack_reorder_rate,
                reorder_delay=self.settings.ack_reorder_delay,
                seed=seed ^ 0xA5A5A5A5,
            ),
        }
        self._effective_configuration = self.settings.to_dict()
        self._log(
            f"Proxy ready on {self.settings.proxy_host}:{self.settings.proxy_port}; "
            f"receiver={self.receiver_address}"
        )
        self._write_stats()

    def _log(self, message: str) -> None:
        if not self.quiet:
            print(message, flush=True)

    def _is_local(self, address: tuple[str, int]) -> bool:
        return address[0] in {"127.0.0.1", "::1"}

    def _handle_datagram(
        self,
        data: bytes,
        address: tuple[str, int],
        *,
        now: float | None = None,
    ) -> None:
        if data == SHUTDOWN_DATAGRAM and self._is_local(address):
            self.stopping = True
            self._write_stats()
            return

        try:
            packet = Packet.decode(data)
        except ValueError:
            self.invalid_datagrams += 1
            self._periodic_flush()
            return

        if packet.packet_type in (DATA, END):
            direction = "data"
            if self.sender_address is None:
                self.sender_address = address
            elif address != self.sender_address:
                self.unexpected_senders += 1
                self._periodic_flush()
                return
            destination = self.receiver_address
        elif packet.packet_type == ACK:
            direction = "ack"
            if address != self.receiver_address:
                self.unexpected_senders += 1
                self._periodic_flush()
                return
            if self.sender_address is None:
                self._periodic_flush()
                return
            destination = self.sender_address
        else:  # Defensive: Packet currently validates this before returning.
            self.invalid_datagrams += 1
            self._periodic_flush()
            return

        self._arrival_order[direction] += 1
        order = self._arrival_order[direction]
        injector = self.injectors[direction]
        copies = injector.inject(data)
        timestamp = time.monotonic() if now is None else now

        for copy in copies:
            delivery = Delivery(direction, copy.data, destination, order)
            self._event_id += 1
            heapq.heappush(
                self._queue,
                (timestamp + copy.delay, self._event_id, delivery),
            )
        self._periodic_flush()

    def _send_delivery(self, delivery: Delivery) -> None:
        self.sock.sendto(delivery.data, delivery.destination)
        injector = self.injectors[delivery.direction]
        injector.record_forwarded()
        previous_max = self._max_delivered_order[delivery.direction]
        if delivery.arrival_order < previous_max:
            injector.record_reordered()
        self._max_delivered_order[delivery.direction] = max(
            previous_max,
            delivery.arrival_order,
        )

    def flush_due(self, *, now: float | None = None) -> int:
        """Forward all currently due copies and return the number sent."""
        timestamp = time.monotonic() if now is None else now
        sent = 0
        while self._queue and self._queue[0][0] <= timestamp:
            _, _, delivery = heapq.heappop(self._queue)
            self._send_delivery(delivery)
            sent += 1
        if sent:
            self._periodic_flush()
        return sent

    def _periodic_flush(self) -> None:
        self._processed_since_flush += 1
        if self._processed_since_flush >= self.stats_flush_interval:
            self._write_stats()
            self._processed_since_flush = 0

    def _write_stats(self) -> None:
        report = {
            "effective_configuration": self._effective_configuration,
            "seed": self.settings.seed,
            "receiver_address": list(self.receiver_address),
            "sender_address": list(self.sender_address) if self.sender_address else None,
            "directions": {
                direction: self.injectors[direction].report()
                for direction in ("data", "ack")
            },
            "invalid_datagrams": self.invalid_datagrams,
            "unexpected_senders": self.unexpected_senders,
            "pending_deliveries": len(self._queue),
            "shutdown_requested": self.stopping,
        }
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(f"{self.stats_path}.tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        os.replace(temporary, self.stats_path)

    def _next_timeout(self) -> float | None:
        if not self._queue:
            return None
        return max(0.0, self._queue[0][0] - time.monotonic())

    def run(self) -> None:
        """Run until a local shutdown datagram arrives and queued work drains."""
        try:
            while True:
                self.flush_due()
                if self.stopping and not self._queue:
                    break
                timeout = self._next_timeout()
                self.sock.settimeout(timeout)
                try:
                    data, address = self.sock.recvfrom(BUFFER_SIZE)
                except socket.timeout:
                    continue
                except ConnectionResetError:
                    continue
                self._handle_datagram(data, address)
        finally:
            self._write_stats()
            if self._owns_socket:
                self.sock.close()


def request_shutdown(
    host: str | None = None,
    port: int | None = None,
    *,
    settings: RuntimeConfig | None = None,
) -> None:
    """Ask a local proxy process to flush pending deliveries and exit."""
    settings = settings or config.load_config()
    destination = (host or settings.proxy_host, port or settings.proxy_port)
    if destination[0] in {"0.0.0.0", ""}:
        destination = ("127.0.0.1", destination[1])
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as shutdown_socket:
        shutdown_socket.sendto(SHUTDOWN_DATAGRAM, destination)


def main() -> int:
    proxy = FaultInjectionProxy(
        stats_path=os.environ.get("PROXY_STATS_PATH", "data/results/proxy_metrics.json"),
        quiet=os.environ.get("QUIET", "1") == "1",
        stats_flush_interval=int(os.environ.get("PROXY_STATS_FLUSH_INTERVAL", "100")),
    )
    print(
        f"READY proxy {proxy.settings.proxy_host}:{proxy.settings.proxy_port}",
        flush=True,
    )
    try:
        proxy.run()
    except KeyboardInterrupt:
        proxy.stopping = True
        while proxy._queue:
            proxy.flush_due(now=float("inf"))
        proxy._write_stats()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
