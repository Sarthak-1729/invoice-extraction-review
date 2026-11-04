"""Generator tests. Run from the repo root: python -m pytest eval/tests"""

import dataclasses
import hashlib
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.invoice import RawExtraction
from app.validation.checks import check_invoice
from app.validation.flags import FlagCode
from app.validation.formats import parse_amount
from eval.generator.formatting import format_date, format_money, format_number
from eval.generator.generate import MANIFEST, generate_split, render_document, write_manifest
from eval.generator.layouts import LAYOUTS
from eval.generator.samples import SAMPLES
from eval.generator.spec import build_spec
from eval.generator.splits import SPLITS
from eval.generator.truth import truth_dict

ARITHMETIC_CODES = {
    FlagCode.LINE_AMOUNT_MISMATCH,
    FlagCode.SUBTOTAL_MISMATCH,
    FlagCode.TOTAL_MISMATCH,
}
ALL_SAMPLES = [config for configs in SAMPLES.values() for config in configs]


@pytest.mark.parametrize(
    ("value", "style", "places", "expected"),
    [
        ("1234567.891", "us", 2, "1,234,567.89"),
        ("1234567.891", "eu", 2, "1.234.567,89"),
        ("1234567.891", "space", 2, "1 234 567,89"),
        ("1234567.891", "swiss", 2, "1'234'567.89"),
        ("1234567.891", "indian", 2, "12,34,567.89"),
        ("1234567.891", "plain", 2, "1234567.89"),
        ("999", "us", 2, "999.00"),
        ("12000", "us", 0, "12,000"),
        ("2.50", "eu", None, "2,5"),
        ("7", "us", None, "7"),
        ("0.005", "us", 2, "0.01"),  # half-up rounding
    ],
)
def test_format_number(value, style, places, expected):
    assert format_number(Decimal(value), style, places) == expected


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("us_slash", "03/25/2026"),
        ("eu_slash", "25/03/2026"),
        ("dotted", "25.03.2026"),
        ("iso", "2026-03-25"),
        ("long_mdy", "March 25, 2026"),
        ("long_dmy", "25 March 2026"),
        ("short_dmy", "25-Mar-2026"),
    ],
)
def test_format_date(style, expected):
    assert format_date(date(2026, 3, 25), style) == expected


@pytest.mark.parametrize("style", ["us", "eu", "space", "swiss", "indian", "plain"])
@pytest.mark.parametrize("display", ["symbol_prefix", "symbol_suffix", "code_prefix", "none"])
@pytest.mark.parametrize("currency", ["USD", "EUR", "CHF", "INR", "JPY"])
def test_printed_money_parses_back_to_value(style, display, currency):
    """Generator formatting and app parsing must agree, or labels would be unreachable."""
    value = Decimal("1234567.5") if currency != "JPY" else Decimal("1234567")
    printed = format_money(value, currency, style, display)
    decimal_hint = "," if style in ("eu", "space") else "."
    minor = 0 if currency == "JPY" else 2
    assert parse_amount(printed, decimal_hint, minor).value == value


def _raw_from_truth(truth: dict) -> RawExtraction:
    """What a perfect extractor would return: every printed string, verbatim."""
    fields = {name: f["printed"] for name, f in truth["fields"].items()}
    items = [{name: f["printed"] for name, f in item.items()} for item in truth["line_items"]]
    return RawExtraction.model_validate({**fields, "line_items": items})


@pytest.mark.parametrize("config", ALL_SAMPLES, ids=lambda c: c.doc_id)
def test_perfect_extraction_normalizes_to_truth(config):
    truth = truth_dict(build_spec(config))
    result = check_invoice(_raw_from_truth(truth))
    invoice = result.invoice

    for name in ("subtotal", "tax", "total"):
        expected = truth["fields"][name]["value"]
        assert (str(getattr(invoice, name)) if getattr(invoice, name) is not None else None) == (
            expected
        ), name
    assert invoice.invoice_date.isoformat() == truth["fields"]["invoice_date"]["value"]
    for item, truth_item in zip(invoice.line_items, truth["line_items"], strict=True):
        assert item.amount == Decimal(truth_item["amount"]["value"])

    arithmetic = {f.code for f in result.flags} & ARITHMETIC_CODES
    if truth["arithmetic_consistent"]:
        assert not arithmetic
    else:
        assert arithmetic


def test_split_definitions_are_sound():
    dev, test = SPLITS["dev"], SPLITS["test"]
    assert (len(dev), len(test)) == (10, 24)
    all_configs = dev + test
    assert len({c.doc_id for c in all_configs}) == len(all_configs)
    assert not {c.seed for c in dev} & {c.seed for c in test}
    assert {c.layout for c in test} == set(LAYOUTS)
    # Agreed counts for the deliberate wrapped-description feature.
    assert sum(c.wrap_descriptions for c in dev) == 1
    assert sum(c.wrap_descriptions for c in test) == 2
    # Multipage docs state their columns explicitly, so features are recorded.
    assert all(c.columns for c in all_configs if c.layout == "multipage")
    for config in all_configs:
        build_spec(config)  # every config is valid


def test_wrapping_rejected_for_unsupported_layout():
    config = dataclasses.replace(SAMPLES["european"][0], wrap_descriptions=True)
    with pytest.raises(ValueError):
        build_spec(config)


def test_spec_is_deterministic():
    config = SAMPLES["classic_us"][0]
    assert truth_dict(build_spec(config)) == truth_dict(build_spec(config))


@pytest.mark.parametrize("config", ALL_SAMPLES, ids=lambda c: c.doc_id)
def test_rendered_pdf_is_verified_and_byte_stable(config, tmp_path):
    first = render_document(config, tmp_path / "a.pdf", tmp_path / "a.json")
    render_document(config, tmp_path / "b.pdf", tmp_path / "b.json")
    assert first["pages"] >= 1

    def digest(name):
        return hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()

    assert digest("a.pdf") == digest("b.pdf")
    assert digest("a.json") == digest("b.json")
    # Wrapped lines are reported only for, and always for, the wrap feature.
    assert bool(first["wrapped_line_items"]) == config.wrap_descriptions


def test_manifest_lists_every_file_and_split_hash_tracks_changes(tmp_path):
    (tmp_path / "pdf").mkdir()
    (tmp_path / "truth").mkdir()
    (tmp_path / "pdf" / "a.pdf").write_bytes(b"pdf")
    (tmp_path / "truth" / "a.json").write_bytes(b"{}")
    first = write_manifest(tmp_path)
    lines = (tmp_path / MANIFEST).read_text(encoding="utf-8").splitlines()
    assert [line.split("  ")[1] for line in lines] == ["pdf/a.pdf", "truth/a.json"]
    assert lines[0].split("  ")[0] == hashlib.sha256(b"pdf").hexdigest()
    assert write_manifest(tmp_path) == first  # the manifest never lists itself

    (tmp_path / "truth" / "a.json").write_bytes(b'{"edited": true}')
    assert write_manifest(tmp_path) != first


def test_split_generation_refuses_to_overwrite(tmp_path):
    (tmp_path / "dev").mkdir()
    with pytest.raises(SystemExit):
        generate_split("dev", tmp_path)
