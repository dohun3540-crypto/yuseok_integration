"""Synthetic raw Stage fixtures only; no actual NCik Native is supplied."""
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from leadtime_guardian.qa.stage_trace import (
    FIELDS_BY_TYPE,
    audit_stage_evidence,
    classify_missing,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/qa_stage_intake_check.py"
JOB = "job_SYNTHETIC_C001"
TYPES = ("purchase_order", "delivery_notice", "quotation")
STAGES = ("Extract", "MergeDocuments", "NormalizeDocuments",
          "IndependentQA_Input", "IndependentQA_Report")


def synthetic_docs():
    return [
        {"document_id": "PO-DOC", "document_type": "purchase_order",
         "supplier_id": None, "revised_delivery": None, "quote": [],
         "items": [{"receipt_id": "R1", "quantity": 100}]},
        {"document_id": "NOTICE-DOC", "document_type": "delivery_notice",
         "supplier_id": None, "quote": [],
         "items": [{"receipt_id": "R1", "quantity": 100}]},
        {"document_id": "QUOTE-DOC", "document_type": "quotation",
         "original_delivery": None, "revised_delivery": None,
         "quote": [{"quote_id": "Q1", "capacity": 60}],
         "items": [{"receipt_id": None, "quantity": 60}]},
    ]


def evidence():
    docs = synthetic_docs()
    raw = {}
    manifest = {
        "schema_version": "leadtime-stage-intake/v1",
        "case_id": "C001", "operational_job_id": JOB,
        "config_id": "cfg_SYNTH", "config_version": 1, "stages": {},
    }
    for stage in STAGES:
        job = JOB if stage in STAGES[:3] else "job_QA_SYNTH"
        data = {"case_id": "C001", "job_id": job,
                "step_run_id": f"step_{stage}"}
        if stage == "IndependentQA_Report":
            data["qa_status"] = "NOT_VERIFIED"
        elif stage == "IndependentQA_Input":
            data["normalized_documents"] = deepcopy(docs)
        else:
            data["documents"] = deepcopy(docs)
        value = json.dumps(data, ensure_ascii=False).encode("utf-8")
        raw[stage] = value
        manifest["stages"][stage] = {
            "sha256": hashlib.sha256(value).hexdigest(),
            "job_id": job, "step_run_id": f"step_{stage}", "case_id": "C001",
        }
        if stage in STAGES[:3]:
            manifest["stages"][stage].update(
                {"config_id": "cfg_SYNTH", "config_version": 1}
            )
    return manifest, raw


def test_22_fields_and_string_types_not_conflated():
    m, raw = evidence()
    output = audit_stage_evidence(m, raw)
    assert output["status"] == "BLOCKED"
    assert len(output["field_trace"]) == 22
    assert output["all_expected_raw_stages_present"] is True
    assert output["normalize_qa_input_status"] == "LOCAL_CONTENT_MATCH"
    assert output["studio_live_execution_authenticated"] is False
    assert output["release_or_merge_authorized"] is False
    assert output["xlsx_shared_index_49_empty_reference_count"] == 22
    row = next(x for x in output["field_trace"] if x["cell"] == "R2")
    assert row["stage_values"]["Extract"]["state"] == "NULL"
    assert output["stages"]["IndependentQA_Input"]["job_id"] == "job_QA_SYNTH"
    assert sum(len(x) for x in FIELDS_BY_TYPE.values()) == 22
    assert classify_missing(0, present=True) == "NUMBER_ZERO"
    assert classify_missing("0", present=True) == "STRING_ZERO"
    assert classify_missing("null", present=True) == "STRING_NULL"
    assert classify_missing("", present=True) == "EMPTY_STRING"
    assert classify_missing(None, present=True) == "NULL"
    assert classify_missing(None, present=False) == "MISSING"
    assert classify_missing(True, present=True) == "INVALID_TYPE"


def test_missing_actual_stages_are_not_invented():
    m, raw = evidence()
    del raw["MergeDocuments"]
    del raw["IndependentQA_Input"]
    result = audit_stage_evidence(m, raw)
    assert result["status"] == "BLOCKED"
    assert result["normalize_qa_input_status"] == "NOT_VERIFIED"
    assert result["first_observed_conversion"] == "UNKNOWN"
    assert result["stages"]["MergeDocuments"]["status"] == "NOT_PROVIDED"


def test_cross_job_native_mixing_fails_even_with_matching_values():
    m, raw = evidence()
    m["stages"]["MergeDocuments"]["job_id"] = "job_WRONG"
    assert audit_stage_evidence(m, raw)["status"] == "FAIL"


def test_modified_raw_sha_fails_without_coercion():
    m, raw = evidence()
    raw["NormalizeDocuments"] += b" "
    result = audit_stage_evidence(m, raw)
    assert result["status"] == "FAIL"
    assert "STAGE_SHA256_MISMATCH" in {x["issue_code"] for x in result["issues"]}


def test_strict_duplicate_json_keys_are_not_silently_accepted():
    m, raw = evidence()
    data = b'{"documents":[],"documents":[]}'
    raw["Extract"] = data
    m["stages"]["Extract"]["sha256"] = hashlib.sha256(data).hexdigest()
    result = audit_stage_evidence(m, raw)
    assert result["status"] == "FAIL"
    assert "STRICT_JSON_FAILED" in {x["issue_code"] for x in result["issues"]}


def test_qa_raw_mismatch_fails_but_different_qa_job_is_allowed():
    m, raw = evidence()
    parsed = json.loads(raw["IndependentQA_Input"])
    parsed["normalized_documents"][0]["supplier_id"] = "S2"
    data = json.dumps(parsed).encode("utf-8")
    raw["IndependentQA_Input"] = data
    m["stages"]["IndependentQA_Input"]["sha256"] = hashlib.sha256(data).hexdigest()
    output = audit_stage_evidence(m, raw)
    assert output["status"] == "FAIL"
    assert output["normalize_qa_input_status"] == "LOCAL_CONTENT_MISMATCH"


def test_known_adjacent_field_change_reports_observation_not_causal_root():
    m, raw = evidence()
    parsed = json.loads(raw["MergeDocuments"])
    parsed["documents"][0]["supplier_id"] = ""
    data = json.dumps(parsed).encode("utf-8")
    raw["MergeDocuments"] = data
    m["stages"]["MergeDocuments"]["sha256"] = hashlib.sha256(data).hexdigest()
    out = audit_stage_evidence(m, raw)
    row = next(x for x in out["field_trace"] if x["cell"] == "R2")
    assert row["first_observed_conversion"] == "Extract->MergeDocuments"
    assert row["stage_values"]["MergeDocuments"]["state"] == "EMPTY_STRING"
    assert out["first_observed_conversion"] == "UNKNOWN"


def test_cli_path_escape_fails_closed(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    m, raw = evidence()
    (tmp_path / "outside.json").write_bytes(raw["Extract"])
    m["stages"]["Extract"]["path"] = "../outside.json"
    path = root / "manifest.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CLI), "--manifest", str(path)],
                          cwd=ROOT, capture_output=True, text=True,
                          check=False, timeout=30)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["status"] == "FAIL"


def test_cli_missing_stages_returns_blocked(tmp_path):
    m, raw = evidence()
    m["stages"]["Extract"]["path"] = "extract.json"
    (tmp_path / "extract.json").write_bytes(raw["Extract"])
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CLI), "--manifest", str(p)],
                          cwd=ROOT, capture_output=True, text=True,
                          check=False, timeout=30)
    out = json.loads(proc.stdout)
    assert proc.returncode == 2, proc.stderr
    assert out["status"] == "BLOCKED"



