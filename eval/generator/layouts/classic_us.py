"""Classic US layout: vendor header left, INVOICE title and meta right,
Bill To block, bordered line-item table with shaded header, totals block."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, Table, TableStyle

from eval.generator.layouts.common import (
    INK,
    MUTED,
    RULE,
    document,
    labels,
    lines_para,
    para,
    style,
)
from eval.generator.spec import InvoiceSpec

DEFAULT_LABELS = {
    "title": "INVOICE",
    "invoice_number": "Invoice #",
    "invoice_date": "Invoice Date",
    "due_date": "Due Date",
    "bill_to": "Bill To",
    "description": "Description",
    "quantity": "Qty",
    "unit_price": "Unit Price",
    "amount": "Amount",
    "subtotal": "Subtotal",
    "total": "Total",
}

WIDTH = LETTER[0] - 36 * mm - 12  # page minus margins minus the frame's 6pt padding per side


def render(spec: InvoiceSpec, path: Path) -> None:
    label = labels(DEFAULT_LABELS, spec)
    small = style("small", 8.5, textColor=MUTED)
    body = style("body", 9.5)
    right = style("right", 9.5, alignment=TA_RIGHT)
    story = []

    # Header: vendor block | title + meta
    vendor = [
        para(spec.vendor_name, style("vendor", 15, bold=True)),
        lines_para([*spec.vendor_address, spec.vendor_phone, spec.vendor_email], small),
    ]
    meta_rows = [
        [label["invoice_number"], spec.invoice_number],
        [label["invoice_date"], spec.day(spec.invoice_date)],
    ]
    if spec.due_date:
        meta_rows.append([label["due_date"], spec.day(spec.due_date)])
    meta = Table(meta_rows, colWidths=[30 * mm, 38 * mm], hAlign="RIGHT")
    meta.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5),
                ("FONT", (1, 0), (1, -1), "Helvetica", 9.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    title = para(label["title"], style("title", 24, bold=True, alignment=TA_RIGHT))
    header = Table(
        [[vendor, [title, Spacer(1, 4 * mm), meta]]], colWidths=[WIDTH * 0.55, WIDTH * 0.45]
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 8 * mm)]

    if spec.bill_to_name:
        story += [
            para(label["bill_to"].upper(), style("bill_label", 8.5, bold=True, textColor=MUTED)),
            para(spec.bill_to_name, style("bill_name", 10.5, bold=True)),
            lines_para(spec.bill_to_address, body),
            Spacer(1, 7 * mm),
        ]

    # Line items
    rows = [[label["description"], label["quantity"], label["unit_price"], label["amount"]]]
    rows += [
        [line.description, spec.quantity(line.quantity), spec.unit_price(line.unit_price),
         spec.money(line.amount)]
        for line in spec.lines
    ]  # fmt: skip
    table = Table(
        rows, colWidths=[WIDTH * 0.52, WIDTH * 0.1, WIDTH * 0.18, WIDTH * 0.2], repeatRows=1
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story += [table, Spacer(1, 4 * mm)]

    # Totals
    total_rows = []
    if spec.subtotal is not None:
        total_rows.append([label["subtotal"], spec.money(spec.subtotal)])
    if spec.tax is not None:
        total_rows.append([spec.tax_heading(), spec.money(spec.tax)])
    total_rows.append([label["total"], spec.money(spec.total)])
    totals = Table(total_rows, colWidths=[45 * mm, 35 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, INK),
                ("TOPPADDING", (0, -1), (-1, -1), 5),
            ]
        )
    )
    story += [totals, Spacer(1, 10 * mm)]

    # Footer: terms, currency note, notes
    footer = [f"Payment terms: {spec.payment_terms}"]
    if spec.currency_note():
        footer.append(spec.currency_note())
    story.append(lines_para(footer, body))
    for note in spec.notes:
        story += [Spacer(1, 3 * mm), para(note, small)]
    story += [Spacer(1, 6 * mm), para("Thank you for your business!", right)]

    document(spec, path, LETTER, 18 * mm).build(story)
