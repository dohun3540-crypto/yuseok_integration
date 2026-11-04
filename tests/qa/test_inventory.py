"""팀원3 검사 도구의 합성 단위 테스트. Studio 성능 시험이 아니다."""

import hashlib
import io
import tarfile

import pytest

from qa.inventory import archive_pdfs, read_local, safe_name, strict_json


@pytest.mark.parametrize("name", ["../a.pdf", "/a.pdf", "a/../b.pdf", "a\\b.pdf", "C:a.pdf"])
def test_unsafe_names(name):
    with pytest.raises(ValueError):
        safe_name(name)


def test_safe_name():
    assert str(safe_name("data/cases/SYN-C002/a.pdf")) == "data/cases/SYN-C002/a.pdf"


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{'])
def test_invalid_json(text):
    with pytest.raises(ValueError):
        strict_json(text)


def test_null_zero_and_identifier():
    value = strict_json('{"id":"001","missing":null,"quantity":0}')
    assert value == {"id": "001", "missing": None, "quantity": 0}
    assert "absent" not in value


def make_archive(path, members):
    with tarfile.open(path, "w:xz") as archive:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(data) if kind == tarfile.REGTYPE else 0
            if kind == tarfile.SYMTYPE:
                info.linkname = "/etc/passwd"
            archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)


def test_archive_read_preserves_bytes(tmp_path):
    path = tmp_path / "input.tar.xz"
    name = "data/cases/SYN-C002/a.pdf"
    data = b"%PDF-1.4\nunit-test-only"
    make_archive(path, [(name, data, tarfile.REGTYPE)])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert archive_pdfs(path, {name}) == {name: data}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_archive_links_rejected(tmp_path, kind):
    path = tmp_path / "input.tar.xz"
    make_archive(path, [("a.pdf", b"", kind)])
    with pytest.raises(ValueError):
        archive_pdfs(path, {"a.pdf"})


def test_archive_duplicate_rejected(tmp_path):
    path = tmp_path / "input.tar.xz"
    entry = ("a.pdf", b"%PDF-1.4", tarfile.REGTYPE)
    make_archive(path, [entry, entry])
    with pytest.raises(ValueError):
        archive_pdfs(path, {"a.pdf"})


def test_archive_unlisted_rejected(tmp_path):
    path = tmp_path / "input.tar.xz"
    make_archive(path, [("extra.pdf", b"%PDF-1.4", tarfile.REGTYPE)])
    with pytest.raises(ValueError):
        archive_pdfs(path, {"expected.pdf"})


def test_archive_fake_pdf_rejected(tmp_path):
    path = tmp_path / "input.tar.xz"
    make_archive(path, [("a.pdf", b"not a pdf", tarfile.REGTYPE)])
    with pytest.raises(ValueError):
        archive_pdfs(path, {"a.pdf"})


def test_missing_local_is_not_zero(tmp_path):
    assert read_local(tmp_path, "absent.pdf") is None


def test_local_symlink_rejected(tmp_path):
    (tmp_path / "target.pdf").write_bytes(b"%PDF-1.4")
    try:
        (tmp_path / "link.pdf").symlink_to(tmp_path / "target.pdf")
    except OSError:
        pytest.skip("이 환경은 심볼릭 링크 생성 권한이 없음")
    with pytest.raises(ValueError):
        read_local(tmp_path, "link.pdf")
