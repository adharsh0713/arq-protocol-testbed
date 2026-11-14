import csv

import pytest

from experiments.results import FIELDS, save_result, validate_schema


def test_failed_attempt_is_written_with_full_frozen_header(tmp_path):
    output = tmp_path / "results.csv"
    save_result({"run_id": "r1", "status": "failed", "error": "sender timeout"}, output)
    validate_schema(output)
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"] == "sender timeout"
    assert rows[0]["throughput"] == ""
    assert rows[0]["data_packets_seen"] == ""
    assert len(FIELDS) == len(set(FIELDS))


def test_result_writer_rejects_unknown_fields(tmp_path):
    with pytest.raises(ValueError, match="outside frozen CSV schema"):
        save_result({"unexpected_metric": 1}, tmp_path / "results.csv")
