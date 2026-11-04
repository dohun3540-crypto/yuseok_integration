"""동일 바이트 검사·PDF 구조 검사 회귀. 합성 시험이며 Gold 검수 아님."""

import io
import tarfile

import pytest

from qa.inventory import archive_pdfs, inspect_pdf, safe_name


def test_archive_accepts_byte_snapshot():
    buffer = io.BytesIO()
    data = b"%PDF-1.4\nsynthetic"
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        member = tarfile.TarInfo("a.pdf")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    snapshot = buffer.getvalue()
    assert archive_pdfs(snapshot, {"a.pdf"}) == {"a.pdf": data}


@pytest.mark.parametrize("name", [".", "a\x00.pdf", "a\n.pdf"])
def test_empty_or_control_path_rejected(name):
    with pytest.raises(ValueError):
        safe_name(name)


def test_blank_page_is_not_source_text():
    pypdf = pytest.importorskip("pypdf", reason="PDF 시험은 qa/requirements.txt 필요")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    pages, available, texts, status, _ = inspect_pdf(buffer.getvalue())
    assert (pages, available, texts, status) == (1, False, [""], "PASS")


def test_invalid_pdf_is_failure():
    assert inspect_pdf(b"not a PDF")[3] == "FAIL"


def test_encrypted_pdf_is_blocked():
    pypdf = pytest.importorskip("pypdf", reason="PDF 시험은 qa/requirements.txt 필요")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("unit-test-only")
    buffer = io.BytesIO()
    writer.write(buffer)
    assert inspect_pdf(buffer.getvalue())[3] == "BLOCKED"
