"""Multi-page ERP-printout layout (Letter): monospace line-item table with a
configurable column order (optional SKU column, amount before quantity),
header row repeated on every page, a slim running header on later pages,
"Page X of Y", "Continued on next page", and totals on the last page only."""

import random
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

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
    "invoice_number": "Invoice No:",
    "invoice_date": "Date:",
    "due_date": "Due Date:",
    "bill_to": "Sold To",
    "sku": "Item",
    "description": "Description",
    "quantity": "Qty",
    "unit_price": "Unit Price",
    "amount": "Amount",
    "subtotal": "Subtotal",
    "total": "Invoice Total",
}
DEFAULT_COLUMNS = ("sku", "description", "quantity", "unit_price", "amount")
# Relative widths and alignment per column.
COLUMN_LAYOUT = {
    "sku": (0.12, "LEFT"),
    "description": (0.42, "LEFT"),
    "quantity": (0.07, "RIGHT"),
    "unit_price": (0.17, "RIGHT"),
    "amount": (0.19, "RIGHT"),
}

MARGIN = 16 * mm
WIDTH = LETTER[0] - 2 * MARGIN - 12  # minus the frame's 6pt padding per side
STRIPE = colors.HexColor("#f0f4f8")


def _canvas_class(spec: InvoiceSpec, invoice_label: str):
    """Canvas that knows the page count, for "Page X of Y" and "Continued"."""
    running_header = f"{spec.vendor_name}  |  {invoice_label} {spec.invoice_number}"

    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._furniture(total)
                super().showPage()
            super().save()

        def _furniture(self, total):
            page = self._pageNumber
            self.saveState()
            self.setFont("Courier", 7.5)
            self.setFillColor(MUTED)
            if page > 1:
                self.drawString(MARGIN, LETTER[1] - 10 * mm, running_header)
            self.drawRightString(LETTER[0] - MARGIN, 9 * mm, f"Page {page} of {total}")
            if page < total:
                self.drawString(MARGIN, 9 * mm, "Continued on next page")
            self.restoreState()

    return NumberedCanvas


def render(spec: InvoiceSpec, path: Path) -> None:
    label = labels(DEFAULT_LABELS, spec)
    columns = spec.config.columns or DEFAULT_COLUMNS
    aux = random.Random(spec.config.seed * 7919 + 3)
    skus = [f"{aux.choice('ABCDEFHKMPRT')}{aux.randint(100, 999)}-{aux.randint(10, 99)}"
            for _ in spec.lines]  # fmt: skip

    cell = style("cell", 8.5)
    cell.fontName = "Courier"  # descriptions wrap, so they are Paragraphs in the table font
    small = style("small", 8.5, textColor=MUTED)
    body = style("body", 9.5)
    story = []

    vendor = [
        para(spec.vendor_name, style("vendor", 14, bold=True)),
        lines_para([*spec.vendor_address, spec.vendor_phone, spec.vendor_email], small),
    ]
    meta_rows = [
        [label["invoice_number"], spec.invoice_number],
        [label["invoice_date"], spec.day(spec.invoice_date)],
    ]
    if spec.due_date:
        meta_rows.append([label["due_date"], spec.day(spec.due_date)])
    meta = Table(meta_rows, colWidths=[28 * mm, 40 * mm], hAlign="RIGHT")
    meta.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("FONT", (1, 0), (1, -1), "Courier", 9.5),
                ("BOX", (0, 0), (-1, -1), 0.75, INK),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    title = para(label["title"], style("title", 20, bold=True, alignment=TA_RIGHT))
    header = Table(
        [[vendor, [title, Spacer(1, 3 * mm), meta]]], colWidths=[WIDTH * 0.55, WIDTH * 0.45]
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 6 * mm)]

    if spec.bill_to_name:
        story += [
            para(label["bill_to"] + ":", style("bill_label", 9, bold=True)),
            lines_para([spec.bill_to_name, *spec.bill_to_address], body),
            Spacer(1, 6 * mm),
        ]

    def value(column: str, i: int):
        line = spec.lines[i]
        return {
            "sku": skus[i],
            "description": para(line.description, cell),
            "quantity": spec.quantity(line.quantity),
            "unit_price": spec.unit_price(line.unit_price),
            "amount": spec.money(line.amount),
        }[column]

    rows = [[label[c] for c in columns]]
    rows += [[value(c, i) for c in columns] for i in range(len(spec.lines))]
    weights = [COLUMN_LAYOUT[c][0] for c in columns]
    widths = [WIDTH * w / sum(weights) for w in weights]
    commands = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Courier", 8.5),
        ("LINEABOVE", (0, 0), (-1, 0), 1, INK),
        ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    for c, column in enumerate(columns):
        commands.append(("ALIGN", (c, 0), (c, -1), COLUMN_LAYOUT[column][1]))
    for r in range(2, len(rows), 2):
        commands.append(("BACKGROUND", (0, r), (-1, r), STRIPE))
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(commands))
    story += [table, Spacer(1, 4 * mm)]

    total_rows = [["Number of items:", str(len(spec.lines))]]
    if spec.subtotal is not None:
        total_rows.append([label["subtotal"], spec.money(spec.subtotal)])
    if spec.tax is not None:
        total_rows.append([spec.tax_heading(), spec.money(spec.tax)])
    total_rows.append([label["total"], spec.money(spec.total)])
    totals = Table(total_rows, colWidths=[48 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (0, -1), "Helvetica", 9),
                ("FONT", (1, 0), (1, -1), "Courier", 9.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONT", (0, -1), (-1, -1), "Courier-Bold", 10.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOX", (0, -1), (-1, -1), 1, INK),
            ]
        )
    )
    closing = [totals, Spacer(1, 6 * mm), para(f"Terms: {spec.payment_terms}", body)]
    if spec.currency_note():
        closing.append(para(spec.currency_note(), body))
    for note in spec.notes:
        closing += [Spacer(1, 3 * mm), para(note, small)]
    story.append(KeepTogether(closing))

    doc = document(spec, path, LETTER, MARGIN)
    doc.build(story, canvasmaker=_canvas_class(spec, label["invoice_number"].rstrip(":")))
