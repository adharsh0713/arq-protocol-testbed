import json
import random

import pytest

from config import load_config
from network.fault_injector import FaultInjector, ScheduledCopy
from network.proxy import FaultInjectionProxy, SHUTDOWN_DATAGRAM
from protocol.packet import ACK, DATA, END, Packet


SENDER = ("127.0.0.1", 41000)
RECEIVER = ("127.0.0.1", 5000)


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def sendto(self, data, destination):
        self.sent.append((data, destination))
        return len(data)

    def close(self):
        self.closed = True


class ScriptedInjector:
    def __init__(self, delays):
        self.delays = iter(delays)
        self._forwarded = 0
        self._reordered = 0

    def inject(self, data):
        return [ScheduledCopy(data, next(self.delays))]

    def record_forwarded(self, count=1):
        self._forwarded += count

    def record_reordered(self, count=1):
        self._reordered += count

    def report(self):
        return {"counts": {"packets_forwarded": self._forwarded,
                           "packets_reordered": self._reordered}}



def settings(**values):
    env = {
        "RECEIVER_IP": "127.0.0.1",
        "RECEIVER_PORT": "5000",
        "PROXY_PORT": "5001",
        "SERVER_PORT": "5001",
        "SEED": "77",
    }
    env.update({key: str(value) for key, value in values.items()})
    return load_config(env)


def packet(sequence, kind, payload=b""):
    return Packet(sequence, kind, payload).encode()


def make_proxy(tmp_path, fake, **config_values):
    return FaultInjectionProxy(
        settings(**config_values),
        sock=fake,
        stats_path=tmp_path / "proxy.json",
        quiet=True,
        stats_flush_interval=1,
    )


def test_fault_injector_is_seeded_and_does_not_use_global_random():
    first = FaultInjector(seed=123, corruption_rate=0.5, duplicate_rate=0.5)
    second = FaultInjector(seed=123, corruption_rate=0.5, duplicate_rate=0.5)

    outcomes_a = [first.inject(b"packet") for _ in range(8)]
    outcomes_b = [second.inject(b"packet") for _ in range(8)]

    assert outcomes_a == outcomes_b
    assert first.stats == second.stats


def test_fault_injector_applies_exact_drop_corrupt_duplicate_delay_and_reorder():
    dropped = FaultInjector(loss_rate=1.0, seed=1)
    assert dropped.inject(b"x") == []
    assert dropped.stats["packets_dropped"] == 1

    corrupted = FaultInjector(corruption_rate=1.0, seed=1)
    result = corrupted.inject(b"x")
    assert result[0].data != b"x"
    assert corrupted.stats["packets_corrupted"] == 1

    duplicated = FaultInjector(duplicate_rate=1.0, seed=1)
    assert len(duplicated.inject(b"x")) == 2
    assert duplicated.stats["packets_duplicated"] == 1

    delayed = FaultInjector(delay=0.25, reorder_rate=1.0, reorder_delay=0.5, seed=1)
    scheduled = delayed.inject(b"x")
    assert scheduled[0].delay == 0.75
    assert delayed.stats["packets_delayed"] == 1
    assert delayed.stats["reorder_scheduled"] == 1


def test_zero_fault_proxy_forwards_data_and_ack_unchanged(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake)
    data = packet(0, DATA, b"hello")
    ack = packet(0, ACK)

    proxy._handle_datagram(data, SENDER, now=0)
    proxy.flush_due(now=0)
    proxy._handle_datagram(ack, RECEIVER, now=1)
    proxy.flush_due(now=1)

    assert fake.sent == [(data, RECEIVER), (ack, SENDER)]
    report = json.loads((tmp_path / "proxy.json").read_text())
    assert report["directions"]["data"]["counts"]["packets_forwarded"] == 1
    assert report["directions"]["ack"]["counts"]["packets_forwarded"] == 1


