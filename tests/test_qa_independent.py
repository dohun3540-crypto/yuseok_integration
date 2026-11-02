"""Independent adversarial QA tests without live Studio or network calls."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from leadtime_guardian.qa import (
    audit_case,
    audit_provenance,
    load_json_strict,
    scorecard,
)


def case():
    return {
        "case_id": "SYN-TEST",
        "snapshot_date": "2026-11-01",
        "documents": [],
        "inventory": [{"product_id": "A", "available_stock": 40}],
        "inbound": [{"receipt_id": "R1", "po_id": "PO1", "product_id": "A", "quantity": 100, "original_eta": "2026-11-03", "eta": "2026-11-08"}],
        "orders": [{"order_id": "O1", "product_id": "A", "quantity": 100, "due_date": "2026-11-05"}],
        "quotes": [{"quote_id": "Q1", "product_id": "A", "supplier_id": "S1",
                    "supplier_risk": "LOW", "capacity": 60, "arrival_date": "2026-11-04",
                    "unit_price": "1000.00", "shipping_cost": "500.00"}],
    }


def codes(result):
    return {item["issue_code"] for item in result["issues"]}


def test_valid_case():
    assert audit_case(case())["qa_status"] == "PASS"


@pytest.mark.parametrize("section,key,value", [
    ("inventory", "available_stock", -1),
    ("inbound", "quantity", True),
    ("orders", "quantity", 1.1),
    ("quotes", "capacity", -9),
    ("inbound", "eta", "2026-02-30"),
    ("orders", "due_date", "2026년 11월 5일"),
    ("quotes", "unit_price", "NaN"),
    ("quotes", "shipping_cost", "-1.00"),
    ("quotes", "currency", "USD"),
])
def test_invalid_fields(section, key, value):
    payload = case()
    payload[section][0][key] = value
    assert audit_case(payload)["qa_status"] == "FAIL"


def test_duplicate_receipt():
    payload = case()
    payload["inbound"].append(payload["inbound"][0].copy())
    assert "DUPLICATE_IDENTIFIER" in codes(audit_case(payload))


@pytest.mark.parametrize("bad", ['{"x":1,"x":2}', '{"n":NaN}', '{"n":Infinity}'])
def test_reject_nonstandard_json(bad):
    with pytest.raises(ValueError):
        load_json_strict(bad)


def test_explicit_no_external_actions():
    assert "EXTERNAL_ACTION_NOT_DISPROVEN" in codes(audit_case(case(), {"external_action_taken": None}))


def test_draft_cannot_claim_accuracy():
    assert "UNSUPPORTED_ACCURACY" in codes(audit_provenance(
        {"provenance": "DRAFT_GOLD", "measured_extraction_accuracy": 1.0}))


def test_studio_requires_ids():
    assert "LIVE_EVIDENCE_MISSING" in codes(audit_provenance({"provenance": "REAL_STUDIO_RUN"}))


def test_human_gold_requires_evidence():
    assert "REVIEW_NOT_EVIDENCED" in codes(audit_provenance({"provenance": "HUMAN_VERIFIED_GOLD"}))


def test_scorecard_does_not_invent_accuracy():
    x = scorecard([audit_case(case()), {"qa_status": "FAIL"}])
    assert x["pass_rate"] == .5
    assert x["studio_extraction_accuracy"] is None


def test_json_round_trip():
    assert load_json_strict(json.dumps(case())) == case()


@pytest.mark.parametrize("missing", [
    "case_id", "snapshot_date", "inventory", "inbound", "orders", "quotes", "documents"
])
def test_no_falsely_pass_when_required_field_missing(missing):
    payload = case()
    del payload[missing]
    assert "MISSING_REQUIRED_FIELD" in codes(audit_case(payload))


def test_empty_case_cannot_pass():
    assert audit_case({})["qa_status"] == "FAIL"


def test_duplicate_inventory_product():
    payload = case()
    payload["inventory"].append(payload["inventory"][0].copy())
    assert "DUPLICATE_IDENTIFIER" in codes(audit_case(payload))


def test_missing_inbound_po():
    payload = case()
    del payload["inbound"][0]["po_id"]
    assert "MISSING_PO_ID" in codes(audit_case(payload))


@pytest.mark.parametrize("field", ["unit_price", "shipping_cost"])
def test_integer_money_allowed_as_in_engine(field):
    payload = case()
    payload["quotes"][0][field] = 500
    assert audit_case(payload)["qa_status"] == "PASS"


@pytest.mark.parametrize("invalid_money", [True, 10.5, "Infinity", "-5", None])
def test_money_rejects_unsafe_types_and_values(invalid_money):
    payload = case()
    payload["quotes"][0]["unit_price"] = invalid_money
    assert "INVALID_MONEY" in codes(audit_case(payload))


@pytest.mark.parametrize("field", ["supplier_id", "supplier_risk"])
def test_missing_supplier_fields_are_blocked(field):
    payload = case()
    del payload["quotes"][0][field]
    assert "MISSING_SUPPLIER_FIELD" in codes(audit_case(payload))


@pytest.mark.parametrize("section", ["inbound", "quotes"])
def test_unknown_product_cannot_pass(section):
    payload = case()
    payload[section][0]["product_id"] = "UNKNOWN"
    assert "UNKNOWN_PRODUCT" in codes(audit_case(payload))


def test_empty_orders_cannot_pass():
    payload = case()
    payload["orders"].clear()
    assert "EMPTY_ORDERS" in codes(audit_case(payload))


def test_inbound_eta_on_snapshot_cannot_pass():
    payload = case()
    payload["inbound"][0]["eta"] = payload["snapshot_date"]
    assert "INBOUND_ETA_NOT_FUTURE" in codes(audit_case(payload))


@pytest.mark.parametrize("broken", [None, True, 17, "invalid"])
def test_bad_sections_fail_without_throwing(broken):
    payload = case()
    payload["orders"] = broken
    assert "INVALID_SECTION" in codes(audit_case(payload))


@pytest.mark.parametrize("invalid_kind", [
    [], {}, ["REAL_STUDIO_RUN"], {"source": "REAL_STUDIO_RUN"},
])
def test_unhashable_provenance_kind_fails_closed_without_exception(invalid_kind):
    result = audit_provenance({"provenance": invalid_kind})
    assert result["qa_status"] == "FAIL"
    assert "UNKNOWN_PROVENANCE" in codes(result)


@pytest.mark.parametrize("raw", [
    '{"value":1e999}', '{"value":-1e999}', '{"nested":[1e999]}',
    '{"value":1e-9999}', '{"value":-1e-9999}',
    '{"value":1e-99999999999999999999999999}',
])
def test_json_exponent_overflow_or_nonzero_underflow_is_rejected(raw):
    with pytest.raises(ValueError):
        load_json_strict(raw)


def test_finite_json_exponent_and_explicit_zero_are_preserved():
    assert load_json_strict('{"value":1.25e2,"zero":0e-9999}') == {
        "value": 125.0, "zero": 0.0,
    }


@pytest.mark.parametrize("invalid_kind", [None, 0, False])
def test_nonstring_provenance_never_promoted_or_crashes(invalid_kind):
    result = audit_provenance({"provenance": invalid_kind})
    assert result["qa_status"] == "FAIL"
    assert "UNKNOWN_PROVENANCE" in codes(result)


def test_strict_json_preserves_negative_zero_and_nested_underflow_is_blocked():
    assert repr(load_json_strict('{"zero":-0e-9999}')["zero"]) == "-0.0"
    with pytest.raises(ValueError):
        load_json_strict('{"nested":[{"amount":-1e-9999}]}')
