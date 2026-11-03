"""Shared reportlab helpers for all layouts."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate

from eval.generator.spec import InvoiceSpec

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#52606d")
RULE = colors.HexColor("#9aa5b1")


def style(name: str, size: float = 9, bold: bool = False, **kwargs) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=size * 1.3,
        textColor=kwargs.pop("textColor", INK),
        **kwargs,
    )


def para(text: str, paragraph_style: ParagraphStyle) -> Paragraph:
    """Paragraph with XML escaping (names may contain '&')."""
    return Paragraph(escape(text), paragraph_style)


def lines_para(lines: list[str], paragraph_style: ParagraphStyle) -> Paragraph:
    return Paragraph("<br/>".join(escape(line) for line in lines), paragraph_style)


def document(spec: InvoiceSpec, path: Path, pagesize, margin: float) -> SimpleDocTemplate:
    """A byte-reproducible document (invariant=1 fixes timestamps and IDs)."""
    return SimpleDocTemplate(
        str(path),
        pagesize=pagesize,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"Invoice {spec.invoice_number}",
        author="Synthetic invoice generator",
        invariant=1,
    )


def labels(defaults: dict[str, str], spec: InvoiceSpec) -> dict[str, str]:
    return {**defaults, **spec.config.labels}
