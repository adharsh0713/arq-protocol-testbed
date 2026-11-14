"""Reproducible figures generated exclusively from the experiment CSV."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


RATE_FIELDS = {
    "loss": "data_loss_rate",
    "reordering": "data_reorder_rate",
}


def _verified(frame: pd.DataFrame) -> pd.DataFrame:
    verified = frame["hash_verified"].astype(str).str.strip().str.lower().isin({"true", "1", "yes"})
    return frame[(frame["status"].astype(str).str.lower() == "success") & verified].copy()


def _reference_file(frame: pd.DataFrame) -> str | None:
    names = set(frame["file_name"].dropna().astype(str))
    if "medium.txt" in names:
        return "medium.txt"
    return sorted(names)[0] if names else None


def _save_lines(
    data: pd.DataFrame,
    *,
    x: str,
    y: str,
    label_fields: tuple[str, ...],
    xlabel: str,
    ylabel: str,
    title: str,
    destination: Path,
) -> bool:
    if data.empty:
        return False
    grouping = [x, *label_fields]
    grouped = data.groupby(grouping, dropna=False, as_index=False)[y].median()
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for labels, subset in grouped.groupby(list(label_fields), dropna=False):
        if not isinstance(labels, tuple):
            labels = (labels,)
        label = " / ".join(str(value) for value in labels)
        subset = subset.sort_values(x)
        ax.plot(subset[x], subset[y], marker="o", label=label)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return True


def generate_plots(frame: pd.DataFrame, output_dir: str | Path = "docs/graphs") -> list[Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    successful = _verified(frame)
    if successful.empty:
        return []
    reference_file = _reference_file(successful)
    if reference_file is not None:
        successful = successful[successful["file_name"] == reference_file]

    generated: list[Path] = []
    loss = successful[successful["fault_matrix"] == "loss"]
    for metric, ylabel, filename in (
        ("completion_time", "Completion time (s)", "completion_time_vs_loss.png"),
        ("throughput", "Verified throughput (bytes/s)", "throughput_vs_loss.png"),
        ("retransmissions", "DATA retransmission events", "retransmissions_vs_loss.png"),
    ):
        path = destination / filename
        if _save_lines(
            loss, x="data_loss_rate", y=metric, label_fields=("protocol", "window"),
            xlabel="Configured DATA loss rate (ACK loss matched)", ylabel=ylabel,
            title=f"{ylabel} vs loss — {reference_file}", destination=path,
        ):
            generated.append(path)

    delay = successful[successful["fault_matrix"] == "delay"]
    if not delay.empty:
        reference_delay = 0.02 if (delay["data_delay"] == 0.02).any() else float(delay["data_delay"].median())
        selected = delay[delay["data_delay"] == reference_delay]
        grouped = selected.groupby(["window", "protocol"], as_index=False)["throughput"].median()
        if not grouped.empty:
            fig, ax = plt.subplots(figsize=(8.5, 5.2))
            for protocol, subset in grouped.groupby("protocol"):
                subset = subset.sort_values("window")
                ax.plot(subset["window"], subset["throughput"], marker="o", label=protocol)
            ax.set_xlabel("Sender/receiver window size")
            ax.set_ylabel("Verified throughput (bytes/s)")
            ax.set_title(f"Throughput vs window at {reference_delay:g}s one-way delay")
            ax.grid(True, alpha=0.3)
            ax.legend()
            fig.tight_layout()
            path = destination / "throughput_vs_window.png"
            fig.savefig(path, dpi=180, bbox_inches="tight")
            plt.close(fig)
            generated.append(path)

    reorder = successful[successful["fault_matrix"] == "reordering"]
    path = destination / "completion_time_under_reordering.png"
    if _save_lines(
        reorder, x="data_reorder_rate", y="completion_time", label_fields=("protocol", "window"),
        xlabel="Configured DATA reorder rate (ACK reorder matched)", ylabel="Completion time (s)",
        title=f"Protocol performance under reordering — {reference_file}", destination=path,
    ):
        generated.append(path)

    if not loss.empty:
        comparison = loss[loss["data_loss_rate"] == 0.1].copy()
        if comparison.empty:
            target_rate = float(loss["data_loss_rate"].median())
            comparison_rate = float(
                loss.iloc[(loss["data_loss_rate"] - target_rate).abs().argmin()]["data_loss_rate"]
            )
            comparison = loss[loss["data_loss_rate"] == comparison_rate].copy()
        else:
            comparison_rate = 0.1
        chosen = []
        for protocol in sorted(comparison["protocol"].unique()):
            subset = comparison[comparison["protocol"] == protocol]
            preferred_window = 1 if protocol == "stop_wait" else 4
            exact = subset[subset["window"] == preferred_window]
            chosen.append((exact if not exact.empty else subset).copy())
        comparison = pd.concat(chosen, ignore_index=True) if chosen else comparison
        grouped = comparison.groupby("protocol", as_index=False)["completion_time"].median()
        if not grouped.empty:
            fig, ax = plt.subplots(figsize=(7.5, 5.0))
            ax.bar(grouped["protocol"], grouped["completion_time"])
            ax.set_ylabel("Median completion time (s)")
            ax.set_title(f"Three-protocol comparison at matched {comparison_rate:.0%} DATA/ACK loss")
            ax.grid(axis="y", alpha=0.3)
            fig.tight_layout()
            path = destination / "three_protocol_comparison.png"
            fig.savefig(path, dpi=180, bbox_inches="tight")
            plt.close(fig)
            generated.append(path)

        variability = comparison.copy()
        if not variability.empty:
            groups = []
            labels = []
            for (protocol, window), subset in variability.groupby(["protocol", "window"]):
                values = subset["completion_time"].dropna().tolist()
                if values:
                    groups.append(values)
                    labels.append(f"{protocol}\nW={int(window)}")
            if groups:
                fig, ax = plt.subplots(figsize=(9.0, 5.2))
                ax.boxplot(groups, tick_labels=labels, showfliers=True)
                ax.set_ylabel("Completion time (s)")
                ax.set_title("Run-to-run variability — verified trials only")
                ax.grid(axis="y", alpha=0.3)
                fig.tight_layout()
                path = destination / "completion_time_variability.png"
                fig.savefig(path, dpi=180, bbox_inches="tight")
                plt.close(fig)
                generated.append(path)

    timeout = successful[successful["fault_matrix"] == "timeout"]
    if not timeout.empty:
        grouped = timeout.groupby(["timeout", "protocol"], as_index=False)["completion_time"].median()
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        for protocol, subset in grouped.groupby("protocol"):
            subset = subset.sort_values("timeout")
            ax.plot(subset["timeout"], subset["completion_time"], marker="o", label=protocol)
        ax.set_xscale("log")
        ax.set_xlabel("Configured retransmission timeout (s, log scale)")
        ax.set_ylabel("Median completion time (s)")
        ax.set_title("Timeout sensitivity at 10% DATA/ACK loss")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        path = destination / "timeout_sensitivity.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        generated.append(path)

    combined = frame[frame["fault_matrix"] == "combined"].copy()
    if not combined.empty:
        verified_indices = set(_verified(combined).index)
        combined["verified_success"] = combined.index.isin(verified_indices)
        grouped = combined.groupby(["file_name", "protocol"], as_index=False).agg(
            attempts=("run_id", "size"), successes=("verified_success", "sum")
        )
        grouped["success_rate"] = grouped["successes"] / grouped["attempts"]
        fig, ax = plt.subplots(figsize=(10, 5.5))
        pivot = grouped.pivot(index="file_name", columns="protocol", values="success_rate")
        pivot.plot(kind="bar", ax=ax)
        ax.set_xlabel("Transferred file type")
        ax.set_ylabel("Verified success rate")
        ax.set_ylim(0, 1.05)
        ax.set_title("Integrity-verified success under combined faults")
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        path = destination / "combined_fault_success_rate.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        generated.append(path)

    manifest = {"source": "experiment_results.csv", "verified_rows_used": int(len(successful)),
                "plots": [path.name for path in generated]}
    (destination / "plots_manifest.json").write_text(
        pd.Series(manifest).to_json(indent=2), encoding="utf-8"
    )
    return generated
