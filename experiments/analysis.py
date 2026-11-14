"""Summarize every attempted run and plot only byte-verified successes."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from experiments.plots import generate_plots
from experiments.results import RESULT_FILE

SUMMARY_FILE = Path("data/results/aggregated_results.csv")

CONFIGURATION_KEYS = [
    "tier", "fault_matrix", "protocol", "file_name", "file_size", "window",
    "chunk_size", "timeout", "data_loss_rate", "data_corruption_rate", "data_delay",
    "data_duplicate_rate", "data_reorder_rate", "data_reorder_delay", "ack_loss_rate",
    "ack_corruption_rate", "ack_delay", "ack_duplicate_rate", "ack_reorder_rate",
    "ack_reorder_delay",
]
PERFORMANCE_METRICS = ("completion_time", "throughput", "retransmissions")


def _as_bool(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def load_results(csv_file: str | Path = RESULT_FILE) -> pd.DataFrame:
    path = Path(csv_file)
    if not path.is_file():
        raise FileNotFoundError(f"Experiment results not found: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError("Experiment results CSV has no run rows")
    required = {"run_id", "status", "hash_verified", *CONFIGURATION_KEYS, *PERFORMANCE_METRICS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Experiment results CSV is missing required columns: {sorted(missing)}")

    frame["hash_verified_bool"] = _as_bool(frame["hash_verified"])
    frame["verified_success"] = frame["status"].astype(str).str.lower().eq("success") & frame["hash_verified_bool"]
    for column in (
        "file_size", "window", "chunk_size", "timeout", "data_loss_rate",
        "data_corruption_rate", "data_delay", "data_duplicate_rate", "data_reorder_rate",
        "data_reorder_delay", "ack_loss_rate", "ack_corruption_rate", "ack_delay",
        "ack_duplicate_rate", "ack_reorder_rate", "ack_reorder_delay",
        *PERFORMANCE_METRICS,
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def aggregate_results(frame: pd.DataFrame, summary_file: str | Path = SUMMARY_FILE) -> pd.DataFrame:
    """Keep failed attempts in denominators; summarize performance only for verified rows."""
    keys = [column for column in CONFIGURATION_KEYS if column in frame.columns]
    counts = (
        frame.groupby(keys, dropna=False, as_index=False)
        .agg(
            attempt_count=("run_id", "size"),
            success_count=("verified_success", "sum"),
        )
    )
    counts["success_rate"] = counts["success_count"] / counts["attempt_count"]

    successful = frame[frame["verified_success"]].copy()
    if successful.empty:
        summary = counts
    else:
        aggregations = {}
        for metric in PERFORMANCE_METRICS:
            aggregations[f"{metric}_median"] = (metric, "median")
            aggregations[f"{metric}_q1"] = (metric, lambda values: values.quantile(0.25))
            aggregations[f"{metric}_q3"] = (metric, lambda values: values.quantile(0.75))
            aggregations[f"{metric}_iqr"] = (
                metric,
                lambda values: values.quantile(0.75) - values.quantile(0.25),
            )
        performance = successful.groupby(keys, dropna=False, as_index=False).agg(**aggregations)
        summary = counts.merge(performance, on=keys, how="left")

    destination = Path(summary_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(destination, index=False)
    return summary



def fault_rate_comparison(
    frame: pd.DataFrame,
    output_file: str | Path = "data/results/fault_rate_comparison.csv",
) -> pd.DataFrame:
    """Compare configured fault parameters with observed event rates per direction.

    Delay has different units from probability: its configured value is seconds,
    while its realized value is the fraction of incoming datagrams assigned delay.
    The output labels units explicitly rather than comparing unlike quantities.
    """
    mappings = {
        "loss": ("loss_rate", "realized_loss_rate", "probability"),
        "corruption": ("corruption_rate", "realized_corruption_rate", "probability"),
        "duplication": ("duplicate_rate", "realized_duplicate_rate", "probability"),
        "reordering": ("reorder_rate", "realized_reorder_rate", "probability"),
        "delay": ("delay", "realized_delay_rate", "seconds"),
    }
    rows: list[dict[str, object]] = []
    for direction in ("data", "ack"):
        for matrix, (configured_suffix, realized_suffix, unit) in mappings.items():
            configured_column = f"{direction}_{configured_suffix}"
            realized_column = f"{direction}_{realized_suffix}"
            if configured_column not in frame or realized_column not in frame:
                continue
            subset = frame[frame["fault_matrix"] == matrix].copy()
            if subset.empty:
                continue
            subset[configured_column] = pd.to_numeric(subset[configured_column], errors="coerce")
            subset[realized_column] = pd.to_numeric(subset[realized_column], errors="coerce")
            for configured, group in subset.groupby(configured_column, dropna=False):
                observed = group[realized_column].dropna()
                rows.append({
                    "fault_matrix": matrix,
                    "direction": direction,
                    "configured_value": configured,
                    "configured_unit": unit,
                    "observed_runs": int(observed.count()),
                    "attempted_runs": int(len(group)),
                    "realized_event_rate_mean": float(observed.mean()) if not observed.empty else None,
                    "realized_event_rate_median": float(observed.median()) if not observed.empty else None,
                    "realized_event_rate_q1": float(observed.quantile(0.25)) if not observed.empty else None,
                    "realized_event_rate_q3": float(observed.quantile(0.75)) if not observed.empty else None,
                })
    comparison = pd.DataFrame(rows, columns=[
        "fault_matrix", "direction", "configured_value", "configured_unit",
        "observed_runs", "attempted_runs", "realized_event_rate_mean",
        "realized_event_rate_median", "realized_event_rate_q1", "realized_event_rate_q3",
    ])
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(destination, index=False)
    return comparison

def analyze(
    csv_file: str | Path = RESULT_FILE,
    summary_file: str | Path = SUMMARY_FILE,
    graph_dir: str | Path = "docs/graphs",
) -> tuple[pd.DataFrame, list[Path]]:
    frame = load_results(csv_file)
    summary = aggregate_results(frame, summary_file)
    fault_rate_comparison(frame, Path(summary_file).parent / "fault_rate_comparison.csv")
    plots = generate_plots(frame, graph_dir)
    return summary, plots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=RESULT_FILE)
    parser.add_argument("--summary", type=Path, default=SUMMARY_FILE)
    parser.add_argument("--graph-dir", type=Path, default=Path("docs/graphs"))
    args = parser.parse_args()
    frame = load_results(args.csv)
    summary = aggregate_results(frame, args.summary)
    comparison = fault_rate_comparison(frame, args.summary.parent / "fault_rate_comparison.csv")
    plots = generate_plots(frame, args.graph_dir)
    attempts = len(frame)
    successes = int(frame["verified_success"].sum())
    print(f"Attempts: {attempts}; verified successes: {successes}; success rate: {successes / attempts:.1%}")
    print(f"Configuration summaries: {len(summary)}")
    print(f"Summary CSV: {args.summary}")
    print(f"Fault-rate comparison rows: {len(comparison)}")
    print(f"Plots generated: {len(plots)} in {args.graph_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
