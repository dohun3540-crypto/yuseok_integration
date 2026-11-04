"""Only local synthetic receipts. Live Studio upload binding is NOT proven."""
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from leadtime_guardian.qa.provenance_link import audit_team2_provenance_link

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/qa_provenance_link_check.py"


def fixture(tmp_path):
    pdf = tmp_path / "C001.pdf"
    pdf.write_bytes(b"%PDF-1.4\nlocal test fixture\n%%EOF")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    qa = {"case_id": "C001", "files": [{
        "filename": pdf.name, "file_id": "file_QA", "sha256": digest,
    }]}
    operational = {"case_id": "C001", "files": [{
        "filename": pdf.name, "file_id": "file_OPERATION", "sha256": digest,
    }]}
    handoff = {
        "protocol_version": "leadtime-cross-agent/v1",
        "studio": {
            "agent_id": "agt_HdtUJPQPXir9rGKgPWSyZG",
            "case_id": "C001",
            "job_id": "job_sandbox",
            "input_file_ids": ["file_QA"],
        },
    }
    team2 = {
        "contract_version": "studio-provenance/1",
        "export_sha256": "a" * 64,
        "studio_metadata_supplied": {"job_execution_id": "job_different_operational"},
        "business_validation_status": "COMPLETED",
        "evidence_verified_against_pdf": False,
    }
    return handoff, team2, qa, operational


def issue_codes(result):
    return {entry["issue_code"] for entry in result["issues"]}


def test_identical_local_pdf_bytes_does_not_authenticate_live_jobs(tmp_path):
    args = fixture(tmp_path)
    outcome = audit_team2_provenance_link(*args, pdf_root=tmp_path)
    assert outcome["same_local_pdf_bytes_verified"] is True
    assert outcome["qa_status"] == "BLOCKED"
    assert outcome["python_qa_status"] == "NOT_VERIFIED"
    assert outcome["cross_agent_release_authorized"] is False
    assert "EXECUTION_PROVENANCE_MISMATCH" not in issue_codes(outcome)


def test_different_pdf_digest_fails_closed(tmp_path):
    handoff, team2, qa, op = fixture(tmp_path)
    op["files"][0]["sha256"] = "b" * 64
    result = audit_team2_provenance_link(
        handoff, team2, qa, op, pdf_root=tmp_path,
    )
    assert result["qa_status"] == "FAIL"
    assert "SOURCE_PDF_SET_MISMATCH" in issue_codes(result)


def test_missing_original_pdf_bytes_remains_blocked(tmp_path):
    handoff, team2, qa, op = fixture(tmp_path)
    result = audit_team2_provenance_link(handoff, team2, qa, op)
    assert result["same_local_pdf_bytes_verified"] is False
    assert result["qa_status"] == "BLOCKED"
    assert "PDF_BYTES_NOT_PROVIDED" in issue_codes(result)


def test_tampered_file_bytes_are_rejected(tmp_path):
    args = fixture(tmp_path)
    (tmp_path / "C001.pdf").write_bytes(b"altered")
    result = audit_team2_provenance_link(*args, pdf_root=tmp_path)
    assert "PDF_BYTES_HASH_MISMATCH" in issue_codes(result)


def test_different_qa_upload_file_id_is_an_error(tmp_path):
    handoff, team2, qa, op = fixture(tmp_path)
    handoff["studio"]["input_file_ids"] = ["file_UNRELATED"]
    result = audit_team2_provenance_link(handoff, team2, qa, op, pdf_root=tmp_path)
    assert "QA_PDF_SOURCE_ID_MISMATCH" in issue_codes(result)


def test_unknown_case_binding_fails_closed(tmp_path):
    handoff, team2, qa, op = fixture(tmp_path)
    op["case_id"] = "C013"
    assert "PDF_CASE_ID_MISMATCH" in issue_codes(
        audit_team2_provenance_link(handoff, team2, qa, op, pdf_root=tmp_path)
    )


def test_draft_verification_claim_cannot_override_pdf_grounding(tmp_path):
    handoff, team2, qa, op = fixture(tmp_path)
    team2["evidence_verified_against_pdf"] = True
    result = audit_team2_provenance_link(handoff, team2, qa, op, pdf_root=tmp_path)
    assert result["qa_status"] == "FAIL"
    assert "UNSUPPORTED_PDF_VERIFICATION_CLAIM" in issue_codes(result)


def test_invalid_team2_contract_fails(tmp_path):
    handoff, team2, qa, op = fixture(tmp_path)
    team2["contract_version"] = "invented-v999"
    assert "TEAM2_CONTRACT_MISMATCH" in issue_codes(
        audit_team2_provenance_link(handoff, team2, qa, op, pdf_root=tmp_path)
    )


def test_no_mutation(tmp_path):
    arguments = fixture(tmp_path)
    saved = deepcopy(arguments)
    audit_team2_provenance_link(*arguments, pdf_root=tmp_path)
    assert arguments == saved


def test_provenance_cli_reports_blocked_not_pass(tmp_path):
    args = fixture(tmp_path)
    paths = [tmp_path / x for x in
             ("qa-handoff.json", "team2.json", "qa-pdf.json", "op-pdf.json")]
    for file, item in zip(paths, args, strict=True):
        file.write_text(json.dumps(item), encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(CLI), "--qa-handoff", str(paths[0]),
         "--team2-provenance", str(paths[1]), "--qa-pdf-receipt", str(paths[2]),
         "--operational-pdf-receipt", str(paths[3]),
         "--pdf-root", str(tmp_path)],
        capture_output=True, text=True, check=False, cwd=ROOT, timeout=30,
    )
    assert process.returncode == 2, process.stderr
    assert json.loads(process.stdout)["same_local_pdf_bytes_verified"] is True


def test_symlinked_pdf_escape_from_trusted_root_is_rejected(tmp_path, requires_symlink):
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 outside file")
    (pdf_root / "C001.pdf").symlink_to(outside)
    handoff, sidecar, qa_receipt, op_receipt = fixture(tmp_path)
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    qa_receipt["files"][0]["sha256"] = digest
    op_receipt["files"][0]["sha256"] = digest
    outcome = audit_team2_provenance_link(
        handoff, sidecar, qa_receipt, op_receipt, pdf_root=pdf_root,
    )
    assert outcome["qa_status"] == "FAIL"
    assert outcome["same_local_pdf_bytes_verified"] is False
    assert "PDF_PATH_OUTSIDE_TRUSTED_ROOT" in issue_codes(outcome)
