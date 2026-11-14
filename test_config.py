import pytest

from config import load_config


def test_default_configuration_uses_fast_localhost_timeout():
    settings = load_config({})
    assert settings.timeout == 0.05
    assert settings.receiver_port == 5000
    assert settings.proxy_port == 5001
    assert settings.server_port == 5001


def test_config_rejects_invalid_protocol_and_ranges():
    with pytest.raises(ValueError, match="Unsupported PROTOCOL"):
        load_config({"PROTOCOL": "tcp"})
    with pytest.raises(ValueError, match="WINDOW_SIZE"):
        load_config({"WINDOW_SIZE": "0"})
    with pytest.raises(ValueError, match="TIMEOUT"):
        load_config({"TIMEOUT": "0"})
    with pytest.raises(ValueError, match="DATA_LOSS_RATE"):
        load_config({"DATA_LOSS_RATE": "1.5"})
    with pytest.raises(ValueError, match="finite"):
        load_config({"TIMEOUT": "nan"})
    with pytest.raises(ValueError, match="negative"):
        load_config({"ACK_DELAY": "-0.1"})


def test_config_supports_independent_ports_timeout_seed_and_faults():
    settings = load_config({
        "TIMEOUT": "0.1",
        "RECEIVER_PORT": "5100",
        "PROXY_PORT": "5101",
        "SEED": "42",
        "DATA_REORDER_RATE": "0.2",
        "ACK_DUPLICATE_RATE": "0.3",
    })
    assert settings.timeout == 0.1
    assert settings.receiver_port == 5100
    assert settings.proxy_port == 5101
    assert settings.server_port == 5101
    assert settings.seed == 42
    assert settings.data_reorder_rate == 0.2
    assert settings.receiver_idle_timeout > settings.timeout
    assert settings.ack_duplicate_rate == 0.3


def test_config_requires_positive_reorder_hold_when_reordering_is_enabled():
    with pytest.raises(ValueError, match="DATA_REORDER_DELAY"):
        load_config({"DATA_REORDER_RATE": "0.1", "DATA_REORDER_DELAY": "0"})
    with pytest.raises(ValueError, match="ACK_REORDER_DELAY"):
        load_config({"ACK_REORDER_RATE": "0.1", "ACK_REORDER_DELAY": "0"})
