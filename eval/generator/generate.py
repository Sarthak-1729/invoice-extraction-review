"""Generate synthetic invoices: ground truth JSON first, then the PDF rendered from it.

Usage (from the repo root, backend venv active):
    python -m eval.generator.generate samples --layout classic_us
    python -m eval.generator.generate split test
"""

import argparse
import hashlib
import json
from pathlib import Path

from eval.generator.layouts import LAYOUTS
from eval.generator.samples import SAMPLES
from eval.generator.spec import DocConfig, build_spec
from eval.generator.splits import SPLITS
from eval.generator.truth import truth_dict, write_truth
from eval.generator.verify import check_text_layer, pdf_text

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS = REPO_ROOT / "eval" / "datasets"
MANIFEST = "MANIFEST.sha256"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(split_dir: Path) -> str:
    """Write ``sha256sum``-format lines for every PDF and truth file, sorted by path.

    Returns the split hash: the SHA-256 of the manifest file itself, so it
    changes if any file is added, removed, renamed or edited.
    """
    files = sorted(
        path.relative_to(split_dir).as_posix()
        for path in split_dir.rglob("*")
        if path.is_file() and path.name != MANIFEST
    )
    lines = [f"{sha256_file(split_dir / name)}  {name}\n" for name in files]
    manifest = split_dir / MANIFEST
    manifest.write_text("".join(lines), encoding="utf-8", newline="\n")
    return sha256_file(manifest)


def generate_split(split: str, out_root: Path) -> None:
    split_dir = out_root / split
    if split_dir.exists():
        raise SystemExit(f"{split_dir} already exists; refusing to overwrite a dataset.")
    for config in SPLITS[split]:
        info = render_document(
            config,
            split_dir / "pdf" / f"{config.doc_id}.pdf",
            split_dir / "truth" / f"{config.doc_id}.json",
        )
        print(json.dumps(info))
    print(f"{split} split hash (sha256 of {MANIFEST}): {write_manifest(split_dir)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    samples = commands.add_parser("samples", help="render review samples for one layout")
    samples.add_argument("--layout", choices=sorted(SAMPLES), required=True)
    samples.add_argument("--out", type=Path, default=REPO_ROOT / "eval" / "samples")
    split = commands.add_parser("split", help="render a dev or test dataset and its manifest")
    split.add_argument("split", choices=sorted(SPLITS))
    split.add_argument("--out", type=Path, default=DATASETS)
    args = parser.parse_args()

    if args.command == "samples":
        generate_samples(args.layout, args.out)
    elif args.command == "split":
        generate_split(args.split, args.out)


if __name__ == "__main__":
    main()
