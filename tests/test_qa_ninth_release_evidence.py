"""Release packaging tests use SYNTHETIC original-byte stand-ins, never Gold."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from leadtime_guardian.qa.release_inventory import (
    audit_release_folder,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/qa_release_evidence_check.py"


def manifest(tmp_path, sources=None):
    data = {
        "schema_version": "leadtime-release-evidence/v1",
        "case_id": "C001",
        "operational_job_id": "job_SYNTH_C001",
        "config_id": "cfg_SYNTH",
        "config_version": 1,
        "sources": {} if sources is None else sources,
    }
    path = tmp_path / "release_manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_originals_identified_without_fabrication(tmp_path):
    result = audit_release_folder(manifest(tmp_path))
    assert result["status"] == "BLOCKED"
    assert "operational_native" in result["missing_inputs"]
    assert "qa_report" in result["missing_inputs"]
    assert "team2_provenance" in result["missing_inputs"]
    assert "human_gold" in result["missing_inputs"]
    assert "source_pdfs.quotation" in result["missing_inputs"]
    assert result["source_authentication_status"] == "NOT_AUTHENTICATED"
    assert result["python_safety_status"] == "NOT_RUN"
    assert result["release_authorized"] is False


def test_computed_local_hash_but_no_cloud_authentication(tmp_path):
    evidence = tmp_path / "original.json"
    original = b'{"synthetic":true}'
    evidence.write_bytes(original)
    path = manifest(tmp_path, {"operational_native": {
        "path": "original.json", "sha256": hashlib.sha256(original).hexdigest(),
    }})
    result = audit_release_folder(path)
    assert result["status"] == "BLOCKED"
    checked = result["checked_inputs"]["operational_native"]
    assert checked["sha256"] == hashlib.sha256(original).hexdigest()
    assert checked["declared_sha256_match"] is True
    assert checked["evidence_status"] == "LOCAL_BYTES_ONLY"
    assert result["source_authentication_status"] == "NOT_AUTHENTICATED"


def test_changed_original_after_manifest_is_fail_closed(tmp_path):
    evidence = tmp_path / "original.json"
    evidence.write_bytes(b"first")
    digest = hashlib.sha256(b"first").hexdigest()
    path = manifest(tmp_path, {
        "operational_native": {"path": "original.json", "sha256": digest},
    })
    evidence.write_bytes(b"tampered")
    result = audit_release_folder(path)
    assert result["status"] == "FAIL"
    assert "operational_native" in result["invalid_inputs"]
    assert "SOURCE_SHA_MISMATCH" in {
        x["issue_code"] for x in result["blocking_issues"]
    }


def test_symlink_outside_manifest_folder_fails(tmp_path, requires_symlink):
    root = tmp_path / "pack"
    root.mkdir()
    outside = tmp_path / "external.json"
    outside.write_text("{}")
    (root / "traversal.json").symlink_to(outside)
    path = manifest(root, {"qa_native": "traversal.json"})
    result = audit_release_folder(path)
    assert result["status"] == "FAIL"
    assert "qa_native" in result["invalid_inputs"]


def test_local_stage_raw_gap_referenced_by_release_report(tmp_path):
    stage = {
        "schema_version": "leadtime-stage-intake/v1",
        "case_id": "C001",
        "operational_job_id": "job_SYNTH_C001",
        "config_id": "cfg_SYNTH",
        "config_version": 1,
        "stages": {},
    }
    (tmp_path / "stage.json").write_text(json.dumps(stage))
    result = audit_release_folder(manifest(
        tmp_path, {"stage_manifest": "stage.json"},
    ))
    assert result["local_stage_status"] == "BLOCKED"
    assert "stage.NormalizeDocuments" in result["missing_inputs"]
    assert "stage.IndependentQA_Input" in result["missing_inputs"]
    assert "stage.IndependentQA_Report" in result["missing_inputs"]
    assert result["release_authorized"] is False


def test_release_stage_identity_mismatch_cannot_be_accepted(tmp_path):
    stage = {
        "schema_version": "leadtime-stage-intake/v1",
        "case_id": "C001", "operational_job_id": "job_OTHER",
        "config_id": "cfg_SYNTH", "config_version": 1, "stages": {},
    }
    (tmp_path / "stage.json").write_text(json.dumps(stage))
    result = audit_release_folder(
        manifest(tmp_path, {"stage_manifest": "stage.json"})
    )
    assert result["status"] == "FAIL"
    assert "STAGE_IDENTITY_CONFLICT" in {
        x["issue_code"] for x in result["blocking_issues"]
    }


def test_cli_creates_machine_and_human_reports_only(tmp_path):
    source = manifest(tmp_path)
    outfile = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    proc = subprocess.run([
        sys.executable, str(CLI), "--manifest", str(source),
        "--json-report", str(outfile),
        "--markdown-report", str(markdown),
    ], cwd=ROOT, capture_output=True, text=True, check=False, timeout=30)
    assert proc.returncode == 2, proc.stderr
    assert json.loads(outfile.read_text())["status"] == "BLOCKED"
    assert "Missing inputs" in markdown.read_text()
    assert "source_pdfs.purchase_order" in markdown.read_text()
    assert "Studio execution authenticated: NO" in render_markdown(
        json.loads(outfile.read_text())
    )


def test_duplicate_release_json_keys_are_rejected(tmp_path):
    p = tmp_path / "release.json"
    p.write_bytes(b'{"sources": {}, "sources": {}}')
    result = audit_release_folder(p)
    assert result["status"] == "FAIL"
    assert result["release_authorized"] is False



def test_without_stage_manifest_names_all_three_extract_sources(tmp_path):
    report = audit_release_folder(manifest(tmp_path))
    for kind in ("purchase_order", "delivery_notice", "quotation"):
        assert "stage.Extract." + kind in report["missing_inputs"]
    assert "stage.MergeDocuments" in report["missing_inputs"]
    assert "stage.NormalizeDocuments" in report["missing_inputs"]
    assert "stage.IndependentQA_Input" in report["missing_inputs"]
    assert "stage.IndependentQA_Report" in report["missing_inputs"]
    assert report["status"] == "BLOCKED"



def test_json_report_cannot_overwrite_original_release_manifest(tmp_path):
    original = manifest(tmp_path)
    original_bytes = original.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(CLI), "--manifest", str(original),
         "--json-report", str(original)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    out = json.loads(proc.stdout)
    assert proc.returncode == 1, proc.stderr
    assert out["status"] == "FAIL"
    assert original.read_bytes() == original_bytes
    assert "REPORT_OUTPUT_NOT_WRITABLE" in {
        issue["issue_code"] for issue in out["blocking_issues"]
    }


def test_markdown_report_cannot_overwrite_existing_pdf_evidence(tmp_path):
    original = manifest(tmp_path)
    pdf = tmp_path / "SYN-C001_quotation.pdf"
    original_pdf_bytes = b"%PDF-1.4 synthetic no real source"
    pdf.write_bytes(original_pdf_bytes)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--manifest", str(original),
         "--markdown-report", str(pdf)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    out = json.loads(proc.stdout)
    assert proc.returncode == 1, proc.stderr
    assert out["status"] == "FAIL"
    assert pdf.read_bytes() == original_pdf_bytes



def _run_reports(manifest_path, json_path, markdown_path):
    proc = subprocess.run(
        [sys.executable, str(CLI), "--manifest", str(manifest_path),
         "--json-report", str(json_path),
         "--markdown-report", str(markdown_path)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    return proc, json.loads(proc.stdout)


def test_identical_json_and_markdown_report_paths_are_rejected_before_creation(
    tmp_path,
):
    source = manifest(tmp_path)
    output = tmp_path / "same_report.txt"
    proc, report = _run_reports(source, output, output)
    assert proc.returncode == 1, proc.stderr
    assert report["status"] == "FAIL"
    assert "REPORT_OUTPUT_NOT_WRITABLE" in {
        issue["issue_code"] for issue in report["blocking_issues"]
    }
    assert not output.exists()
    assert source.is_file()


def test_preexisting_second_report_rolls_back_first_without_touching_original(
    tmp_path,
):
    source = manifest(tmp_path)
    first = tmp_path / "new_report.json"
    second = tmp_path / "existing_source.pdf"
    original = b"UNTOUCHED ORIGINAL BYTES"
    second.write_bytes(original)
    proc, report = _run_reports(source, first, second)
    assert proc.returncode == 1, proc.stderr
    assert report["status"] == "FAIL"
    assert not first.exists()
    assert second.read_bytes() == original


def test_reports_with_alias_paths_resolve_to_same_file_and_are_rejected(
    tmp_path, requires_symlink,
):
    source = manifest(tmp_path)
    target = tmp_path / "reports"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    output = target / "same.json"
    proc, report = _run_reports(
        source, output, alias / "same.json",
    )
    assert proc.returncode == 1, proc.stderr
    assert report["status"] == "FAIL"
    assert not output.exists()
