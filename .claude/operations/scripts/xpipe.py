#!/usr/bin/env python3
"""xpipe — cross-account / cross-tool pipeline with per-participant off-flags.

Participants (each can be switched off, or vanish gracefully when unavailable):

  brain   a second Claude account (default CLAUDE_CONFIG_DIR ~/.claude-acct-b)
          that PLANS and gates the merge — typically the Team/Enterprise seat
          running Fable. Off: --no-brain. Auto-off: config dir missing/empty.
  cursor  a non-Claude cross-reviewer (cursor-agent on PATH). Off: --no-cursor.
          Auto-off: not installed.
  hands   the CURRENT default account — reviews (when brain planned) and
          implements. Always on; it is "the workflow now".

Modes resolve from flags + availability:

  full      brain plans -> hands reviews -> cursor cross-reviews -> hands implements
  no-brain  hands plans in-account; cursor still cross-reviews
  no-cursor brain plans -> hands reviews -> hands implements
  solo      everything off -> exit 0 telling the caller to run the standard
            in-session pipeline (/plan -> /review -> /implement). Nothing lost:
            solo IS the normal ClaudeKit workflow.

Safety: stages run headless with per-stage scoped --allowedTools (see
.claude/agents/_shared/INVOCATION.md). --dangerously-skip-permissions is never
used. A REVISE verdict from any reviewer stops the chain (exit 3).

Exit codes: 0 ok/solo, 1 operational error, 2 validation refusal, 3 gate REVISE.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_BRAIN_DIR = "~/.claude-acct-b"
STAGE_TIMEOUT = 1800  # seconds per headless stage

PLAN_TOOLS = "Read,Grep,Glob,Write,Bash"
# Bash+Write so the reviewer can record its verdict via the project's
# review-record mechanism (binds APPROVED to sha256(ops.json); /implement
# gates on that record) — a printed verdict alone is not a valid handoff.
REVIEW_TOOLS = "Read,Grep,Glob,Write,Bash"
IMPLEMENT_TOOLS = "Read,Grep,Glob,Write,Edit,Bash"


def project_root() -> Path:
    env = os.environ.get("CLAUDEKIT_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd()


def brain_dir(args: argparse.Namespace) -> Path:
    raw = args.brain_dir or os.environ.get("XPIPE_BRAIN_DIR") or DEFAULT_BRAIN_DIR
    return Path(os.path.expanduser(raw))


def brain_available(args: argparse.Namespace) -> bool:
    """Logged in = credentials file present, or .claude.json records an OAuth
    account (macOS Keychain case). A merely-launched dir (startup state only)
    is NOT logged in."""
    d = brain_dir(args)
    if not d.is_dir():
        return False
    if (d / ".credentials.json").is_file():
        return True
    state = d / ".claude.json"
    if state.is_file():
        try:
            return "oauthAccount" in json.load(open(state, encoding="utf-8"))
        except (OSError, ValueError):
            return False
    return False


def cursor_available() -> "tuple[bool, str]":
    """(available, reason-if-not). Requires the binary AND working auth in
    THIS process context — macOS Keychain tokens are often unreadable from
    headless shells; CURSOR_API_KEY always works."""
    exe = os.environ.get("XPIPE_CURSOR_BIN", "cursor-agent")
    if shutil.which(exe) is None:
        return False, "cursor auto-off: cursor-agent not on PATH"
    if os.environ.get("CURSOR_API_KEY"):
        return True, ""
    try:
        proc = subprocess.run([exe, "status"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False, "cursor auto-off: cursor-agent status failed"
    if proc.returncode != 0 or "Not logged in" in proc.stdout + proc.stderr:
        return False, ("cursor auto-off: not authenticated in this shell context "
                       "(Keychain tokens are session-bound — set CURSOR_API_KEY "
                       "for headless runs, or run xpipe from your own terminal)")
    return True, ""


def resolve_mode(args: argparse.Namespace) -> Dict[str, object]:
    """Flags can only turn participants OFF; availability can only degrade."""
    notes: List[str] = []
    brain = not args.solo and not args.no_brain
    cursor = not args.solo and not args.no_cursor
    if brain and not brain_available(args):
        brain = False
        notes.append(
            f"brain auto-off: no credentials in {brain_dir(args)} (second account "
            "not logged in — run: CLAUDE_CONFIG_DIR=" + str(brain_dir(args)) + " claude, then /login)"
        )
    if cursor:
        cursor_ok, reason = cursor_available()
        if not cursor_ok:
            cursor = False
            notes.append(reason)
    if brain and cursor:
        mode = "full"
    elif brain:
        mode = "no-cursor"
    elif cursor:
        mode = "no-brain"
    else:
        mode = "solo"
    return {"mode": mode, "brain": brain, "cursor": cursor, "notes": notes}


def stage_commands(args: argparse.Namespace, state: Dict[str, object]) -> List[Dict[str, object]]:
    """The exact headless commands per stage (also what --dry-run prints)."""
    task = args.task or "<task>"
    stages: List[Dict[str, object]] = []
    plan_env = {"CLAUDE_CONFIG_DIR": str(brain_dir(args))} if state["brain"] else {}
    planner = "brain" if state["brain"] else "hands"
    stages.append({
        "stage": "plan", "runner": planner, "env": plan_env,
        "cmd": ["claude", "-p",
                f"Run /plan for this task and save the plan to .claude/plans/. "
                f"Print ONLY the plan file path on the last line. Task: {task}",
                "--allowedTools", PLAN_TOOLS],
    })
    stages.append({
        "stage": "review", "runner": "hands", "env": {},
        "cmd": ["claude", "-p",
                "Run /review on the plan file at {PLAN_PATH} (90/100 gate). "
                "Follow the full reviewer handoff: if the project has the "
                "review-record mechanism "
                "(.claude/operations/scripts/review-record.py), record the "
                "verdict bound to the plan's ops.json so /implement's approval "
                "gate resolves. Print ONLY 'APPROVED <score>' or "
                "'REVISE <score>' on the last line, findings above it.",
                "--allowedTools", REVIEW_TOOLS],
    })
    if state["cursor"]:
        stages.append({
            "stage": "cross-review", "runner": "cursor", "env": {},
            # --trust: workspace read access for reviewing the plan file.
            # Never --yolo/-f — the cross-reviewer gets no force-allowed commands.
            "cmd": [os.environ.get("XPIPE_CURSOR_BIN", "cursor-agent"), "--trust", "-p",
                    "Adversarially review the implementation plan at {PLAN_PATH} "
                    "for defects a same-vendor reviewer would miss. Print ONLY "
                    "'APPROVED' or 'REVISE' on the last line, findings above it."],
        })
    stages.append({
        "stage": "implement", "runner": "hands", "env": {},
        "cmd": ["claude", "-p",
                "Run /implement for the approved plan at {PLAN_PATH} inside a "
                "worktree (use /worktree; commit on the agent/* branch; never "
                "merge). Report the branch and commit on the last line.",
                "--allowedTools", IMPLEMENT_TOOLS],
    })
    return stages


def print_status(args: argparse.Namespace, state: Dict[str, object]) -> None:
    print(f"mode: {state['mode']}")
    print(f"  brain  (plan/merge, {brain_dir(args)}): {'ON' if state['brain'] else 'off'}")
    print(f"  cursor (cross-review):                {'ON' if state['cursor'] else 'off'}")
    print("  hands  (review+implement, default account): ON")
    for note in state["notes"]:  # type: ignore[union-attr]
        print(f"  ! {note}")
    if state["mode"] == "solo":
        print("solo: run the standard in-session pipeline "
              "(/plan -> /review -> /implement, or /coordinator).")


def run_stage(stage: Dict[str, object], plan_path: Optional[str], log_dir: Path) -> "subprocess.CompletedProcess[str]":
    cmd = [str(c).replace("{PLAN_PATH}", plan_path or "") for c in stage["cmd"]]  # type: ignore[union-attr]
    env = dict(os.environ)
    env.update(stage["env"])  # type: ignore[arg-type]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=STAGE_TIMEOUT)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = log_dir / f"{stamp}-{stage['stage']}.log"
    log.write_text(
        f"cmd: {' '.join(cmd)}\nrc: {proc.returncode}\n--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}\n", encoding="utf-8",
    )
    return proc


def last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def normalize_plan_location(root: Path, raw_path: str) -> Optional[str]:
    """Enforce the .claude/plans/ convention. Headless planner sessions can
    have .claude/** writes refused and fall back to the repo root or a
    scratchpad — move the plan (and its sibling ops-*.json / ops.json) home.
    Returns the repo-relative plan path, or None if the path isn't a file."""
    src = Path(raw_path) if os.path.isabs(raw_path) else root / raw_path
    if not src.is_file():
        return None
    plans_dir = root / ".claude" / "plans"
    try:
        if plans_dir in src.resolve().parents:
            return os.path.relpath(str(src.resolve()), str(root))
    except OSError:
        return None
    plans_dir.mkdir(parents=True, exist_ok=True)
    moved = plans_dir / src.name
    shutil.move(str(src), str(moved))
    # sibling ops config: plan-<slug>.md -> ops-<slug>.json, plus plain ops.json
    candidates = []
    if src.name.startswith("plan-") and src.name.endswith(".md"):
        candidates.append("ops-" + src.name[len("plan-"):-3] + ".json")
    candidates.append("ops.json")
    for name in candidates:
        sib = src.parent / name
        if sib.is_file():
            shutil.move(str(sib), str(plans_dir / name))
            print(f"xpipe: moved {name} -> .claude/plans/ (location convention)")
    print(f"xpipe: moved {src.name} -> .claude/plans/ (location convention)")
    return os.path.relpath(str(moved), str(root))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("task", nargs="?", help="the task to pipeline")
    parser.add_argument("--no-brain", action="store_true",
                        help="skip the second-account plan/merge stage")
    parser.add_argument("--no-cursor", action="store_true",
                        help="skip the cross-vendor review stage")
    parser.add_argument("--solo", action="store_true",
                        help="all external participants off — standard in-session workflow")
    parser.add_argument("--status", action="store_true",
                        help="report participant availability and resolved mode")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the exact stage commands without executing")
    parser.add_argument("--brain-dir", default=None,
                        help=f"second account CLAUDE_CONFIG_DIR (default {DEFAULT_BRAIN_DIR})")
    args = parser.parse_args(argv)

    state = resolve_mode(args)

    if args.status:
        print_status(args, state)
        return 0

    if state["mode"] == "solo":
        print_status(args, state)
        return 0

    if not args.task:
        print("xpipe: a task is required unless --status", file=sys.stderr)
        return 2

    stages = stage_commands(args, state)
    if args.dry_run:
        print_status(args, state)
        for stage in stages:
            env = " ".join(f"{k}={v}" for k, v in stage["env"].items())  # type: ignore[union-attr]
            prefix = f"{env} " if env else ""
            print(f"[{stage['stage']} @ {stage['runner']}] {prefix}" +
                  " ".join(f"'{c}'" if " " in str(c) else str(c) for c in stage["cmd"]))  # type: ignore[union-attr]
        return 0

    root = project_root()
    log_dir = root / ".claude" / "reports" / "xpipe"
    plan_path: Optional[str] = None
    for stage in stages:
        print(f"xpipe: running {stage['stage']} on {stage['runner']} ...")
        try:
            proc = run_stage(stage, plan_path, log_dir)
        except subprocess.TimeoutExpired:
            print(f"xpipe: {stage['stage']} timed out after {STAGE_TIMEOUT}s", file=sys.stderr)
            return 1
        except FileNotFoundError as exc:
            print(f"xpipe: {exc}", file=sys.stderr)
            return 1
        tail = last_line(proc.stdout)
        if proc.returncode != 0:
            print(f"xpipe: {stage['stage']} failed (rc={proc.returncode}); "
                  f"log in {log_dir}", file=sys.stderr)
            return 1
        if stage["stage"] == "plan":
            plan_path = normalize_plan_location(root, tail)
            if plan_path is None:
                print(f"xpipe: plan stage did not yield a plan file (got {tail!r})",
                      file=sys.stderr)
                return 1
            print(f"xpipe: plan -> {plan_path}")
        elif stage["stage"] in ("review", "cross-review"):
            verdict = tail.upper()
            print(f"xpipe: {stage['stage']} verdict: {tail}")
            if not verdict.startswith("APPROVED"):
                print(f"xpipe: gate stopped the chain at {stage['stage']} "
                      f"(verdict {tail!r}); findings in {log_dir}", file=sys.stderr)
                return 3
        elif stage["stage"] == "implement":
            print(f"xpipe: implement -> {tail}")
    print("xpipe: pipeline complete. Merge stays with the merge authority "
          "(gitOps Multi-Agent Merge Protocol) — review the agent/* branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
