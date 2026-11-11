"""review-panel.py: prompts (plan resolution, panel on/off, log row) and merge (validation,
dedup against the reviewer, round numbering and the EGM stop rule). Subprocess on a tmp repo.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "review-panel.py"
PROMPT_RE = re.compile(r"^Plan: (/.+\.md)\. Review it\.$")

REVIEWER = """=== REVIEW ===
SCORE: 80
ISSUES:
- src/cache.py: the eviction handler swallows exceptions silently without logging anything
=== END REVIEW ===
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    plans = tmp_path / ".claude" / "plans"
    plans.mkdir(parents=True)
    monkeypatch.delenv("CK_REVIEW_PANEL", raising=False)
    return tmp_path


def run(repo, *args, env=None):
    full = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    full.pop("CK_REVIEW_PANEL", None)
    full.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(repo), env=full,
                          capture_output=True, text=True, timeout=30)


def plan(repo, name="plan-a.md", body="# plan\n"):
    path = repo / ".claude" / "plans" / name
    path.write_text(body, encoding="utf-8")
    return path


def lines(out):
    return dict(ln.split(": ", 1) for ln in out.strip().splitlines())


def log_rows(repo):
    path = repo / ".claude" / "hooks" / ".state" / "review-panel.jsonl"
    return [json.loads(ln) for ln in path.read_text().splitlines()]


# ------------------------------------------------------------------ prompts

def test_prompts_panel_on_by_default_and_logs(repo):
    p = plan(repo)
    r = run(repo, "prompts", ".claude/plans/plan-a.md")
    assert r.returncode == 0, r.stderr
    got = lines(r.stdout)
    real = os.path.realpath(str(p))
    assert got["PLAN"] == real
    assert got["PANEL"] == "on (default)"
    m = PROMPT_RE.match(r.stdout.strip().splitlines()[-1].split(": ", 1)[1])
    assert m and m.group(1) == real
    row = log_rows(repo)[-1]
    assert row["plan"] == real and row["panel"] == "on" and len(row["plan_sha256"]) == 64


def test_prompts_off_by_flag(repo):
    plan(repo)
    r = run(repo, "prompts", "--no-panel", ".claude/plans/plan-a.md")
    assert r.returncode == 0
    assert lines(r.stdout)["PANEL"] == "off (--no-panel)"
    assert log_rows(repo)[-1]["why"] == "--no-panel"


@pytest.mark.parametrize("value", ["0", "off", "FALSE"])
def test_prompts_off_by_env(repo, value):
    plan(repo)
    r = run(repo, "prompts", ".claude/plans/plan-a.md", env={"CK_REVIEW_PANEL": value})
    assert lines(r.stdout)["PANEL"].startswith("off (CK_REVIEW_PANEL=")
    assert log_rows(repo)[-1]["panel"] == "off"


def test_prompts_defaults_to_newest_plan_skipping_siblings(repo):
    old = plan(repo, "plan-old.md")
    new = plan(repo, "plan-new.md")
    os.utime(old, (1, 1))
    os.utime(new, (2_000_000_000, 2_000_000_000))
    sib = plan(repo, "plan-new.review.md")
    os.utime(sib, (2_100_000_000, 2_100_000_000))
    r = run(repo, "prompts")
    assert r.returncode == 0, r.stdout
    prompt = lines(r.stdout)["CRITIC_PROMPT"]
    m = PROMPT_RE.match(prompt)
    assert m and m.group(1) == os.path.realpath(str(new))


def test_prompts_no_plan_exits_1(repo):
    r = run(repo, "prompts")
    assert r.returncode == 1
    assert r.stdout.strip() == "ERROR: no plan"


# ------------------------------------------------------------------ merge

def write(repo, name, text):
    path = repo / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def merge(repo, p, *critics, reviewer=REVIEWER):
    rev = write(repo, "reviewer.txt", reviewer)
    args = ["merge", str(p), "--reviewer", rev]
    for i, text in enumerate(critics):
        args += ["--critic", "plan-design-critic=%s" % write(repo, "c%d.txt" % i, text)]
    r = run(repo, *args)
    assert r.returncode == 0, r.stderr
    return r.stdout


