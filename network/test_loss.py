"""Loss regression tests; these replace the former print-only script."""

from network.fault_injector import FaultInjector


def test_zero_loss_forwards_each_packet_once():
    injector = FaultInjector(loss_rate=0.0, duplicate_rate=0.0, seed=23)
    for payload in (b"a", b"b", b"c"):
        copies = injector.inject(payload)
        assert len(copies) == 1
        assert copies[0].data == payload
    assert injector.stats["packets_dropped"] == 0
    assert injector.stats["packets_seen"] == 3
