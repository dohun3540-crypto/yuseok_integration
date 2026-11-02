"""XLSX 원본을 수정하지 않고 셀 값·자료형·표시 형식을 별도 JSON으로 기록한다.

수식은 실행하지 않는다. 표시 문자열을 재현하거나 정답/승인 기록을 보정하지 않는다.
"""

import argparse
import hashlib
import io
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zipfile import ZipFile

MAX_BYTES = 10 * 1024 * 1024
MAX_UNPACKED = 50 * 1024 * 1024
MAX_ROWS = 2000
MAX_COLUMNS = 64
MAX_SHEETS = 10


def check_container(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("XLSX 파일 크기 제한")
    with ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > 1000 or len(names) != len(set(names)):
            raise ValueError("압축 항목 수 또는 중복 오류")
        if sum(entry.file_size for entry in entries) > MAX_UNPACKED:
            raise ValueError("압축 해제 크기 제한")
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError("암호화 압축파일 거절")
        if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
            raise ValueError("XLSX 구성 누락")
        if any("vbaproject" in name.lower() or name.startswith("xl/externalLinks/")
               for name in names):
            raise ValueError("매크로 또는 외부 통합문서 연결 거절")


def encode_value(value):
    """날짜형과 문자열을 구분하며 숫자 표시 형식으로 값을 꾸미지 않는다."""
    if isinstance(value, (datetime, date, time)):
        return {"python_type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"python_type": "timedelta", "value": str(value)}
    if value is None or isinstance(value, (str, bool, int, float)):
        return {"python_type": type(value).__name__, "value": value}
    raise TypeError("지원하지 않는 셀 값 유형")


def snapshot(raw, sheet_name=None):
    check_container(raw)
    # XML 엔티티 확장을 방어하는 선택 라이브러리를 필수 확인한다.
    import defusedxml  # noqa: F401
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(raw), read_only=False, data_only=False,
                             keep_links=False)
    try:
        if len(workbook.sheetnames) > MAX_SHEETS:
            raise ValueError("시트 수 제한")
        if sheet_name is None:
            if len(workbook.sheetnames) != 1:
                raise ValueError("시트가 여러 개이면 --sheet를 명시해야 한다")
            sheet_name = workbook.sheetnames[0]
        if sheet_name not in workbook.sheetnames:
            raise ValueError("지정한 시트 없음")
        sheet = workbook[sheet_name]
        if sheet.max_row > MAX_ROWS or sheet.max_column > MAX_COLUMNS:
            raise ValueError("셀 범위 제한")
        cells, issues = [], []
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                entry = {
                    "coordinate": cell.coordinate, "row": cell.row,
                    "column": cell.column, "excel_type": cell.data_type,
                    "number_format": cell.number_format, **encode_value(cell.value),
                }
                cells.append(entry)
                if cell.data_type in {"f", "e"}:
                    issues.append({"cell": cell.coordinate,
                                   "reason": "수식 또는 Excel 오류 셀; 승인값으로 사용 금지"})
        merged = [str(region) for region in sheet.merged_cells.ranges]
        if merged:
            issues.append({"reason": "병합 셀 존재; 행별 기록 매핑 전 확인 필요"})
        hidden_rows = [index for index, dim in sheet.row_dimensions.items() if dim.hidden]
        hidden_columns = [index for index, dim in sheet.column_dimensions.items() if dim.hidden]
        return {
            "status": "NEEDS_REVIEW" if issues else "PASS",
            "scope": "선택한 시트의 셀 읽기만; Gold 승인·정확도 평가 아님",
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "sheet": sheet_name, "available_sheets": workbook.sheetnames,
            "sheet_state": sheet.sheet_state, "epoch": workbook.epoch.isoformat(),
            "max_row": sheet.max_row, "max_column": sheet.max_column,
            "cells": cells, "merged_ranges": merged,
            "hidden_rows": hidden_rows, "hidden_columns": hidden_columns,
            "empty_cells": "cells에 없는 좌표는 비어 있음; 원본 범위 내에서만 해석",
            "issues": issues, "formulas_executed": False, "gold_promoted": False,
            "official_metrics_eligible": False,
        }
    finally:
        workbook.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source, target = Path(args.input), Path(args.out)
    if source.suffix.lower() != ".xlsx":
        raise ValueError("XLSX 파일만 허용")
    if target.exists() or source.resolve() == target.resolve():
        raise FileExistsError("새 출력 파일 경로 필요")
    with source.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    result = snapshot(raw, args.sheet)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
