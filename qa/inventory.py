"""원본 무변경 PDF 검사. python -m qa.inventory --root . --out 새경로.

기계 검사는 사람 검수·Studio 실행·Gold 승인과 다르다.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import re
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 200 * 1024 * 1024
KINDS = {"purchase_order", "delivery_notice", "quotation"}
REVIEW_COLUMNS = [
    "case_id", "document_id", "source_filename", "source_file_sha256",
    "page", "line_or_table_location", "field_path", "source_original_text",
    "normalized_candidate_json", "draft_value_json", "draft_match",
    "ambiguity", "reviewer", "reviewed_at", "decision", "approval_state",
    "gold_version", "gold_sha256",
]


def strict_json(text):
    """중복 키와 비표준 숫자를 거절한다."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"중복 JSON 키: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"비표준 JSON 숫자: {value}")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid,
                      parse_float=finite_float)


def safe_name(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("잘못된 경로")
    if any(ord(char) < 32 for char in name):
        raise ValueError("경로 제어문자 거절")
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or ".." in path.parts
            or path.as_posix() != name):
        raise ValueError(f"안전하지 않은 경로: {name}")
    return path


def read_local(root, relative):
    """신뢰된 로컬 체크아웃에서 링크를 따라가지 않고 제한된 바이트를 읽는다."""
    path = Path(root)
    for part in safe_name(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"심볼릭 링크 거절: {relative}")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"파일 유형 또는 크기 제한: {relative}")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"파일 크기 제한: {relative}")
    return data


def archive_pdfs(path, allowed):
    """파일 경로 또는 바이트 스냅샷에서 허용 PDF만 읽는다. 디스크 해제 없음."""
    result, seen, total = {}, set(), 0
    options = {"fileobj": io.BytesIO(path)} if isinstance(path, bytes) else {"name": path}
    with tarfile.open(mode="r:xz", **options) as archive:
        for index, member in enumerate(archive):
            if index >= 1000:
                raise ValueError("아카이브 항목 수 제한")
            name = member.name.removeprefix("./")
            if member.isdir():
                if name in {"", "."}:
                    continue
                directory = safe_name(name.rstrip("/"))
                if not any(directory in PurePosixPath(x).parents for x in allowed):
                    raise ValueError(f"허용되지 않은 디렉터리: {name}")
                continue
            safe_name(name)
            if not member.isfile() or name not in allowed or name in seen:
                raise ValueError(f"허용되지 않은 파일·링크·중복: {name}")
            seen.add(name)
            if member.size < 0 or member.size > MAX_FILE_BYTES:
                raise ValueError(f"아카이브 파일 크기 제한: {name}")
            total += member.size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("아카이브 전체 크기 제한")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"아카이브 읽기 실패: {name}")
            with stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) != member.size or not data.startswith(b"%PDF-"):
                raise ValueError(f"PDF 바이트 형식 오류: {name}")
            result[name] = data
    return result


