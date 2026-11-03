"""European layout (A4): small sender line above the recipient address
(window-envelope style), vendor block on the right, a horizontal meta row with
a customer number as a distractor, Pos./Unit columns, net/VAT/gross totals,
and a three-column company footer on every page."""

import random
from pathlib import Path

from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
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
    "title": "Invoice",
    "invoice_number": "Invoice no.",
    "invoice_date": "Invoice date",
    "customer_number": "Customer no.",
    "due_date": "Due date",
    "position": "Pos.",
    "description": "Description",
    "quantity": "Qty",
    "unit": "Unit",
    "unit_price": "Unit price",
    "amount": "Amount",
    "subtotal": "Net amount",
    "total": "Total amount",
}

MARGIN = 20 * mm
WIDTH = A4[0] - 2 * MARGIN - 12  # minus the frame's 6pt padding per side


def _payment_text(spec: InvoiceSpec) -> str:
    if spec.due_date is None:
        return "Payable immediately without deduction."
    days = (spec.due_date - spec.invoice_date).days
    return (
        f"Payable within {days} days without deduction. "
        "Please quote the invoice number with your payment."
    )


def render(spec: InvoiceSpec, path: Path) -> None:
    label = labels(DEFAULT_LABELS, spec)
    # Layout-only details (not labeled fields) use their own RNG so the shared
    # spec sequence stays unchanged.
    aux = random.Random(spec.config.seed * 7919 + 1)
    customer_number = f"K-{aux.randint(10000, 99999)}"
    vat_id = f"VAT ID XX{aux.randint(100000000, 999999999)}"
    unit = "h" if spec.config.services else "pcs"

    tiny = style("tiny", 7, textColor=MUTED)
    small = style("small", 8.5, textColor=MUTED)
    body = style("body", 9.5)
    story = []

    sender = " · ".join([spec.vendor_name, *spec.vendor_address])
    recipient = (
        [para(spec.bill_to_name, style("recipient", 10.5, bold=True)),
         lines_para(spec.bill_to_address, style("recipient_address", 10.5))]
        if spec.bill_to_name
        else []
    )  # fmt: skip
    vendor = [
        para(spec.vendor_name, style("vendor", 14, bold=True, alignment=TA_RIGHT)),
        lines_para(
            [*spec.vendor_address, spec.vendor_phone, spec.vendor_email, vat_id],
            style("vendor_lines", 8.5, textColor=MUTED, alignment=TA_RIGHT),
        ),
    ]
    header = Table(
        [[[para(sender, tiny), Spacer(1, 2 * mm), *recipient], vendor]],
        colWidths=[WIDTH * 0.55, WIDTH * 0.45],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 14 * mm), para(label["title"], style("title", 18, bold=True))]
    story.append(Spacer(1, 4 * mm))

    meta_labels = [label["invoice_number"], label["invoice_date"], label["customer_number"]]
    meta_values = [spec.invoice_number, spec.day(spec.invoice_date), customer_number]
    if spec.due_date:
        meta_labels.append(label["due_date"])
        meta_values.append(spec.day(spec.due_date))
    meta = Table([meta_labels, meta_values], hAlign="LEFT", colWidths=[36 * mm] * len(meta_labels))
    meta.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica", 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story += [meta, Spacer(1, 6 * mm)]
    story += [
        para("Dear Sir or Madam,", body),
        para("we hereby invoice the following goods and services:", body),
        Spacer(1, 4 * mm),
    ]

    rows = [[label["position"], label["description"], label["quantity"], label["unit"],
             label["unit_price"], label["amount"]]]  # fmt: skip
    rows += [
        [str(i), line.description, spec.quantity(line.quantity), unit,
         spec.unit_price(line.unit_price), spec.money(line.amount)]
        for i, line in enumerate(spec.lines, 1)
    ]  # fmt: skip
    widths = [0.07, 0.43, 0.08, 0.07, 0.16, 0.19]
    table = Table(rows, colWidths=[WIDTH * w for w in widths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, RULE),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [table, Spacer(1, 3 * mm)]

    total_rows = []
    if spec.subtotal is not None:
        total_rows.append([label["subtotal"], spec.money(spec.subtotal)])
    if spec.tax is not None:
        total_rows.append([spec.tax_heading(), spec.money(spec.tax)])
    total_rows.append([label["total"], spec.money(spec.total)])
    totals = Table(total_rows, colWidths=[45 * mm, 38 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.75, INK),
                ("LINEBELOW", (0, -1), (-1, -1), 0.75, INK),
            ]
        )
    )
    story += [totals, Spacer(1, 8 * mm), para(_payment_text(spec), body)]
    if spec.currency_note():
        story.append(para(spec.currency_note(), body))
    for note in spec.notes:
        story += [Spacer(1, 3 * mm), para(note, small)]
    story += [Spacer(1, 6 * mm), para("Kind regards", body), para(spec.vendor_name, body)]

    footer_columns = [
        [spec.vendor_name, *spec.vendor_address],
        [f"Phone {spec.vendor_phone}", spec.vendor_email],
        [vat_id, "Registered office: " + spec.vendor_address[-1]],
    ]

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN, 22 * mm, A4[0] - MARGIN, 22 * mm)
        column_width = (A4[0] - 2 * MARGIN) / 3
        for c, column in enumerate(footer_columns):
            for r, text in enumerate(column):
                canvas.drawString(MARGIN + c * column_width, 18 * mm - r * 3.2 * mm, text)
        canvas.drawRightString(A4[0] - MARGIN, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = document(spec, path, A4, MARGIN)
    doc.bottomMargin = 30 * mm  # room for the footer
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
