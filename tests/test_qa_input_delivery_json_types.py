"""Strict JSON type comparisons without weakening Studio wrapper/case checks.

Synthetic local contract tests; not Studio live-input authentication.
"""
import json
from copy import deepcopy

import pytest

from leadtime_guardian.qa.input_delivery import audit_normalize_qa_input


def audit_values(left, right):
    normalize = [{"document_id": "PO-DOC", "value": left}]
    qa_input = [{"document_id": "PO-DOC", "value": right}]
    return audit_normalize_qa_input(
        {"status": "COMPLETED", "case_id": "C001",
         "content": json.dumps({"documents": normalize}, allow_nan=False)
         if _serializable(left) else {"documents": normalize}},
        {"case_id": "C001", "input": {"normalized_documents": qa_input}},
        expected_case_id="C001",
    )


def _serializable(value):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return False
    return True


@pytest.mark.parametrize(("left", "right"), [
    (0, False),
    (1, True),
    (100, 100.0),
    (0, 0.0),
    (None, "null"),
    (None, ""),
    (None, []),
    ("100", 100),
    ([1, 2], (1, 2)),
    ({"1": "value"}, {1: "value"}),
    ({"items": [{"quantity": 0}]}, {"items": [{"quantity": False}]}),
    ({"nested": {"x": 100}}, {"nested": {"x": 100.0}}),
    ([1, 2], [2, 1]),
])
def test_json_type_or_content_changes_fail_closed(left, right):
    result = audit_values(left, right)
    assert result["input_delivery_status"] == "LOCAL_CONTENT_MISMATCH"
    assert result["qa_status"] == "FAIL"
    assert result["actual_cloud_input_authenticated"] is False
    assert result["release_or_merge_authorized"] is False


@pytest.mark.parametrize("value", [
    (1, 2),
    {"nested": (1, 2)},
    {1: "value"},
    {"nested": {1: "value"}},
    float("nan"),
    float("inf"),
    -float("inf"),
    {"confidence": float("nan")},
])
def test_non_json_values_cannot_be_local_matches_even_if_identical(value):
    result = audit_values(value, deepcopy(value))
    assert result["input_delivery_status"] == "LOCAL_CONTENT_MISMATCH"
    assert result["qa_status"] == "FAIL"


@pytest.mark.parametrize("value", [
    0, False, None, "null", "", 100, 100.0, [],
    {"quote": None}, {"items": [{"quantity": 0}]},
])
def test_valid_identical_json_values_preserve_local_only_status(value):
    result = audit_values(value, deepcopy(value))
    assert result["input_delivery_status"] == "LOCAL_CONTENT_MATCH"
    assert result["qa_status"] == "BLOCKED"
    assert result["actual_cloud_input_authenticated"] is False
    assert result["release_or_merge_authorized"] is False


def test_dict_key_order_does_not_change_json_content():
    result = audit_values(
        {"quantity": 0, "quote": None},
        {"quote": None, "quantity": 0},
    )
    assert result["input_delivery_status"] == "LOCAL_CONTENT_MATCH"


def test_comparison_does_not_mutate_inputs():
    left = {"items": [{"quantity": 0}], "quote": None}
    right = {"items": [{"quantity": False}], "quote": None}
    before_left, before_right = deepcopy(left), deepcopy(right)
    audit_values(left, right)
    assert left == before_left
    assert right == before_right
    assert type(left["items"][0]["quantity"]) is int
    assert type(right["items"][0]["quantity"]) is bool


def test_different_case_is_still_blocked_by_existing_case_binding():
    doc = [{"document_id": "PO-DOC", "quantity": 100}]
    result = audit_normalize_qa_input(
        {"status": "COMPLETED", "case_id": "C001",
         "output": {"documents": doc}},
        {"case_id": "C013", "normalized_documents": doc},
        expected_case_id="C001",
    )
    assert result["case_binding_conflict"] is True
    assert result["qa_status"] == "FAIL"


def test_double_wrapped_qa_payload_remains_unverified():
    doc = [{"document_id": "PO-DOC", "quantity": 100}]
    result = audit_normalize_qa_input(
        {"status": "COMPLETED", "output": {"documents": doc}},
        {"content": json.dumps(json.dumps({"normalized_documents": doc}))},
        expected_case_id="C001",
    )
    assert result["input_delivery_status"] == "QA_INPUT_WRAPPING_UNVERIFIED"
    assert result["qa_status"] == "BLOCKED"
