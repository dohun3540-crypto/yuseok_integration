"""B0/E1 experiment eligibility contract; no fabricated QA or accuracy metrics.

Manifest-only evidence may block a comparison or establish a structural mismatch.
It cannot independently authenticate Upstage jobs or source PDF upload bytes.
"""
from __future__ import annotations

import re
from typing import Any

HEX64 = re.compile(r"^[a-fA-F0-9]{64}$")
REQUIRED_TYPES = frozenset({"purchase_order", "delivery_notice", "quotation"})
REQUIRED_STEPS = frozenset({
    "Extract", "MergeDocuments", "NormalizeDocuments", "IndependentQA",
})
VERSION = "leadtime-experiment-compare/v1"


def audit_b0_e1_readiness(b0: Any, e1: Any) -> dict[str, Any]:
    """Never compute accuracy/cost/quality metrics from incomplete manifests."""
    issues: list[dict[str, str]] = []
    status = "BLOCKED"

    def add(code: str, side: str, *, severity: str = "WARNING") -> None:
        issues.append({"issue_code": code, "side": side, "severity": severity})

    result = {
        "comparison_status": "NOT_MEASURED",
        "eligibility": "BLOCKED",
        "case_id": None,
        "pdf_sha256_sets_equal": False,
        "normalized_original_sha256_by_side": {},
        "normalized_job_metadata_by_side": {},
        "local_pdf_bytes_verified": False,
        "studio_job_authenticity_verified": False,
        "exact_saved_config_verified": False,
        "independent_qa_report_verified": False,
        "accuracy": "NOT_MEASURED",
        "evidence_completeness": "NOT_MEASURED",
        "null_and_zero_preservation": "NOT_MEASURED",
        "qa_status_change": "NOT_MEASURED",
        "release_or_merge_authorized": False,
        "issues": issues,
    }
    if not isinstance(b0, dict) or not isinstance(e1, dict):
        add("MANIFESTS_REQUIRED", "both", severity="ERROR")
        return result

    def inspect(raw: dict, side: str):
        if raw.get("schema_version") != VERSION:
            add("INVALID_EXPERIMENT_MANIFEST_VERSION", side, severity="ERROR")
        if raw.get("experiment") != side:
            add("WRONG_EXPERIMENT_ALIAS", side, severity="ERROR")
        case = raw.get("case_id")
        if not isinstance(case, str) or not case.strip():
            add("CASE_ID_NOT_OBSERVED", side, severity="ERROR")
        if (type(raw.get("single_case_job_count")) is not int
                or raw["single_case_job_count"] != 1):
            add("SINGLE_CASE_JOB_NOT_CONFIRMED", side)
        job = raw.get("job_id")
        if not isinstance(job, str) or not job.startswith("job_"):
            add("JOB_ID_NOT_OBSERVED", side)
        config = raw.get("config_id")
        version = raw.get("config_version")
        if (not isinstance(config, str) or not config.startswith("cfg_")
                or type(version) is not int or version < 1):
            add("SAVED_CONFIG_REFERENCE_MISSING", side)
        if raw.get("saved_config_evidence") is not True:
            add("SAVED_CONFIG_NOT_AUTHENTICATED", side)
        originals = raw.get("source_pdfs")
        mapping = {}
        source_file_ids: set[str] = set()
        if not isinstance(originals, list) or len(originals) != 3:
            add("THREE_PDF_SOURCES_NOT_OBSERVED", side)
        else:
            for item in originals:
                if not isinstance(item, dict):
                    add("INVALID_PDF_SOURCE_ENTRY", side, severity="ERROR")
                    continue
                name, digest, fid, kind = (
                    item.get("filename"), item.get("sha256"),
                    item.get("file_id"), item.get("document_type"),
                )
                if (not isinstance(name, str) or not name.endswith(".pdf")
                        or "/" in name or "\\" in name
                        or not isinstance(digest, str) or not HEX64.fullmatch(digest)
                        or not isinstance(fid, str) or not fid.startswith("file_")
                        or not isinstance(kind, str) or kind not in REQUIRED_TYPES):
                    add("PDF_ORIGINAL_SHA_AND_FILE_ID_REQUIRED", side)
                    continue
                if name in mapping:
                    add("DUPLICATE_PDF_FILENAME", side, severity="ERROR")
                if fid in source_file_ids:
                    add("DUPLICATE_SOURCE_FILE_ID", side, severity="ERROR")
                source_file_ids.add(fid)
                mapping[name] = (digest.lower(), kind)
            if {x[1] for x in mapping.values()} != REQUIRED_TYPES:
                add("PDF_DOCUMENT_TYPE_SET_INCOMPLETE", side)
        steps = raw.get("step_artifacts")
        if not isinstance(steps, dict):
            add("STEP_ARTIFACTS_NOT_PROVIDED", side)
        else:
            operational_step_ids: set[str] = set()
            for step in sorted(REQUIRED_STEPS):
                data = steps.get(step)
                if (not isinstance(data, dict)
                        or not isinstance(data.get("step_run_id"), str)
                        or not data["step_run_id"].strip()
                        or not isinstance(data.get("original_sha256"), str)
                        or not HEX64.fullmatch(data["original_sha256"])):
                    add("RAW_STEP_ARTIFACT_NOT_VERIFIED:" + step, side)
                    continue
                # IndependentQA may run as a separate QA Studio Job.
                # Only operational stages must bind to this side's Job/Config.
                if step != "IndependentQA":
                    sid = data["step_run_id"]
                    if sid in operational_step_ids:
                        add("DUPLICATE_OPERATIONAL_STEP_ID", side, severity="ERROR")
                    operational_step_ids.add(sid)
                    if any(
                        field in data and data[field] != expected
                        for field, expected in (
                            ("job_id", job), ("config_id", config),
                            ("config_version", version),
                        )
                    ):
                        add("OPERATIONAL_STEP_RUN_BINDING_MISMATCH:" + step,
                            side, severity="ERROR")
        if isinstance(steps, dict):
            norm = steps.get("NormalizeDocuments")
            if (isinstance(norm, dict)
                    and isinstance(norm.get("original_sha256"), str)
                    and HEX64.fullmatch(norm["original_sha256"])):
                result["normalized_original_sha256_by_side"][side] = (
                    norm["original_sha256"].lower()
                )
        result["normalized_job_metadata_by_side"][side] = {
            "job_id": job, "config_id": config,
            "config_version": version,
            "normalize_step_run_id": (
                steps.get("NormalizeDocuments", {}).get("step_run_id")
                if isinstance(steps, dict)
                and isinstance(steps.get("NormalizeDocuments"), dict)
                else None
            ),
        }
        if not isinstance(raw.get("execution_conditions"), dict):
            add("EXECUTION_CONDITIONS_NOT_RECORDED", side)
        return case, mapping

    case0, pdf0 = inspect(b0, "B0")
    case1, pdf1 = inspect(e1, "E1")
    if isinstance(case0, str) and case0 == case1:
        result["case_id"] = case0
    else:
        add("EXPERIMENT_CASE_ID_MISMATCH", "pair", severity="ERROR")
    if pdf0 and pdf1 and pdf0 == pdf1 and len(pdf0) == 3:
        result["pdf_sha256_sets_equal"] = True
    elif pdf0 and pdf1:
        add("B0_E1_PDF_SOURCE_MISMATCH", "pair", severity="ERROR")
    if (b0.get("job_id") is not None and b0.get("job_id") == e1.get("job_id")):
        add("DUPLICATE_EXPERIMENT_JOB_ID", "pair", severity="ERROR")
    conditions_b = b0.get("execution_conditions")
    conditions_e = e1.get("execution_conditions")
    if (isinstance(conditions_b, dict) and isinstance(conditions_e, dict)
            and set(conditions_b) != set(conditions_e)):
        add("EXPERIMENT_CONDITION_KEYS_DIFFER", "pair")
    if any(x["severity"] == "ERROR" for x in issues):
        status = "FAIL"
    # No local raw bytes were supplied through this manifest-only API.
    # Equal self-asserted SHA values cannot authenticate actual Studio uploads.
    result["eligibility"] = status
    return result



