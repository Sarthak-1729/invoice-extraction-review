"""Extract one PDF and print raw values, normalized values and flags as JSON.

Run from backend/ with the venv active:
    python -m app.extract ../eval/datasets/dev/pdf/dev-01.pdf --provider gemini

Settings (API key, model, pacing) come from the environment or .env.
Test-set PDFs are refused unless --allow-test-set is given (Phase 7 only).
Exit codes: 0 extracted, 1 extraction failed, 2 rejected (PDF or test-set guard).
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import Settings
from app.llm import LLMError, get_provider
from app.pdf_text import PdfRejected, sha256_bytes
from app.pipeline import run_pipeline
from app.testset_guard import TestSetGuardError, guard_test_set


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.extract", description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--provider", choices=["fake", "gemini"], help="override LLM_PROVIDER")
    parser.add_argument(
        "--allow-test-set", action="store_true", help="only for the Phase 7 evaluation"
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # amounts like 1.234,50 € on Windows

    def fail(code: str, message: str, status: int) -> int:
        print(json.dumps({"error": {"code": code, "message": message}}, indent=2))
        return status

    if not args.pdf.is_file():
        return fail("FILE_NOT_FOUND", f"{args.pdf} does not exist.", 2)
    try:
        guard_test_set(args.pdf, args.allow_test_set)
    except TestSetGuardError as error:
        return fail("TEST_SET_GUARD", str(error), 2)

    overrides = {"llm_provider": args.provider} if args.provider else {}
    settings = Settings(**overrides)
    try:
        provider = get_provider(settings)
        result = run_pipeline(args.pdf, provider, settings)
    except PdfRejected as error:
        return fail(error.code, error.message, 2)
    except LLMError as error:
        return fail(error.code, error.message, 1)

    output = {
        "file": args.pdf.name,
        "sha256": sha256_bytes(args.pdf.read_bytes()),
        **result.to_dict(),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
