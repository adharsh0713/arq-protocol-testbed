"""Single source of truth for protocol and network configuration."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Mapping

MAX_PAYLOAD = 60_000
MAX_SEQUENCE = (1 << 32) - 1
MAX_UDP_PAYLOAD = 65_507

PROTOCOLS = {"stop_wait", "go_back_n", "selective_repeat"}


def max_transfer_size(chunk_size: int) -> int:
    """Largest file whose DATA count and following END sequence both fit."""
    if not 1 <= chunk_size <= MAX_PAYLOAD:
        raise ValueError(f"chunk_size must be between 1 and {MAX_PAYLOAD}")
    return chunk_size * MAX_SEQUENCE


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, str(default)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        value = float(env.get(name, str(default)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _rate(env: Mapping[str, str], name: str) -> float:
    value = _float(env, name, 0.0)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True)
class RuntimeConfig:
    protocol: str
    window_size: int
    chunk_size: int
    timeout: float
    max_retries: int
    receiver_idle_timeout: float
    server_ip: str
    server_port: int
    receiver_host: str
    receiver_ip: str
    receiver_port: int
    proxy_host: str
    proxy_port: int
    output_file: str
    seed: int
    data_loss_rate: float
    data_corruption_rate: float
    data_delay: float
    data_duplicate_rate: float
    data_reorder_rate: float
    data_reorder_delay: float
    ack_loss_rate: float
    ack_corruption_rate: float
    ack_delay: float
    ack_duplicate_rate: float
    ack_reorder_rate: float
    ack_reorder_delay: float

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(environ: Mapping[str, str] | None = None) -> RuntimeConfig:
    env = os.environ if environ is None else environ
    protocol = env.get("PROTOCOL", "selective_repeat").strip().lower()
    if protocol not in PROTOCOLS:
        raise ValueError(f"Unsupported PROTOCOL: {protocol!r}")

    window = _int(env, "WINDOW_SIZE", 4)
    chunk = _int(env, "CHUNK_SIZE", 4096)
    timeout = _float(env, "TIMEOUT", 0.05)
    retries = _int(env, "MAX_RETRIES", 15)
    receiver_idle_timeout = _float(
        env,
        "RECEIVER_IDLE_TIMEOUT",
        max(timeout * (retries + 1) + max(0.1, timeout), 5.0),
    )
    receiver_port = _int(env, "RECEIVER_PORT", 5000)
    proxy_port = _int(env, "PROXY_PORT", 5001)
    server_port = _int(env, "SERVER_PORT", proxy_port)

    if window < 1:
        raise ValueError("WINDOW_SIZE must be at least 1")
    if not 1 <= chunk <= MAX_PAYLOAD:
        raise ValueError(f"CHUNK_SIZE must be between 1 and {MAX_PAYLOAD}")
    if chunk + 11 > MAX_UDP_PAYLOAD:
        raise ValueError("CHUNK_SIZE exceeds the UDP datagram payload limit")
    if timeout <= 0:
        raise ValueError("TIMEOUT must be greater than 0")
    if retries < 0:
        raise ValueError("MAX_RETRIES cannot be negative")
    if receiver_idle_timeout <= 0:
        raise ValueError("RECEIVER_IDLE_TIMEOUT must be greater than 0")
    for name, port in (
        ("SERVER_PORT", server_port),
        ("RECEIVER_PORT", receiver_port),
        ("PROXY_PORT", proxy_port),
    ):
        if not 1 <= port <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535")

    rates = {
        name: _rate(env, name)
        for name in (
            "DATA_LOSS_RATE",
            "DATA_CORRUPTION_RATE",
            "DATA_DUPLICATE_RATE",
            "DATA_REORDER_RATE",
            "ACK_LOSS_RATE",
            "ACK_CORRUPTION_RATE",
            "ACK_DUPLICATE_RATE",
            "ACK_REORDER_RATE",
        )
    }
    delays = {
        "data_delay": _float(env, "DATA_DELAY", 0.0),
        "ack_delay": _float(env, "ACK_DELAY", 0.0),
        "data_reorder_delay": _float(env, "DATA_REORDER_DELAY", 0.05),
        "ack_reorder_delay": _float(env, "ACK_REORDER_DELAY", 0.05),
    }
    if any(value < 0 for value in delays.values()):
        raise ValueError("Delay values cannot be negative")
    if rates["DATA_REORDER_RATE"] > 0 and delays["data_reorder_delay"] <= 0:
        raise ValueError("DATA_REORDER_DELAY must be positive when DATA_REORDER_RATE is nonzero")
    if rates["ACK_REORDER_RATE"] > 0 and delays["ack_reorder_delay"] <= 0:
        raise ValueError("ACK_REORDER_DELAY must be positive when ACK_REORDER_RATE is nonzero")

    return RuntimeConfig(
        protocol=protocol,
        window_size=window,
        chunk_size=chunk,
        timeout=timeout,
        max_retries=retries,
        receiver_idle_timeout=receiver_idle_timeout,
        server_ip=env.get("SERVER_IP", "127.0.0.1"),
        server_port=server_port,
        receiver_host=env.get("RECEIVER_HOST", "0.0.0.0"),
        receiver_ip=env.get("RECEIVER_IP", "127.0.0.1"),
        receiver_port=receiver_port,
        proxy_host=env.get("PROXY_HOST", "0.0.0.0"),
        proxy_port=proxy_port,
        output_file=env.get("OUTPUT_FILE", f"data/results/{protocol}_received.bin"),
        seed=_int(env, "SEED", 0),
        data_loss_rate=rates["DATA_LOSS_RATE"],
        data_corruption_rate=rates["DATA_CORRUPTION_RATE"],
        data_delay=delays["data_delay"],
        data_duplicate_rate=rates["DATA_DUPLICATE_RATE"],
        data_reorder_rate=rates["DATA_REORDER_RATE"],
        data_reorder_delay=delays["data_reorder_delay"],
        ack_loss_rate=rates["ACK_LOSS_RATE"],
        ack_corruption_rate=rates["ACK_CORRUPTION_RATE"],
        ack_delay=delays["ack_delay"],
        ack_duplicate_rate=rates["ACK_DUPLICATE_RATE"],
        ack_reorder_rate=rates["ACK_REORDER_RATE"],
        ack_reorder_delay=delays["ack_reorder_delay"],
    )


SETTINGS = load_config()

# Compatibility aliases for modules not yet migrated to RuntimeConfig.
PROTOCOL = SETTINGS.protocol
WINDOW_SIZE = SETTINGS.window_size
CHUNK_SIZE = SETTINGS.chunk_size
TIMEOUT = SETTINGS.timeout
MAX_RETRIES = SETTINGS.max_retries
SERVER_IP = SETTINGS.server_ip
SERVER_PORT = SETTINGS.server_port
RECEIVER_HOST = SETTINGS.receiver_host
RECEIVER_PORT = SETTINGS.receiver_port
PROXY_HOST = SETTINGS.proxy_host
PROXY_PORT = SETTINGS.proxy_port
OUTPUT_FILE = SETTINGS.output_file