def inspect_pdf(data):
    if not data.startswith(b"%PDF-"):
        return None, None, [], "FAIL", "PDF 헤더 오류"
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError:
        return None, None, [], "BLOCKED", "pypdf 설치 필요"
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            return None, None, [], "BLOCKED", "암호화 PDF"
        texts = [page.extract_text() or "" for page in reader.pages]
        if not texts:
            return 0, False, [], "FAIL", "페이지 없음"
        return len(texts), any(t.strip() for t in texts), texts, "PASS", ""
    except (PyPdfError, ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        return None, None, [], "FAIL", f"PDF 분석 실패: {type(exc).__name__}"


def manifest_entries(root):
    entries = []
    for number in range(1, 21):
        case_id = f"SYN-C{number:03d}"
        folder = f"data/cases/{case_id}"
        raw = read_local(root, f"{folder}/manifest.json")
        if raw is None:
            raise FileNotFoundError(f"{folder}/manifest.json")
        manifest = strict_json(raw.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError(f"manifest 객체 필요: {case_id}")
        docs = manifest.get("documents")
        if manifest.get("case_id") != case_id or not isinstance(docs, list):
            raise ValueError(f"manifest 케이스 또는 배열 오류: {case_id}")
        if len(docs) != 3 or not all(isinstance(d, dict) for d in docs):
            raise ValueError(f"문서 객체 3개 필요: {case_id}")
        if {d.get("document_type") for d in docs} != KINDS:
            raise ValueError(f"문서 3종 구성 오류: {case_id}")
        identifiers, names = set(), set()
        for doc in docs:
            filename = doc.get("filename")
            if len(safe_name(filename).parts) != 1 or not filename.endswith(".pdf"):
                raise ValueError(f"PDF 파일명 오류: {case_id}")
            did, digest = doc.get("document_id"), doc.get("sha256")
            if not isinstance(did, str) or not did.strip() or did in identifiers:
                raise ValueError(f"문서 ID 누락·중복: {case_id}")
            if filename in names or not isinstance(digest, str):
                raise ValueError(f"파일명 중복 또는 해시 누락: {case_id}")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"SHA-256 형식 오류: {case_id}")
            pages = doc.get("pages")
            if pages is not None and (type(pages) is not int or pages < 1):
                raise ValueError(f"페이지 수 형식 오류: {case_id}")
            identifiers.add(did)
            names.add(filename)
            entries.append((case_id, folder, doc, manifest))
    return entries


def collect(root):
    root = Path(root).resolve()
    entries = manifest_entries(root)
    allowed = {f"{folder}/{doc['filename']}" for cid, folder, doc, _ in entries
               if cid != "SYN-C001"}
    archive_path = "data/cases/SYN-C002-C020_DRAFT_PDFs.tar.xz"
    archive_bytes = read_local(root, archive_path)
    # 해시와 PDF 검사가 동일한 원본 바이트 스냅샷을 사용한다.
    archived = archive_pdfs(archive_bytes, allowed) if archive_bytes is not None else {}
    rows, text_pages = [], []
    for cid, folder, doc, manifest in entries:
        relative = f"{folder}/{doc['filename']}"
        local, packed = read_local(root, relative), archived.get(relative)
        conflict = local is not None and packed is not None and local != packed
        data = local if local is not None else packed
        row = {
            "case_id": cid, "document_id": doc["document_id"],
            "document_type": doc["document_type"], "filename": doc["filename"],
            "source_path": relative,
            "source_storage": "local" if local is not None else (
                "archive" if packed is not None else "missing"),
            "file_exists": data is not None, "local_file_exists": local is not None,
            "expected_sha256": doc["sha256"], "sha256": None,
            "expected_page_count": doc.get("pages"), "page_count": None,
            "source_text_available": None, "manifest_match": None,
            "label_status": "DRAFT", "human_reviewed": None,
            "human_review_status": "NOT_VERIFIED", "studio_executed": None,
            "manifest_studio_executed": manifest.get("studio_executed"),
            "status": "BLOCKED", "reason": "원본 파일 없음",
        }
        if data is not None:
            digest = hashlib.sha256(data).hexdigest()
            count, available, texts, status, reason = inspect_pdf(data)
            match = digest == doc["sha256"]
            row.update(sha256=digest, page_count=count, source_text_available=available,
                       manifest_match=match, status=status, reason=reason)
            wrong_pages = (doc.get("pages") is not None and count is not None
                           and count != doc["pages"])
            if conflict or not match or wrong_pages:
                row.update(status="FAIL", reason="원본 복사본·해시·페이지 수 불일치")
            for page, text in enumerate(texts, 1):
                text_pages.append({
                    "case_id": cid, "document_id": doc["document_id"],
                    "source_filename": doc["filename"], "source_file_sha256": digest,
                    "page": page, "text": text, "human_reviewed": False,
                    "source": "pypdf", "visual_review": "NOT_RUN",
                })
        rows.append(row)
    hashes = {}
    for row in rows:
        if row["sha256"]:
            hashes.setdefault(row["sha256"], []).append(row["source_path"])
    duplicates = {key: paths for key, paths in hashes.items() if len(paths) > 1}
    archive_hash = hashlib.sha256(archive_bytes).hexdigest() if archive_bytes else None
    return rows, text_pages, duplicates, archive_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root, out = Path(args.root).resolve(), Path(args.out).resolve()
    if out == root or root / "data" == out or root / "data" in out.parents:
        raise ValueError("원본 data 아래에는 출력할 수 없음")
    if out.exists():
        raise FileExistsError("출력은 새 디렉터리만 허용")
    rows, pages, duplicates, archive_hash = collect(root)
    out.mkdir(parents=True, exist_ok=False)
    with (out / "DATA_INVENTORY.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (out / "SOURCE_TEXT_MACHINE.jsonl").open("x", encoding="utf-8") as stream:
        for page in pages:
            stream.write(json.dumps(page, ensure_ascii=False) + "\n")
    statuses = {row["status"] for row in rows}
    status = "FAIL" if "FAIL" in statuses else (
        "BLOCKED" if "BLOCKED" in statuses or duplicates else "PASS")
    report = {
        "status": status, "scope": "원본 기계 검사만; 사람 검수·성능 평가 아님",
        "created_at": datetime.now(UTC).isoformat(),
        "archive_sha256": archive_hash, "documents": len(rows),
        "status_counts": {s: sum(r["status"] == s for r in rows)
                          for s in ("PASS", "FAIL", "BLOCKED")},
        "duplicate_hashes": duplicates, "human_review": "NOT_RUN",
        "studio_evaluation": "NOT_RUN", "visual_review": "NOT_RUN",
    }
    with (out / "INVENTORY_REPORT.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
