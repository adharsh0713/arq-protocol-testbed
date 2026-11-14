import pandas as pd

from experiments.analysis import aggregate_results


def test_aggregation_counts_failures_but_only_uses_verified_runs_for_performance(tmp_path):
    common = {
        "tier": "quick", "fault_matrix": "loss", "protocol": "selective_repeat",
        "file_name": "medium.txt", "file_size": 1000, "window": 4,
        "chunk_size": 4096, "timeout": 0.05, "data_loss_rate": 0.1,
        "data_corruption_rate": 0.0, "data_delay": 0.0, "data_duplicate_rate": 0.0,
        "data_reorder_rate": 0.0, "data_reorder_delay": 0.02, "ack_loss_rate": 0.1,
        "ack_corruption_rate": 0.0, "ack_delay": 0.0, "ack_duplicate_rate": 0.0,
        "ack_reorder_rate": 0.0, "ack_reorder_delay": 0.02,
    }
    frame = pd.DataFrame([
        {**common, "run_id": "ok1", "verified_success": True,
         "completion_time": 1.0, "throughput": 1000.0, "retransmissions": 2},
        {**common, "run_id": "ok2", "verified_success": True,
         "completion_time": 3.0, "throughput": 500.0, "retransmissions": 4},
        {**common, "run_id": "bad", "verified_success": False,
         "completion_time": None, "throughput": None, "retransmissions": None},
    ])
    summary = aggregate_results(frame, tmp_path / "summary.csv")
    row = summary.iloc[0]
    assert row["attempt_count"] == 3
    assert row["success_count"] == 2
    assert row["success_rate"] == 2 / 3
    assert row["completion_time_median"] == 2.0
    assert row["completion_time_iqr"] == 1.0
    assert row["throughput_median"] == 750.0
    assert (tmp_path / "summary.csv").is_file()


def test_fault_rate_comparison_keeps_data_and_ack_directions_separate(tmp_path):
    from experiments.analysis import fault_rate_comparison

    frame = pd.DataFrame([
        {"fault_matrix": "loss", "data_loss_rate": 0.1,
         "data_realized_loss_rate": 0.08, "ack_loss_rate": 0.1,
         "ack_realized_loss_rate": 0.12},
        {"fault_matrix": "loss", "data_loss_rate": 0.1,
         "data_realized_loss_rate": 0.10, "ack_loss_rate": 0.1,
         "ack_realized_loss_rate": 0.08},
    ])
    output = tmp_path / "fault_comparison.csv"
    comparison = fault_rate_comparison(frame, output)
    assert len(comparison) == 2
    data_row = comparison[comparison["direction"] == "data"].iloc[0]
    ack_row = comparison[comparison["direction"] == "ack"].iloc[0]
    assert data_row["realized_event_rate_mean"] == 0.09
    assert ack_row["realized_event_rate_mean"] == 0.10
    assert data_row["configured_unit"] == "probability"
    assert output.is_file()


def test_plots_are_generated_only_from_verified_rows(tmp_path):
    from experiments.plots import generate_plots

    rows = []
    for matrix, rate_column, rates in (
        ("loss", "data_loss_rate", (0.0, 0.1, 0.2)),
        ("reordering", "data_reorder_rate", (0.0, 0.1, 0.2)),
        ("delay", "data_delay", (0.0, 0.02)),
        ("timeout", "timeout", (0.01, 0.05, 0.1)),
        ("combined", "data_loss_rate", (0.05,)),
    ):
        for protocol, window in (("stop_wait", 1), ("go_back_n", 4), ("selective_repeat", 4)):
            for rate in rates:
                for trial in range(2):
                    row = {
                        "fault_matrix": matrix, "file_name": "medium.txt", "protocol": protocol,
                        "window": window, "status": "success", "hash_verified": True,
                        "completion_time": 1.0 + trial, "throughput": 1000.0 - trial,
                        "retransmissions": float(trial), "run_id": f"{matrix}-{protocol}-{rate}-{trial}",
                        "data_loss_rate": 0.0, "data_reorder_rate": 0.0, "data_delay": 0.0,
                        "timeout": 0.05,
                    }
                    row[rate_column] = rate
                    rows.append(row)
    # A failed combined-fault trial must reduce success rate but never enter performance plots.
    rows.append({**rows[-1], "run_id": "failed", "status": "failed", "hash_verified": False,
                 "completion_time": None, "throughput": None, "retransmissions": None})
    frame = pd.DataFrame(rows)
    generated = generate_plots(frame, tmp_path / "graphs")
    names = {path.name for path in generated}
    assert "completion_time_vs_loss.png" in names
    assert "throughput_vs_window.png" in names
    assert "completion_time_under_reordering.png" in names
    assert "three_protocol_comparison.png" in names
    assert "completion_time_variability.png" in names
    assert "timeout_sensitivity.png" in names
    assert "combined_fault_success_rate.png" in names


def test_fault_rate_comparison_labels_delay_units_separately(tmp_path):
    from experiments.analysis import fault_rate_comparison

    frame = pd.DataFrame([
        {"fault_matrix": "delay", "data_delay": 0.02,
         "data_realized_delay_rate": 0.9, "ack_delay": 0.02,
         "ack_realized_delay_rate": 0.8},
    ])
    comparison = fault_rate_comparison(frame, tmp_path / "delay.csv")
    assert set(comparison["direction"]) == {"data", "ack"}
    assert set(comparison["configured_unit"]) == {"seconds"}
    assert comparison["realized_event_rate_mean"].tolist() == [0.9, 0.8]
