"""Evidence-bounded NormalizeDocuments → IndependentQA input consistency check.

Completed nodes or model assertions never prove actual cloud input delivery.
Locally supplied payloads may be JSON-string wrapped; inspect them strictly and
report the path/encoding, without authenticating the Studio provider.
"""
from __future__ import annotations

import math
from typing import Any

from leadtime_guardian.strict_json import loads_strict


def _read_documents(value: Any, *, qa_side: bool) -> tuple[Any, str | None, str, int]:
    """Decode only documented wrappers; never search arbitrary nested objects.

    A QA input list must be under normalized_documents. A Normalize list must
    be under documents. Duplicate-key, invalid JSON and double encoded input
    are not silently repaired.
    """
    path = "$"
    key = "normalized_documents" if qa_side else "documents"
    wrappers = ("input", "content") if qa_side else ("output", "content")
    reached_key = False
    encodings = 0
    for _ in range(8):
        if isinstance(value, str):
            try:
                value = loads_strict(value)
            except (ValueError, TypeError, UnicodeError):
                return None, "MALFORMED_JSON_STRING", path, encodings
            encodings += 1
            continue
        if isinstance(value, list):
            if not reached_key:
                return None, "DOCUMENTS_KEY_NOT_OBSERVED", path, encodings
            return value, None, path, encodings
        if not isinstance(value, dict):
            return None, "UNSUPPORTED_PAYLOAD_TYPE", path, encodings
        if key in value:
            reached_key = True
            value = value[key]
            path += "." + key
            continue
        observed = [wrapper for wrapper in wrappers if wrapper in value]
        if len(observed) != 1:
            return None, ("AMBIGUOUS_WRAPPER" if observed
                          else "DOCUMENTS_KEY_NOT_OBSERVED"), path, encodings
        value = value[observed[0]]
        path += "." + observed[0]
    return None, "WRAPPER_DEPTH_EXCEEDED", path, encodings


def _compare_json(left: Any, right: Any) -> bool:
    """Compare valid JSON values exactly, preserving Python JSON types.

    Only dicts with string keys and JSON primitives/arrays are accepted. A
    Python tuple must not silently compare equal to a JSON list, nor should
    non-string dict keys be coerced to strings by serialization. This remains
    local content evidence, not authentication of Studio cloud delivery.
    """
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        if any(type(key) is not str for key in left):
            return False
        if any(type(key) is not str for key in right):
            return False
        return left.keys() == right.keys() and all(
            _compare_json(value, right[key]) for key, value in left.items()
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _compare_json(a, b) for a, b in zip(left, right, strict=True)
        )
    if type(left) is float:
        return (math.isfinite(left) and math.isfinite(right) and left == right
                and math.copysign(1, left) == math.copysign(1, right))
    if left is None or type(left) in (str, int, bool):
        return left == right
    return False

def _typed_json_equal(left: Any, right: Any) -> bool:
    """Fail closed on cyclic/deep non-JSON inputs as well as type changes."""
    try:
        return _compare_json(left, right)
    except (TypeError, ValueError, RecursionError):
        return False


