# Milestone 5 Analysis Supersession Notice

The corrected analysis in Milestone 6 supersedes the research interpretations generated in the earlier `Reliable_UDP_Milestone_5_Research_Complete.zip` package.

The earlier analysis used the wrong experiment family for RQ2: the registered question is **delay × sender-window size**, but the earlier report analyzed window-size comparisons from loss and reordering matrices. It also pooled or summarized some RQ1, RQ3 and RQ6 comparisons without consistently preserving the preregistered matched window/file configuration.

Milestone 6 fixes this by:

- analyzing RQ1 by protocol and sender window;
- analyzing RQ2 from the delay matrix by protocol and window;
- analyzing RQ3 by protocol and window under reordering;
- keeping RQ4 probability, delay-duration and actual reordering-delivery measures distinct;
- testing RQ5's U-shaped hypothesis against the actual timeout sweep rather than assuming it;
- analyzing RQ6 per file and protocol, retaining failed attempts.

The earlier package may be retained as a historical artifact, but its RQ tables and conclusions should not be quoted. Use `docs/CORRECTED_BENCHMARKS.md` and its linked CSV tables for research claims.

This notice does not retroactively solve missing source provenance or per-run logs. The current CSV export is internally consistent, but all full-tier `git_commit` values remain `unknown`.
