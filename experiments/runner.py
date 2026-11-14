"""Tiered, reproducible process-level benchmark runner.

Examples (run from the repository root):
    python -m experiments.runner --tier smoke
    python -m experiments.runner --tier quick --workers 1
    python -m experiments.runner --tier full --workers 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import socket
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.results import RESULT_FILE, save_result, validate_schema
from network.proxy import request_shutdown

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "test_files"
RUNS_DIR = ROOT / "data" / "results" / "runs"
_PORT_LOCK = threading.Lock()
_RESERVED_PORTS: set[int] = set()
PROTOCOLS = ("stop_wait", "go_back_n", "selective_repeat")
TEST_FILES = ("small.txt", "medium.txt", "large.txt", "image.png", "audio.wav")
WINDOWS = {"stop_wait": (1,), "go_back_n": (4, 16), "selective_repeat": (4, 16)}
_PROCESS_START_LOCK = threading.Lock()

FAULT_KEYS = (
    "data_loss_rate", "data_corruption_rate", "data_delay", "data_duplicate_rate",
    "data_reorder_rate", "data_reorder_delay", "ack_loss_rate", "ack_corruption_rate",
    "ack_delay", "ack_duplicate_rate", "ack_reorder_rate", "ack_reorder_delay",
)


@dataclass(frozen=True)
class ExperimentTask:
    tier: str
    fault_matrix: str
    protocol: str
    file_name: str
    window: int
    trial: int
    seed: int
    timeout: float = 0.05
    chunk_size: int = 4096
    max_retries: int = 15
    faults: dict[str, float] = field(default_factory=dict)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def _default_faults() -> dict[str, float]:
    return {
        "data_loss_rate": 0.0,
        "data_corruption_rate": 0.0,
        "data_delay": 0.0,
        "data_duplicate_rate": 0.0,
        "data_reorder_rate": 0.0,
        "data_reorder_delay": 0.02,
        "ack_loss_rate": 0.0,
        "ack_corruption_rate": 0.0,
        "ack_delay": 0.0,
        "ack_duplicate_rate": 0.0,
        "ack_reorder_rate": 0.0,
        "ack_reorder_delay": 0.02,
    }


def _faults(**overrides: float) -> dict[str, float]:
    values = _default_faults()
    values.update(overrides)
    return values


def build_tasks(tier: str, base_seed: int = 20261113) -> list[ExperimentTask]:
    """Create the frozen smoke, quick or full matrix with stable per-run seeds."""
    if tier not in {"smoke", "quick", "full"}:
        raise ValueError("tier must be smoke, quick or full")

    specifications: list[tuple[str, str, str, int, int, float, dict[str, float]]] = []

    def add(matrix: str, file_name: str, protocol: str, window: int,
            trials: int, timeout: float, fault_values: dict[str, float]) -> None:
        for trial in range(1, trials + 1):
            specifications.append((matrix, file_name, protocol, window, trial, timeout, fault_values))

    if tier == "smoke":
        for protocol in PROTOCOLS:
            for loss in (0.0, 0.2):
                add("loss", "small.txt", protocol, 1 if protocol == "stop_wait" else 4,
                    1, 0.05, _faults(data_loss_rate=loss, ack_loss_rate=loss))

    elif tier == "quick":
        for protocol in PROTOCOLS:
            window = 1 if protocol == "stop_wait" else 4
            for file_name in ("small.txt", "medium.txt"):
                for loss in (0.0, 0.1, 0.2):
                    add("loss", file_name, protocol, window, 2, 0.05,
                        _faults(data_loss_rate=loss, ack_loss_rate=loss))

    else:
        # RQ1: 10 trials, matched medium file; all supported protocol windows.
        for protocol in PROTOCOLS:
            for window in WINDOWS[protocol]:
                for loss in (0.0, 0.05, 0.1, 0.2):
                    add("loss", "medium.txt", protocol, window, 10, 0.05,
                        _faults(data_loss_rate=loss, ack_loss_rate=loss))

        # RQ2: delay x window; all protocols, with Stop-and-Wait fixed at W=1.
        for protocol in PROTOCOLS:
            for window in (1, 4, 16) if protocol != "stop_wait" else (1,):
                for delay in (0.0, 0.005, 0.02, 0.05):
                    add("delay", "medium.txt", protocol, window, 5, 0.05,
                        _faults(data_delay=delay, ack_delay=delay))

        # RQ3: 10-trial headline reordering experiment.
        for protocol in PROTOCOLS:
            for window in WINDOWS[protocol]:
                for rate in (0.0, 0.05, 0.1, 0.2):
                    add("reordering", "medium.txt", protocol, window, 10, 0.05,
                        _faults(data_reorder_rate=rate, ack_reorder_rate=rate))

        # RQ4: isolated corruption and duplication sweeps, both directions.
        for matrix, data_key, ack_key in (
            ("corruption", "data_corruption_rate", "ack_corruption_rate"),
            ("duplication", "data_duplicate_rate", "ack_duplicate_rate"),
        ):
            for protocol in PROTOCOLS:
                for window in WINDOWS[protocol]:
                    for rate in (0.0, 0.05, 0.1, 0.2):
                        add(matrix, "medium.txt", protocol, window, 5, 0.05,
                            _faults(**{data_key: rate, ack_key: rate}))

        # RQ5: timeout sensitivity at 10% loss and the specified W=4 (W=1 for S&W).
        for protocol in PROTOCOLS:
            window = 1 if protocol == "stop_wait" else 4
            for timeout in (0.01, 0.025, 0.05, 0.1, 0.25, 1.0):
                add("timeout", "medium.txt", protocol, window, 5, timeout,
                    _faults(data_loss_rate=0.1, ack_loss_rate=0.1))

        # RQ6: all five required file types under combined, bidirectional faults.
        combined = _faults(
            data_loss_rate=0.05, ack_loss_rate=0.05,
            data_corruption_rate=0.02, ack_corruption_rate=0.02,
            data_delay=0.005, ack_delay=0.005,
            data_duplicate_rate=0.02, ack_duplicate_rate=0.02,
            data_reorder_rate=0.02, ack_reorder_rate=0.02,
        )
        for file_name in TEST_FILES:
            for protocol in PROTOCOLS:
                window = 1 if protocol == "stop_wait" else 4
                add("combined", file_name, protocol, window, 5, 0.05, combined)

    tasks: list[ExperimentTask] = []
    for run_number, (matrix, file_name, protocol, window, trial, timeout, fault_values) in enumerate(
        specifications, start=1
    ):
        tasks.append(ExperimentTask(
            tier=tier,
            fault_matrix=matrix,
            protocol=protocol,
            file_name=file_name,
            window=window,
            trial=trial,
            seed=base_seed + run_number - 1,
            timeout=timeout,
            faults=dict(fault_values),
        ))
    return tasks


def _allocate_ports() -> tuple[int, int]:
    """Reserve a unique UDP port pair across concurrently running experiments."""
    with _PORT_LOCK:
        for _ in range(100):
            ports: list[int] = []
            probes: list[socket.socket] = []
            try:
                for _ in range(2):
                    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    probe.bind(("127.0.0.1", 0))
                    probes.append(probe)
                    ports.append(int(probe.getsockname()[1]))
            finally:
                for probe in probes:
                    probe.close()
            if len(set(ports)) == 2 and not (_RESERVED_PORTS & set(ports)):
                _RESERVED_PORTS.update(ports)
                return ports[0], ports[1]
    raise RuntimeError("Unable to reserve a unique UDP port pair")


def _release_ports(*ports: int) -> None:
    with _PORT_LOCK:
        _RESERVED_PORTS.difference_update(ports)


def _start_ready_process(
    module: str,
    label: str,
    env: dict[str, str],
    timeout: float = 10.0,
    log_path: Path | None = None,
) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-m", module],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        try:
            if log_path is None:
                for line in process.stdout:
                    lines.put(line.rstrip())
            else:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("w", encoding="utf-8") as log:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        lines.put(line.rstrip())
        finally:
            lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + timeout
    captured: list[str] = []
    while time.monotonic() < deadline:
        if process.poll() is not None and lines.empty():
            break
        try:
            line = lines.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if line is None:
            break
        captured.append(line)
        if line.startswith(f"READY {label} "):
            return process
    _stop_process(process)
    detail = "\n".join(captured[-20:])
    raise RuntimeError(f"{label} did not become ready within {timeout}s. Output:\n{detail}")


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=2, check=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _base_result(task: ExperimentTask, run_id: str, source: Path) -> dict[str, Any]:
    faults = _default_faults()
    faults.update(task.faults)
    return {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": task.tier,
        "fault_matrix": task.fault_matrix,
        "trial": task.trial,
        "seed": task.seed,
        "status": "failed",
        "error": "Run did not reach completion",
        "protocol": task.protocol,
        "file_name": source.name,
        "file_size": source.stat().st_size if source.is_file() else "",
        "window": task.window,
        "chunk_size": task.chunk_size,
        "timeout": task.timeout,
        "max_retries": task.max_retries,
        **faults,
        "source_sha256": sha256_file(source) if source.is_file() else "",
        "hash_verified": False,
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "machine_name": platform.node(),
    }


def _merge_reports(result: dict[str, Any], sender: dict[str, Any], receiver: dict[str, Any], proxy: dict[str, Any]) -> None:
    # Keep process-specific ownership explicit; never overwrite a sender metric with a receiver zero.
    for key in (
        "completion_time", "throughput", "retransmissions", "end_retries", "total_bytes_sent",
        "data_packets_sent", "control_packets_sent", "acks_received", "duplicate_acks_received",
        "retransmitted_packets", "recovery_samples", "recovery_time_mean", "recovery_time_max",
        "duplicate_acks_for_retransmitted_packets",
    ):
        if key in sender:
            result[key] = sender[key]
    for key in (
        "unique_data_received", "unique_data_delivered", "data_arrivals", "duplicate_arrivals",
        "corrupt_discarded", "out_of_window_discarded", "invalid_chunk_discarded",
        "bytes_received", "received_size",
        "received_sha256", "integrity_verified",
    ):
        if key in receiver:
            result[key] = receiver[key]
    result["acks_sent"] = receiver.get("acks_sent", "")

    directions = proxy.get("directions", {})
    for direction in ("data", "ack"):
        report = directions.get(direction, {})
        counts = report.get("counts", {})
        rates = report.get("realized_rates", {})
        prefix = "data" if direction == "data" else "ack"
        for key, value in counts.items():
            normalized = {
                "packets_seen": "packets_seen",
                "packets_dropped": "packets_dropped",
                "packets_corrupted": "packets_corrupted",
                "packets_duplicated": "packets_duplicated",
                "packets_delayed": "packets_delayed",
                "reorder_scheduled": "reorder_scheduled",
                "packets_forwarded": "packets_forwarded",
                "packets_reordered": "packets_reordered",
            }[key]
            result[f"{prefix}_{normalized}"] = value
        for key, value in rates.items():
            normalized = {
                "loss_rate": "realized_loss_rate",
                "corruption_rate": "realized_corruption_rate",
                "duplicate_rate": "realized_duplicate_rate",
                "delay_rate": "realized_delay_rate",
                "reorder_rate": "realized_reorder_rate",
                "reorder_delivery_rate": "realized_reorder_delivery_rate",
            }[key]
            result[f"{prefix}_{normalized}"] = value


def run_single_experiment(
    task: ExperimentTask,
    *,
    source_dir: str | Path = TEST_DIR,
    run_root: str | Path = RUNS_DIR,
) -> dict[str, Any]:
    """Execute one isolated sender/receiver/proxy process run and return its CSV row."""
    from scripts.make_test_files import generate_test_files

    source = Path(source_dir) / task.file_name
    if not source.is_file() and Path(source_dir).resolve() == TEST_DIR.resolve():
        generate_test_files(source_dir)
    run_id = f"{task.tier}-{task.fault_matrix}-{task.protocol}-{source.stem}-w{task.window}-t{task.trial}-{uuid.uuid4().hex[:8]}"
    result = _base_result(task, run_id, source)
    if not source.is_file():
        result["error"] = f"Test fixture is missing: {source}"
        return result

    run_dir = Path(run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    sender_metrics_path = run_dir / "sender_metrics.json"
    receiver_metrics_path = run_dir / "receiver_metrics.json"
    proxy_metrics_path = run_dir / "proxy_metrics.json"
    output_path = run_dir / "received.bin"
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT) + os.pathsep + env.get("PYTHONPATH", ""),
        "PROTOCOL": task.protocol,
        "WINDOW_SIZE": str(task.window),
        "CHUNK_SIZE": str(task.chunk_size),
        "TIMEOUT": str(task.timeout),
        "MAX_RETRIES": str(task.max_retries),
        "RECEIVER_IDLE_TIMEOUT": str(max(5.0, task.timeout * (task.max_retries + 1) + 2.0)),
        "SERVER_IP": "127.0.0.1",
        "RECEIVER_HOST": "127.0.0.1",
        "RECEIVER_IP": "127.0.0.1",
        "PROXY_HOST": "127.0.0.1",
        "OUTPUT_FILE": str(output_path),
        "SEED": str(task.seed),
        "EXPECTED_FILE_SIZE": str(source.stat().st_size),
        "EXPECTED_FILE_SHA256": result["source_sha256"],
        "SENDER_METRICS_PATH": str(sender_metrics_path),
        "RECEIVER_METRICS_PATH": str(receiver_metrics_path),
        "PROXY_STATS_PATH": str(proxy_metrics_path),
        "QUIET": "1",
    })
    env_map = {
        "data_loss_rate": "DATA_LOSS_RATE",
        "data_corruption_rate": "DATA_CORRUPTION_RATE",
        "data_delay": "DATA_DELAY",
        "data_duplicate_rate": "DATA_DUPLICATE_RATE",
        "data_reorder_rate": "DATA_REORDER_RATE",
        "data_reorder_delay": "DATA_REORDER_DELAY",
        "ack_loss_rate": "ACK_LOSS_RATE",
        "ack_corruption_rate": "ACK_CORRUPTION_RATE",
        "ack_delay": "ACK_DELAY",
        "ack_duplicate_rate": "ACK_DUPLICATE_RATE",
        "ack_reorder_rate": "ACK_REORDER_RATE",
        "ack_reorder_delay": "ACK_REORDER_DELAY",
    }
    for source_key, env_key in env_map.items():
        env[env_key] = str(result[source_key])

    receiver_process: subprocess.Popen | None = None
    proxy_process: subprocess.Popen | None = None
    receiver_port: int | None = None
    proxy_port: int | None = None
    try:
        # Keep ephemeral-port reservation and both child binds atomic relative
        # to other worker threads in this runner. The transfers run concurrently
        # after both processes report READY.
        with _PROCESS_START_LOCK:
            receiver_port, proxy_port = _allocate_ports()
            env.update({
                "SERVER_PORT": str(proxy_port),
                "RECEIVER_PORT": str(receiver_port),
                "PROXY_PORT": str(proxy_port),
            })
            receiver_process = _start_ready_process(
                "receiver.receiver", "receiver", env, log_path=run_dir / "receiver.log"
            )
            proxy_process = _start_ready_process(
                "network.proxy", "proxy", env, log_path=run_dir / "proxy.log"
            )
        packet_count = (source.stat().st_size + task.chunk_size - 1) // task.chunk_size
        if task.tier in {"smoke", "quick"}:
            # Fast tiers must fail visibly rather than spend minutes on a stalled sender.
            sender_timeout = 30.0
        else:
            retry_budget = (packet_count + 10) * task.timeout * (task.max_retries + 1)
            sender_timeout = min(180.0, max(60.0, retry_budget * 0.15 + 10.0))
        completed = subprocess.run(
            [sys.executable, "-m", "sender.sender", str(source.resolve())],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=sender_timeout,
            check=False,
        )
        (run_dir / "sender.log").write_text(
            (completed.stdout or "") + (completed.stderr or ""), encoding="utf-8"
        )
        if completed.returncode != 0:
            sender_error = (completed.stderr or completed.stdout or "Sender failed").strip()
            raise RuntimeError(f"Sender exited with code {completed.returncode}: {sender_error[-1500:]}")

        receiver_wait = max(5.0, task.timeout * (task.max_retries + 1) + max(0.1, task.timeout) + 3.0)
        receiver_code = receiver_process.wait(timeout=receiver_wait)
        if receiver_code != 0:
            raise RuntimeError(f"Receiver exited with code {receiver_code}")

        request_shutdown(host="127.0.0.1", port=proxy_port)
        max_pending_delay = max(
            result["data_delay"] + result["data_reorder_delay"],
            result["ack_delay"] + result["ack_reorder_delay"],
        )
        proxy_code = proxy_process.wait(timeout=max(5.0, max_pending_delay + 3.0))
        if proxy_code != 0:
            raise RuntimeError(f"Proxy exited with code {proxy_code}")

        sender_report = _load_json(sender_metrics_path)
        receiver_report = _load_json(receiver_metrics_path)
        proxy_report = _load_json(proxy_metrics_path)
        if not sender_report or not receiver_report or not proxy_report:
            raise RuntimeError("One or more process metrics reports are missing or unreadable")

        configurations = [
            sender_report.get("effective_configuration"),
            receiver_report.get("effective_configuration"),
            proxy_report.get("effective_configuration"),
        ]
        if any(value != configurations[0] for value in configurations[1:]):
            raise RuntimeError("Sender, receiver and proxy effective configurations disagree")
        if receiver_report.get("status") != "completed":
            raise RuntimeError(f"Receiver status: {receiver_report.get('status')}: {receiver_report.get('error')}")
        if not output_path.is_file():
            raise RuntimeError("Receiver did not publish the final output file")

        received_size = output_path.stat().st_size
        received_hash = sha256_file(output_path)
        hash_verified = received_size == source.stat().st_size and received_hash == result["source_sha256"]
        if not hash_verified or receiver_report.get("integrity_verified") is not True:
            raise RuntimeError("Byte-count or SHA-256 integrity verification failed")

        _merge_reports(result, sender_report, receiver_report, proxy_report)
        result["received_size"] = received_size
        result["received_sha256"] = received_hash
        result["hash_verified"] = True
        result["status"] = "success"
        result["error"] = ""
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if proxy_process is not None and proxy_process.poll() is None:
            try:
                request_shutdown(host="127.0.0.1", port=proxy_port)
                proxy_process.wait(timeout=5)
            except Exception:
                _stop_process(proxy_process)
        if receiver_process is not None and receiver_process.poll() is None:
            _stop_process(receiver_process)
        _release_ports(*(port for port in (receiver_port, proxy_port) if port is not None))

        # Preserve every available process report, including partial/failing runs.
        sender_report = _load_json(sender_metrics_path)
        receiver_report = _load_json(receiver_metrics_path)
        proxy_report = _load_json(proxy_metrics_path)
        _merge_reports(result, sender_report, receiver_report, proxy_report)
        if result["status"] != "success":
            result["throughput"] = ""
            result["completion_time"] = result.get("completion_time", "")
            result["hash_verified"] = False

    return result


def run_experiment(protocol: str, filename: str, loss: float, window: int, run: int,
                   *, timeout: float = 0.05, seed: int = 0) -> dict[str, Any]:
    """Compatibility helper for a single data/ACK loss experiment."""
    task = ExperimentTask(
        tier="custom", fault_matrix="loss", protocol=protocol, file_name=filename,
        window=window, trial=run, seed=seed + run - 1, timeout=timeout,
        faults=_faults(data_loss_rate=loss, ack_loss_rate=loss),
    )
    return run_single_experiment(task)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("smoke", "quick", "full"), default="smoke")
    parser.add_argument("--protocol", action="append", choices=PROTOCOLS, help="Filter; repeatable")
    parser.add_argument("--file", action="append", dest="files", choices=TEST_FILES, help="Filter; repeatable")
    parser.add_argument("--loss", action="append", type=float, help="Filter data-loss rate; repeatable")
    parser.add_argument("--matrix", action="append", choices=(
        "loss", "delay", "reordering", "corruption", "duplication", "timeout", "combined"
    ), help="Run selected experiment matrix; repeatable")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent transfers; use 1-2 for timing matrices")
    parser.add_argument("--seed", type=int, default=20261113, help="Base seed; run seeds increment by run number")
    parser.add_argument("--results-file", type=Path, default=RESULT_FILE)
    parser.add_argument("--run-root", type=Path, default=RUNS_DIR)
    parser.add_argument("--overwrite", action="store_true",
                        help="replace the selected results CSV and derived analysis outputs")
    parser.add_argument("--dry-run", action="store_true", help="Print matrix size/configuration without running")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    tasks = build_tasks(args.tier, args.seed)
    if args.protocol:
        tasks = [task for task in tasks if task.protocol in args.protocol]
    if args.files:
        tasks = [task for task in tasks if task.file_name in args.files]
    if args.loss is not None:
        tasks = [task for task in tasks if any(abs(task.faults.get("data_loss_rate", 0.0) - value) < 1e-12 for value in args.loss)]
    if args.matrix:
        tasks = [task for task in tasks if task.fault_matrix in args.matrix]
    if not tasks:
        raise SystemExit("No experiment tasks remain after applying filters")
    print(f"Tier={args.tier}; attempts={len(tasks)}; workers={args.workers}; seed_base={args.seed}")
    if args.workers > 2:
        print("WARNING: more than two workers can distort timing measurements through CPU contention.")
    if args.dry_run:
        by_matrix: dict[str, int] = {}
        for task in tasks:
            by_matrix[task.fault_matrix] = by_matrix.get(task.fault_matrix, 0) + 1
        print(json.dumps(by_matrix, indent=2))
        return 0

    args.results_file = args.results_file.resolve()
    args.run_root = args.run_root.resolve()
    if args.overwrite:
        args.results_file.unlink(missing_ok=True)
        (ROOT / "data" / "results" / "aggregated_results.csv").unlink(missing_ok=True)
        (ROOT / "data" / "results" / "fault_rate_comparison.csv").unlink(missing_ok=True)
        shutil.rmtree(ROOT / "docs" / "graphs", ignore_errors=True)
    elif args.results_file.exists():
        validate_schema(args.results_file)
    failed = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_single_experiment, task, run_root=args.run_root): task
            for task in tasks
        }
        for completed_count, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                row = future.result()
            except Exception as error:  # Defensive: each attempt should normally return a failure row.
                row = _base_result(task, f"runner-error-{uuid.uuid4().hex[:8]}", TEST_DIR / task.file_name)
                row["error"] = f"Runner exception: {type(error).__name__}: {error}"
            save_result(row, args.results_file)
            if row["status"] != "success":
                failed += 1
            print(
                f"[{completed_count}/{len(tasks)}] {row['status'].upper()} "
                f"{task.protocol} {task.file_name} {task.fault_matrix} trial={task.trial} "
                f"seed={task.seed}"
            )
    elapsed = time.perf_counter() - started
    print(f"Completed {len(tasks)} attempts in {elapsed:.2f}s; failures={failed}")
    print(f"Results: {args.results_file}")
    from experiments.analysis import analyze
    summary, plots = analyze(args.results_file)
    print(f"Analysis configurations: {len(summary)}; plots generated: {len(plots)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
