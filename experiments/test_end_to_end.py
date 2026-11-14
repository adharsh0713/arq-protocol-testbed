from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest

from experiments.runner import ExperimentTask, PROTOCOLS, run_single_experiment


FAULTS = {
    "data_loss_rate": 0.05,
    "data_corruption_rate": 0.02,
    "data_delay": 0.001,
    "data_duplicate_rate": 0.05,
    "data_reorder_rate": 0.05,
    "data_reorder_delay": 0.008,
    "ack_loss_rate": 0.05,
    "ack_corruption_rate": 0.02,
    "ack_delay": 0.001,
    "ack_duplicate_rate": 0.05,
    "ack_reorder_rate": 0.05,
    "ack_reorder_delay": 0.008,
}


def _assert_verified(result, source: bytes):
    digest = hashlib.sha256(source).hexdigest()
    assert result["status"] == "success", result["error"]
    assert result["hash_verified"] is True
    assert result["source_sha256"] == digest == result["received_sha256"]
    assert result["file_size"] == result["received_size"] == len(source)
    assert result["data_packets_seen"] > 0
    assert result["ack_packets_seen"] > 0


def _task(protocol, matrix, trial, seed, file_name="payload.bin", faults=None):
    return ExperimentTask(
        tier="integration", fault_matrix=matrix, protocol=protocol,
        file_name=file_name, window=1 if protocol == "stop_wait" else 4,
        trial=trial, seed=seed, timeout=0.05, chunk_size=64,
        max_retries=8, faults=faults or {},
    )


def _execute_tasks(tasks, source_dir, run_root):
    with ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(
            lambda task: run_single_experiment(
                task, source_dir=source_dir, run_root=run_root
            ),
            tasks,
        ))


@pytest.mark.integration
def test_all_protocols_transfer_through_seeded_bidirectional_faults(tmp_path):
    """Fast CI gate: tiny payloads, actual UDP processes and all supported faults."""
    source = bytes((index * 37) % 256 for index in range(512))
    (tmp_path / "payload.bin").write_bytes(source)
    tasks = [
        _task(protocol, "combined", 1, 44117 + index, faults=FAULTS)
        for index, protocol in enumerate(PROTOCOLS)
    ]
    results = _execute_tasks(tasks, tmp_path, tmp_path / "runs")
    assert len(results) == 3
    for result in results:
        _assert_verified(result, source)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("scenario", ("baseline", "loss", "combined"))
def test_extended_loopback_scenarios(protocol, scenario, tmp_path):
    """Three transfer scenarios per protocol; excluded from default fast CI suite."""
    source = bytes((index * 19 + 7) % 256 for index in range(4096))
    (tmp_path / "payload.bin").write_bytes(source)
    if scenario == "baseline":
        faults = {}
    elif scenario == "loss":
        faults = {"data_loss_rate": 0.15, "ack_loss_rate": 0.15}
    else:
        faults = FAULTS
    task = _task(protocol, scenario, 1, 51000 + PROTOCOLS.index(protocol) * 10 +
                 (0 if scenario == "baseline" else 1 if scenario == "loss" else 2),
                 faults=faults)
    result = run_single_experiment(task, source_dir=tmp_path, run_root=tmp_path / "runs")
    _assert_verified(result, source)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("edge_name,source", (
    ("empty.bin", b""),
    ("sub_chunk.bin", b"short payload"),
    ("exact_chunk.bin", bytes(range(128))),
))
def test_edge_case_file_transfers(protocol, edge_name, source, tmp_path):
    (tmp_path / edge_name).write_bytes(source)
    task = _task(protocol, "baseline", 1, 61000 + PROTOCOLS.index(protocol),
                 file_name=edge_name, faults={})
    result = run_single_experiment(task, source_dir=tmp_path, run_root=tmp_path / "runs")
    _assert_verified(result, source)
