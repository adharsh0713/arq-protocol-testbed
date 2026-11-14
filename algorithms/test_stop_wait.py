import socket

import pytest

from algorithms.stop_wait import send_packet
from experiments.metrics import Metrics
from protocol.packet import ACK, DATA, Packet


class FakeSocket:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.sent = []
        self.timeout = None

    def sendto(self, data, address):
        self.sent.append((data, address))

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


def data_packet(sequence=0):
    return Packet(sequence, DATA, b"payload")


def test_accepts_matching_ack_after_ignoring_foreign_stale_and_non_ack():
    address = ("127.0.0.1", 5001)
    corrupted = bytearray(Packet(0, ACK, b"").encode())
    corrupted[-1] ^= 0x01
    sock = FakeSocket([
        (bytes(corrupted), address),
        ack(0, ("127.0.0.1", 9999)),
        (Packet(0, DATA, b"not an ACK").encode(), address),
        ack(99, address),
        ack(0, address),
    ])
    metrics = Metrics("stop_wait")

    assert send_packet(sock, address, data_packet(), metrics, timeout=0.1) is True
    assert metrics.data_packets_sent == 1
    assert metrics.acks_received == 1
    assert sock.timeout is None


def test_retransmits_after_timeout_and_accepts_ack():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket([socket.timeout(), ack(0, address)])
    metrics = Metrics("stop_wait")

    send_packet(sock, address, data_packet(), metrics, timeout=0.001, max_retries=1)
    assert len(sock.sent) == 2
    assert metrics.retransmissions == 1


def test_stops_after_retry_limit():
    address = ("127.0.0.1", 5001)
    sock = FakeSocket()
    metrics = Metrics("stop_wait")

    with pytest.raises(TimeoutError, match="after 1 retransmissions"):
        send_packet(sock, address, data_packet(), metrics,
                    timeout=0.001, max_retries=1)
    assert len(sock.sent) == 2
    assert sock.timeout is None


def test_malformed_and_foreign_datagrams_do_not_restart_deadline(monkeypatch):
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

    monkeypatch.setattr("algorithms.stop_wait.time.monotonic", lambda: clock["now"])
    sock = SlowSocket()
    with pytest.raises(TimeoutError):
        send_packet(sock, address, data_packet(), Metrics("stop_wait"),
                    timeout=1.0, max_retries=0)
    assert sock.requested_timeouts == pytest.approx([1.0, 0.6, 0.2])
