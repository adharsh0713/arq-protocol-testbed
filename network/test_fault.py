"""Focused deterministic tests for isolated fault decisions."""

from network.fault_injector import FaultInjector


def test_loss_rate_one_drops_every_observed_packet():
    injector = FaultInjector(loss_rate=1.0, seed=5)
    assert injector.inject(b"one") == []
    assert injector.inject(b"two") == []
    assert injector.stats["packets_dropped"] == 2


def test_duplicate_rate_one_returns_two_identical_copies():
    injector = FaultInjector(duplicate_rate=1.0, seed=5)
    copies = injector.inject(b"same")
    assert [copy.data for copy in copies] == [b"same", b"same"]
