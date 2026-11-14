# 2–3 Minute Project Demonstration Script

**Recording status:** Script and shot list prepared; no video file has been recorded or published in this workspace.

## Recording setup

Use a terminal in the repository root with the pinned virtual environment active. Use a 1920×1080 screen recording if available, hide unrelated desktop content, and keep terminal font size readable. Do not display credentials or personal paths.

## Timeline and narration

| Time | Screen | Narration / action |
|---|---|---|
| 0:00–0:20 | README title and project overview | “This is an experimental reliable-transfer layer over UDP. It compares Stop-and-Wait, Go-Back-N, and Selective Repeat under controlled packet faults.” |
| 0:20–0:45 | `docs/DIAGRAMS.md`, packet format and architecture | Explain the 11-byte header, CRC32, sender/proxy/receiver process layout, and bidirectional fault injection. |
| 0:45–1:15 | Terminal: `python -m pytest -q` | Show the fast test suite, including the three process-level transfers. Mention that the full matrix is separate from CI. |
| 1:15–1:45 | Terminal: `python -m experiments.runner --tier smoke --workers 1` | Show all three protocols completing and the run CSV being written. Open one run's sender, receiver, and proxy JSON metrics. |
| 1:45–2:20 | `docs/graphs/` and `data/results/` | Open the loss plots and explain the smoke sample count. Explicitly say these are pipeline/correctness plots, not final research evidence. After the full matrix is run, replace this section with `completion_time_under_reordering.png` and `BENCHMARKS.md`'s verified RQ3 comparison. |
| 2:20–2:50 | `docs/LIMITATIONS.md` and release checklist | Explain localhost-only scope, the absence of congestion control/bandwidth shaping, and the full-matrix/release gate. |

## Commands to show

```bash
python -m pytest -q
python -m experiments.runner --tier smoke --workers 1
python -m experiments.analysis
```

## Proxy metrics to show

Open a run directory under `data/results/runs/` and show `proxy.json`'s DATA and ACK direction counters. Point out that configured probability and realized event rate are different fields and that a single small transfer can deviate substantially from the configured percentage.

## Final recording gate

Before presenting an actual GBN-versus-SR reordering result, execute the complete full matrix or at minimum the pre-registered reordering matrix and use its CSV-derived plot. Do not narrate an unmeasured protocol winner. Export a 2–3 minute MP4 and attach it to the final v1.0 GitHub release; the script is not a substitute for that recording.
