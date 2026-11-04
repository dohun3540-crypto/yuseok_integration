"""Read-only, repository-level bridge between V6/Independent QA and data review.

Run with ``python -m qa.integration`` from the repository after installing
requirements-validation.txt. Candidate comparisons are diagnostics, never Gold
accuracy or authority to release. Original input bytes are hashed, not rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path

from leadtime_guardian.qa.input_delivery import _typed_json_equal
from leadtime_guardian.strict_json import loads_strict
from leadtime_guardian.studio_integration import documents_from_export
from qa.inventory import collect
from qa.review_records import inspect_records, load_csv
from qa.xlsx_snapshot import snapshot
from scripts.qa_combined_e2e_check import audit_combined_bytes


def compare_candidate(candidate, documents, case_id, inventory):
    """Bind candidate facts to case/document/source IDs without promoting them."""
    if not isinstance(candidate, dict) or candidate.get("case_id") != "SYN-" + case_id:
        raise ValueError("candidate case mismatch")
    facts, sources = candidate.get("field_gold_candidate"), candidate.get("sources")
    if not isinstance(facts, list) or not facts or not isinstance(sources, list):
        raise ValueError("candidate facts/sources missing")

    def index(rows):
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("document must be object")
            identifier = row.get("document_id")
            if not isinstance(identifier, str) or not identifier or identifier in result:
                raise ValueError("missing/duplicate document ID")
            result[identifier] = row
        return result

    expected, observed, source_by_id = index(facts), index(documents), index(sources)
    if expected.keys() != source_by_id.keys():
        raise ValueError("candidate source/document mismatch")
    inventory_by_id = index([r for r in inventory if r["case_id"] == "SYN-" + case_id])
    source_issues = []
    for identifier, source in source_by_id.items():
        row = inventory_by_id.get(identifier)
        if (row is None or row["status"] != "PASS"
                or source.get("filename") != row["filename"]
                or source.get("sha256") != row["sha256"]):
            source_issues.append(identifier)
    differences = []
    for identifier in sorted(expected.keys() | observed.keys()):
        if identifier not in expected or identifier not in observed:
            differences.append({"document_id": identifier, "field": "$",
                                "reason": "MISSING_OR_EXTRA_DOCUMENT"})
            continue
        for field, value in expected[identifier].items():
            if field not in observed[identifier] or not _typed_json_equal(
                value, observed[identifier][field]
            ):
                differences.append({"document_id": identifier, "field": field,
                                    "reason": "MISSING_OR_DIFFERENT_VALUE"})
    return {
        "status": "NEEDS_REVIEW" if differences or source_issues else "LOCAL_CANDIDATE_MATCH",
        "candidate_label_status": candidate.get("label_status"),
        "source_binding_status": "FAIL" if source_issues else "PASS_LOCAL",
        "source_binding_failures": source_issues, "differences": differences,
        "scope": "Candidate fields only; evidence/warning accuracy is not measured",
        "gold_promoted": False, "official_metrics_eligible": False,
        "accuracy_status": "NOT_MEASURED",
    }


def audit_integration(root, *, native_bytes, base_bytes, schema_bytes, case_id,
                      job_id, github_sha, candidate_bytes=None, review_bytes=None,
                      baseline_bytes=None, xlsx_bytes=None, sheet=None, **qa_options):
    """Join the real code paths; retain every independently blocked gate."""
    result = {
        "status": "BLOCKED", "scope": "READ_ONLY_LOCAL_REPLAY",
        "studio_native_e2e": "NOT_VERIFIED", "human_gold": "BLOCKED",
        "accuracy_status": "NOT_MEASURED", "release_or_merge_authorized": False,
        "external_action_taken": False, "sha256": {}, "issues": [],
    }
    for name, raw in (("native", native_bytes), ("base", base_bytes),
                      ("schema", schema_bytes), ("candidate", candidate_bytes),
                      ("review", review_bytes), ("baseline", baseline_bytes),
                      ("xlsx", xlsx_bytes)):
        if raw is not None:
            result["sha256"][name] = hashlib.sha256(raw).hexdigest()
    try:
        rows, _, duplicates, archive_hash = collect(root)
        counts = {s: sum(r["status"] == s for r in rows) for s in ("PASS", "FAIL", "BLOCKED")}
        result["inventory"] = {"counts": counts, "archive_sha256": archive_hash,
                               "duplicate_hashes": duplicates}
        if counts["FAIL"] or duplicates:
            result["status"] = "FAIL"
        if native_bytes is not None:
            combined = audit_combined_bytes(
                native_bytes, base_bytes, schema_bytes, operational_job_id=job_id,
                case_id=case_id, github_sha=github_sha, **qa_options,
            )
            result["combined"] = combined
            if combined["status"] == "FAIL":
                result["status"] = "FAIL"
            if candidate_bytes is not None:
                result["candidate"] = compare_candidate(
                    loads_strict(candidate_bytes),
                    documents_from_export(loads_strict(native_bytes), expected_job_id=job_id),
                    case_id, rows,
                )
                if result["candidate"]["source_binding_status"] == "FAIL":
                    result["status"] = "FAIL"
        else:
            result["issues"].append("NATIVE_NOT_PROVIDED")
        if review_bytes is not None or baseline_bytes is not None:
            if review_bytes is None or baseline_bytes is None:
                raise ValueError("review CSV and baseline CSV must be supplied together")
            result["review_records"] = inspect_records(
                load_csv(review_bytes), load_csv(baseline_bytes)
            )
        else:
            result["issues"].append("HUMAN_REVIEW_RECORDS_NOT_PROVIDED")
        if xlsx_bytes is not None:
            result["xlsx"] = snapshot(xlsx_bytes, sheet)
        else:
            result["issues"].append("REVIEWED_XLSX_NOT_PROVIDED")
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        result["status"] = "FAIL"
        result["issues"].append("INVALID_INPUT:" + type(exc).__name__)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    for name in ("native", "trusted-base", "schema", "candidate", "review", "baseline", "xlsx",
                 "qa-native", "qa-report"):
        parser.add_argument("--" + name, type=Path)
    for name in ("case-id", "job-id", "github-sha"):
        parser.add_argument("--" + name, required=True)
    for name in ("sheet", "qa-agent-id", "qa-config-id"):
        parser.add_argument("--" + name)
    parser.add_argument("--qa-config-version", type=int)
    args = parser.parse_args()
    schema = args.schema or args.root / "configs/schemas/document_extraction.schema.json"

    def read(path):
        return path.read_bytes() if path is not None else None

    try:
        result = audit_integration(
            args.root, native_bytes=read(args.native), base_bytes=read(args.trusted_base),
            schema_bytes=read(schema), case_id=args.case_id, job_id=args.job_id,
            github_sha=args.github_sha, candidate_bytes=read(args.candidate),
            review_bytes=read(args.review), baseline_bytes=read(args.baseline),
            xlsx_bytes=read(args.xlsx), sheet=args.sheet,
            qa_native_bytes=read(args.qa_native), qa_report_bytes=read(args.qa_report),
            qa_agent_id=args.qa_agent_id, qa_config_id=args.qa_config_id,
            qa_config_version=args.qa_config_version, execution_kind="ARCHIVED_REPLAY",
        )
    except OSError:
        result = {"status": "FAIL", "issues": ["INPUT_NOT_READABLE"],
                  "release_or_merge_authorized": False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if result["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
