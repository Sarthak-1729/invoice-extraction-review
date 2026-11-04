"""Print the feature mix of each split as Markdown tables (no files are written)."""

from collections import Counter

from eval.generator.spec import DocConfig, InvoiceSpec, build_spec
from eval.generator.splits import SPLITS

MISSING = ("no_due_date", "no_bill_to", "no_tax", "no_subtotal")
COLUMN_FEATURES = ("sku_column", "amount_before_qty", "qty_first")


def _row(config: DocConfig, spec: InvoiceSpec) -> dict[str, str]:
    features = spec.features
    total = spec.money(spec.total)
    return {
        "doc": config.doc_id,
        "layout": config.layout,
        "currency": f"{config.currency} ({spec.currency_printed()})",
        "date": f"{config.date_style} `{spec.day(spec.invoice_date)}`",
        "number": f"{config.number_style} `{total}`",
        "lines": str(len(spec.lines)),
        "missing": ", ".join(f.removeprefix("no_") for f in features if f in MISSING) or "-",
        "error": next((f.split(":")[1] for f in features if f.startswith("arith_error")), "-"),
        "injection": "yes" if "injection" in features else "-",
        "columns": ", ".join(f for f in features if f in COLUMN_FEATURES) or "-",
        "wrapped": "yes" if "wrapped_descriptions" in features else "-",
        "labels": "yes" if "odd_labels" in features else "-",
    }


def _table(rows: list[dict[str, str]]) -> str:
    header = list(rows[0])
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row[h] for h in header) + " |" for row in rows]
    return "\n".join(lines)


def _tags(config: DocConfig, spec: InvoiceSpec) -> set[str]:
    """Comparable feature tags for the dev/test overlap check."""
    tags = {f"currency:{config.currency}", f"date:{config.date_style}",
            f"numbers:{config.number_style}", f"layout:{config.layout}",
            f"currency_display:{config.currency_display}"}  # fmt: skip
    tags |= {f for f in spec.features if ":" not in f or f.startswith("arith_error")}
    return tags


def main() -> None:
    tags: dict[str, Counter] = {}
    for split, configs in SPLITS.items():
        specs = [(c, build_spec(c)) for c in configs]
        print(f"\n## {split} ({len(configs)} documents)\n")
        print(_table([_row(c, s) for c, s in specs]))
        tags[split] = Counter(t for c, s in specs for t in _tags(c, s))

    print("\n## Documents per feature\n")
    all_tags = sorted(set(tags["dev"]) | set(tags["test"]))
    print("| feature | dev | test |\n|---|---|---|")
    for tag in all_tags:
        print(f"| {tag} | {tags['dev'][tag]} | {tags['test'][tag]} |")

    print("\n## Only in one split\n")
    for tag in all_tags:
        if not tags["dev"][tag] or not tags["test"][tag]:
            where = "test only" if not tags["dev"][tag] else "dev only"
            print(f"- {tag}: {where}")


if __name__ == "__main__":
    main()
