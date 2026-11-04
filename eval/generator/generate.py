"""Generate synthetic invoices: ground truth JSON first, then the PDF rendered from it.

Usage (from the repo root, backend venv active):
    python -m eval.generator.generate samples --layout classic_us
"""

import argparse
import json
from pathlib import Path

from eval.generator.layouts import LAYOUTS
from eval.generator.samples import SAMPLES
from eval.generator.spec import DocConfig, build_spec
from eval.generator.truth import truth_dict, write_truth
from eval.generator.verify import check_text_layer, pdf_text

REPO_ROOT = Path(__file__).resolve().parents[2]


def render_document(config: DocConfig, pdf_path: Path, truth_path: Path) -> dict:
    """Render one invoice and its truth file; fail if any printed value is not in the text."""
    spec = build_spec(config)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    LAYOUTS[config.layout](spec, pdf_path)

    check = check_text_layer(pdf_path, truth_dict(spec))
    if check.missing:
        raise SystemExit(
            f"{config.doc_id}: printed values missing from PDF text:\n  "
            + "\n  ".join(check.missing)
        )
    write_truth(truth_dict(spec, check.wrapped_line_items), truth_path)
    _, pages = pdf_text(pdf_path)
    return {
        "doc_id": config.doc_id,
        "pages": pages,
        "lines": len(spec.lines),
        "wrapped_line_items": check.wrapped_line_items,
        "features": spec.features,
    }


def generate_samples(layout: str, out_dir: Path) -> None:
    for config in SAMPLES[layout]:
        target = out_dir / layout
        info = render_document(
            config, target / f"{config.doc_id}.pdf", target / f"{config.doc_id}.json"
        )
        print(json.dumps(info))
        print(f"  -> {(target / f'{config.doc_id}.pdf').resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    samples = commands.add_parser("samples", help="render review samples for one layout")
    samples.add_argument("--layout", choices=sorted(SAMPLES), required=True)
    samples.add_argument("--out", type=Path, default=REPO_ROOT / "eval" / "samples")
    args = parser.parse_args()

    if args.command == "samples":
        generate_samples(args.layout, args.out)


if __name__ == "__main__":
    main()
