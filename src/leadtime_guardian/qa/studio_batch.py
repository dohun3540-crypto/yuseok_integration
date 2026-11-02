"""Read-only grouping audit for a *reported* Studio batch.

A list of three completed one-file Jobs is not a single C001 integration Job.
Positive grouping claims from a user/Studio AI report need the original Native,
Job metadata and PDF upload receipts before becoming observed evidence.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

REQUIRED_TYPES = frozenset({"purchase_order", "delivery_notice", "quotation"})
OBSERVATION_VERSION = "leadtime-studio-batch-observation/v1"
SUPPORTED_EVIDENCE = frozenset({
    "USER_REPORTED_STUDIO_AI_SUMMARY",
    "STUDIO_EXPORT_USER_SUPPLIED",
})


def audit_studio_case_batch(
    report: Any, *, expected_case_id: str,
    expected_config_id: str | None = None,
    expected_config_version: int | None = None,
    expected_job_id: str | None = None,
) -> dict[str, Any]:
    """Classify grouping without turning self-reported completion into QA PASS."""
    issues: list[dict[str, str]] = []

    def flag(code: str, field: str, severity: str = "ERROR") -> None:
        issues.append({"issue_code": code, "field": field, "severity": severity})

    answer: dict[str, Any] = {
        "qa_status": "BLOCKED",
        "single_case_grouping_status": "NOT_VERIFIED",
        "experiment_comparison_allowed": False,
        "native_bytes_authenticated": False,
        "studio_qa_verdict": "UNKNOWN",
        "pdf_sha256_verified": False,
        "python_qa_verified": False,
        "release_or_merge_authorized": False,
        "job_ids": [],
        "issues": issues,
    }
    if not isinstance(report, dict):
        flag("INVALID_BATCH_OBSERVATION", "$")
        answer["qa_status"] = "FAIL"
        return answer
    if report.get("schema_version") != OBSERVATION_VERSION:
        flag("UNSUPPORTED_BATCH_SCHEMA", "schema_version")
    provenance_level = report.get("provenance_level")
    if not isinstance(provenance_level, str) or provenance_level not in SUPPORTED_EVIDENCE:
        flag("UNVERIFIED_BATCH_OBSERVATION_SOURCE", "provenance_level")
    if (not isinstance(expected_case_id, str) or not expected_case_id.strip()
            or report.get("case_id") != expected_case_id):
        flag("BATCH_CASE_ID_MISMATCH", "case_id")
    config_id, config_version = report.get("config_id"), report.get("config_version")
    if not isinstance(config_id, str) or not config_id.startswith("cfg_"):
        flag("INVALID_BATCH_CONFIG", "config_id")
    if type(config_version) is not int or config_version < 1:
        flag("INVALID_BATCH_CONFIG_VERSION", "config_version")
    if expected_config_id is not None and config_id != expected_config_id:
        flag("BATCH_CONFIG_ID_MISMATCH", "config_id")
    if expected_config_version is not None and config_version != expected_config_version:
        flag("BATCH_CONFIG_VERSION_MISMATCH", "config_version")
    jobs = report.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        flag("INVALID_BATCH_JOBS", "jobs")
        answer["qa_status"] = "FAIL"
        return answer
    count = report.get("batch_run_count")
    if type(count) is not int or count != len(jobs):
        flag("BATCH_RUN_COUNT_CONFLICT", "batch_run_count")
    ids = []
    names = []
    kinds = []
    for i, row in enumerate(jobs):
        prefix = f"jobs[{i}]"
        if not isinstance(row, dict):
            flag("INVALID_BATCH_JOB", prefix)
            continue
        job_id = row.get("job_id")
        if not isinstance(job_id, str) or not job_id.startswith("job_"):
            flag("INVALID_BATCH_JOB_ID", prefix + ".job_id")
        else:
            ids.append(job_id)
        if row.get("execution_status") != "COMPLETED":
            flag("BATCH_JOB_NOT_COMPLETED", prefix + ".execution_status", "WARNING")
        if row.get("config_id") != config_id or row.get("config_version") != config_version:
            flag("JOB_CONFIG_INCONSISTENT", prefix + ".config_id")
        filename, kind = row.get("filename"), row.get("document_type")
        if (not isinstance(filename, str) or not filename.endswith(".pdf")
                or "/" in filename or "\\" in filename):
            flag("INVALID_SOURCE_PDF_FILENAME", prefix + ".filename")
        else:
            names.append(filename)
        if not isinstance(kind, str) or kind not in REQUIRED_TYPES:
            flag("INVALID_EXPECTED_DOCUMENT_TYPE", prefix + ".document_type")
        else:
            kinds.append(kind)
    answer["job_ids"] = ids
    if len(ids) != len(jobs) or len(ids) != len(set(ids)):
        flag("DUPLICATE_OR_MISSING_BATCH_JOB_ID", "jobs")
    if len(names) != len(jobs) or len(names) != len(set(names)):
        flag("DUPLICATE_OR_MISSING_SOURCE_FILE", "jobs")
    if len(jobs) == 3 and Counter(kinds) != Counter(REQUIRED_TYPES):
        flag("BATCH_DOCUMENT_TYPE_SET_MISMATCH", "jobs")
    if any(x["severity"] == "ERROR" for x in issues):
        answer["qa_status"] = "FAIL"
        return answer
    # Reported three file-specific jobs cannot be joined by matching a case
    # number; the original raw Merge/Normalize/IndependentQA never crossed jobs.
    if len(set(ids)) != 1:
        flag("MULTIPLE_INDEPENDENT_STUDIO_JOBS", "jobs", "WARNING")
        answer["single_case_grouping_status"] = "INVALID_SPLIT_JOBS"
        if expected_job_id is not None and expected_job_id not in ids:
            flag("EXPECTED_JOB_NOT_IN_REPORTED_BATCH", "expected_job_id", "WARNING")
        return answer
    if expected_job_id is not None and expected_job_id != ids[0]:
        flag("BATCH_EXPECTED_JOB_ID_MISMATCH", "expected_job_id")
        answer["qa_status"] = "FAIL"
        return answer
    # Even a one-job report is only a claim until exact Native and file receipts
    # substantiate all three source files in the same Job.
    sources = jobs[0].get("source_files")
    if (not isinstance(sources, list) or len(sources) != 3
            or any(not isinstance(s, dict) for s in sources)):
        flag("SINGLE_JOB_SOURCE_SET_NOT_PROVIDED", "jobs[0].source_files", "WARNING")
    else:
        file_names = [s.get("filename") for s in sources]
        file_ids = [s.get("file_id") for s in sources]
        types = [s.get("document_type") for s in sources]
        if (not all(isinstance(x, str) and x.endswith(".pdf") for x in file_names)
                or len({x for x in file_names if isinstance(x, str)}) != 3
                or not all(isinstance(x, str) for x in types)
                or Counter(x for x in types if isinstance(x, str)) != Counter(REQUIRED_TYPES)):
            flag("SINGLE_JOB_SOURCE_SET_INCONSISTENT", "jobs[0].source_files")
            answer["qa_status"] = "FAIL"
            return answer
        # Missing file IDs in a user-reported new Job are missing evidence,
        # not a confirmed Studio file-ID mismatch. Do NOT fabricate them.
        if all(x is None for x in file_ids):
            flag("SINGLE_JOB_SOURCE_FILE_IDS_NOT_OBSERVED",
                 "jobs[0].source_files", "WARNING")
        elif (not all(isinstance(x, str) and x.startswith("file_") for x in file_ids)
                or len({x for x in file_ids if isinstance(x, str)}) != 3):
            flag("SINGLE_JOB_SOURCE_FILE_IDS_INCONSISTENT", "jobs[0].source_files")
            answer["qa_status"] = "FAIL"
            return answer
    answer["single_case_grouping_status"] = "REPORTED_SINGLE_JOB_UNAUTHENTICATED"
    flag("NATIVE_AND_PDF_UPLOAD_RECEIPTS_REQUIRED", "source_evidence", "WARNING")
    return answer
