"""Every `.claude/agents/*.md` frontmatter line must be a `key: value` line.

Regression guard: an ops.json `add_after` without a leading newline once produced
`color: orangememory: project` in seven agents. Every generator gate and 180 tests stayed
green while the headline feature was inert, because nothing parsed the block as a whole.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
AGENTS = sorted(p for p in (REPO / ".claude" / "agents").glob("*.md")
                if p.read_text(encoding="utf-8").startswith("---\n"))  # skips QUICK_START/HANDOFF_PROTOCOL
MEMORY_AGENTS = {"code-reviewer", "debugger", "explore", "planner", "reviewer",
                 "security-scanner", "verifier"}
KEY_LINE = re.compile(r"^[a-z][a-z0-9_-]*:(\s|$)")


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "%s: no frontmatter" % path.name
    body = text[4:].split("\n---", 1)[0]
    fields = {}
    for line in body.splitlines():
        if not line.strip() or line.startswith((" ", "\t", "-")):
            continue  # continuation / list item under a key
        assert KEY_LINE.match(line), "%s: not a key line: %r" % (path.name, line)
        key, _, value = line.partition(":")
        fields[key] = value.strip()
    return fields


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_every_frontmatter_line_is_a_key_line(path):
    fields = _frontmatter(path)
    assert "name" in fields, path.name
    for key, value in fields.items():
        assert not re.search(r"[a-z]memory:", key + ":" + value), \
            "%s: glued key in %s: %r" % (path.name, key, value)


def test_documented_memory_agents_declare_memory_project():
    readme = (REPO / ".claude" / "agent-memory" / "README.md").read_text(encoding="utf-8")
    for stem in sorted(MEMORY_AGENTS):
        fields = _frontmatter(REPO / ".claude" / "agents" / (stem + ".md"))
        assert fields.get("memory") == "project", "%s: memory=%r" % (stem, fields.get("memory"))
        assert stem in readme, "%s not listed in agent-memory/README.md" % stem


def test_agents_outside_the_set_do_not_silently_gain_memory():
    extra = {p.stem for p in AGENTS if _frontmatter(p).get("memory")} - MEMORY_AGENTS
    assert not extra, "undocumented memory agents: %s" % sorted(extra)
