"""검수 기록의 CSV 형식 검사. 사람 신원·원문 정답을 인증하지 않는다."""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path

KEYS = ("document_id", "source_filename", "field_path")
REQUIRED = set(KEYS) | {
    "page", "normalized_candidate", "value_type", "source_text",
    "reviewer", "reviewed_at", "decision", "approval_state",
}
TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})"
)


def valid_timestamp(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return False
    if not value.endswith("Z"):
        hours, minutes = int(value[-5:-3]), int(value[-2:])
        if minutes >= 60 or hours > 14 or (hours == 14 and minutes):
            return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def load_csv(raw):
    """UTF-8 CSV 바이트만 읽는다. OCR/파싱 텍스트로 셀을 복원하지 않는다."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)) or not REQUIRED.issubset(headers):
        raise ValueError("헤더 누락 또는 중복")
    rows = list(reader)
    if not rows:
        raise ValueError("검수 행 없음")
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("행의 열 수 불일치")
    return rows


def row_key(row):
    return tuple(row.get(key, "") for key in KEYS)


def inspect_records(rows, baseline):
    expected = {}
    for row in baseline:
        key = row_key(row)
        if any(not part for part in key) or key in expected:
            raise ValueError("기준 후보 식별자 누락 또는 중복")
        expected[key] = row
    if not expected:
        raise ValueError("기준 후보가 비어 있음")
    issues, seen, valid = [], set(), 0
    for line, row in enumerate(rows, 2):
        key, codes = row_key(row), []
        if key in seen:
            codes.append("DUPLICATE_FIELD")
        seen.add(key)
        if key not in expected:
            codes.append("UNKNOWN_FIELD")
        else:
            if not row.get("reviewer", "").strip():
                codes.append("MISSING_REVIEWER")
            if not valid_timestamp(row.get("reviewed_at")):
                codes.append("INVALID_REVIEW_TIME")
            if row.get("approval_state") != "REVIEWED_BY_MEMBER3":
                codes.append("UNSUPPORTED_APPROVAL_STATE")
            if row.get("decision") != "ACCEPT":
                codes.append("DECISION_REQUIRES_SEPARATE_REVIEW")
            for field in ("page", "normalized_candidate", "value_type", "source_text"):
                if row.get(field) != expected[key].get(field):
                    codes.append(f"BASELINE_CHANGED:{field}")
        issues.extend({"row": line, "code": code} for code in codes)
        if not codes:
            valid += 1
    for key in sorted(set(expected) - seen):
        issues.append({"row": None, "code": "MISSING_FIELD", "key": list(key)})
    return {
        "record_check_status": "PASS" if not issues else "NEEDS_REVIEW",
        "scope": "CSV 형식과 기준 후보 일치만 검사",
        "expected_rows": len(expected), "received_rows": len(rows),
        "structurally_valid_rows": valid, "issues": issues,
        "human_identity_verified": False, "source_visual_review_verified": False,
        "gold_promoted": False, "official_metrics_eligible": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    review_path, base_path, out = map(Path, (args.review, args.baseline, args.out))
    if review_path.suffix.lower() != ".csv" or base_path.suffix.lower() != ".csv":
        raise ValueError("CSV만 지원한다. XLSX 확장자만 변경하면 안 된다.")
    if out.exists() or out.resolve() in {review_path.resolve(), base_path.resolve()}:
        raise FileExistsError("새 보고서 경로 필요; 입력 덮어쓰기 금지")
    raw, base = review_path.read_bytes(), base_path.read_bytes()
    report = inspect_records(load_csv(raw), load_csv(base))
    report["review_sha256"] = hashlib.sha256(raw).hexdigest()
    report["baseline_sha256"] = hashlib.sha256(base).hexdigest()
    with out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return 0 if report["record_check_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
