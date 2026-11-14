from pathlib import Path

from scripts.verify_release import ROOT, audit_docs, audit_results


def test_release_docs_preflight_is_complete():
    assert audit_docs(ROOT) == []


def test_smoke_csv_does_not_pass_the_full_evidence_gate():
    errors = audit_results(ROOT / "data/results/experiment_results.csv", ROOT)
    assert any("Expected 905 attempts" in error for error in errors)
    assert any("Matrix counts mismatch" in error for error in errors)
