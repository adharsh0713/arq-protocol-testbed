import socket

import pytest

from algorithms import selective_repeat
from experiments.metrics import Metrics
from protocol.packet import ACK, DATA, Packet


class FakeSocket:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.sent = []
        self.timeout = None

    def sendto(self, data, address):
        self.sent.append((Packet.decode(data), address))

    def recvfrom(self, _size):
        if not self.responses:
            raise socket.timeout()
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def settimeout(self, value):
        self.timeout = value


def ack(sequence, address):
    return Packet(sequence, ACK, b"").encode(), address


def make_packets(count):
    return [Packet(i, DATA, f"packet-{i}".encode()) for i in range(count)]


def test_selective_repeat_accepts_out_of_order_acks():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket([ack(1, address), ack(0, address), ack(2, address)])
    metrics = Metrics("selective_repeat")

    selective_repeat.send_file(sock, address, make_packets(3), metrics,
                               window_size=2, timeout=0.1)
    assert metrics.acks_received == 3
    assert metrics.retransmissions == 0
    assert sock.timeout is None


def test_selective_repeat_retransmits_only_expired_packet(monkeypatch):
    address = ("127.0.0.1", 5001)
    sock = FakeSocket([socket.timeout(), ack(0, address), ack(1, address)])
    metrics = Metrics("selective_repeat")
    times = iter([0.000, 0.005, 0.006, 0.011, 0.011, 0.012, 0.013, 0.013, 0.014])
    monkeypatch.setattr(selective_repeat.time, "monotonic", lambda: next(times, 0.014))

    selective_repeat.send_file(sock, address, make_packets(2), metrics,
                               window_size=2, timeout=0.01, max_retries=1)
    assert [packet.sequence for packet, _ in sock.sent] == [0, 1, 0]
    assert metrics.retransmissions == 1
    assert sock.timeout is None


def test_selective_repeat_rejects_foreign_and_unrelated_acks():
    address = ("127.0.0.1", 5001)
    corrupted = bytearray(Packet(0, ACK, b"").encode())
    corrupted[-1] ^= 0x01
    sock = FakeSocket([
        (bytes(corrupted), address),
        ack(0, ("127.0.0.1", 9999)),
        ack(99, address),
        ack(0, address),
    ])
    metrics = Metrics("selective_repeat")

    selective_repeat.send_file(sock, address, make_packets(1), metrics,
                               window_size=1, timeout=0.1)
    assert metrics.acks_received == 1
    assert metrics.data_packets_sent == 1


def test_selective_repeat_retry_limit():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket()
    metrics = Metrics("selective_repeat")

    with pytest.raises(TimeoutError, match="after 0 retransmissions"):
        selective_repeat.send_file(sock, address, make_packets(1), metrics,
                                   timeout=0.001, max_retries=0)
    assert metrics.retransmissions == 0


def test_invalid_datagrams_do_not_skip_packet_timer_checks(monkeypatch):
    address = ("127.0.0.1", 5001)
    clock = {"now": 0.0}

    class SlowSocket(FakeSocket):
        def __init__(self):
            super().__init__([
                ack(0, ("127.0.0.1", 9999)),
                (b"bad", address),
                (Packet(0, DATA, b"not ACK").encode(), address),
            ])
            self.requested_timeouts = []

        def settimeout(self, value):
            self.timeout = value
            if value is not None:
                self.requested_timeouts.append(value)

        def recvfrom(self, size):
            clock["now"] += 0.4
            return super().recvfrom(size)

    monkeypatch.setattr("algorithms.selective_repeat.time.monotonic", lambda: clock["now"])
    sock = SlowSocket()
    with pytest.raises(TimeoutError):
        selective_repeat.send_file(sock, address, make_packets(1),
                                   Metrics("selective_repeat"),
                                   timeout=1.0, window_size=1, max_retries=0)
    assert sock.requested_timeouts == pytest.approx([1.0, 0.6, 0.2])
