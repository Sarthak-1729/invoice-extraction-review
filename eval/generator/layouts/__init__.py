"""Layout registry: each layout renders an InvoiceSpec to a PDF file."""

from collections.abc import Callable
from pathlib import Path

from eval.generator.layouts import classic_us
from eval.generator.spec import InvoiceSpec

Renderer = Callable[[InvoiceSpec, Path], None]

LAYOUTS: dict[str, Renderer] = {
    "classic_us": classic_us.render,
}