def summary(out):
    return [ln for ln in out.splitlines() if ln.startswith("PANEL:")][-1]


def test_merge_valid_reply_numbers_findings(repo):
    p = plan(repo)
    out = merge(repo, p, "- [Blocker] D3 never says which file owns the lock\n"
                         "**Major**: rollback path untested\nPANEL: 1 blocker, 1 major\n")
    assert "plan-design-critic-r1-1 plan-design-critic: [Blocker]" in out
    assert "plan-design-critic-r1-2 plan-design-critic: [Major]" in out
    assert summary(out).startswith("PANEL: 1 blocker, 1 major (uncovered); round 1; CONTINUE")


@pytest.mark.parametrize("reply, reason", [
    ("[Blocker] something\n", "no PANEL line"),
    ("API Error: overloaded\nPANEL: 0 blocker, 0 major\n", "API error"),
    ("x" * 3001 + "\nPANEL: 0 blocker, 0 major\n", "over 3000 chars"),
    ("PANEL: incomplete - plan unreadable\n", "critic reported"),
    ("   \n", "empty or missing reply"),
])
def test_merge_marks_bad_replies_incomplete(repo, reply, reason):
    out = merge(repo, plan(repo), reply)
    assert "plan-design-critic: incomplete (%s" % reason in out
    assert summary(out).startswith("PANEL: 0 blocker, 0 major")


def test_merge_drops_finding_the_reviewer_covers(repo):
    out = merge(repo, plan(repo), "[Blocker] src/cache.py eviction handler swallows exceptions\n"
                                  "PANEL: 1 blocker, 0 major\n")
    assert "-r1-" not in out
    assert summary(out).startswith("PANEL: 0 blocker, 0 major")


@pytest.mark.parametrize("finding", [
    "[Blocker] src/other.py eviction handler swallows exceptions",  # different path
    "[Blocker] src/cache.py needs a migration test",                # too few shared words
])
def test_merge_keeps_uncovered_finding(repo, finding):
    out = merge(repo, plan(repo), finding + "\nPANEL: 1 blocker, 0 major\n")
    assert "plan-design-critic-r1-1" in out


def test_merge_usage_errors_exit_2(repo):
    p = plan(repo)
    rev = write(repo, "reviewer.txt", REVIEWER)
    assert run(repo, "merge", str(p), "--reviewer", rev, "--critic", "noequals").returncode == 2
    assert run(repo, "merge", str(repo / "missing.md"), "--reviewer", rev).returncode == 2
    assert run(repo, "merge", str(p)).returncode == 2
    assert run(repo).returncode == 2


# ------------------------------------------------------------------ rounds + stop rule

CLEAN = "PANEL: 0 blocker, 0 major\n"


def blocker(text):
    return "[Blocker] %s\nPANEL: 1 blocker, 0 major\n" % text


def test_same_sha_is_one_round(repo):
    p = plan(repo)
    merge(repo, p, blocker("first"))
    out = merge(repo, p, blocker("first"))
    assert "; round 1;" in summary(out)


def test_two_clean_rounds_stop(repo):
    p = plan(repo)
    merge(repo, p, CLEAN)
    p.write_text("# plan v2\n")
    out = merge(repo, p, CLEAN)
    assert "; round 2; STOP: 2 consecutive clean rounds" in summary(out)


def test_repeated_blocker_stops(repo):
    p = plan(repo)
    merge(repo, p, blocker("lock owner unnamed"))
    p.write_text("# plan v2\n")
    out = merge(repo, p, blocker("lock owner unnamed"))
    assert "; round 2; STOP: round 2 raised no new Blocker" in summary(out)


def test_new_blocker_continues_then_caps_at_5(repo):
    p = plan(repo)
    for k in range(1, 6):
        p.write_text("# plan v%d\n" % k)
        out = merge(repo, p, blocker("distinct problem number %d" % k))
        assert "; round %d;" % k in summary(out)
        if k < 5:
            assert "CONTINUE" in summary(out)
    assert "CAP: round 5" in summary(out)