def test_three_original_extract_branch_files_preserve_individual_step_provenance():
    manifest, data = evidence()
    raw = {}
    branch_metadata = {}
    for kind, doc in zip(TYPES, synthetic_docs()):
        obj = {
            "case_id": "C001", "job_id": JOB,
            "step_run_id": "extract_" + kind, "document": doc,
        }
        content = json.dumps(obj).encode("utf-8")
        raw[kind] = content
        branch_metadata[kind] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "job_id": JOB, "step_run_id": "extract_" + kind,
            "case_id": "C001", "config_id": "cfg_SYNTH",
            "config_version": 1,
        }
    data["Extract"] = raw
    manifest["stages"]["Extract"] = {"branches": branch_metadata}
    report = audit_stage_evidence(manifest, data)
    assert report["status"] == "BLOCKED"
    assert report["stages"]["Extract"]["document_count"] == 3
    assert report["stages"]["Extract"]["branches"]["quotation"]["step_run_id"] == (
        "extract_quotation"
    )
    assert report["normalize_qa_input_status"] == "LOCAL_CONTENT_MATCH"


def test_mixed_operational_extract_branches_are_rejected():
    manifest, data = evidence()
    branches = {}
    branch_metadata = {}
    for kind, doc in zip(TYPES, synthetic_docs()):
        value = json.dumps({"document": doc}).encode()
        branches[kind] = value
        branch_metadata[kind] = {
            "sha256": hashlib.sha256(value).hexdigest(),
            "job_id": "job_OTHER" if kind == "quotation" else JOB,
            "step_run_id": "extract_" + kind, "case_id": "C001",
            "config_id": "cfg_SYNTH", "config_version": 1,
        }
    data["Extract"] = branches
    manifest["stages"]["Extract"] = {"branches": branch_metadata}
    result = audit_stage_evidence(manifest, data)
    assert result["status"] == "FAIL"
    assert "EXTRACT_BRANCH_SHA_OR_RUN_BINDING_MISMATCH" in {
        i["issue_code"] for i in result["issues"]
    }


