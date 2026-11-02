"""Pure QA functions. No network, purchases, file writes or engine mutations."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from leadtime_guardian.strict_json import loads_strict

PROVENANCE = frozenset({
    "REAL_STUDIO_RUN", "SDK_HTTP_MOCK", "FAKE_CLIENT_TEST",
    "LOCAL_ENGINE_ONLY", "DRAFT_GOLD", "HUMAN_VERIFIED_GOLD",
})


def load_json_strict(data: str | bytes) -> Any:
    """Use the V6 boundary, including finite floats and valid UTF-8."""
    return loads_strict(data)


def issue(code: str, field: str, reason: str, severity: str = "ERROR") -> dict[str, str]:
    return {"issue_code": code, "field": field, "reason": reason, "severity": severity}


def _date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _nonnegative(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _money(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return False
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return amount.is_finite() and amount >= 0


def audit_case(payload: dict[str, Any], output: dict[str, Any] | None = None) -> dict[str, Any]:
    """Audit trusted case records and reported actions, never infer missing values."""
    problems: list[dict[str, str]] = []
    if not isinstance(payload, dict):
        return {"qa_status": "FAIL", "issues": [issue("INVALID_CASE", "$", "case must be an object")]}
    if output is not None and not isinstance(output, dict):
        return {"qa_status": "FAIL", "issues": [issue("INVALID_OUTPUT", "output", "output must be an object")]}

    for key in ("case_id", "snapshot_date", "inventory", "inbound", "orders", "quotes", "documents"):
        if key not in payload:
            problems.append(issue("MISSING_REQUIRED_FIELD", key, "required field absent"))
    if not isinstance(payload.get("case_id"), str) or not payload.get("case_id", "").strip():
        problems.append(issue("INVALID_CASE_ID", "case_id", "nonempty ID required"))
    if not _date(payload.get("snapshot_date")):
        problems.append(issue("INVALID_SNAPSHOT_DATE", "snapshot_date", "strict ISO date required"))
    if "documents" in payload and (
        not isinstance(payload["documents"], list)
        or any(not isinstance(x, dict) for x in payload["documents"])
    ):
        problems.append(issue("INVALID_DOCUMENTS", "documents", "expected list of objects"))
    orders = payload.get("orders")
    if isinstance(orders, list) and not orders:
        problems.append(issue("EMPTY_ORDERS", "orders", "at least one order required"))
    known_skus = {
        item["product_id"]
        for section in ("inventory", "orders")
        for item in (payload.get(section) if isinstance(payload.get(section), list) else [])
        if isinstance(item, dict) and isinstance(item.get("product_id"), str)
    }
    for section in ("inventory", "inbound", "orders", "quotes"):
        rows = payload.get(section, [])
        if not isinstance(rows, list):
            problems.append(issue("INVALID_SECTION", section, "expected list"))
            continue
        id_key = {"inventory": "product_id", "inbound": "receipt_id", "orders": "order_id", "quotes": "quote_id"}[section]
        seen: set[str] = set()
        for i, row in enumerate(rows):
            path = f"{section}[{i}]"
            if not isinstance(row, dict):
                problems.append(issue("INVALID_ROW", path, "expected object"))
                continue
            if id_key:
                identifier = row.get(id_key)
                if not isinstance(identifier, str) or not identifier:
                    problems.append(issue("MISSING_IDENTIFIER", path + "." + id_key, "nonempty ID required"))
                elif identifier in seen:
                    problems.append(issue("DUPLICATE_IDENTIFIER", path + "." + id_key, "repeated ID"))
                else:
                    seen.add(identifier)
            if not isinstance(row.get("product_id"), str) or not row.get("product_id", "").strip():
                problems.append(issue("MISSING_PRODUCT_ID", path + ".product_id", "nonempty SKU required"))
            if section == "inbound" and (
                not isinstance(row.get("po_id"), str) or not row.get("po_id", "").strip()
            ):
                problems.append(issue("MISSING_PO_ID", path + ".po_id", "nonempty PO required"))
            if (section in ("inbound", "quotes") and isinstance(row.get("product_id"), str)
                    and row["product_id"] not in known_skus):
                problems.append(issue("UNKNOWN_PRODUCT", path + ".product_id", "SKU not in orders/stock"))
            if (section == "inbound" and _date(row.get("eta")) and _date(payload.get("snapshot_date"))
                    and row["eta"] <= payload["snapshot_date"]):
                problems.append(issue("INBOUND_ETA_NOT_FUTURE", path + ".eta", "ETA must follow snapshot"))
            if section == "quotes":
                for field in ("supplier_id", "supplier_risk"):
                    if not isinstance(row.get(field), str) or not row[field].strip():
                        problems.append(issue("MISSING_SUPPLIER_FIELD", path + "." + field, "nonempty supplier field required"))
            for key in {
                "inventory": ("available_stock",),
                "inbound": ("quantity",),
                "orders": ("quantity",),
                "quotes": ("capacity",),
            }[section]:
                if not _nonnegative(row.get(key)):
                    problems.append(issue("INVALID_QUANTITY", path + "." + key, "expected nonnegative integer"))
            for key in {
                "inventory": (),
                "inbound": ("original_eta", "eta"),
                "orders": ("due_date",),
                "quotes": ("arrival_date",),
            }[section]:
                if not _date(row.get(key)):
                    problems.append(issue("INVALID_DATE", path + "." + key, "expected actual ISO date"))
            if section == "quotes":
                for key in ("unit_price", "shipping_cost"):
                    if not _money(row.get(key)):
                        problems.append(issue("INVALID_MONEY", path + "." + key, "expected nonnegative finite decimal string or integer"))
                if row.get("currency", "KRW") != "KRW":
                    problems.append(issue("CURRENCY_UNSUPPORTED", path + ".currency", "expected KRW"))
    if output is not None:
        if output.get("external_action_taken") is not False:
            problems.append(issue("EXTERNAL_ACTION_NOT_DISPROVEN", "external_action_taken", "must be explicitly false"))
        if output.get("evidence_verified_against_pdf") is True:
            problems.append(issue("EVIDENCE_CLAIM_UNSUPPORTED", "evidence_verified_against_pdf", "requires independent source proof"))
        if output.get("status") == "OK" and output.get("needs_review") is True:
            problems.append(issue("CONTRADICTORY_REVIEW_STATUS", "status", "OK while needs_review=true"))
    return {"qa_status": "FAIL" if problems else "PASS", "issues": problems}


def audit_provenance(record: dict[str, Any]) -> dict[str, Any]:
    """Prevent draft truth or simulation results being reported as live inference."""
    issues: list[dict[str, str]] = []
    if not isinstance(record, dict):
        return {"qa_status": "FAIL", "issues": [issue("INVALID_PROVENANCE", "$", "object required")]}
    kind = record.get("provenance")
    if not isinstance(kind, str) or kind not in PROVENANCE:
        issues.append(issue("UNKNOWN_PROVENANCE", "provenance", "unrecognized source type"))
    if kind == "REAL_STUDIO_RUN":
        for field in ("agent_id", "config_id", "job_id"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                issues.append(issue("LIVE_EVIDENCE_MISSING", field, "real run requires execution identifier"))
    if kind == "HUMAN_VERIFIED_GOLD" and record.get("evidence_verified_against_pdf") is not True:
        issues.append(issue("REVIEW_NOT_EVIDENCED", "evidence_verified_against_pdf", "explicit human source verification required"))
    if kind in ("DRAFT_GOLD", "SDK_HTTP_MOCK", "FAKE_CLIENT_TEST", "LOCAL_ENGINE_ONLY") and record.get("measured_extraction_accuracy") is not None:
        issues.append(issue("UNSUPPORTED_ACCURACY", "measured_extraction_accuracy", "cannot claim real extraction accuracy"))
    return {"qa_status": "FAIL" if issues else "PASS", "issues": issues}


def scorecard(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: sum(1 for r in results if r.get("qa_status") == key) for key in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")}
    return {"total": len(results), "counts": counts, "pass_rate": counts["PASS"] / len(results) if results else None,
            "studio_extraction_accuracy": None, "studio_extraction_accuracy_status": "NOT_VERIFIED"}


def audit_json_files(case_file: str | Path, output_file: str | Path | None = None) -> dict[str, Any]:
    case = load_json_strict(Path(case_file).read_bytes())
    output = load_json_strict(Path(output_file).read_bytes()) if output_file is not None else None
    return audit_case(case, output)
