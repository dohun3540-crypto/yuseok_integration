"""Real joined modules over archived/synthetic inputs, never current live proof."""
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import Workbook

from leadtime_guardian.qa.input_delivery import _typed_json_equal
from leadtime_guardian.strict_json import loads_strict
from qa.integration import audit_integration, compare_candidate
from qa.inventory import collect

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "qa/gold_candidates/SYN-C001/candidate.v1.json"
NATIVE = ROOT / "data/results/studio_runs/C001_20261030_v4/instruct_original.json"


def run(**overrides):
    raw = NATIVE.read_bytes()
    options = {
        "native_bytes": raw,
        "base_bytes": (ROOT / "data/cases/SYN-C001/trusted_base_case.json").read_bytes(),
        "schema_bytes": (ROOT / "configs/schemas/document_extraction.schema.json").read_bytes(),
        "case_id": "C001", "job_id": loads_strict(raw)["metadata"]["job_execution_id"],
        "github_sha": "a" * 40, "candidate_bytes": CANDIDATE.read_bytes(),
    }
    options.update(overrides)
    return audit_integration(ROOT, **options)


def test_archived_engine_qa_inventory_and_candidate_are_actually_connected():
    before = NATIVE.read_bytes()
    result = run()
    assert result["combined"]["python_safety_status"] == "PASS_LOCAL"
    assert result["combined"]["python_summary"]["changed_shortage_quantity"] == 60
    assert result["inventory"]["counts"] == {"PASS": 60, "FAIL": 0, "BLOCKED": 0}
    assert result["candidate"]["status"] == "LOCAL_CANDIDATE_MATCH"
    assert result["candidate"]["official_metrics_eligible"] is False
    assert result["status"] == "BLOCKED"
    assert result["studio_native_e2e"] == "NOT_VERIFIED"
    assert result["accuracy_status"] == "NOT_MEASURED"
    assert NATIVE.read_bytes() == before
    assert result["sha256"]["native"] == hashlib.sha256(before).hexdigest()


@pytest.fixture(scope="module")
def candidate_inputs():
    candidate = loads_strict(CANDIDATE.read_bytes())
    docs = loads_strict(loads_strict(NATIVE.read_bytes())["content"])["documents"]
    return candidate, docs, collect(ROOT)[0]


def test_candidate_source_hash_mismatch_fails_joined_gate():
    candidate = loads_strict(CANDIDATE.read_bytes())
    candidate["sources"][0]["sha256"] = "0" * 64
    result = run(candidate_bytes=json.dumps(candidate).encode())
    assert result["candidate"]["source_binding_status"] == "FAIL"
    assert result["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["wrong_case", "duplicate", "missing_source"])
def test_candidate_identity_is_not_inferred(candidate_inputs, mutation):
    candidate, docs, rows = deepcopy(candidate_inputs)
    if mutation == "wrong_case":
        candidate["case_id"] = "SYN-C013"
    elif mutation == "duplicate":
        candidate["field_gold_candidate"].append(candidate["field_gold_candidate"][0])
    else:
        candidate["sources"].pop()
    with pytest.raises(ValueError):
        compare_candidate(candidate, docs, "C001", rows)


@pytest.mark.parametrize("value", [None, False, 100.0])
def test_candidate_diagnostic_preserves_quantity_types(candidate_inputs, value):
    candidate, docs, rows = deepcopy(candidate_inputs)
    docs[0]["items"][0]["quantity"] = value
    result = compare_candidate(candidate, docs, "C001", rows)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["differences"]
    assert result["gold_promoted"] is False


def test_missing_optional_field_is_not_same_as_explicit_null(candidate_inputs):
    candidate, docs, rows = deepcopy(candidate_inputs)
    del docs[0]["supplier_id"]
    result = compare_candidate(candidate, docs, "C001", rows)
    assert result["differences"] == [{"document_id": "PO-DOC", "field": "supplier_id",
                                      "reason": "MISSING_OR_DIFFERENT_VALUE"}]


def test_csv_and_xlsx_join_without_promoting_gold():
    baseline = (CANDIDATE.parent / "PDF_EVIDENCE_MATRIX.csv").read_bytes()
    workbook = Workbook()
    workbook.active.append(["reviewer", "approval_state", "formula"])
    workbook.active.append([None, "PENDING", "=1+1"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    raw = buffer.getvalue()
    result = run(review_bytes=baseline, baseline_bytes=baseline, xlsx_bytes=raw)
    assert result["review_records"]["record_check_status"] == "NEEDS_REVIEW"
    assert result["xlsx"]["status"] == "NEEDS_REVIEW"
    assert result["xlsx"]["formulas_executed"] is False
    assert result["human_gold"] == "BLOCKED"
    assert result["sha256"]["xlsx"] == hashlib.sha256(raw).hexdigest()


def test_missing_native_still_checks_data_and_stays_blocked():
    result = run(native_bytes=None)
    assert result["inventory"]["counts"]["PASS"] == 60
    assert "NATIVE_NOT_PROVIDED" in result["issues"]
    assert "combined" not in result
    assert result["status"] == "BLOCKED"


def test_review_without_baseline_fails_closed():
    assert run(review_bytes=b"csv")["status"] == "FAIL"


def test_recursive_comparison_keeps_cycle_and_signed_zero_protection():
    cyclic = []
    cyclic.append(cyclic)
    assert _typed_json_equal(cyclic, cyclic) is False
    assert _typed_json_equal(0.0, -0.0) is False
