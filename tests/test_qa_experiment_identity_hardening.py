"""Cross-run identity hardening with synthetic-only experiment manifests.

No generated report or local match authenticates Upstage or authorizes release.
"""
from copy import deepcopy

import pytest

from leadtime_guardian.qa.experiment_compare import (
    REQUIRED_STEPS,
    audit_b0_e1_readiness,
    compare_normalized_field_values,
)

KINDS = ("purchase_order", "delivery_notice", "quotation")


def _manifest(alias, case="C001"):
    return {
        "schema_version": "leadtime-experiment-compare/v1",
        "experiment": alias,
        "case_id": case,
        "single_case_job_count": 1,
        "job_id": f"job_{alias}",
        "config_id": f"cfg_{alias}",
        "config_version": 1,
        "saved_config_evidence": True,
        "source_pdfs": [
            {"filename": f"{case}_{kind}.pdf", "sha256": "a" * 64,
             "file_id": f"file_{alias}_{kind}", "document_type": kind}
            for kind in KINDS
        ],
        "step_artifacts": {
            step: {"step_run_id": f"step_{alias}_{step}",
                   "original_sha256": "b" * 64}
            for step in REQUIRED_STEPS
        },
        "execution_conditions": {"mode": "synthetic"},
    }


def _check(b0, e1):
    return audit_b0_e1_readiness(b0, e1)


def _codes(result):
    return {(issue["issue_code"], issue["side"]) for issue in result["issues"]}


@pytest.mark.parametrize("side", ("B0", "E1"))
def test_duplicate_source_file_ids_are_structural_failures(side):
    b0, e1 = _manifest("B0"), _manifest("E1")
    target = b0 if side == "B0" else e1
    target["source_pdfs"][1]["file_id"] = target["source_pdfs"][0]["file_id"]
    before = deepcopy((b0, e1))
    result = _check(b0, e1)
    assert result["eligibility"] == "FAIL"
    assert ("DUPLICATE_SOURCE_FILE_ID", side) in _codes(result)
    assert result["comparison_status"] == "NOT_MEASURED"
    assert result["release_or_merge_authorized"] is False
    assert (b0, e1) == before


def test_duplicate_operational_step_ids_are_rejected():
    b0, e1 = _manifest("B0"), _manifest("E1")
    b0["step_artifacts"]["MergeDocuments"]["step_run_id"] = (
        b0["step_artifacts"]["Extract"]["step_run_id"]
    )
    result = _check(b0, e1)
    assert result["eligibility"] == "FAIL"
    assert ("DUPLICATE_OPERATIONAL_STEP_ID", "B0") in _codes(result)


@pytest.mark.parametrize("key,bad_value", [
    ("job_id", "job_UNRELATED"),
    ("config_id", "cfg_UNRELATED"),
    ("config_version", 2),
])
def test_operational_stage_optional_identity_conflict_fails_closed(key, bad_value):
    b0, e1 = _manifest("B0"), _manifest("E1")
    b0["step_artifacts"]["NormalizeDocuments"][key] = bad_value
    result = _check(b0, e1)
    assert result["eligibility"] == "FAIL"
    assert (
        "OPERATIONAL_STEP_RUN_BINDING_MISMATCH:NormalizeDocuments", "B0"
    ) in _codes(result)


def test_separate_independent_qa_job_is_not_false_operational_mismatch():
    b0, e1 = _manifest("B0"), _manifest("E1")
    b0["step_artifacts"]["IndependentQA"].update({
        "job_id": "job_SEPARATE_QA",
        "config_id": "cfg_SEPARATE_QA",
        "config_version": 2,
    })
    result = _check(b0, e1)
    assert result["eligibility"] == "BLOCKED"
    assert not any("OPERATIONAL_STEP_RUN_BINDING_MISMATCH" in code
                   for code, _ in _codes(result))
    assert result["studio_job_authenticity_verified"] is False


def _normalized(case, quantity):
    return {
        "case_id": case,
        "documents": [
            {"document_id": f"{case}_{kind}", "document_type": kind,
             "quantity": quantity if kind == "purchase_order" else 0}
            for kind in KINDS
        ],
    }


def test_c013_same_case_local_diff_never_measures_gold_or_releases():
    b0, e1 = _manifest("B0", "C013"), _manifest("E1", "C013")
    ready = _check(b0, e1)
    assert ready["case_id"] == "C013"
    assert ready["eligibility"] == "BLOCKED"
    result = compare_normalized_field_values(
        _normalized("C013", 40), _normalized("C013", 45), ready,
    )
    assert result["field_comparison_status"] == "CHANGED_UNVERIFIED"
    assert result["changed_field_count"] == 1
    assert result["improvement_verdict"] == "NOT_MEASURED"
    assert result["studio_comparison_authenticated"] is False
    assert result["release_or_merge_authorized"] is False


def test_cross_case_normalize_is_rejected_for_c013():
    ready = _check(_manifest("B0", "C013"), _manifest("E1", "C013"))
    result = compare_normalized_field_values(
        _normalized("C013", 40), _normalized("C001", 40), ready,
    )
    assert result["field_comparison_status"] == "BLOCKED"
    assert "E1_NORMALIZED_CASE_ID_MISMATCH" in result["issues"]
    assert result["release_or_merge_authorized"] is False
