"""합성 기록 시험. 사용자 엑셀 검증 결과가 아니다."""

from copy import deepcopy

import pytest

from qa.review_records import inspect_records, load_csv, valid_timestamp


def baseline_row():
    return {
        "document_id": "TEST-DOC", "source_filename": "test.pdf",
        "field_path": "po_id", "page": "1", "normalized_candidate": "001",
        "value_type": "string", "source_text": "001", "reviewer": "",
        "reviewed_at": "", "decision": "", "approval_state": "PENDING",
    }


def accepted_row():
    return dict(baseline_row(), reviewer="합성 시험 검수자",
                reviewed_at="2026-11-01T17:20:00+09:00",
                decision="ACCEPT", approval_state="REVIEWED_BY_MEMBER3")


@pytest.mark.parametrize("value", [
    "2026-11-01T17:20:00+09:00", "2026-11-01T08:20:00Z",
])
def test_valid_time(value):
    assert valid_timestamp(value)


@pytest.mark.parametrize("value", [
    None, "", "2026-11-01", "2026-11-01T17:20:00",
    "2026-11-01T117:20:00+09:00", "2026-02-30T17:20:00+09:00",
    "2026-11-01T17:20:00+09:60", "2026-11-01T17:20:00+14:01",
])
def test_invalid_time(value):
    assert not valid_timestamp(value)


def test_pass_does_not_promote_gold():
    row = accepted_row()
    before = deepcopy(row)
    report = inspect_records([row], [baseline_row()])
    assert report["record_check_status"] == "PASS"
    assert report["structurally_valid_rows"] == 1
    assert report["official_metrics_eligible"] is False
    assert report["gold_promoted"] is False
    assert row == before


@pytest.mark.parametrize("field,value,code", [
    ("reviewer", "", "MISSING_REVIEWER"),
    ("reviewed_at", "", "INVALID_REVIEW_TIME"),
    ("approval_state", "REVIEWD_BY_MEMBER3", "UNSUPPORTED_APPROVAL_STATE"),
    ("approval_state", "TEAM_APPROVED", "UNSUPPORTED_APPROVAL_STATE"),
    ("decision", "CORRECT", "DECISION_REQUIRES_SEPARATE_REVIEW"),
    ("normalized_candidate", "1", "BASELINE_CHANGED:normalized_candidate"),
    ("source_text", "변경", "BASELINE_CHANGED:source_text"),
    ("page", "2", "BASELINE_CHANGED:page"),
])
def test_invalid_record(field, value, code):
    row = accepted_row()
    row[field] = value
    report = inspect_records([row], [baseline_row()])
    assert report["record_check_status"] == "NEEDS_REVIEW"
    assert code in {issue["code"] for issue in report["issues"]}


def test_missing_and_duplicate_rows():
    assert inspect_records([], [baseline_row()])["issues"][0]["code"] == "MISSING_FIELD"
    report = inspect_records([accepted_row(), accepted_row()], [baseline_row()])
    assert "DUPLICATE_FIELD" in {issue["code"] for issue in report["issues"]}


def test_unknown_field():
    row = dict(accepted_row(), field_path="other")
    report = inspect_records([row], [baseline_row()])
    assert {i["code"] for i in report["issues"]} == {"UNKNOWN_FIELD", "MISSING_FIELD"}


def test_duplicate_baseline_rejected():
    with pytest.raises(ValueError):
        inspect_records([], [baseline_row(), baseline_row()])


@pytest.mark.parametrize("raw", [b"a,a\n1,2\n", b"a\n1\n", b""])
def test_bad_csv_headers(raw):
    with pytest.raises(ValueError):
        load_csv(raw)


def test_csv_keeps_identifier():
    row = baseline_row()
    raw = (",".join(row) + "\n" + ",".join(row.values()) + "\n").encode()
    assert load_csv(raw)[0]["normalized_candidate"] == "001"
