# v1.0 Release Checklist

A release is created only after every required research and correctness gate is satisfied.

## Implementation and tests

- [x] All three ARQ senders and the receiver implement the documented ACK/window behavior.
- [x] Proxy supports seeded loss, corruption, delay, duplication, and reordering in both directions.
- [x] Receiver publishes `.part` output only after valid END and configured integrity checks.
- [x] Default fast pytest suite: 102 passed, 18 slow tests deselected in the M4 working tree (the archived M3 source remains 100 passed, 18 deselected).
- [x] Extended slow process-level and file-boundary cases passed in the M3 validation report.
- [x] Smoke matrix: 6/6 successful, byte-count and SHA-256 verified in the current M4 run.

## Research and evidence

- [ ] Execute all 905 pre-registered full-matrix attempts.
- [ ] Confirm that the result CSV includes every attempt, including failures, and has the frozen schema.
- [ ] Re-run `python -m experiments.analysis` from the committed CSV.
- [ ] Review median, Q1, Q3, IQR and success rate for every matched configuration.
- [ ] Complete all six entries in `BENCHMARKS.md` as confirmed, refuted, or inconclusive.
- [ ] Verify that every figure in `docs/graphs/` is generated from the final CSV and is listed in `plots_manifest.json`.
- [ ] Keep unsupported or inconclusive claims in `LIMITATIONS.md`.

## Documentation and repository hygiene

- [x] `README.md`, `PROTOCOL_SPEC.md`, `FAULT_MODEL.md`, `ARCHITECTURE.md`, `EXPERIMENT_METHODOLOGY.md`, `BENCHMARKS.md`, and `LIMITATIONS.md` exist.
- [x] Packet format, architecture, and three ARQ sequence diagrams are documented.
- [x] Decision rationale and interview preparation are included.
- [x] MIT license and GitHub description/topics are prepared.
- [x] Demo recording script and storyboard are prepared.
- [ ] Record and review the 2–3 minute demonstration video.
- [ ] Re-run test suite and release verifier from a clean checkout.

## GitHub publication (requires repository access)

```bash
git status --short
git add README.md LICENSE CHANGELOG.md .gitignore .github docs data/results/experiment_results.csv data/results/aggregated_results.csv data/results/fault_rate_comparison.csv
git add docs/graphs/*.png docs/graphs/plots_manifest.json
git commit -m "Prepare Reliable UDP v1.0 release"
git tag -a v1.0 -m "Reliable UDP ARQ testbed v1.0"
git push origin main --tags
```

Then create a GitHub Release for tag `v1.0` and attach the final CSV, generated figures, and demo MP4. Do not run these commands until all unchecked research/release items pass. No remote push or tag is performed by this project workspace.
