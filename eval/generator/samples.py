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
}
