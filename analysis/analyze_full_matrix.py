#!/usr/bin/env python3
"""Rebuild the corrected Reliable UDP RQ1-RQ6 analysis from run-level CSV data."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

EXPECTED = {"loss": 200, "delay": 140, "reordering": 200, "corruption": 100,
            "duplication": 100, "timeout": 90, "combined": 75}
PROTOCOLS = ["stop_wait", "go_back_n", "selective_repeat"]
LABELS = {"stop_wait": "Stop-and-Wait", "go_back_n": "Go-Back-N", "selective_repeat": "Selective Repeat"}


def summary(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(keys, dropna=False, sort=True):
        if not isinstance(key, tuple): key = (key,)
        row = dict(zip(keys, key))
        good = group[group.status.eq("success")]
        row.update(attempts=len(group), successes=len(good), failures=len(group)-len(good),
                   success_rate=len(good)/len(group))
        for metric in ["completion_time", "throughput", "retransmissions"]:
            values = good[metric].dropna()
            q1 = values.quantile(.25) if len(values) else np.nan
            q3 = values.quantile(.75) if len(values) else np.nan
            row[f"{metric}_median"] = values.median() if len(values) else np.nan
            row[f"{metric}_q1"] = q1
            row[f"{metric}_q3"] = q3
            row[f"{metric}_iqr"] = q3-q1 if len(values) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def correlation_table(df: pd.DataFrame, group_cols: list[str], x: str, y: str) -> pd.DataFrame:
    rows=[]
    for key,g in df[df.status.eq("success")].groupby(group_cols, dropna=False, sort=True):
        if not isinstance(key, tuple): key=(key,)
        vals=g[[x,y]].dropna()
        if len(vals) >= 3 and vals[x].nunique() > 1 and vals[y].nunique() > 1:
            test=stats.spearmanr(vals[x], vals[y])
            rho,p=float(test.statistic),float(test.pvalue)
        else: rho,p=np.nan,np.nan
        rows.append({**dict(zip(group_cols,key)),"n_success":len(vals),"spearman_rho":rho,"p_value":p})
    return pd.DataFrame(rows)


def audit(raw: pd.DataFrame, agg: pd.DataFrame, fault: pd.DataFrame) -> dict:
    full=raw[raw.tier.eq("full")].copy(); smoke=raw[raw.tier.eq("smoke")].copy()
    task_cols=["fault_matrix","protocol","file_name","window","chunk_size","timeout","max_retries",
      "data_loss_rate","data_corruption_rate","data_delay","data_duplicate_rate","data_reorder_rate","data_reorder_delay",
      "ack_loss_rate","ack_corruption_rate","ack_delay","ack_duplicate_rate","ack_reorder_rate","ack_reorder_delay","trial"]
    critical=["run_id","timestamp_utc","fault_matrix","trial","seed","status","protocol","file_name","file_size",
      "window","chunk_size","timeout","max_retries","source_sha256","git_commit","python_version","os"]
    success=full[full.status.eq("success")]; failed=full[full.status.eq("failed")]
    observed={k:int(v) for k,v in full.fault_matrix.value_counts().items()}
    ordered=full.sort_values("timestamp_utc").reset_index(drop=True)
    expected_seeds=list(range(20261113,20261113+905))
    unique_tasks=int(full[task_cols].drop_duplicates().shape[0])
    # Recompute aggregate table exactly from raw records, including smoke rows.
    group_cols=["tier","fault_matrix","protocol","file_name","file_size","window","chunk_size","timeout",
      "data_loss_rate","data_corruption_rate","data_delay","data_duplicate_rate","data_reorder_rate","data_reorder_delay",
      "ack_loss_rate","ack_corruption_rate","ack_delay","ack_duplicate_rate","ack_reorder_rate","ack_reorder_delay"]
    rec=[]
    for key,g in raw.groupby(group_cols,dropna=False,sort=False):
        if not isinstance(key,tuple): key=(key,)
        row=dict(zip(group_cols,key)); ok=g[g.status.eq("success")]
        row.update(attempt_count=len(g),success_count=len(ok),success_rate=len(ok)/len(g))
        for m in ["completion_time","throughput","retransmissions"]:
            vals=ok[m].dropna(); q1=vals.quantile(.25) if len(vals) else np.nan; q3=vals.quantile(.75) if len(vals) else np.nan
            row[f"{m}_median"]=vals.median() if len(vals) else np.nan
            row[f"{m}_q1"]=q1; row[f"{m}_q3"]=q3; row[f"{m}_iqr"]=q3-q1 if len(vals) else np.nan
        rec.append(row)
    rec=pd.DataFrame(rec)
    merge=agg.merge(rec,on=group_cols,suffixes=("_input","_recalc"),how="outer",indicator=True)
    aggregate_match=bool(merge._merge.eq("both").all())
    agg_metrics=["attempt_count","success_count","success_rate"]+[f"{m}_{q}" for m in ["completion_time","throughput","retransmissions"] for q in ["median","q1","q3","iqr"]]
    agg_max_diff={c:float((merge[f"{c}_input"]-merge[f"{c}_recalc"]).abs().max()) for c in agg_metrics}
    aggregate_match=aggregate_match and all(v < 1e-7 for v in agg_max_diff.values())
    # Recompute the configured-vs-realized fault summary for all tiers.
    fault_maps={"loss":("loss_rate","loss_rate"),"corruption":("corruption_rate","corruption_rate"),
      "delay":("delay","delay_rate"),"duplication":("duplicate_rate","duplicate_rate"),
      "reordering":("reorder_rate","reorder_rate")}
    fr=[]
    for matrix,g in raw[raw.fault_matrix.isin(fault_maps)].groupby("fault_matrix"):
        conf_suffix,real_suffix=fault_maps[matrix]
        for direction in ["data","ack"]:
            conf=f"{direction}_{conf_suffix}"; real=f"{direction}_realized_{real_suffix}"
            for value,x in g.groupby(conf):
                vals=x[real].dropna()
                fr.append({"fault_matrix":matrix,"direction":direction,"configured_value":value,
                  "observed_runs":len(vals),"attempted_runs":len(x),
                  "realized_event_rate_mean":vals.mean(),"realized_event_rate_median":vals.median(),
                  "realized_event_rate_q1":vals.quantile(.25),"realized_event_rate_q3":vals.quantile(.75)})
    fr=pd.DataFrame(fr)
    fmerge=fault.merge(fr,on=["fault_matrix","direction","configured_value"],suffixes=("_input","_recalc"),how="outer",indicator=True)
    fault_match=bool(fmerge._merge.eq("both").all())
    fmetrics=["observed_runs","attempted_runs","realized_event_rate_mean","realized_event_rate_median","realized_event_rate_q1","realized_event_rate_q3"]
    fault_max_diff={c:float((fmerge[f"{c}_input"]-fmerge[f"{c}_recalc"]).abs().max()) for c in fmetrics}
    fault_match=fault_match and all(v < 1e-7 for v in fault_max_diff.values())
    matrix_counts_match=observed==EXPECTED
    ids_unique=bool(raw.run_id.is_unique)
    seeds_sequential=ordered.seed.astype(int).tolist()==expected_seeds
    no_duplicate_tasks=unique_tasks==len(full)
    critical_missing={c:int(full[c].isna().sum()) for c in critical}
    sha_match=int((success.source_sha256==success.received_sha256).sum())
    size_match=int((success.file_size==success.received_size).sum())
    integrity_flags=int((success.hash_verified.eq(True)&success.integrity_verified.eq(True)).sum())
    failed_errors=int(failed.error.notna().sum())
    failed_throughput=int(failed.throughput.notna().sum())
    nested_failure_causes=[]
    for message in failed.error.fillna("").astype(str):
        hits=re.findall(r"(?:^|\n)(TimeoutError|BlockingIOError):", message)
        nested_failure_causes.append(hits[-1] if hits else "Other/unknown")
    failure_cause_counts={k:int(v) for k,v in pd.Series(nested_failure_causes).value_counts().items()}
    equal_directions={suffix:bool((full[f"data_{suffix}"].fillna(-1)==full[f"ack_{suffix}"].fillna(-1)).all())
      for suffix in ["loss_rate","corruption_rate","delay","duplicate_rate","reorder_rate","reorder_delay"]}
    # Trial count checks against the registered point dimensions.
    trial_specs={
      "loss":(["protocol","window","data_loss_rate"],10),
      "delay":(["protocol","window","data_delay"],5),
      "reordering":(["protocol","window","data_reorder_rate"],10),
      "corruption":(["protocol","window","data_corruption_rate"],5),
      "duplication":(["protocol","window","data_duplicate_rate"],5),
      "timeout":(["protocol","timeout"],5),
      "combined":(["protocol","file_name"],5),
    }
    trials={}
    for matrix,(cols,n) in trial_specs.items():
        counts=full[full.fault_matrix.eq(matrix)].groupby(cols,dropna=False).size()
        trials[matrix]={"groups":int(len(counts)),"all_expected_repetitions":bool(counts.eq(n).all()),"repetitions_per_group":n}
    # Registered parameter values and common run controls.
    param_levels={
      "loss":sorted(full[full.fault_matrix.eq("loss")].data_loss_rate.unique().tolist()),
      "delay":sorted(full[full.fault_matrix.eq("delay")].data_delay.unique().tolist()),
      "reordering":sorted(full[full.fault_matrix.eq("reordering")].data_reorder_rate.unique().tolist()),
      "corruption":sorted(full[full.fault_matrix.eq("corruption")].data_corruption_rate.unique().tolist()),
      "duplication":sorted(full[full.fault_matrix.eq("duplication")].data_duplicate_rate.unique().tolist()),
      "timeout":sorted(full[full.fault_matrix.eq("timeout")].timeout.unique().tolist()),
      "combined_files":sorted(full[full.fault_matrix.eq("combined")].file_name.unique().tolist())}
    expected_levels={
      "loss":[0.0,0.05,0.10,0.20], "delay":[0.0,0.005,0.02,0.05],
      "reordering":[0.0,0.05,0.10,0.20], "corruption":[0.0,0.05,0.10,0.20],
      "duplication":[0.0,0.05,0.10,0.20], "timeout":[0.01,0.025,0.05,0.10,0.25,1.0],
      "combined_files":["audio.wav","image.png","large.txt","medium.txt","small.txt"]}
    level_checks={k:bool(np.allclose(param_levels[k],v) if v and isinstance(v[0],(int,float)) else param_levels[k]==v)
      for k,v in expected_levels.items()}
    expected_windows={
      "loss":{"stop_wait":[1],"go_back_n":[4,16],"selective_repeat":[4,16]},
      "delay":{"stop_wait":[1],"go_back_n":[1,4,16],"selective_repeat":[1,4,16]},
      "reordering":{"stop_wait":[1],"go_back_n":[4,16],"selective_repeat":[4,16]},
      "corruption":{"stop_wait":[1],"go_back_n":[4,16],"selective_repeat":[4,16]},
      "duplication":{"stop_wait":[1],"go_back_n":[4,16],"selective_repeat":[4,16]},
      "timeout":{"stop_wait":[1],"go_back_n":[4],"selective_repeat":[4]},
      "combined":{"stop_wait":[1],"go_back_n":[4],"selective_repeat":[4]}}
    observed_windows={m:{p:sorted(int(v) for v in full[(full.fault_matrix==m)&(full.protocol==p)].window.unique()) for p in expected_windows[m]} for m in expected_windows}
    window_checks={m:observed_windows[m]==expected_windows[m] for m in expected_windows}
    expected_sizes={"small.txt":8192,"medium.txt":262144,"large.txt":1048576,"image.png":36865,"audio.wav":16044}
    size_checks=all(set(full[full.file_name.eq(name)].file_size.astype(int).unique())=={size} for name,size in expected_sizes.items())
    common_controls=bool(full.chunk_size.eq(4096).all() and full.max_retries.eq(15).all())
    constant_timeout_matrices=bool(full[~full.fault_matrix.eq("timeout")].timeout.eq(0.05).all())
    isolated_checks={}
    prob_fields=["loss_rate","corruption_rate","duplicate_rate","reorder_rate"]
    for m in ["loss","delay","reordering","corruption","duplication"]:
        g=full[full.fault_matrix.eq(m)]
        active={"loss":"loss_rate","delay":"delay","reordering":"reorder_rate","corruption":"corruption_rate","duplication":"duplicate_rate"}[m]
        others=[x for x in prob_fields if x!=active]
        zeros=all(g[f"{d}_{x}"].eq(0).all() for d in ["data","ack"] for x in others)
        if m!="delay": zeros=zeros and g.data_delay.eq(0).all() and g.ack_delay.eq(0).all()
        isolated_checks[m]=bool(zeros)
    timeout_rows=full[full.fault_matrix.eq("timeout")]
    timeout_config=bool(timeout_rows.data_loss_rate.eq(.10).all() and timeout_rows.ack_loss_rate.eq(.10).all() and
      all(timeout_rows[f"{d}_{x}"].eq(0).all() for d in ["data","ack"] for x in ["corruption_rate","delay","duplicate_rate","reorder_rate"]))
    combined_rows=full[full.fault_matrix.eq("combined")]
    combined_config=bool(combined_rows.data_loss_rate.eq(.05).all() and combined_rows.ack_loss_rate.eq(.05).all() and
      combined_rows.data_corruption_rate.eq(.02).all() and combined_rows.ack_corruption_rate.eq(.02).all() and
      combined_rows.data_delay.eq(.005).all() and combined_rows.ack_delay.eq(.005).all() and
      combined_rows.data_duplicate_rate.eq(.02).all() and combined_rows.ack_duplicate_rate.eq(.02).all() and
      combined_rows.data_reorder_rate.eq(.02).all() and combined_rows.ack_reorder_rate.eq(.02).all())
    design_checks={"parameter_levels_match_preregistration":all(level_checks.values()),
      "parameter_level_details":level_checks,"window_allocations_match_preregistration":all(window_checks.values()),
      "window_allocation_details":window_checks,"fixture_sizes_match_expected":size_checks,
      "chunk_size_4096_and_max_retries_15":common_controls,"timeout_50ms_for_non_timeout_matrices":constant_timeout_matrices,
      "isolated_fault_matrices_have_other_faults_disabled":all(isolated_checks.values()),
      "timeout_matrix_has_symmetric_10pct_loss_and_no_other_faults":timeout_config,
      "combined_matrix_matches_registered_fault_values":combined_config,
      "data_ack_fault_parameters_match":all(equal_directions.values()),
      "all_trial_repetitions_match":all(v["all_expected_repetitions"] for v in trials.values())}
    return {
      "raw_rows":int(len(raw)),"full_attempts":int(len(full)),"smoke_attempts":int(len(smoke)),
      "full_successes":int(len(success)),"full_failures":int(len(failed)),"full_success_rate":float(len(success)/len(full)),
      "matrix_expected":EXPECTED,"matrix_observed":observed,"matrix_counts_match":matrix_counts_match,
      "unique_run_ids":int(raw.run_id.nunique()),"duplicate_run_ids":int(raw.run_id.duplicated().sum()),
      "unique_full_seeds":int(full.seed.nunique()),"seeds_sequential_by_timestamp":seeds_sequential,
      "unique_task_combinations":unique_tasks,"duplicate_task_combinations":int(len(full)-unique_tasks),
      "critical_missing_values":critical_missing,"successful_sha256_equal":sha_match,
      "successful_size_equal":size_match,"successful_integrity_flags_true":integrity_flags,
      "failed_rows_with_error":failed_errors,"failed_rows_with_throughput":failed_throughput,
      "nested_failure_cause_counts":failure_cause_counts,
      "same_data_ack_config_by_fault_family":equal_directions,
      "trial_repetition_checks":trials,"observed_parameter_levels":param_levels,
      "observed_protocol_windows":observed_windows,"registered_design_checks":design_checks,
      "csv_column_count":int(len(raw.columns)),"duplicate_column_names":int(raw.columns.duplicated().sum()),
      "git_commit_values":full.git_commit.value_counts(dropna=False).to_dict(),
      "python_versions":full.python_version.value_counts(dropna=False).to_dict(),
      "operating_systems":full.os.value_counts(dropna=False).to_dict(),
      "machine_names":full.machine_name.value_counts(dropna=False).to_dict(),
      "aggregate_rows":int(len(agg)),"aggregate_recomputed_match":aggregate_match,"aggregate_max_abs_differences":agg_max_diff,
      "fault_rate_rows":int(len(fault)),"fault_rate_recomputed_match":fault_match,"fault_rate_max_abs_differences":fault_max_diff,
      "per_run_process_reports_in_uploaded_archive":False,
      "source_fixture_files_and_manifest_in_uploaded_archive":False,
      "source_commit_provenance_complete":bool(full.git_commit.notna().all() and not full.git_commit.astype(str).str.lower().isin(["unknown","none",""]).any()),
    }


def make_figures(out: Path, rq1, rq2, rq3, rq5, rq6, fault, reorder_delivery):
    figdir=out/"figures"; figdir.mkdir(parents=True,exist_ok=True)
    # RQ1: one line for each actual protocol/window combination, retaining matched groups.
    fig,ax=plt.subplots(figsize=(9,5.5))
    for _,g in rq1.groupby(["protocol","window"]):
        g=g.sort_values("data_loss_rate")
        label=f"{LABELS[g.protocol.iloc[0]]} (W={int(g.window.iloc[0])})"
        ax.plot(g.data_loss_rate*100,g.throughput_median/1e6,marker="o",label=label)
        ax.fill_between(g.data_loss_rate*100,g.throughput_q1/1e6,g.throughput_q3/1e6,alpha=.12)
    ax.set(title="RQ1 — Packet loss vs verified throughput (matched windows)",xlabel="Configured DATA/ACK loss (%)",ylabel="Median throughput (MB/s)")
    ax.grid(True,alpha=.3); ax.legend(fontsize=8,ncol=2); fig.tight_layout(); fig.savefig(figdir/"rq1_loss_vs_throughput.png",dpi=180); plt.close(fig)
    # RQ2: delay vs throughput. Stop-and-Wait has only W=1; GBN/SR include W=1/4/16.
    fig,axs=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
    for ax,protocol in zip(axs,["go_back_n","selective_repeat"]):
        d=rq2[rq2.protocol.eq(protocol)]
        for w,g in d.groupby("window"):
            g=g.sort_values("data_delay")
            ax.plot(g.data_delay*1000,g.throughput_median/1e6,marker="o",label=f"W={int(w)}")
            ax.fill_between(g.data_delay*1000,g.throughput_q1/1e6,g.throughput_q3/1e6,alpha=.12)
        ax.set(title=LABELS[protocol],xlabel="One-way DATA and ACK delay (ms)",ylabel="Median throughput (MB/s)")
        ax.grid(True,alpha=.3); ax.legend()
    fig.suptitle("RQ2 — Delay × sender window (fixed 50 ms timeout)"); fig.tight_layout(); fig.savefig(figdir/"rq2_delay_window.png",dpi=180); plt.close(fig)
    # RQ3: matched GBN/SR windows, plot throughput and success rate separately.
    fig,axs=plt.subplots(1,2,figsize=(11,4.8),sharex=True)
    for ax,w in zip(axs,[4,16]):
        d=rq3[rq3.window.eq(w)]
        for protocol,g in d.groupby("protocol"):
            g=g.sort_values("data_reorder_rate")
            ax.plot(g.data_reorder_rate*100,g.throughput_median/1e6,marker="o",label=LABELS[protocol])
        ax.set(title=f"Window {w}",xlabel="Configured DATA/ACK reorder probability (%)",ylabel="Median throughput (MB/s)")
        ax.grid(True,alpha=.3); ax.legend()
    fig.suptitle("RQ3 — Go-Back-N vs Selective Repeat under reordering"); fig.tight_layout(); fig.savefig(figdir/"rq3_reordering_windows.png",dpi=180); plt.close(fig)
    # RQ4: probability-based calibration, keeping direction and fault type explicit.
    fig,ax=plt.subplots(figsize=(9,5.6))
    prob=fault[fault.configured_unit.eq("probability")]
    for (matrix,direction),g in prob.groupby(["fault_matrix","direction"]):
        ax.plot(g.configured_value*100,g.realized_event_rate_mean*100,marker="o",label=f"{matrix} / {direction}")
    ax.plot([0,20],[0,20],linestyle="--",label="Ideal y=x")
    ax.set(title="RQ4 — Configured vs realized probability-fault rates",xlabel="Configured probability (%)",ylabel="Mean realized event rate (%)")
    ax.grid(True,alpha=.3); ax.legend(fontsize=7,ncol=2); fig.tight_layout(); fig.savefig(figdir/"rq4_fault_calibration.png",dpi=180); plt.close(fig)
    # RQ5: actual medians + IQR, timeout sweep by protocol.
    fig,ax=plt.subplots(figsize=(8.8,5.4))
    for protocol,g in rq5.groupby("protocol"):
        g=g.sort_values("timeout")
        ax.plot(g.timeout*1000,g.completion_time_median,marker="o",label=LABELS[protocol])
        ax.fill_between(g.timeout*1000,g.completion_time_q1,g.completion_time_q3,alpha=.12)
    ax.set_xscale("log"); ax.set(title="RQ5 — Timeout sensitivity (10% symmetric loss)",xlabel="Timeout (ms, log scale)",ylabel="Median completion time (s)")
    ax.grid(True,alpha=.3); ax.legend(); fig.tight_layout(); fig.savefig(figdir/"rq5_timeout_sensitivity.png",dpi=180); plt.close(fig)
    # RQ6: success rate by file, keeping file sizes separate.
    fig,ax=plt.subplots(figsize=(9.5,5.5))
    pivot=rq6.pivot(index="file_name",columns="protocol",values="success_rate").reindex(["small.txt","medium.txt","large.txt","image.png","audio.wav"])
    pivot.plot(kind="bar",ax=ax)
    ax.set(title="RQ6 — Combined-fault success rate by file type",xlabel="Fixture",ylabel="Successful verified transfers (%)")
    ax.set_yticks([0,.2,.4,.6,.8,1.0],labels=["0","20","40","60","80","100"])
    ax.grid(True,axis="y",alpha=.3); ax.legend([LABELS.get(x,x) for x in pivot.columns]); fig.tight_layout(); fig.savefig(figdir/"rq6_combined_success_by_file.png",dpi=180); plt.close(fig)
    # Overall matrix success rate.
    fig,ax=plt.subplots(figsize=(8.5,4.8))
    mat=pd.read_csv(out/"matrix_success_summary.csv").sort_values("fault_matrix")
    ax.bar(mat.fault_matrix,mat.success_rate*100)
    ax.set(title="Overall full-tier completion rate by fault matrix",xlabel="Matrix",ylabel="Verified success rate (%)",ylim=(0,105))
    ax.tick_params(axis="x",rotation=25); ax.grid(True,axis="y",alpha=.3); fig.tight_layout(); fig.savefig(figdir/"matrix_success_rates.png",dpi=180); plt.close(fig)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="input"); ap.add_argument("--output",default="outputs")
    args=ap.parse_args(); inp=Path(args.input); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    raw=pd.read_csv(inp/"experiment_results.csv"); agg=pd.read_csv(inp/"aggregated_results.csv"); fault=pd.read_csv(inp/"fault_rate_comparison.csv")
    full=raw[raw.tier.eq("full")].copy()
    audit_result=audit(raw,agg,fault)
    (out/"audit.json").write_text(json.dumps(audit_result,indent=2,default=str),encoding="utf-8")
    # Overall status summaries: failure rows stay in denominators.
    ms=full.groupby("fault_matrix").agg(attempts=("status","size"),successes=("status",lambda x:int(x.eq("success").sum())),
      failures=("status",lambda x:int(x.eq("failed").sum()))).reset_index()
    ms["success_rate"]=ms.successes/ms.attempts; ms.to_csv(out/"matrix_success_summary.csv",index=False)
    ps=full.groupby("protocol").agg(attempts=("status","size"),successes=("status",lambda x:int(x.eq("success").sum())),
      failures=("status",lambda x:int(x.eq("failed").sum()))).reset_index()
    ps["success_rate"]=ps.successes/ps.attempts; ps.to_csv(out/"protocol_success_summary.csv",index=False)
    # RQ1: loss by protocol AND window, never pool the two sliding-window settings.
    loss=full[full.fault_matrix.eq("loss")]
    rq1=summary(loss,["protocol","window","data_loss_rate"])
    rq1.to_csv(out/"rq1_loss_by_protocol_window.csv",index=False)
    c1=correlation_table(loss,["protocol","window"],"data_loss_rate","completion_time").rename(columns={"spearman_rho":"loss_vs_completion_rho","p_value":"loss_vs_completion_p"})
    c2=correlation_table(loss,["protocol","window"],"data_loss_rate","retransmissions").rename(columns={"spearman_rho":"loss_vs_retransmissions_rho","p_value":"loss_vs_retransmissions_p"})
    c1.merge(c2,on=["protocol","window"],suffixes=("","_retransmissions")).to_csv(out/"rq1_loss_correlations.csv",index=False)
    # RQ2: the pre-registered delay × window matrix.
    delay=full[full.fault_matrix.eq("delay")]
    rq2=summary(delay,["protocol","window","data_delay"])
    rq2.to_csv(out/"rq2_delay_by_protocol_window.csv",index=False)
    tests=[]
    for protocol in ["go_back_n","selective_repeat"]:
        for dly in sorted(delay.data_delay.unique()):
            sub=delay[delay.protocol.eq(protocol)&delay.data_delay.eq(dly)]
            for wref,wcmp in [(1,4),(4,16),(1,16)]:
                a=sub[(sub.window.eq(wref))&sub.status.eq("success")].throughput.dropna()
                b=sub[(sub.window.eq(wcmp))&sub.status.eq("success")].throughput.dropna()
                p=stats.mannwhitneyu(a,b,alternative="two-sided").pvalue if len(a) and len(b) else np.nan
                tests.append({"protocol":protocol,"one_way_delay_seconds":dly,"reference_window":wref,"comparison_window":wcmp,
                  "reference_success_n":len(a),"comparison_success_n":len(b),"reference_median_throughput_Bps":a.median() if len(a) else np.nan,
                  "comparison_median_throughput_Bps":b.median() if len(b) else np.nan,
                  "comparison_over_reference_ratio":b.median()/a.median() if len(a) and len(b) and a.median()!=0 else np.nan,
                  "mann_whitney_p_successes_only":p})
    pd.DataFrame(tests).to_csv(out/"rq2_window_tests.csv",index=False)
    # RQ3: reordering by protocol AND window.
    reorder=full[full.fault_matrix.eq("reordering")]
    rq3=summary(reorder,["protocol","window","data_reorder_rate"])
    rq3.to_csv(out/"rq3_reordering_by_protocol_window.csv",index=False)
    tests=[]
    for w in [4,16]:
        for rate in sorted(reorder.data_reorder_rate.unique()):
            sub=reorder[reorder.window.eq(w)&reorder.data_reorder_rate.eq(rate)]
            a=sub[(sub.protocol.eq("go_back_n"))&sub.status.eq("success")].throughput.dropna()
            b=sub[(sub.protocol.eq("selective_repeat"))&sub.status.eq("success")].throughput.dropna()
            p=stats.mannwhitneyu(a,b,alternative="two-sided").pvalue if len(a) and len(b) else np.nan
            tests.append({"window":w,"configured_reorder_rate":rate,"GBN_success_n":len(a),"SR_success_n":len(b),
              "GBN_median_throughput_Bps":a.median() if len(a) else np.nan,"SR_median_throughput_Bps":b.median() if len(b) else np.nan,
              "SR_over_GBN_throughput_ratio":b.median()/a.median() if len(a) and len(b) and a.median()!=0 else np.nan,
              "mann_whitney_p_successes_only":p})
    pd.DataFrame(tests).to_csv(out/"rq3_protocol_tests.csv",index=False)
    # RQ4: performance summaries by protocol/window/rate for the two corruption/duplication matrices.
    corruption=full[full.fault_matrix.eq("corruption")]
    duplication=full[full.fault_matrix.eq("duplication")]
    rq4c=summary(corruption,["protocol","window","data_corruption_rate"]); rq4c.to_csv(out/"rq4_corruption_outcomes.csv",index=False)
    rq4d=summary(duplication,["protocol","window","data_duplicate_rate"]); rq4d.to_csv(out/"rq4_duplication_outcomes.csv",index=False)
    fr=fault.copy(); prob=fr[fr.configured_unit.eq("probability")].copy()
    prob["signed_error"]=prob.realized_event_rate_mean-prob.configured_value
    prob["absolute_error"]=prob.signed_error.abs()
    prob.to_csv(out/"rq4_probability_fault_realization.csv",index=False)
    fr[fr.fault_matrix.eq("delay")].to_csv(out/"rq4_delay_event_rates.csv",index=False)
    reorder_delivery=[]
    for matrix in ["reordering"]:
        for d in ["data","ack"]:
            for rate,g in full[full.fault_matrix.eq(matrix)].groupby(f"{d}_reorder_rate"):
                scheduled=g[f"{d}_realized_reorder_rate"].dropna(); actual=g[f"{d}_realized_reorder_delivery_rate"].dropna()
                reorder_delivery.append({"direction":d,"configured_reorder_probability":rate,"attempts":len(g),
                  "mean_selected_for_reorder_hold":scheduled.mean(),"mean_actual_out_of_order_delivery_rate":actual.mean(),
                  "scheduled_median":scheduled.median(),"actual_delivery_median":actual.median()})
    pd.DataFrame(reorder_delivery).to_csv(out/"rq4_reordering_hold_vs_delivery.csv",index=False)
    # RQ5: timeout response by protocol, preserving 5 attempts per point.
    timeout=full[full.fault_matrix.eq("timeout")]
    rq5=summary(timeout,["protocol","timeout"]); rq5.to_csv(out/"rq5_timeout_by_protocol.csv",index=False)
    t1=correlation_table(timeout,["protocol"],"timeout","completion_time").rename(columns={"spearman_rho":"timeout_vs_completion_rho","p_value":"timeout_vs_completion_p"})
    t2=correlation_table(timeout,["protocol"],"timeout","throughput").rename(columns={"spearman_rho":"timeout_vs_throughput_rho","p_value":"timeout_vs_throughput_p"})
    t1.merge(t2,on="protocol",suffixes=("","_throughput")).to_csv(out/"rq5_timeout_correlations.csv",index=False)
    # RQ6: never pool across fixture sizes; report per protocol and file.
    combined=full[full.fault_matrix.eq("combined")]
    rq6=summary(combined,["protocol","file_name","file_size"]); rq6.to_csv(out/"rq6_combined_by_file.csv",index=False)
    # Generate figures and persist compact manifest.
    make_figures(out,rq1,rq2,rq3,rq5,rq6,fault,pd.DataFrame(reorder_delivery))
    manifest={"analysis":"Reliable UDP Milestone 6 corrected research analysis","source_rows":len(raw),"full_attempts":len(full),
      "outputs":sorted([p.name for p in out.glob("*.csv")]),"figures":sorted([p.name for p in (out/"figures").glob("*.png")]),
      "important_interpretation":"RQ1 and RQ3 remain separated by window; RQ2 is delay x window; RQ6 remains separated by file size."}
    (out/"analysis_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({"full_attempts":len(full),"successes":int(full.status.eq("success").sum()),
      "failures":int(full.status.eq("failed").sum()),"audit_matrix_counts_match":audit_result["matrix_counts_match"],
      "aggregate_recomputed_match":audit_result["aggregate_recomputed_match"],"fault_rate_recomputed_match":audit_result["fault_rate_recomputed_match"],
      "source_commit_provenance_complete":audit_result["source_commit_provenance_complete"],"output":str(out)},indent=2))

if __name__=="__main__": main()
