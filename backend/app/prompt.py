"""Versioned extraction prompt.

The rules live only in ``system.txt``. The user message carries the PDF text
inside <document_text> tags, labeled as untrusted. Any tag-like text in the
document that could open or close that block is escaped, so the document
cannot end the data block early and pose as instructions.

Every prompt change gets a new version directory and an entry in
docs/PROMPT_LOG.md. ``PROMPT_HASH`` covers the system prompt, the user
template and the response schema, and is recorded with every result.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

PROMPT_VERSION = "extraction_v1"
PROMPTS_DIR = Path(__file__).parent / "prompts"
PLACEHOLDER = "{document_text}"

# "<document_text", "</document_text", "< / DOCUMENT_TEXT", ... in any case.
_TAG = re.compile(r"<(\s*/?\s*document_text)", re.IGNORECASE)


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    user_template: str
    schema: dict[str, Any]
    sha256: str

    def user_message(self, document_text: str) -> str:
        return self.user_template.replace(PLACEHOLDER, escape_document_text(document_text))


def escape_document_text(text: str) -> str:
    return _TAG.sub(r"&lt;\1", text)


def _read(version: str, name: str) -> str:
    # Read bytes and decode, so the hash is the same on every OS.
    return (PROMPTS_DIR / version / name).read_bytes().decode("utf-8")


@cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    system, user, schema = (_read(version, n) for n in ("system.txt", "user.txt", "schema.json"))
    if user.count(PLACEHOLDER) != 1:
        raise ValueError(f"{version}/user.txt must contain {PLACEHOLDER} exactly once")
    digest = hashlib.sha256()
    for part in (system, user, schema):
        digest.update(part.encode("utf-8") + b"\0")
    return Prompt(
        version=version,
        system=system.strip(),
        user_template=user.strip(),
        schema=json.loads(schema),
        sha256=digest.hexdigest(),
    )