def test_ack_duplication_uses_same_fault_path_as_data(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake, ACK_DUPLICATE_RATE=1)
    proxy._handle_datagram(packet(0, DATA, b"x"), SENDER, now=0)
    proxy.flush_due(now=0)

    ack = packet(0, ACK)
    proxy._handle_datagram(ack, RECEIVER, now=1)
    proxy.flush_due(now=1)

    ack_deliveries = [item for item in fake.sent if item[1] == SENDER]
    assert len(ack_deliveries) == 2
    assert all(item[0] == ack for item in ack_deliveries)
    assert proxy.injectors["ack"].stats["packets_duplicated"] == 1


def test_delay_queue_does_not_block_other_direction_and_detects_reordering(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake)
    proxy.injectors["data"] = ScriptedInjector([2.0, 0.0])
    proxy._handle_datagram(packet(0, DATA, b"first"), SENDER, now=0)
    proxy._handle_datagram(packet(1, DATA, b"second"), SENDER, now=0)

    assert proxy.flush_due(now=0) == 1
    assert Packet.decode(fake.sent[0][0]).sequence == 1
    assert proxy.flush_due(now=2) == 1
    assert Packet.decode(fake.sent[1][0]).sequence == 0
    assert proxy.injectors["data"]._reordered == 1


def test_rejects_second_sender_and_ack_from_unexpected_port(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake)
    proxy._handle_datagram(packet(0, DATA, b"x"), SENDER, now=0)
    proxy._handle_datagram(packet(1, DATA, b"y"), ("127.0.0.1", 41001), now=0)
    proxy._handle_datagram(packet(0, ACK), ("127.0.0.1", 5002), now=0)
    proxy.flush_due(now=0)

    assert len(fake.sent) == 1
    assert proxy.unexpected_senders == 2


def test_proxy_shutdown_datagram_is_local_and_stats_are_flushed(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake)
    proxy._handle_datagram(SHUTDOWN_DATAGRAM, ("127.0.0.1", 41000), now=0)

    assert proxy.stopping is True
    saved = json.loads((tmp_path / "proxy.json").read_text())
    assert saved["shutdown_requested"] is True
    assert saved["pending_deliveries"] == 0


def test_invalid_packet_is_counted_not_forwarded(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake)
    proxy._handle_datagram(b"not a packet", SENDER, now=0)

    assert not fake.sent
    assert proxy.invalid_datagrams == 1


@pytest.mark.parametrize(
    "direction,fault_env,packet_bytes,source,destination",
    [
        ("data", "DATA_LOSS_RATE", packet(0, DATA, b"data"), SENDER, RECEIVER),
        ("ack", "ACK_LOSS_RATE", packet(0, ACK), RECEIVER, SENDER),
    ],
)
def test_loss_is_applied_in_both_directions(
    tmp_path, direction, fault_env, packet_bytes, source, destination
):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake, **{fault_env: 1})
    if direction == "ack":
        proxy._handle_datagram(packet(0, DATA, b"pin sender"), SENDER, now=0)
        proxy.flush_due(now=0)
    proxy._handle_datagram(packet_bytes, source, now=1)
    proxy.flush_due(now=1)

    assert not [item for item in fake.sent if item[1] == destination and item[0] == packet_bytes]
    assert proxy.injectors[direction].stats["packets_dropped"] == 1


@pytest.mark.parametrize(
    "direction,fault_env,packet_bytes,source,destination",
    [
        ("data", "DATA_CORRUPTION_RATE", packet(0, DATA, b"data"), SENDER, RECEIVER),
        ("ack", "ACK_CORRUPTION_RATE", packet(0, ACK), RECEIVER, SENDER),
    ],
)
def test_corruption_is_applied_in_both_directions(
    tmp_path, direction, fault_env, packet_bytes, source, destination
):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake, **{fault_env: 1})
    if direction == "ack":
        proxy._handle_datagram(packet(0, DATA, b"pin sender"), SENDER, now=0)
        proxy.flush_due(now=0)
    proxy._handle_datagram(packet_bytes, source, now=1)
    proxy.flush_due(now=1)

    delivered = [data for data, target in fake.sent if target == destination]
    assert len(delivered) == 1
    with pytest.raises(ValueError):
        Packet.decode(delivered[0])
    assert proxy.injectors[direction].stats["packets_corrupted"] == 1


