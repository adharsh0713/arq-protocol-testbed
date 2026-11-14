"""Deterministic, direction-local packet fault decisions."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledCopy:
    data: bytes
    delay: float


class FaultInjector:
    """Apply independent faults without sleeping or using global randomness.

    ``delay`` is a base per-packet delay. A packet selected for reordering gets
    an additional ``reorder_delay`` so a later packet can overtake it in the
    proxy's delivery queue.
    """

    def __init__(
        self,
        *,
        loss_rate: float = 0.0,
        corruption_rate: float = 0.0,
        delay: float = 0.0,
        duplicate_rate: float = 0.0,
        reorder_rate: float = 0.0,
        reorder_delay: float = 0.05,
        seed: int | None = None,
    ) -> None:
        for name, rate in (
            ("loss_rate", loss_rate),
            ("corruption_rate", corruption_rate),
            ("duplicate_rate", duplicate_rate),
            ("reorder_rate", reorder_rate),
        ):
            self._validate_rate(name, rate)
        for name, value in (("delay", delay), ("reorder_delay", reorder_delay)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")

        self.loss_rate = float(loss_rate)
        self.corruption_rate = float(corruption_rate)
        self.delay = float(delay)
        self.duplicate_rate = float(duplicate_rate)
        self.reorder_rate = float(reorder_rate)
        self.reorder_delay = float(reorder_delay)
        self.seed = seed
        self.rng = random.Random(seed)
        self._stats = {
            "packets_seen": 0,
            "packets_dropped": 0,
            "packets_corrupted": 0,
            "packets_duplicated": 0,
            "packets_delayed": 0,
            "reorder_scheduled": 0,
            "packets_forwarded": 0,
            "packets_reordered": 0,
        }

    @staticmethod
    def _validate_rate(name: str, rate: float) -> None:
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
            raise ValueError(f"{name} must be between 0 and 1")

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def inject(self, data: bytes) -> list[ScheduledCopy]:
        """Return zero, one or two scheduled copies for one observed datagram."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("data must be bytes-like")
        payload = bytes(data)
        self._stats["packets_seen"] += 1

        if self.rng.random() < self.loss_rate:
            self._stats["packets_dropped"] += 1
            return []

        if self.rng.random() < self.corruption_rate:
            payload = self._corrupt(payload)
            self._stats["packets_corrupted"] += 1

        delay = self.delay
        if delay > 0:
            self._stats["packets_delayed"] += 1

        if self.rng.random() < self.reorder_rate:
            delay += self.reorder_delay
            self._stats["reorder_scheduled"] += 1
            if self.reorder_delay > 0 and self.delay == 0:
                self._stats["packets_delayed"] += 1

        copies = 2 if self.rng.random() < self.duplicate_rate else 1
        if copies == 2:
            self._stats["packets_duplicated"] += 1

        return [ScheduledCopy(payload, delay) for _ in range(copies)]

    def _corrupt(self, data: bytes) -> bytes:
        if not data:
            return data
        corrupted = bytearray(data)
        index = self.rng.randrange(len(corrupted))
        corrupted[index] ^= 1 << self.rng.randrange(8)
        return bytes(corrupted)

    def record_forwarded(self, count: int = 1) -> None:
        self._stats["packets_forwarded"] += count

    def record_reordered(self, count: int = 1) -> None:
        self._stats["packets_reordered"] += count

    def report(self) -> dict[str, object]:
        return {
            "configuration": {
                "loss_rate": self.loss_rate,
                "corruption_rate": self.corruption_rate,
                "delay": self.delay,
                "duplicate_rate": self.duplicate_rate,
                "reorder_rate": self.reorder_rate,
                "reorder_delay": self.reorder_delay,
                "seed": self.seed,
            },
            "counts": self.stats,
            "realized_rates": self.realized_rates(),
        }

    def realized_rates(self) -> dict[str, float]:
        seen = self._stats["packets_seen"]
        divisor = seen or 1
        return {
            "loss_rate": self._stats["packets_dropped"] / divisor,
            "corruption_rate": self._stats["packets_corrupted"] / divisor,
            "duplicate_rate": self._stats["packets_duplicated"] / divisor,
            "delay_rate": self._stats["packets_delayed"] / divisor,
            # Fraction selected for extra hold; actual overtaking is reported separately.
            "reorder_rate": self._stats["reorder_scheduled"] / divisor,
            "reorder_delivery_rate": (
                self._stats["packets_reordered"] / max(1, self._stats["packets_forwarded"])
            ),
        }