def test_cli_three_extract_branch_files(tmp_path):
    manifest, _ = evidence()
    branches = {}
    for kind, doc in zip(TYPES, synthetic_docs()):
        filename = f"{kind}.json"
        value = json.dumps({"document": doc}).encode("utf-8")
        (tmp_path / filename).write_bytes(value)
        branches[kind] = {
            "path": filename, "sha256": hashlib.sha256(value).hexdigest(),
            "job_id": JOB, "step_run_id": "extract_" + kind,
            "case_id": "C001", "config_id": "cfg_SYNTH", "config_version": 1,
        }
    manifest["stages"]["Extract"] = {"branches": branches}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    proc = subprocess.run(
        [sys.executable, str(CLI), "--manifest", str(manifest_path)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    out = json.loads(proc.stdout)
    assert proc.returncode == 2, proc.stderr
    assert out["status"] == "BLOCKED"
    assert out["stages"]["Extract"]["document_count"] == 3
    assert out["normalize_qa_input_status"] == "NOT_VERIFIED"



def test_false_quantity_is_not_equal_to_numeric_zero_in_qa_input():
    manifest, raw = evidence()
    for stage, key, value in (
        ("NormalizeDocuments", "documents", 0),
        ("IndependentQA_Input", "normalized_documents", False),
    ):
        parsed = json.loads(raw[stage])
        parsed[key][0]["items"][0]["quantity"] = value
        content = json.dumps(parsed).encode("utf-8")
        raw[stage] = content
        manifest["stages"][stage]["sha256"] = hashlib.sha256(content).hexdigest()
    result = audit_stage_evidence(manifest, raw)
    assert result["status"] == "FAIL"
    assert result["normalize_qa_input_status"] == "LOCAL_CONTENT_MISMATCH"
    assert any(i["issue_code"] == "QA_NORMALIZED_CONTENT_MISMATCH"
               for i in result["issues"])


def test_unknown_stage_and_unknown_extract_branch_fail_closed():
    manifest, raw = evidence()
    manifest["stages"]["UnauthorizedStep"] = {"path": "other.json"}
    report = audit_stage_evidence(manifest, raw)
    assert report["status"] == "FAIL"
    assert "UNEXPECTED_STAGE_NAME" in {i["issue_code"] for i in report["issues"]}

    manifest, raw = evidence()
    manifest["stages"]["Extract"] = {
        "branches": {"unknown_document": {"job_id": JOB}},
    }
    report = audit_stage_evidence(manifest, raw)
    assert report["status"] == "FAIL"
    assert "UNEXPECTED_EXTRACT_BRANCH" in {
        i["issue_code"] for i in report["issues"]
    }


def test_duplicate_job_and_step_run_identity_fails():
    manifest, raw = evidence()
    parsed = json.loads(raw["MergeDocuments"])
    parsed["step_run_id"] = "step_Extract"
    value = json.dumps(parsed).encode()
    raw["MergeDocuments"] = value
    manifest["stages"]["MergeDocuments"]["step_run_id"] = "step_Extract"
    manifest["stages"]["MergeDocuments"]["sha256"] = hashlib.sha256(value).hexdigest()
    out = audit_stage_evidence(manifest, raw)
    assert out["status"] == "FAIL"
    assert "DUPLICATE_JOB_STEP_ID" in {i["issue_code"] for i in out["issues"]}


def test_qa_input_report_mixed_sandbox_jobs_fails():
    manifest, raw = evidence()
    parsed = json.loads(raw["IndependentQA_Report"])
    parsed["job_id"] = "job_DIFFERENT_SANDBOX"
    value = json.dumps(parsed).encode()
    raw["IndependentQA_Report"] = value
    manifest["stages"]["IndependentQA_Report"]["job_id"] = "job_DIFFERENT_SANDBOX"
    manifest["stages"]["IndependentQA_Report"]["sha256"] = (
        hashlib.sha256(value).hexdigest()
    )
    out = audit_stage_evidence(manifest, raw)
    assert out["status"] == "FAIL"
    assert "QA_INPUT_REPORT_JOB_MISMATCH" in {
        i["issue_code"] for i in out["issues"]
    }


def test_excessive_manifest_size_is_safely_rejected(tmp_path):
    m, _ = evidence()
    m["padding"] = "x" * (1024 * 1024)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CLI), "--manifest", str(path)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["status"] == "FAIL"


def test_stage_path_symlink_outside_evidence_directory_is_rejected(tmp_path, requires_symlink):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    symlink = evidence_dir / "linked.json"
    symlink.symlink_to(outside)
    m, _ = evidence()
    m["stages"]["Extract"]["path"] = "linked.json"
    manifest = evidence_dir / "manifest.json"
    manifest.write_text(json.dumps(m))
    proc = subprocess.run(
        [sys.executable, str(CLI), "--manifest", str(manifest)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["status"] == "FAIL"
