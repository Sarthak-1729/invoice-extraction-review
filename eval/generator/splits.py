"""Dev and test split definitions. Every document is listed explicitly so the
feature mix is a deliberate choice, not an accident of random sampling.

- dev (10 docs, seeds 1001-1010): for prompt tuning only.
- test (24 docs, seeds 2001-2024): held out; frozen before the first extraction run.

A few variants appear only in test on purpose (see the plan table) to measure
generalization to formats the prompt was never tuned on.
"""

from decimal import Decimal

from eval.generator.spec import DocConfig

SKU_STANDARD = ("sku", "description", "quantity", "unit_price", "amount")
SKU_AMOUNT_FIRST = ("sku", "description", "amount", "quantity", "unit_price")
AMOUNT_FIRST = ("description", "amount", "quantity", "unit_price")
QTY_FIRST = ("quantity", "description", "unit_price", "amount")

# Shared locale settings.
UK = dict(region="UK", currency="GBP", date_style="eu_slash", tax_label="VAT",
          tax_rate=Decimal("0.20"))  # fmt: skip
EUR = dict(region="EU", currency="EUR", number_style="eu", tax_label="VAT")
CHF = dict(region="EU", currency="CHF", number_style="swiss", currency_display="code_prefix",
           tax_label="VAT", tax_rate=Decimal("0.081"))  # fmt: skip
INR = dict(region="IN", currency="INR", number_style="indian", tax_label="GST")
JPY = dict(region="JP", currency="JPY", tax_label="Consumption tax")
AUD = dict(region="UK", currency="AUD", date_style="eu_slash")
CAD = dict(currency="CAD", tax_label="GST/HST", tax_rate=Decimal("0.13"))
NO_EXTRAS = dict(tax_rate=None, currency_note=False)


def _doc(split: str, n: int, layout: str, **settings) -> DocConfig:
    seed = (1000 if split == "dev" else 2000) + n
    return DocConfig(doc_id=f"{split}-{n:02d}", layout=layout, seed=seed, **settings)


DEV: list[DocConfig] = [
    _doc("dev", 1, "classic_us"),
    _doc("dev", 2, "classic_us", **UK, arithmetic_error="line", labels={"total": "Amount Due"}),
    _doc("dev", 3, "classic_us", date_style="long_mdy", services=True, has_due_date=False,
         **NO_EXTRAS),
    _doc("dev", 4, "european", **EUR, date_style="dotted", currency_display="symbol_suffix",
         currency_note=False, tax_rate=Decimal("0.19")),
    _doc("dev", 5, "european", **{**EUR, "number_style": "space"}, date_style="iso",
         currency_display="code_suffix", currency_note=False, tax_rate=Decimal("0.21"),
         injection=True, arithmetic_error="total"),
    _doc("dev", 6, "european", **CHF, date_style="long_dmy", arithmetic_error="subtotal",
         labels={"invoice_number": "Ref no."}),
    _doc("dev", 7, "modern", **INR, date_style="short_dmy", currency_note=False,
         tax_rate=Decimal("0.18")),
    _doc("dev", 8, "modern", **AUD, services=True, show_subtotal=False, has_bill_to=False,
         **NO_EXTRAS),
    _doc("dev", 9, "multipage", columns=SKU_STANDARD, n_lines=(35, 45), tax_rate=Decimal("0.07"),
         wrap_descriptions=True),
    _doc("dev", 10, "multipage", **UK, columns=QTY_FIRST, n_lines=(40, 50)),
]  # fmt: skip

TEST: list[DocConfig] = [
    # classic_us
    _doc("test", 1, "classic_us"),
    _doc("test", 2, "classic_us", date_style="long_mdy", services=True, has_due_date=False,
         **NO_EXTRAS, labels={"invoice_number": "Invoice No.", "total": "Amount Due"}),
    _doc("test", 3, "classic_us", **UK, arithmetic_error="total", injection=True),
    _doc("test", 4, "classic_us", **CAD, wrap_descriptions=True),
    _doc("test", 5, "classic_us", date_style="iso", currency_display="code_prefix",
         currency_note=False, has_bill_to=False, tax_rate=Decimal("0.06")),
    _doc("test", 6, "classic_us", **AUD, tax_label="GST", tax_rate=Decimal("0.10"),
         labels={"total": "Balance Due"}),
    # european
    _doc("test", 7, "european", **EUR, date_style="dotted", currency_display="symbol_suffix",
         currency_note=False, tax_rate=Decimal("0.19")),
    _doc("test", 8, "european", **{**EUR, "number_style": "space"}, date_style="iso",
         currency_display="code_suffix", currency_note=False, tax_rate=Decimal("0.21"),
         services=True, has_due_date=False, arithmetic_error="subtotal",
         labels={"invoice_number": "Ref no.", "total": "Amount payable"}),
    _doc("test", 9, "european", **CHF, date_style="long_dmy", injection=True),
    _doc("test", 10, "european", **EUR, date_style="short_dmy", currency_display="code_prefix",
         currency_note=False, tax_rate=Decimal("0.20"), has_bill_to=False),
    _doc("test", 11, "european", **EUR, date_style="dotted", currency_display="symbol_suffix",
         tax_rate=Decimal("0.07"), services=True),
    _doc("test", 12, "european", **CHF, date_style="dotted",
         labels={"subtotal": "Subtotal excl. VAT", "total": "Total incl. VAT"}),
    # modern
    _doc("test", 13, "modern", **INR, date_style="short_dmy", currency_note=False,
         tax_rate=Decimal("0.18")),
    _doc("test", 14, "modern", **JPY, date_style="iso", tax_rate=Decimal("0.10"),
         labels={"invoice_number": "Document no."}),
    _doc("test", 15, "modern", **AUD, services=True, show_subtotal=False, has_bill_to=False,
         **NO_EXTRAS),
    _doc("test", 16, "modern", **INR, date_style="long_dmy", currency_display="code_prefix",
         currency_note=False, tax_rate=Decimal("0.12"), arithmetic_error="line"),
    _doc("test", 17, "modern", date_style="long_mdy", services=True, **NO_EXTRAS),
    _doc("test", 18, "modern", **JPY, date_style="long_dmy", currency_display="code_suffix",
         currency_note=False, tax_rate=Decimal("0.08"), has_due_date=False),
    # multipage
    _doc("test", 19, "multipage", columns=SKU_STANDARD, n_lines=(40, 48),
         tax_rate=Decimal("0.07")),
    _doc("test", 20, "multipage", **EUR, date_style="dotted", currency_display="symbol_suffix",
         columns=SKU_AMOUNT_FIRST, n_lines=(35, 45), tax_rate=Decimal("0.20"),
         arithmetic_error="line", labels={"total": "Balance due"}),
    _doc("test", 21, "multipage", **CAD, date_style="long_dmy", number_style="plain",
         currency_display="code_prefix", currency_note=False, columns=QTY_FIRST,
         n_lines=(55, 60), has_due_date=False),
    _doc("test", 22, "multipage", columns=SKU_STANDARD, n_lines=(35, 40),
         tax_rate=Decimal("0.08"), wrap_descriptions=True),
    _doc("test", 23, "multipage", **UK, number_style="us", columns=AMOUNT_FIRST,
         n_lines=(36, 44)),
    _doc("test", 24, "multipage", **JPY, date_style="iso", columns=SKU_STANDARD,
         n_lines=(35, 45), tax_rate=Decimal("0.10")),
]  # fmt: skip

SPLITS = {"dev": DEV, "test": TEST}
