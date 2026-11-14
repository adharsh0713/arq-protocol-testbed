# Changelog

## Unreleased — Milestone 4 release candidate

- Added packet-format, architecture, Stop-and-Wait, Go-Back-N, and Selective Repeat diagrams.
- Added evidence-bounded benchmark report with explicit inconclusive status for research questions not supported by the current smoke dataset.
- Added demo storyboard, v1.0 release checklist, and GitHub repository metadata.
- Executed and retained a fresh six-transfer smoke matrix with byte-count and SHA-256 verification.
- Prepared the full-matrix instructions; the 905-attempt run and final v1.0 publication remain release gates.

## Milestone 3 — Experimental framework

- Added deterministic small/medium/large text, PNG, and WAV fixtures.
- Added smoke, quick, and full experiment tiers with deterministic seeds and per-run isolation.
- Added sender, receiver, and proxy metrics; failure-aware CSV persistence; median/IQR analysis; and reproducible plots.
- Added fast and slow integration tests plus CI smoke validation.

## Milestones 1–2 — Protocol and network implementation

- Implemented Stop-and-Wait, Go-Back-N, and Selective Repeat over a fixed binary UDP packet format.
- Added CRC32 validation, retransmission timers, receiver window handling, and END handshake.
- Added deterministic bidirectional fault injection, scheduled delivery, reordering, and proxy statistics.
