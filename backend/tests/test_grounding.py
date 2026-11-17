"""Grounding (VALUE_NOT_IN_DOCUMENT), checked against the real dev text layers."""

import json
from functools import cache

import pytest

from app.pdf_text import extract_text
from app.schemas.invoice import RawExtraction
from app.testset_guard import REPO_ROOT
from app.validation.checks import check_invoice
from app.validation.grounding import DocumentText, check_grounding, is_grounded

DEV = REPO_ROOT / "eval" / "datasets" / "dev"
DEV_IDS = [f"dev-{n:02d}" for n in range(1, 11)]


@cache
def dev_text(doc_id):
    return extract_text(DEV / "pdf" / f"{doc_id}.pdf", max_pages=20).text


def truth(doc_id):
    return json.loads((DEV / "truth" / f"{doc_id}.json").read_text(encoding="utf-8"))


def printed_raw(t):
    raw = {k: f["printed"] for k, f in t["fields"].items()}
    raw["line_items"] = [{k: f["printed"] for k, f in li.items()} for li in t["line_items"]]
    return raw


def test_zero_false_flags_on_all_645_dev_truth_values():
    values = flags = 0
    for doc_id in DEV_IDS:
        raw = printed_raw(truth(doc_id))
        values += sum(1 for v in raw.values() if isinstance(v, str))
        values += sum(1 for line in raw["line_items"] for v in line.values() if v)
        flags += len(check_grounding(RawExtraction.model_validate(raw), dev_text(doc_id)))
    assert values == 645
    assert flags == 0


def test_wrapped_descriptions_need_the_fallback_and_get_it():
    """dev-09's 22 wrapped descriptions are not contiguous in the text layer."""
    t = truth("dev-09")
    document = DocumentText(dev_text("dev-09"))
    wrapped = [
        li["description"]["printed"]
        for i, li in enumerate(t["line_items"])
        if i in t["wrapped_line_items"]
    ]
    assert len(wrapped) == 22
    assert not any(document.contains(d) for d in wrapped)
    assert all(document.contains_wrapped(d) for d in wrapped)


DEV09 = DocumentText(dev_text("dev-09")) if (DEV / "pdf" / "dev-09.pdf").exists() else None


@pytest.mark.parametrize(
    ("value", "field"),
    [
        ("Laser toner cartridge #3743, matteblack finish", "description"),  # missing space
        ("Network switch, 8-port#4901", "description"),  # missing space
        ("Laser toner cartridge #3743, matte black two-year limited warranty", "description"),
        ("INV-2026-782", "invoice_number"),  # prefix of the printed number
        ("$2,788.53", "amount"),  # one digit off
        ("Evil Corp", "vendor_name"),  # invented
    ],
)
def test_rejected_values(value, field):
    assert not is_grounded(value, DEV09, field)


@pytest.mark.parametrize(
    ("value", "field"),
    [
        ("INV-2026-7821", "invoice_number"),
        ("$2,788.52", "amount"),
        ("2,788.52", "amount"),  # the currency symbol dropped: still in the text
        ("$", "currency"),
        ("Laser toner cartridge #3743, matte black", "description"),
        ("  Network   switch, 8-port #4901 ", "description"),  # extra spaces collapse
    ],
)
def test_accepted_values(value, field):
    assert is_grounded(value, DEV09, field)


def test_wrapped_fallback_is_for_descriptions_only():
    wrapped = (
        "Laser toner cartridge #3743, matte black finish, wall-mount bracket included, "
        "two-year limited warranty"
    )
    assert is_grounded(wrapped, DEV09, "description")
    assert not is_grounded(wrapped, DEV09, "vendor_name")


def test_misplaced_values_are_a_known_limit():
    """An item code inserted into a wrapped description is still in the text.
    Documented in the README; grounding cannot catch misplaced values."""
    misplaced = (
        "Laser toner cartridge #3743, matte black C396-82 finish, wall-mount bracket "
        "included, two-year limited warranty"
    )
    assert is_grounded(misplaced, DEV09, "description")


def test_flags_name_the_field_path_and_skip_nulls():
    raw = printed_raw(truth("dev-01"))
    raw["vendor_name"] = "Invented Vendor GmbH"
    raw["due_date"] = None
    raw["line_items"][2]["amount"] = "$46.15"
    flags = check_grounding(RawExtraction.model_validate(raw), dev_text("dev-01"))
    assert [(f.field_path, f.code, f.severity) for f in flags] == [
        ("vendor_name", "VALUE_NOT_IN_DOCUMENT", "error"),
        ("line_items[2].amount", "VALUE_NOT_IN_DOCUMENT", "error"),
    ]


def test_check_invoice_adds_grounding_only_with_text():
    raw = printed_raw(truth("dev-01"))
    raw["vendor_name"] = "Invented Vendor GmbH"
    model = RawExtraction.model_validate(raw)
    assert not any(f.code == "VALUE_NOT_IN_DOCUMENT" for f in check_invoice(model).flags)
    with_text = check_invoice(model, document_text=dev_text("dev-01")).flags
    assert [f.field_path for f in with_text if f.code == "VALUE_NOT_IN_DOCUMENT"] == ["vendor_name"]