def compare_normalized_field_values(
    b0_raw: Any, e1_raw: Any, readiness: dict,
    *, original_raw_sha256_by_side: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Safe local field diff only; never assert Gold accuracy or improvement.

    A same-hash *manifest claim* is necessary, but insufficient to authenticate
    actual Upstage upload bytes. Changes are therefore CHANGED_UNVERIFIED.
    """
    from leadtime_guardian.qa.input_delivery import _read_documents

    result: dict[str, Any] = {
        "field_comparison_status": "BLOCKED",
        "fields_compared": 0,
        "changed_field_count": 0,
        "changes": [],
        "human_gold_accuracy": "NOT_MEASURED",
        "studio_comparison_authenticated": False,
        "improvement_verdict": "NOT_MEASURED",
        "release_or_merge_authorized": False,
        "issues": [],
    }

    def issue(code: str) -> dict[str, Any]:
        result["issues"].append(code)
        return result

    if (not isinstance(readiness, dict)
            or not isinstance(readiness.get("case_id"), str)
            or not readiness["case_id"].strip()
            or readiness.get("pdf_sha256_sets_equal") is not True
            or readiness.get("eligibility") != "BLOCKED"
            or any(x.get("severity") == "ERROR"
                   for x in readiness.get("issues", []))):
        return issue("B0_E1_READINESS_NOT_ESTABLISHED")
    if original_raw_sha256_by_side is not None:
        expected = readiness.get("normalized_original_sha256_by_side")
        if (not isinstance(expected, dict)
                or set(expected) != {"B0", "E1"}
                or not isinstance(original_raw_sha256_by_side, dict)
                or set(original_raw_sha256_by_side) != {"B0", "E1"}):
            return issue("ORIGINAL_NORMALIZE_SHA_BINDING_MISSING")
        for side in ("B0", "E1"):
            if original_raw_sha256_by_side[side] != expected[side]:
                return issue(side + "_NORMALIZE_RAW_SHA_MISMATCH")
    rows = {}
    for side, content in (("B0", b0_raw), ("E1", e1_raw)):
        if not isinstance(content, dict):
            return issue(side + "_NORMALIZED_RAW_NOT_OBJECT")
        if ("case_id" in content
                and content["case_id"] != readiness["case_id"]):
            return issue(side + "_NORMALIZED_CASE_ID_MISMATCH")
        if original_raw_sha256_by_side is not None:
            expected_binding = readiness["normalized_job_metadata_by_side"][side]
            metadata = content.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                return issue(side + "_NORMALIZE_METADATA_INVALID")
            observed = content if metadata is None else metadata
            for field, expected_field in (
                ("job_id", "job_id"),
                ("job_execution_id", "job_id"),
                ("step_run_id", "normalize_step_run_id"),
                ("config_id", "config_id"),
                ("config_version", "config_version"),
            ):
                if (field in observed
                        and observed[field] != expected_binding[expected_field]):
                    return issue(side + "_NORMALIZE_IDENTITY_MISMATCH:" + field)
        docs, error, _, layers = _read_documents(content, qa_side=False)
        if error or layers > 1 or not isinstance(docs, list) or len(docs) != 3:
            return issue(side + "_DOCUMENTS_NOT_VALIDATED")
        if (not all(isinstance(d, dict)
                    and isinstance(d.get("document_id"), str)
                    and d["document_id"]
                    and d.get("document_type") in REQUIRED_TYPES for d in docs)):
            return issue(side + "_DOCUMENTS_NOT_VALIDATED")
        kinds = [d["document_type"] for d in docs]
        ids = [d["document_id"] for d in docs]
        if (set(kinds) != REQUIRED_TYPES or len(set(ids)) != 3):
            return issue(side + "_DOCUMENTS_DUPLICATE_OR_MISSING")
        rows[side] = {d["document_type"]: d for d in docs}
    if any(rows["B0"][k]["document_id"] != rows["E1"][k]["document_id"]
           for k in REQUIRED_TYPES):
        return issue("DOCUMENT_IDENTITY_CHANGED")
    sentinel = object()

    def flat(value: Any, path: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return {key: member
                    for k, item in value.items()
                    for key, member in flat(item, f"{path}.{k}").items()}
        if isinstance(value, list):
            if not value:
                return {path: []}
            return {key: member
                    for i, item in enumerate(value)
                    for key, member in flat(item, f"{path}[{i}]").items()}
        return {path: value}

    for kind in sorted(REQUIRED_TYPES):
        left = flat(rows["B0"][kind], kind)
        right = flat(rows["E1"][kind], kind)
        for field in sorted(set(left) | set(right)):
            a, b = left.get(field, sentinel), right.get(field, sentinel)
            a_type = "MISSING" if a is sentinel else type(a).__name__
            b_type = "MISSING" if b is sentinel else type(b).__name__
            result["fields_compared"] += 1
            if a_type != b_type or a != b:
                result["changes"].append({
                    "path": field, "b0_type": a_type, "e1_type": b_type,
                    "b0_value": None if a is sentinel else a,
                    "e1_value": None if b is sentinel else b,
                    "evidence_label": "LOCAL_RAW_FIELD_DIFF_ONLY",
                })
    result["changed_field_count"] = len(result["changes"])
    result["field_comparison_status"] = (
        "CHANGED_UNVERIFIED" if result["changes"] else "UNCHANGED"
    )
    return result