def audit_normalize_qa_input(
    normalize_step: Any, qa_step_input: Any = None, qa_report: Any = None,
    *, expected_case_id: str | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    status = "UNKNOWN"
    normalize_docs = None
    qa_docs = None
    normalize_path = None
    qa_path = None
    qa_string_layers = 0
    case_binding_conflict = False

    def note(code: str, severity: str = "WARNING") -> None:
        issues.append({"issue_code": code, "severity": severity})

    if not isinstance(normalize_step, dict):
        note("NORMALIZE_STEP_NOT_PROVIDED")
    elif normalize_step.get("status") not in ("completed", "COMPLETED"):
        status = "NORMALIZE_NOT_COMPLETED"
        note("NORMALIZE_EXECUTION_NOT_COMPLETED")
    else:
        normalize_docs, nerror, normalize_path, ndepth = _read_documents(
            normalize_step, qa_side=False)
        if nerror is not None:
            note("NORMALIZE_OUTPUT_" + nerror)
        elif ndepth > 1:
            note("NORMALIZE_OUTPUT_DOUBLE_JSON_WRAPPED")
        elif not isinstance(qa_step_input, dict):
            note("QA_INPUT_NOT_OBSERVED")
        else:
            qa_docs, qerror, qa_path, qa_string_layers = _read_documents(
                qa_step_input, qa_side=True)
            if qerror is not None:
                note("QA_INPUT_" + qerror)
            elif qa_string_layers > 1:
                status = "QA_INPUT_WRAPPING_UNVERIFIED"
                note("QA_INPUT_DOUBLE_JSON_WRAPPED")
            elif not _typed_json_equal(qa_docs, normalize_docs):
                status = "LOCAL_CONTENT_MISMATCH"
                note("QA_NORMALIZED_DOCUMENTS_MISMATCH", "ERROR")
            elif not (isinstance(normalize_docs, list)
                      and isinstance(qa_docs, list)
                      and bool(normalize_docs) and bool(qa_docs)
                      and all(isinstance(x, dict)
                              and isinstance(x.get("document_id"), str)
                              and x["document_id"].strip()
                              for x in (*normalize_docs, *qa_docs))):
                status = "QA_INPUT_MALFORMED"
                note("QA_OR_NORMALIZE_DOCUMENTS_NOT_STRUCTURED", "ERROR")
            elif len({x["document_id"] for x in normalize_docs}) != len(normalize_docs) or (
                len({x["document_id"] for x in qa_docs}) != len(qa_docs)
            ):
                status = "QA_INPUT_MALFORMED"
                note("DUPLICATE_DOCUMENT_IDS", "ERROR")
            else:
                status = "LOCAL_CONTENT_MATCH"

    # Apply only a supplied explicit same-case binding; do not infer a case
    # from document file names, or promote local content match to cloud proof.
    if expected_case_id is not None:
        if not isinstance(expected_case_id, str) or not expected_case_id.strip():
            status = "QA_INPUT_MALFORMED"
            note("EXPECTED_CASE_ID_INVALID", "ERROR")
        else:
            for value, side in (
                (normalize_step, "NORMALIZE"),
                (qa_step_input, "QA_INPUT"),
            ):
                if (isinstance(value, dict) and "case_id" in value
                        and value["case_id"] != expected_case_id):
                    status = "LOCAL_CONTENT_MISMATCH"
                    case_binding_conflict = True
                    note(side + "_CASE_ID_MISMATCH", "ERROR")
    if isinstance(qa_report, dict):
        feedback = qa_report.get("issues")
        if isinstance(feedback, list):
            for item in feedback:
                if (isinstance(item, dict)
                        and item.get("issue_code", item.get("code"))
                        == "NORMALIZED_OUTPUT_NOT_PROVIDED"):
                    note("QA_REPORTS_NORMALIZED_OUTPUT_MISSING")
                    # Model assertion alone cannot prove transfer failure.
                    break
        provenance = qa_report.get("execution_provenance")
        if not isinstance(provenance, dict) or any(
            provenance.get(k) is None
            for k in ("workflow_id", "config_id", "job_id", "source_files")
        ):
            note("QA_EXECUTION_PROVENANCE_INCOMPLETE")

    if isinstance(qa_report, dict) and expected_case_id is not None:
        observed_report_case = qa_report.get("case_id")
        if observed_report_case is not None and observed_report_case != expected_case_id:
            status = "LOCAL_CONTENT_MISMATCH"
            case_binding_conflict = True
            note("QA_REPORT_CASE_ID_MISMATCH", "ERROR")

    return {
        "qa_status": ("FAIL" if status in ("LOCAL_CONTENT_MISMATCH",
                                            "QA_INPUT_MALFORMED") else "BLOCKED"),
        "case_binding_conflict": case_binding_conflict,
        "expected_case_id": expected_case_id,
        "input_delivery_status": status,
        "normalize_document_count": len(normalize_docs) if isinstance(normalize_docs, list) else None,
        "qa_input_document_count": len(qa_docs) if isinstance(qa_docs, list) else None,
        "normalize_payload_path": normalize_path,
        "qa_input_payload_path": qa_path,
        "qa_input_json_encoding_layers": qa_string_layers,
        "requires_human_review": bool(issues),
        "actual_cloud_input_authenticated": False,
        "release_or_merge_authorized": False,
        "issues": issues,
    }
