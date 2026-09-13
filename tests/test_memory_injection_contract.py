"""The agent-memory INJECTION CONTRACT.

NOT proof that an agent reads its memory and behaves differently -- that needs a
live model call, which is neither deterministic nor available in CI. This pins the
structural contract Claude Code's loader depends on, so a drift that would silently
stop injection fails here instead of going unnoticed. Named for what it is.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLAUDE = REPO / ".claude"
MEM = CLAUDE / "agent-memory"
LINE_CAP = 200
BYTE_CAP = 25 * 1024


def declaring_agents():
    out = []
    for f in sorted((CLAUDE / "agents").glob("*.md")):
        head = f.read_text(encoding="utf-8").splitlines()[:40]
        if any(line.strip() == "memory: project" for line in head):
            out.append(f.stem)
    return out


def test_every_declaring_agent_has_the_directory_injection_reads():
    """Claude Code loads .claude/agent-memory/<agent>/MEMORY.md. A renamed agent
    whose directory was not renamed with it injects nothing, silently."""
    missing = [a for a in declaring_agents() if not (MEM / a).is_dir()]
    assert not missing, f"no agent-memory directory for: {missing}"


def test_the_declaring_set_is_not_empty():
    assert declaring_agents(), "fixture invalid: no agent declares memory: project"


def test_no_memory_file_exceeds_the_truncation_limits():
    """Past 200 lines / 25 KB Claude Code loads the first part and drops the rest
    with no error, so the agent reads half a memory it believes is whole."""
    for mf in sorted(MEM.glob("*/MEMORY.md")):
        text = mf.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= LINE_CAP, f"{mf} is {len(text.splitlines())} lines"
        assert len(text.encode("utf-8")) <= BYTE_CAP, f"{mf} is {len(text.encode())} bytes"


def test_a_memory_index_carries_no_frontmatter():
    """MEMORY.md is injected verbatim; a --- block would arrive as literal text."""
    for mf in sorted(MEM.glob("*/MEMORY.md")):
        first = mf.read_text(encoding="utf-8").lstrip().splitlines()[:1]
        assert first != ["---"], f"{mf} starts with a frontmatter fence"


def test_every_link_in_an_index_resolves():
    """A dangling pointer is a memory the agent is told about and cannot follow."""
    dangling = []
    for mf in sorted(MEM.glob("*/MEMORY.md")):
        text = mf.read_text(encoding="utf-8")
        targets = re.findall(r"\]\(([^)]+\.md)\)", text)
        targets += [f"{n}.md" for n in re.findall(r"\[\[([^\]]+)\]\]", text)]
        for t in targets:
            if t.startswith(("http://", "https://", "/")):
                continue
            if not (mf.parent / t).is_file():
                dangling.append(f"{mf.parent.name}/{t}")
    assert not dangling, f"dangling memory links: {dangling}"


def test_the_readme_is_present_and_is_not_an_agent_directory():
    assert (MEM / "README.md").is_file()
    assert not (MEM / "README.md").is_dir()
