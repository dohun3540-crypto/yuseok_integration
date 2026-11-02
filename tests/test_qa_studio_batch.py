"""Observed B0-C001: three completed jobs are NOT one normalized case."""
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from leadtime_guardian.qa.audit import load_json_strict
from leadtime_guardian.qa.studio_batch import audit_studio_case_batch

ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = (
    ROOT / "data/observations/B0_C001_20261101_USER_REPORTED_STUDIO_AI.json"
)
BATCH_CLI = ROOT / "scripts/qa_studio_batch_check.py"
COMBINED_CLI = ROOT / "scripts/qa_combined_e2e_check.py"
ARCHIVE = ROOT / "data/results/studio_runs/C001_20261030_v4/instruct_original.json"
BASE = ROOT / "data/cases/SYN-C001/trusted_base_case.json"


def reported():
    return load_json_strict(OBSERVATION.read_bytes())


def codes(r):
    return {i["issue_code"] for i in r["issues"]}


def test_b0_c001_completions_do_not_create_an_integrated_case():
    raw = reported()
    original = deepcopy(raw)
    result = audit_studio_case_batch(
        raw, expected_case_id="C001",
        expected_config_id="cfg_X2xXakDtmDTHh2RoqVysvL",
        expected_config_version=1,
    )
    assert result["qa_status"] == "BLOCKED"
    assert result["single_case_grouping_status"] == "INVALID_SPLIT_JOBS"
    assert "MULTIPLE_INDEPENDENT_STUDIO_JOBS" in codes(result)
    assert len(result["job_ids"]) == 3
    assert result["studio_qa_verdict"] == "UNKNOWN"
    assert result["experiment_comparison_allowed"] is False
    assert result["native_bytes_authenticated"] is False
    assert raw == original


def test_b0_report_missing_source_proofs_does_not_claim_live_qa():
    raw = reported()
    assert raw["qa_report_body_available"] is False
    assert raw["source_pdf_sha256_available"] is False
    assert raw["normalized_content_available"] is False
    result = audit_studio_case_batch(raw, expected_case_id="C001")
    assert result["pdf_sha256_verified"] is False
    assert result["python_qa_verified"] is False
    assert result["release_or_merge_authorized"] is False


def test_wrong_case_or_config_rejected():
    raw = reported()
    for kwargs, issue in (
        ({"expected_case_id": "C013"}, "BATCH_CASE_ID_MISMATCH"),
        ({"expected_case_id": "C001", "expected_config_id": "cfg_CHANGED"},
         "BATCH_CONFIG_ID_MISMATCH"),
        ({"expected_case_id": "C001", "expected_config_version": 2},
         "BATCH_CONFIG_VERSION_MISMATCH"),
    ):
        output = audit_studio_case_batch(raw, **kwargs)
        assert output["qa_status"] == "FAIL"
        assert issue in codes(output)


def test_conflicting_or_duplicate_jobs_rejected():
    report = reported()
    report["jobs"][1]["job_id"] = report["jobs"][0]["job_id"]
    assert "DUPLICATE_OR_MISSING_BATCH_JOB_ID" in codes(
        audit_studio_case_batch(report, expected_case_id="C001")
    )
    report = reported()
    report["jobs"][1]["config_version"] = 2
    assert "JOB_CONFIG_INCONSISTENT" in codes(
        audit_studio_case_batch(report, expected_case_id="C001")
    )


def test_bad_report_schema_and_count_fail_closed():
    report = reported()
    report["batch_run_count"] = 1
    assert "BATCH_RUN_COUNT_CONFLICT" in codes(
        audit_studio_case_batch(report, expected_case_id="C001")
    )
    report = reported()
    report["jobs"][0]["document_type"] = ["invalid"]
    assert "INVALID_EXPECTED_DOCUMENT_TYPE" in codes(
        audit_studio_case_batch(report, expected_case_id="C001")
    )


def test_one_job_is_only_structurally_plausible_without_original_native():
    report = reported()
    report["batch_run_count"] = 1
    report["jobs"] = [{
        "job_id": "job_SINGLE",
        "filename": "SYN-C001_purchase_order.pdf",
        "document_type": "purchase_order",
        "execution_status": "COMPLETED",
        "config_id": report["config_id"],
        "config_version": report["config_version"],
        "source_files": [
            {"filename": f"SYN-C001_{name}.pdf", "file_id": f"file_{name}",
             "document_type": kind}
            for name, kind in (
                ("purchase_order", "purchase_order"),
                ("delivery_notice", "delivery_notice"),
                ("quotation", "quotation"),
            )
        ],
    }]
    result = audit_studio_case_batch(
        report, expected_case_id="C001", expected_job_id="job_SINGLE",
    )
    assert result["qa_status"] == "BLOCKED"
    assert result["single_case_grouping_status"] == (
        "REPORTED_SINGLE_JOB_UNAUTHENTICATED"
    )
    assert "NATIVE_AND_PDF_UPLOAD_RECEIPTS_REQUIRED" in codes(result)
    assert result["experiment_comparison_allowed"] is False


def test_batch_cli_blocks_b0_without_any_studio_reexecution():
    proc = subprocess.run([
        sys.executable, str(BATCH_CLI),
        "--report", str(OBSERVATION), "--case-id", "C001",
        "--config-id", "cfg_X2xXakDtmDTHh2RoqVysvL", "--config-version", "1",
    ], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    output = json.loads(proc.stdout)
    assert proc.returncode == 2, proc.stderr
    assert output["single_case_grouping_status"] == "INVALID_SPLIT_JOBS"
    assert output["studio_qa_verdict"] == "UNKNOWN"


def test_combined_cli_rejects_comparing_archived_c001_to_three_new_jobs():
    actual_job_id = load_json_strict(ARCHIVE.read_bytes())[
        "metadata"
    ]["job_execution_id"]
    proc = subprocess.run([
        sys.executable, str(COMBINED_CLI),
        "--operational-native", str(ARCHIVE),
        "--trusted-base", str(BASE),
        "--operational-job-id", actual_job_id,
        "--case-id", "C001", "--github-sha", "a" * 40,
        "--studio-batch-report", str(OBSERVATION),
    ], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    output = json.loads(proc.stdout)
    assert proc.returncode == 2, proc.stderr
    assert output["status"] == "BLOCKED"
    assert output["single_case_grouping_status"] == "INVALID_SPLIT_JOBS"
    assert "python_summary" not in output
    assert output["python_business_status"] == "NOT_VERIFIED"
    assert "MULTI_JOB_B0_NOT_INTEGRATED_C001" in codes(output)
    assert output["release_or_merge_authorized"] is False


def test_unhashable_reported_provenance_level_fails_closed():
    for value in ([], {}, ["STUDIO_EXPORT_USER_SUPPLIED"]):
        raw = reported()
        raw["provenance_level"] = value
        result = audit_studio_case_batch(raw, expected_case_id="C001")
        assert result["qa_status"] == "FAIL"
        assert "UNVERIFIED_BATCH_OBSERVATION_SOURCE" in codes(result)


@pytest.mark.parametrize("invalid_level", [None, 0, False, {"nested": {"items": []}}])
def test_reported_provenance_nonstring_is_rejected_safely(invalid_level):
    raw = reported()
    raw["provenance_level"] = invalid_level
    result = audit_studio_case_batch(raw, expected_case_id="C001")
    assert result["qa_status"] == "FAIL"
    assert "UNVERIFIED_BATCH_OBSERVATION_SOURCE" in codes(result)
    assert result["release_or_merge_authorized"] is False
