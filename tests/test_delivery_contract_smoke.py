"""Zero-LLM-cost regression test for the "paths, never payloads" delivery contract
(plan-token-waste-workflow-fixes.md). A fake `claude` stub stands in for the real
opus spawn -- what's under test is the *transport*: does the surrounding shell
plumbing keep a large fake plan/ops payload off stdout and on disk, regardless of
what the model itself said. Runs the actual scripts (extract-json-from-plan.py,
validate-config-json.py) against a realistic ~40KB payload, matching the size of
the originally observed leak.

Coverage is uneven by design, not oversight: `/plan`'s scripted bash block is
extracted from the real command file and executed, so it exercises the literal
current text. `/refine`'s scripted mode is pseudocode fragments across several
markdown sections with `<N>`/`<MAX_ITER>`/`$last_score` placeholders that aren't a
standalone runnable script -- the `/refine` test below assembles an equivalent
2-iteration script matching the DESIGN refine.md documents, not the literal file
content. That means it pins the mechanism (fixed paths, write-in-place, no echo)
but can NOT catch a prompt-text-level bug embedded in refine.md's actual
PLANNER_MSG strings (e.g. the iteration-1 message once told the headless planner
to "report only a short summary" while the wrapper it hands off to only saves
stdout to disk -- self-contradictory, would have broken at runtime; fixed
2026-07-31). `test_refine_scripted_messages_are_not_self_contradictory` below is
the mechanical (regex, not execution) guard against that specific class of bug.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS_DIR = os.path.join(REPO_ROOT, ".claude", "operations", "scripts")
PLAN_MD = os.path.join(REPO_ROOT, ".claude", "commands", "plan.md")
REFINE_MD = os.path.join(REPO_ROOT, ".claude", "commands", "refine.md")

FAKE_OPS = {
    "plan": "toy-smoke-test",
    "operations": [
        {
            "type": "file_create",
            "path": "src/toy_smoke.py",
            # Padded content to land the whole payload near the ~40KB scale of the
            # originally observed leak (ops-hardening-implementer-contract.json).
            "content": "def toy():\n    return 1\n" + ("# padding line\n" * 1500),
        }
    ],
}
FAKE_PAYLOAD_MARKER = "UNIQUE-FAKE-PLAN-BODY-MARKER-DO-NOT-ECHO"


def _fake_plan_doc():
    # NOTE: plan.md's documented contract intentionally echoes the plan's first 3
    # non-blank lines to stdout as the summary -- that's the spec, not a leak. The
    # marker goes in the padded body (line 5+), which must NEVER reach stdout.
    body = (
        "# Implementation Plan: Toy Task\n\n"
        "## Overview\nThis is a fake planner response used only to test transport.\n\n"
        + (f"Filler prose line ({FAKE_PAYLOAD_MARKER}) padding the plan body.\n" * 400)
        + "\n```json\n" + json.dumps(FAKE_OPS) + "\n```\n"
    )
    return body


def _make_stub_claude(bin_dir, stdout_text):
    """A `claude` on PATH that ignores its args/stdin and just prints stdout_text --
    standing in for a real `claude -p --agent planner` spawn."""
    stub = os.path.join(bin_dir, "claude")
    with open(stub, "w") as f:
        f.write("#!/bin/sh\ncat <<'STUB_EOF'\n" + stdout_text + "\nSTUB_EOF\n")
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _extract_scripted_bash_block(markdown_text):
    """Pull the ```bash fence under '## Invocation — scripted' out of plan.md --
    tests the ACTUAL current command text, not a hand-copied mirror that can drift."""
    section = markdown_text.split("## Invocation — scripted", 1)[1]
    match = re.search(r"```bash\n(.*?)```", section, re.S)
    assert match, "plan.md's scripted invocation block structure changed"
    return match.group(1)


def _prepare_fake_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude" / "plans").mkdir(parents=True)
    shutil.copytree(SCRIPTS_DIR, repo / ".claude" / "operations" / "scripts")
    return repo


def test_plan_scripted_path_keeps_stdout_small_and_files_valid(tmp_path):
    repo = _prepare_fake_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_stub_claude(str(bin_dir), _fake_plan_doc())

    script = _extract_scripted_bash_block(open(PLAN_MD).read())

    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env["ARGUMENTS"] = "toy smoke-test task"

    result = subprocess.run(
        ["bash", "-c", script], cwd=str(repo), env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    plans_dir = repo / ".claude" / "plans"
    plan_files = list(plans_dir.glob("plan-*.md"))
    assert len(plan_files) == 1, list(plans_dir.iterdir())
    ops_files = list(plans_dir.glob("*.ops.json"))
    assert len(ops_files) == 1, list(plans_dir.iterdir())

    # The fake ~40KB payload landed on disk...
    assert FAKE_PAYLOAD_MARKER in plan_files[0].read_text()
    assert json.loads(ops_files[0].read_text())["plan"] == "toy-smoke-test"

    # ...but never reached stdout: the marker and the padded body are absent, and
    # total stdout stays near the plan's documented ≤15-line / small-summary limit,
    # regardless of the ~40KB input.
    assert FAKE_PAYLOAD_MARKER not in result.stdout
    assert "padding line" not in result.stdout
    assert len(result.stdout) < 2000, result.stdout
    non_blank_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(non_blank_lines) <= 15, result.stdout


def test_refine_scripted_loop_keeps_stdout_small_and_writes_in_place(tmp_path):
    """Assembles the single self-contained script /refine's scripted mode documents
    (fixed PLAN_FILE/OPS_FILE decided once; planner writes in place; reviewer handed
    only paths) for a 2-iteration toy run, and asserts the design actually holds:
    total stdout stays scoreboard-sized and both iterations land on the SAME file."""
    repo = _prepare_fake_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    plan_v1 = _fake_plan_doc()
    plan_v2 = plan_v1.replace("Toy Task", "Toy Task REVISED")

    claude_stub = bin_dir / "claude"
    # Iteration-aware stub: planner calls emit the (large) plan; reviewer calls emit
    # a small scoreboard. Distinguished by --agent flag, matching the real CLI shape.
    claude_stub.write_text(f"""#!/bin/sh
for arg in "$@"; do
  if [ "$prev" = "--agent" ]; then agent="$arg"; fi
  prev="$arg"
done
if [ "$agent" = "reviewer" ]; then
  if [ -f "{repo}/.claude/plans/.iter2" ]; then
    echo "=== REFINE REVIEW ITERATION 2 ==="
    echo "SCORE: 95"
    echo "DECISION: APPROVED"
    echo "CRITICAL_MAJOR_COUNT: 0"
    echo "ISSUES: none"
    echo "=== END REVIEW ITERATION 2 ==="
  else
    touch "{repo}/.claude/plans/.iter2"
    echo "=== REFINE REVIEW ITERATION 1 ==="
    echo "SCORE: 70"
    echo "DECISION: REVISE"
    echo "CRITICAL_MAJOR_COUNT: 1"
    echo "ISSUES: - [MAJOR] toy issue -- Location: src/toy_smoke.py -- Fix: pad less"
    echo "=== END REVIEW ITERATION 1 ==="
  fi
else
  if [ -f "{repo}/.claude/plans/.iter2" ]; then
    cat <<'STUB_EOF'
{plan_v2}
STUB_EOF
  else
    cat <<'STUB_EOF'
{plan_v1}
STUB_EOF
  fi
fi
""")
    claude_stub.chmod(claude_stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Assembled per refine.md's documented single-script design: fixed paths decided
    # once, planner output saved silently (never echoed), reviewer handed only paths.
    script = """
set -e
PLAN_FILE=".claude/plans/plan-toy-slug.md"
OPS_FILE=".claude/plans/ops-toy-slug.json"
TOTAL_STDOUT_CHARS=0

run_planner() {
  plan_output=$(echo "$1" | claude -p --agent planner --model opus)
  printf '%s\\n' "$plan_output" > "$PLAN_FILE"
  python3 .claude/operations/scripts/extract-json-from-plan.py "$PLAN_FILE" --output "$OPS_FILE" > /dev/null
}

run_reviewer() {
  review_output=$(echo "REVIEW_MSG" | claude -p --agent reviewer --model opus)
  echo "$review_output"
}

run_planner "PLANNER_MSG iteration 1"
run_reviewer
run_planner "PLANNER_MSG iteration 2 (revision)"
run_reviewer

echo "Plan saved to: $PLAN_FILE"
echo "Ops config: $OPS_FILE"
"""
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]

    result = subprocess.run(
        ["bash", "-c", script], cwd=str(repo), env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    plans_dir = repo / ".claude" / "plans"
    plan_files = list(plans_dir.glob("plan-*.md"))
    ops_files = list(plans_dir.glob("ops-*.json"))
    # Both iterations wrote the SAME fixed path -- no per-iteration file pileup.
    assert len(plan_files) == 1, list(plans_dir.iterdir())
    assert len(ops_files) == 1, list(plans_dir.iterdir())
    # Final on-disk content is the iteration-2 (revised) version, in place.
    assert "REVISED" in plan_files[0].read_text()

    assert FAKE_PAYLOAD_MARKER not in result.stdout
    assert "padding line" not in result.stdout
    # Only the two scoreboards + two summary lines should reach stdout -- nowhere
    # near the ~90KB (two ~40KB plan bodies) that leaked in the original bug.
    assert len(result.stdout) < 3000, result.stdout


def _scripted_planner_messages(markdown_text):
    """Both PLANNER_MSG string literals from refine.md's scripted Cycle A block, in
    iteration order. Doesn't execute them (they contain unassembled placeholders) --
    just extracts the literal instruction text sent to the headless planner."""
    section = markdown_text.split("#### Cycle A: Planner", 1)[1].split("#### Cycle B", 1)[0]
    return re.findall(r'PLANNER_MSG="(.*?)"\n\nplan_output=', section, re.S)


def test_refine_scripted_messages_are_not_self_contradictory():
    """Regression guard for the exact bug this test suite couldn't catch by execution
    (see module docstring): a scripted-mode PLANNER_MSG telling the headless planner to
    return only a summary, when the surrounding wrapper's only delivery channel is
    stdout-to-file (`printf '%s\\n' "$plan_output" > "$PLAN_FILE"`). If the planner
    obeyed that instruction, the plan file would contain a summary instead of a plan +
    ops.json, and extract-json-from-plan.py would find nothing to extract."""
    messages = _scripted_planner_messages(open(REFINE_MD).read())
    assert len(messages) == 2, "expected iteration-1 and iteration-2+ PLANNER_MSG blocks"

    summary_only_phrases = ("report only a short summary", "return only a short summary",
                             "return only a summary")
    for msg in messages:
        lowered = msg.lower()
        assert not any(p in lowered for p in summary_only_phrases), (
            "a headless-mode PLANNER_MSG instructs the planner to return only a "
            "summary, but the wrapper's only delivery channel is stdout-to-file -- "
            f"the plan/ops payload would never reach $PLAN_FILE:\n{msg}"
        )
        # Every scripted-mode message must tell the planner its stdout IS the
        # payload (it has no Write access headless), not merely a report of one.
        assert "wrapper" in lowered and ("saves" in lowered or "captures" in lowered), msg


def test_queued_ops_configs_validate_against_head():
    """Every queued (non-archived) ops config in .claude/plans/ must validate against
    the current tree. A stale config -- authored against files that have since changed --
    fails at execution time at best, or silently re-applies superseded text at worst
    (found live 2026-07-31: an archived config's replacement text would have reintroduced
    the `PLAN TO REVIEW: $PLAN_CONTENT` payload leak). Spent or stale configs belong in
    .claude/plans/archive/ (see its README), which this test deliberately skips."""
    plans_dir = os.path.join(REPO_ROOT, ".claude", "plans")
    queued = sorted(
        f for f in os.listdir(plans_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(plans_dir, f))
    )
    failures = []
    for name in queued:
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "validate-config-json.py"),
             os.path.join(plans_dir, name)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            failures.append(f"{name}: {result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr.strip()}")
    assert not failures, (
        "queued ops config(s) no longer validate against HEAD -- regenerate via /plan "
        "or move to .claude/plans/archive/ with a README entry:\n" + "\n".join(failures)
    )
