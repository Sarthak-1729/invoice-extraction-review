"""Sample configs for reviewing each layout by eye before the real splits exist.

Samples are written to eval/samples/ (git-ignored) and are not part of any split.
"""

from decimal import Decimal

from eval.generator.spec import DocConfig

SAMPLES: dict[str, list[DocConfig]] = {
    "classic_us": [
        # Baseline: USD, MM/DD/YYYY, $ prefix, sales tax, currency note.
        DocConfig(doc_id="sample-classic-01", layout="classic_us", seed=101),
        # Services with fractional hours, long dates, no due date, no tax,
        # only "$" shown (ambiguous currency), unusual labels.
        DocConfig(
            doc_id="sample-classic-02",
            layout="classic_us",
            seed=102,
            date_style="long_mdy",
            services=True,
            has_due_date=False,
            tax_rate=None,
            currency_note=False,
            labels={"invoice_number": "Invoice No.", "total": "Amount Due"},
        ),
        # UK: GBP, DD/MM/YYYY, VAT 20%, deliberate total error, injection line.
        DocConfig(
            doc_id="sample-classic-03",
            layout="classic_us",
            seed=103,
            region="UK",
            currency="GBP",
            date_style="eu_slash",
            tax_label="VAT",
            tax_rate=Decimal("0.20"),
            arithmetic_error="total",
            injection=True,
        ),
    ],
    "european": [
        # Germany-style: EUR, DD.MM.YYYY, 1.234,56 €, VAT 19%, only € shown.
        DocConfig(
            doc_id="sample-euro-01",
            layout="european",
            seed=201,
            region="EU",
            currency="EUR",
            date_style="dotted",
            number_style="eu",
            currency_display="symbol_suffix",
            currency_note=False,
            tax_label="VAT",
            tax_rate=Decimal("0.19"),
        ),
        # ISO dates, 1 234,56 EUR, VAT 21%, hourly services, no due date,
        # unusual labels, deliberate subtotal error.
        DocConfig(
            doc_id="sample-euro-02",
            layout="european",
            seed=202,
            region="EU",
            currency="EUR",
            date_style="iso",
            number_style="space",
            currency_display="code_suffix",
            currency_note=False,
            services=True,
            has_due_date=False,
            tax_label="VAT",
            tax_rate=Decimal("0.21"),
            labels={"invoice_number": "Ref no.", "total": "Amount payable"},
            arithmetic_error="subtotal",
        ),
        # Swiss: CHF 1'234.56, "3 April 2026" dates, VAT 8.1%, deliberate
        # line-amount error, injection line.
        DocConfig(
            doc_id="sample-euro-03",
            layout="european",
            seed=203,
            region="EU",
            currency="CHF",
            date_style="long_dmy",
            number_style="swiss",
            currency_display="code_prefix",
            currency_note=True,
            tax_label="VAT",
            tax_rate=Decimal("0.081"),
            arithmetic_error="line",
            injection=True,
        ),
    ],
    "modern": [
        # India: Rs. 1,23,456.00 (lakh grouping), 21-Mar-2026 dates, GST 18%.
        DocConfig(
            doc_id="sample-modern-01",
            layout="modern",
            seed=301,
            region="IN",
            currency="INR",
            date_style="short_dmy",
            number_style="indian",
            currency_display="symbol_prefix",
            currency_note=False,
            tax_label="GST",
            tax_rate=Decimal("0.18"),
        ),
        # Japan: zero-decimal yen (¥12,000; "¥" alone is ambiguous, the note
        # says JPY), ISO dates, consumption tax 10%, unusual invoice-number label.
        DocConfig(
            doc_id="sample-modern-02",
            layout="modern",
            seed=302,
            region="JP",
            currency="JPY",
            date_style="iso",
            number_style="us",
            currency_display="symbol_prefix",
            currency_note=True,
            tax_label="Consumption tax",
            tax_rate=Decimal("0.10"),
            labels={"invoice_number": "Document no."},
        ),
        # Australia-style: A$, DD/MM/YYYY, hourly services, no tax, no subtotal
        # line, no bill-to block (optional fields missing).
        DocConfig(
            doc_id="sample-modern-03",
            layout="modern",
            seed=303,
            region="UK",
            currency="AUD",
            date_style="eu_slash",
            number_style="us",
            currency_display="symbol_prefix",
            currency_note=False,
            services=True,
            tax_rate=None,
            show_subtotal=False,
            has_bill_to=False,
        ),
    ],
}
