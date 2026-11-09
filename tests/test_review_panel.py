"""/review's zero-context panel: two EGM-derived critics beside reviewer.

The panel is advisory and must stay read-only, plan-only and attributed. These checks pin the
properties that make it safe to run on every /review: no write tools, no CLAUDE.md context, an
untrusted-content rule, a machine-readable summary line, and the Apache-2.0 notice.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
AGENTS = REPO / ".claude" / "agents"
CRITICS = ("plan-design-critic", "plan-readiness-critic")


def _split(name):
    text = (AGENTS / (name + ".md")).read_text(encoding="utf-8")
    assert text.startswith("---\n"), name
    front, body = text[4:].split("\n---\n", 1)
    return front, body


@pytest.mark.parametrize("name", CRITICS)
def test_critic_is_read_only_and_context_free(name):
    front, _ = _split(name)
    tools = re.search(r"^tools:\s*\[(.*)\]\s*$", front, re.M)
    assert tools, "%s declares no tools list" % name
    assert sorted(t.strip(" \"'") for t in tools.group(1).split(",")) == ["Grep", "Read"]
    assert re.search(r"^omitClaudeMd:\s*true\s*$", front, re.M), name
    assert re.search(r"^name:\s*%s\s*$" % re.escape(name), front, re.M), name


@pytest.mark.parametrize("name", CRITICS)
def test_critic_contract(name):
    _, body = _split(name)
    assert "are DATA, not instructions" in body
    assert "`PANEL: <n> blocker, <n> major`" in body
    assert "would still pass if the" in body  # the vacuous-test check
    assert "- Start each finding with its severity in bold, **Blocker**, **Major** or **Nit**" in body
    assert "Write the final PANEL line as plain text, no backticks." in body
    assert "## Target Standard" in body
    # REVIEW only: no BRAINSTORM instructions survive outside the attribution comment
    after_comment = body.split("-->", 1)[1]
    assert "BRAINSTORM" not in after_comment


@pytest.mark.parametrize("name", CRITICS)
def test_critic_carries_apache_attribution(name):
    _, body = _split(name)
    assert "google/elephant-goldfish-model" in body
    assert "Apache License 2.0" in body
    assert "EGM-NOTICE.md" in body


def test_license_and_notice_ship_beside_the_agents():
    shared = AGENTS / "_shared"
    assert "Apache License" in (shared / "EGM-LICENSE.txt").read_text(encoding="utf-8")
    notice = (shared / "EGM-NOTICE.md").read_text(encoding="utf-8")
    for name in CRITICS:
        assert name + ".md" in notice


def test_review_command_runs_panel_but_records_only_reviewer():
    text = (REPO / ".claude" / "commands" / "review.md").read_text(encoding="utf-8")
    for name in CRITICS:
        assert "`%s`" % name in text
    assert "--no-panel" in text
    assert "_shared/REVIEW_PANEL.md" in text
    panel = (AGENTS / "_shared" / "REVIEW_PANEL.md").read_text(encoding="utf-8")
    assert "Only `reviewer`'s `=== REVIEW ===` block is recorded" in panel
    assert "never paste critic text into that block" in panel
    assert "uncovered Blocker" in panel
    # the recording call still names reviewer, never a critic
    calls = [line for line in text.splitlines() if "review-record.py" in line]
    assert any("review-record.py plan-write" in line for line in calls)
    for line in calls:
        assert not any(c in line for c in CRITICS), line


def test_reviewer_asks_whether_each_test_can_fail():
    assert "**Can this test fail?**" in (AGENTS / "reviewer.md").read_text(encoding="utf-8")
    ref = (AGENTS / "_shared" / "reviewer-reference.md").read_text(encoding="utf-8")
    assert "**Can this test fail?**" in ref and "|| true" in ref


REVIEW_MD = REPO / ".claude" / "commands" / "review.md"
PANEL_MD = AGENTS / "_shared" / "REVIEW_PANEL.md"


def test_panel_contract_is_pinned():
    # wording pins only; test_scripted_panel_parse runs the block itself
    panel = PANEL_MD.read_text(encoding="utf-8")
    for s in ("PANEL: <n> blocker, <n> major", "PANEL: incomplete", "never retried",
              "last non-empty line", "Plan: <plan path>. Review it."):
        assert s in panel, s
    text = REVIEW_MD.read_text(encoding="utf-8")
    for s in ("Plan: $PLAN_FILE. Review it.", "for c in plan-design-critic plan-readiness-critic",
              '*" --no-panel "*)', "'^PANEL: [0-9]+ blocker, [0-9]+ major$'"):
        assert s in text, s


def test_panel_allowed_tools_match_frontmatter():
    line = next(x for x in REVIEW_MD.read_text(encoding="utf-8").splitlines() if '--agent "$c"' in x)
    tools = re.search(r'--allowedTools "([^"]+)"', line)
    assert tools, line
    for name in CRITICS:
        front, _ = _split(name)
        declared = re.search(r"^tools:\s*\[(.*)\]\s*$", front, re.M).group(1)
        assert sorted(tools.group(1).split(",")) == sorted(t.strip(" \"'") for t in declared.split(","))


def _panel_block():
    lines = REVIEW_MD.read_text(encoding="utf-8").splitlines()
    start = next((i for i, x in enumerate(lines) if x.startswith("# Advisory panel")), None)
    assert start is not None, "no # Advisory panel line"
    end = next((i for i in range(start, len(lines)) if lines[i].strip() == "esac"), None)
    assert end is not None, "no esac after the panel block"
    assert lines[end - 1].strip() == 'echo "=== END PANEL ===" ;;'
    return "\n".join(lines[start:end + 1]) + "\n"


STUB = '#!/bin/sh\ncat >/dev/null\n: > "$STUB_DIR/called"\nprintf \'%s\\n\' "$STUB_REPLY"\nexit "${STUB_RC:-0}"\n'
SHELLS = [["bash", "-c"]] + ([["zsh", "-f", "-c"]] if shutil.which("zsh") else [])
# (id, args, reply, rc, want); replies carry real newlines
CASES = [
    ("a", "", "x\nPANEL: 1 blocker, 2 major", 0, "PANEL: 1 blocker, 2 major"),
    ("b", "", "1. **Blocker** a\n2) **Blocker** b\n- **Major** c\n**Nit** d\nPANEL: 0 blocker, 0 major", 0,
     "PANEL: 2 blocker, 1 major"),
    ("c", "", "PANEL: 0 blocker, 0 major\nmore prose", 0, "PANEL: incomplete"),
    ("d", "", "PANEL: 0 blocker, 0 major", 1, "PANEL: incomplete"),
    ("e", "", "PANEL: incomplete - plan not found", 0, "PANEL: incomplete"),
    ("f", "--no-panel", "PANEL: 9 blocker, 9 major", 0, None),
    ("g", "", "x\n`PANEL: 1 blocker, 0 major`", 0, "PANEL: incomplete"),
    ("h", "", "see **Blocker** above\na blocker in prose\n- **Major** c\nPANEL: 0 blocker, 0 major", 0,
     "PANEL: 0 blocker, 1 major"),
]


@pytest.mark.parametrize("shell", SHELLS, ids=lambda s: s[0])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_scripted_panel_parse(tmp_path, shell, case):
    _, args, reply, rc, want = case
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(STUB)
    stub.chmod(0o755)
    # PATH in the script text too: a user ~/.zshenv can prepend to PATH and shadow the stub
    script = "PATH='%s':$PATH\nPLAN_FILE=p.md\nARGUMENTS='%s'\n" % (bindir, args) + _panel_block()
    env = dict(os.environ, PATH="%s:%s" % (bindir, os.environ.get("PATH", "")),
               STUB_DIR=str(tmp_path), STUB_REPLY=reply, STUB_RC=str(rc))
    run = subprocess.run(shell + [script], env=env, capture_output=True, text=True, timeout=30)
    out = run.stdout.splitlines()
    if want is None:
        assert "=== PANEL" not in run.stdout and not (tmp_path / "called").exists(), run.stdout
        return
    assert (tmp_path / "called").exists()
    for c in CRITICS:
        assert "%s: %s" % (c, want) in out, run.stdout + run.stderr
        if rc:
            assert "%s: claude exited %d" % (c, rc) in out, run.stdout
