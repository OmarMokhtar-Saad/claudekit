"""Structure test: reviewer.md must require the verdict block INSIDE the saved report.

Three sessions (2026-09-11, 2026-09-16, 2026-09-17) hand-pasted the block from the reviewer's
reply into the report because review-record.py --from-review reads a FILE and the reply is
never saved. This pins the instruction text; it cannot prove the agent obeys it.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_reviewer_prompt_requires_block_in_written_report():
    text = (REPO / ".claude/agents/reviewer.md").read_text(encoding="utf-8")
    assert "A written report ENDS with the same `=== REVIEW ===`" in text
    assert "the record binder reads the file, not your reply" in text
