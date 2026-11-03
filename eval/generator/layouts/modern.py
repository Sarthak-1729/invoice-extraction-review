"""Modern minimal layout (A4): accent bar, large title with the invoice number,
three label/value blocks (From, Billed to, Details), a borderless table with
price BEFORE quantity and a "Line total" column, and a large "Total due"."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, Table, TableStyle

from eval.generator.layouts.common import (
    MUTED,
    document,
    labels,
    lines_para,
    para,
    style,
)
from eval.generator.spec import InvoiceSpec

ACCENT = colors.HexColor("#0f766e")
HAIRLINE = colors.HexColor("#d9e2ec")

DEFAULT_LABELS = {
    "title": "Invoice",
    "from": "From",
    "bill_to": "Billed to",
    "details": "Details",
    "invoice_number": "Number",
    "invoice_date": "Issued",
    "due_date": "Due",
    "description": "Item",
    "unit_price": "Price",
    "quantity": "Qty",
    "amount": "Line total",
    "subtotal": "Subtotal",
    "total": "Total due",
}
SERVICE_LABELS = {"unit_price": "Rate", "quantity": "Hours"}

MARGIN = 22 * mm
WIDTH = A4[0] - 2 * MARGIN - 12  # minus the frame's 6pt padding per side


def render(spec: InvoiceSpec, path: Path) -> None:
    defaults = {**DEFAULT_LABELS, **(SERVICE_LABELS if spec.config.services else {})}
    label = labels(defaults, spec)
    caption = style("caption", 7.5, bold=True, textColor=MUTED)
    body = style("body", 9.5)
    small = style("small", 8.5, textColor=MUTED)
    story = []

    title = Table(
        [[para(label["title"], style("title", 26, bold=True, textColor=ACCENT)),
          para(f"# {spec.invoice_number}", style("number", 13, bold=True, alignment=TA_RIGHT))]],
        colWidths=[WIDTH * 0.5, WIDTH * 0.5],
    )  # fmt: skip
    title.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    story += [title, Spacer(1, 10 * mm)]

    def block(heading: str, lines: list[str], first_bold: bool = True):
        if not lines:
            return []
        content = [para(heading.upper(), caption), Spacer(1, 1.5 * mm)]
        if first_bold:
            content.append(para(lines[0], style("block_head", 10, bold=True)))
            lines = lines[1:]
        return [*content, lines_para(lines, body)] if lines else content

    details = [
        f"{label['invoice_number']}: {spec.invoice_number}",
        f"{label['invoice_date']}: {spec.day(spec.invoice_date)}",
    ]
    if spec.due_date:
        details.append(f"{label['due_date']}: {spec.day(spec.due_date)}")
    bill_to = [spec.bill_to_name, *spec.bill_to_address] if spec.bill_to_name else []
    blocks = Table(
        [[
            block(label["from"], [spec.vendor_name, *spec.vendor_address, spec.vendor_email]),
            block(label["bill_to"], bill_to),
            block(label["details"], details, first_bold=False),
        ]],
        colWidths=[WIDTH * 0.38, WIDTH * 0.32, WIDTH * 0.30],
    )  # fmt: skip
    blocks.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0)]))  # fmt: skip
    story += [blocks, Spacer(1, 12 * mm)]

    rows = [[label["description"].upper(), label["unit_price"].upper(),
             label["quantity"].upper(), label["amount"].upper()]]  # fmt: skip
    rows += [
        [line.description, spec.unit_price(line.unit_price), spec.quantity(line.quantity),
         spec.money(line.amount)]
        for line in spec.lines
    ]  # fmt: skip
    table = Table(rows, colWidths=[WIDTH * w for w in (0.46, 0.2, 0.12, 0.22)], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, HAIRLINE),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story += [table, Spacer(1, 6 * mm)]

    total_rows = []
    if spec.subtotal is not None:
        total_rows.append([label["subtotal"], spec.money(spec.subtotal)])
    if spec.tax is not None:
        total_rows.append([spec.tax_heading(), spec.money(spec.tax)])
    total_rows.append([label["total"], spec.money(spec.total)])
    totals = Table(total_rows, colWidths=[42 * mm, 42 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 14),
                ("TEXTCOLOR", (0, -1), (-1, -1), ACCENT),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, -1), (-1, -1), 8),
            ]
        )
    )
    story += [totals, Spacer(1, 12 * mm)]

    footer = [spec.payment_terms]
    if spec.currency_note():
        footer.append(spec.currency_note())
    footer.append(f"Questions? Contact {spec.vendor_email}")
    story.append(lines_para(footer, small))
    for note in spec.notes:
        story += [Spacer(1, 3 * mm), para(note, small)]

    def draw_accent(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(ACCENT)
        canvas.rect(0, A4[1] - 6 * mm, A4[0], 6 * mm, stroke=0, fill=1)
        canvas.restoreState()

    document(spec, path, A4, MARGIN).build(story, onFirstPage=draw_accent, onLaterPages=draw_accent)
