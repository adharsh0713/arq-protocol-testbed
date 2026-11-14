import socket

import pytest

from algorithms.go_back_n import GoBackN
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


def make_ack(sequence, address):
    return Packet(sequence, ACK, b"").encode(), address


def packets(count):
    return [Packet(i, DATA, f"p{i}".encode()) for i in range(count)]


def test_window_slides_after_each_cumulative_ack():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket([make_ack(0, address), make_ack(1, address), make_ack(2, address)])
    metrics = Metrics("go_back_n")
    sender = GoBackN(sock, address, metrics, window_size=2, timeout=0.1)

    sender.send_file(packets(3))

    first_sends = [packet.sequence for packet, _ in sock.sent]
    assert first_sends[:2] == [0, 1]
    assert first_sends[2] == 2  # New data is sent as soon as the window advances.
    assert sender.base == 3
    assert metrics.acks_received == 3
    assert sock.timeout is None


def test_ignores_foreign_invalid_non_ack_and_out_of_range_ack():
    address = ("127.0.0.1", 5001)
    corrupted = bytearray(Packet(0, ACK, b"").encode())
    corrupted[-1] ^= 0x01
    sock = FakeSocket([
        (bytes(corrupted), address),
        make_ack(0, ("127.0.0.1", 9999)),
        (b"bad", address),
        (Packet(0, DATA, b"not ACK").encode(), address),
        make_ack(9, address),
        make_ack(0, address),
    ])
    metrics = Metrics("go_back_n")
    sender = GoBackN(sock, address, metrics, window_size=1, timeout=0.1)

    sender.send_file(packets(1))
    assert sender.base == 1
    assert metrics.acks_received == 1


def test_timeout_retransmits_all_outstanding_and_exhausts_retries():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket()
    metrics = Metrics("go_back_n")
    sender = GoBackN(sock, address, metrics, window_size=2,
                     timeout=0.001, max_retries=1)

    with pytest.raises(TimeoutError, match="after 1 retransmissions"):
        sender.send_file(packets(2))

    sent = [packet.sequence for packet, _ in sock.sent]
    assert sent == [0, 1, 0, 1]
    assert metrics.retransmissions == 2


def test_duplicate_stale_ack_does_not_advance_base():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket([make_ack(0, address), make_ack(0, address), make_ack(1, address)])
    metrics = Metrics("go_back_n")
    sender = GoBackN(sock, address, metrics, window_size=2, timeout=0.1)

    sender.send_file(packets(2))
    assert sender.base == 2
    assert metrics.acks_received == 2


def test_gbn_accepts_ack_at_highest_sent_sequence():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket([make_ack(1, address)])
    metrics = Metrics("go_back_n")
    sender = GoBackN(sock, address, metrics, window_size=2, timeout=0.1)

    sender.send_file(packets(2))
    assert sender.base == 2
    assert metrics.acks_received == 1


def test_invalid_datagrams_do_not_restart_base_deadline(monkeypatch):
    address = ("127.0.0.1", 5001)
    clock = {"now": 0.0}

    class SlowSocket(FakeSocket):
        def __init__(self):
            super().__init__([
                make_ack(0, ("127.0.0.1", 9999)),
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

    monkeypatch.setattr("algorithms.go_back_n.time.monotonic", lambda: clock["now"])
    sock = SlowSocket()
    sender = GoBackN(sock, address, Metrics("go_back_n"),
                     timeout=1.0, window_size=1, max_retries=0)
    with pytest.raises(TimeoutError):
        sender.send_file(packets(1))
    assert sock.requested_timeouts == pytest.approx([1.0, 0.6, 0.2])
