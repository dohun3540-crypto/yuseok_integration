"""합성 XLSX 셀 보존 시험. 사용자 수정본 검사와는 다르다."""

import hashlib
import io
from datetime import datetime

import pytest

from qa.xlsx_snapshot import snapshot


@pytest.fixture
def workbook():
    pytest.importorskip("defusedxml")
    library = pytest.importorskip("openpyxl")
    book = library.Workbook()
    yield book
    book.close()


def as_bytes(book):
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def test_types_and_formats_preserved(workbook):
    sheet = workbook.active
    sheet.append(["001", "1000.00", 1000, datetime(2026, 11, 3), "null"])
    sheet["C1"].number_format = "0.00"
    raw = as_bytes(workbook)
    digest = hashlib.sha256(raw).hexdigest()
    result = snapshot(raw)
    cells = {cell["coordinate"]: cell for cell in result["cells"]}
    assert cells["A1"]["value"] == "001"
    assert cells["B1"]["value"] == "1000.00"
    assert cells["C1"]["value"] == 1000
    assert cells["C1"]["number_format"] == "0.00"
    assert cells["D1"]["python_type"] == "datetime"
    assert cells["D1"]["value"] == "2026-11-03T00:00:00"
    assert cells["E1"]["value"] == "null"
    assert result["source_sha256"] == digest
    assert hashlib.sha256(raw).hexdigest() == digest
    assert result["gold_promoted"] is False


def test_formula_never_runs(workbook):
    workbook.active["A1"] = "=1+1"
    result = snapshot(as_bytes(workbook))
    assert result["cells"][0]["value"] == "=1+1"
    assert result["status"] == "NEEDS_REVIEW"
    assert result["formulas_executed"] is False


def test_multiple_sheets_require_selection(workbook):
    workbook.create_sheet("두번째")
    raw = as_bytes(workbook)
    with pytest.raises(ValueError, match="시트가 여러"):
        snapshot(raw)
    assert snapshot(raw, "두번째")["sheet"] == "두번째"


def test_merged_cells_reported(workbook):
    workbook.active.merge_cells("A1:B1")
    result = snapshot(as_bytes(workbook))
    assert result["merged_ranges"] == ["A1:B1"]
    assert result["status"] == "NEEDS_REVIEW"


def test_hidden_and_empty_cells_preserved(workbook):
    sheet = workbook.active
    sheet["C3"] = "확인"
    sheet.row_dimensions[3].hidden = True
    result = snapshot(as_bytes(workbook))
    assert result["hidden_rows"] == [3]
    assert len(result["cells"]) == 1
    assert result["cells"][0]["coordinate"] == "C3"