@pytest.mark.parametrize(
    "direction,fault_env,packet_bytes,source,destination",
    [
        ("data", "DATA_DUPLICATE_RATE", packet(0, DATA, b"data"), SENDER, RECEIVER),
        ("ack", "ACK_DUPLICATE_RATE", packet(0, ACK), RECEIVER, SENDER),
    ],
)
def test_duplication_is_applied_in_both_directions(
    tmp_path, direction, fault_env, packet_bytes, source, destination
):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake, **{fault_env: 1})
    if direction == "ack":
        proxy._handle_datagram(packet(0, DATA, b"pin sender"), SENDER, now=0)
        proxy.flush_due(now=0)
    proxy._handle_datagram(packet_bytes, source, now=1)
    proxy.flush_due(now=1)

    delivered = [data for data, target in fake.sent if target == destination]
    assert delivered == [packet_bytes, packet_bytes]
    assert proxy.injectors[direction].stats["packets_duplicated"] == 1


@pytest.mark.parametrize(
    "direction,fault_env,packet_bytes,source,destination",
    [
        ("data", "DATA_DELAY", packet(0, DATA, b"data"), SENDER, RECEIVER),
        ("ack", "ACK_DELAY", packet(0, ACK), RECEIVER, SENDER),
    ],
)
def test_delay_is_scheduled_without_sleeping_in_both_directions(
    tmp_path, direction, fault_env, packet_bytes, source, destination
):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake, **{fault_env: 2})
    if direction == "ack":
        proxy._handle_datagram(packet(0, DATA, b"pin sender"), SENDER, now=0)
        proxy.flush_due(now=0)
    proxy._handle_datagram(packet_bytes, source, now=1)

    assert proxy.flush_due(now=1) == 0
    assert proxy.flush_due(now=3) == 1
    assert fake.sent[-1] == (packet_bytes, destination)
    assert proxy.injectors[direction].stats["packets_delayed"] == 1


@pytest.mark.parametrize("direction", ["data", "ack"])
def test_seeded_reordering_is_observed_in_both_directions(tmp_path, direction):
    fake = FakeSocket()
    proxy = make_proxy(
        tmp_path,
        fake,
        **{
            "DATA_REORDER_RATE": 0.5 if direction == "data" else 0,
            "ACK_REORDER_RATE": 0.5 if direction == "ack" else 0,
            "DATA_REORDER_DELAY": 0.5,
            "ACK_REORDER_DELAY": 0.5,
        },
    )
    injector = proxy.injectors[direction]
    injector.rng = random.Random(0)
    if direction == "data":
        source, destination = SENDER, RECEIVER
        first = packet(0, DATA, b"first")
        second = packet(1, DATA, b"second")
        proxy._handle_datagram(first, source, now=0)
        proxy._handle_datagram(second, source, now=0)
    else:
        proxy._handle_datagram(packet(0, DATA, b"pin sender"), SENDER, now=0)
        proxy.flush_due(now=0)
        source, destination = RECEIVER, SENDER
        first = packet(0, ACK)
        second = packet(1, ACK)
        proxy._handle_datagram(first, source, now=1)
        proxy._handle_datagram(second, source, now=1)

    assert proxy.flush_due(now=0 if direction == "data" else 1) == 1
    assert proxy.flush_due(now=0.5 if direction == "data" else 1.5) == 1
    delivered = [data for data, target in fake.sent if target == destination]
    assert delivered[-2:] == [second, first]
    assert injector.stats["packets_reordered"] == 1


def test_end_corruption_uses_data_direction_fault_model(tmp_path):
    fake = FakeSocket()
    proxy = make_proxy(tmp_path, fake, DATA_CORRUPTION_RATE=1)
    end_packet = packet(0, END)

    proxy._handle_datagram(end_packet, SENDER, now=0)
    proxy.flush_due(now=0)

    assert len(fake.sent) == 1
    with pytest.raises(ValueError):
        Packet.decode(fake.sent[0][0])
    assert proxy.injectors["data"].stats["packets_corrupted"] == 1
