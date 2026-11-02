"""Read-only C001 candidate/manifest/matrix consistency checks.

Checks consistency of provided *draft* records, not original PDF semantic accuracy.
Gold approval, Studio inference accuracy, and human review remain NOT_VERIFIED.
"""
import csv
import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "data/cases/SYN-C001"
CANDIDATE_ROOT = ROOT / "qa/gold_candidates/SYN-C001"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _records():
    candidate = _json(CANDIDATE_ROOT / "candidate.v1.json")
    manifest = _json(CASE / "manifest.json")
    draft = _json(CASE / "extraction_gold.DRAFT.json")
    with (CANDIDATE_ROOT / "PDF_EVIDENCE_MATRIX.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        matrix = list(csv.DictReader(stream))
    return candidate, manifest, draft, matrix


def _field(document, path):
    obj = document
    for part in path.split("."):
        match = re.fullmatch(r"([A-Za-z_]+)\[(\d+)\]", part)
        if match:
            obj = obj[match.group(1)][int(match.group(2))]
        else:
            obj = obj[part]
    return obj


def test_candidate_source_identity_binds_three_manifest_pdf_hashes():
    candidate, manifest, _, _ = _records()
    expected = {d["document_id"]: d for d in manifest["documents"]}
    assert candidate["case_id"] == manifest["case_id"] == "SYN-C001"
    assert len(candidate["sources"]) == len(expected) == 3
    assert {s["document_id"] for s in candidate["sources"]} == set(expected)
    for src in candidate["sources"]:
        record = expected[src["document_id"]]
        assert (src["filename"], src["sha256"], src["source_page"]) == (
            record["filename"], record["sha256"], record["pages"]
        )
        assert record["document_type"] == candidate["document_class_gold_candidate"][
            src["document_id"]
        ]


def test_candidate_remains_unapproved_and_source_draft_not_rewritten():
    candidate, manifest, draft, _ = _records()
    assert candidate["label_status"] == "AI_CANDIDATE"
    assert candidate["human_reviewed"] is False
    assert candidate["team_approved"] is False
    assert candidate["gold_frozen"] is False
    assert candidate["eligible_for_official_metrics"] is False
    assert candidate["gold_sha256"] is None
    assert manifest["human_gold_reviewed"] is False
    assert draft["human_reviewed"] is False
    assert draft["provenance"] == "generator source; NOT Studio predictions"
    assert all(d["warnings"] == [] and d["evidence"] == []
               for d in draft["documents"])


def test_candidate_preserves_draft_value_types_without_fabricating_gold():
    candidate, _, draft, _ = _records()
    cdocs = {x["document_id"]: x for x in candidate["field_gold_candidate"]}
    ddocs = {x["document_id"]: x for x in draft["documents"]}
    assert set(cdocs) == set(ddocs)
    for identifier, doc in cdocs.items():
        expected = {key: value for key, value in ddocs[identifier].items()
                    if key not in ("warnings", "evidence")}
        assert doc == expected
        assert type(doc["items"][0]["quantity"]) is int


def test_evidence_matrix_all_rows_bind_exact_candidate_types_and_source():
    candidate, _, _, rows = _records()
    source_by_id = {s["document_id"]: s for s in candidate["sources"]}
    docs = {d["document_id"]: d for d in candidate["field_gold_candidate"]}
    assert len(rows) == 40
    assert len({(r["document_id"], r["field_path"]) for r in rows}) == 40
    for row in rows:
        did = row["document_id"]
        assert did in source_by_id
        assert row["source_filename"] == source_by_id[did]["filename"]
        assert row["page"] == str(source_by_id[did]["source_page"])
        value = _field(docs[did], row["field_path"])
        typed = row["value_type"]
        if typed == "null":
            assert value is None
            assert row["normalized_candidate"] == "null"
        elif typed == "integer":
            assert type(value) is int
            assert row["normalized_candidate"] == str(value)
        else:
            assert typed == "string"
            assert type(value) is str
            assert row["normalized_candidate"] == value
        assert row["approval_state"] == "PENDING"
        assert not row["reviewer"] and not row["reviewed_at"]
        assert not row["decision"]


def test_po_notice_quote_roles_and_decimal_strings_remain_distinct():
    candidate, _, _, _ = _records()
    docs = {d["document_type"]: d for d in candidate["field_gold_candidate"]}
    po, notice, quote = (docs[t] for t in (
        "purchase_order", "delivery_notice", "quotation"
    ))
    assert po["po_id"] == notice["po_id"] == quote["po_id"] == "PO1"
    assert po["items"][0]["quantity"] == notice["items"][0]["quantity"] == 100
    assert quote["items"][0]["quantity"] == quote["quote"]["capacity"] == 60
    assert quote["items"][0]["receipt_id"] is None
    assert notice["revised_delivery"] == "2026-11-08"
    assert po["revised_delivery"] is None
    assert quote["quote"]["currency"] == "KRW"
    assert type(quote["quote"]["unit_price"]) is str
    assert type(quote["quote"]["shipping_cost"]) is str
    assert Decimal(quote["quote"]["unit_price"]) == Decimal("1000.00")
    assert Decimal(quote["quote"]["shipping_cost"]) == Decimal(500)
