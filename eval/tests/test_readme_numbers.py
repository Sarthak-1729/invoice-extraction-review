"""The README's Results and Limitations numbers come only from the committed
baseline results.json, never typed by hand.

If this fails after a deliberate change, regenerate the blocks with
python -m eval.report <run folder> --readme (do not edit numbers by hand).
"""

import json
import re

from eval.report import README, readme_blocks, replace_block
from eval.sets import REPO_ROOT

RUN = "eval/results/test/gemini-3.5-flash-lite__extraction_v4__852b70c465cb"
# Numbers allowed outside the generated blocks, none of them a result:
ALLOWED = {
    "09",  # the document id dev-09
    "1234",  # the prompt's example reference "#1234"
    "7.98",  # an example generated price (CAD 7.98), not a measured number
}


def _sections(text: str) -> str:
    return text[text.index("## Results") : text.index("## Future work")]


def test_generated_blocks_match_the_committed_results():
    results = json.loads((REPO_ROOT / RUN / "results.json").read_text(encoding="utf-8"))
    text = README.read_text(encoding="utf-8")
    expected = text
    for name, body in readme_blocks(results, RUN).items():
        expected = replace_block(expected, name, body)
    assert text == expected, "README numbers drifted from results.json; regenerate with --readme"


def test_no_hand_typed_numbers_outside_the_generated_blocks():
    text = _sections(README.read_text(encoding="utf-8"))
    outside = re.sub(r"<!-- generated:(\S+) -->.*?<!-- /generated:\1 -->", "", text, flags=re.S)
    numbers = set(re.findall(r"\d+(?:[.,]\d+)*", outside))
    assert numbers <= ALLOWED, numbers - ALLOWED


def test_results_block_states_the_baseline_and_its_counts():
    text = README.read_text(encoding="utf-8")
    block = text.split("<!-- generated:results -->")[1].split("<!-- /generated:results -->")[0]
    assert "recorded before any fix and is the headline result" in block
    for match in re.finditer(r"\d+\.\d%", block):
        assert block[match.end() : match.end() + 2] == " (", "percentage without counts"
