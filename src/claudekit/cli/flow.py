"""``ck flow "<task>"``: the headless plan -> review -> record chain.

Each agent phase is one ``claude -p --agent <role>`` run with the role's scoped
``--allowedTools`` (``.claude/agents/_shared/INVOCATION.md``) and ``--output-format json``;
the usage block of that JSON is what the per-phase table reports (turns, average context
per turn, rebilled input tokens, cost). Headless agents cannot write under ``.claude/``
(platform gate), so every artifact is saved here from the agent's stdout.

The record phase runs ``review-record.py plan-write`` with ``--python``; that defaults to
the main checkout's ``.venv`` interpreter (the first entry of ``git worktree list``),
because worktrees do not carry a venv of their own. ``ck flow`` prints which one.

The chain stops once the plan is approved: the main session then edits directly.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List

SCRIPTS = Path(".claude") / "operations" / "scripts"
PLANS = Path(".claude") / "plans"

# role -> (default model, scoped --allowedTools) per INVOCATION.md.
AGENTS = {
    "planner": ("opus", "Read,Grep,Glob,Write"),
    "reviewer": ("sonnet", "Read,Grep,Glob"),
}
PHASE_ORDER = ("planner", "reviewer", "record")


class Phase:
    def __init__(self, name, rc, text, usage=None, seconds=0.0, stderr=""):
        self.name = name
        self.rc = rc
        self.text = text
        self.usage = usage  # None for local (non-agent) phases
        self.seconds = seconds
        self.stderr = stderr


def parse_result_json(stdout):
    """The result object of ``--output-format json``: the whole stdout, or the last line
    that parses as a JSON object (wrappers may print before it). ``{}`` when none does."""
    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    return {}


def usage_of(data):
    """turns / rebilled / avg_ctx / cost from a result object; zeros when absent."""
    u = data.get("usage") or {}
    rebilled = 0
    for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        try:
            rebilled += int(u.get(key) or 0)
        except (TypeError, ValueError):
            pass
    try:
        turns = int(data.get("num_turns") or 0)
    except (TypeError, ValueError):
        turns = 0
    try:
        cost = float(data.get("total_cost_usd") or 0.0)
    except (TypeError, ValueError):
        cost = 0.0
    return {"turns": turns, "rebilled": rebilled,
            "avg_ctx": rebilled // turns if turns else 0, "cost": cost}


def default_python(root):
    """(interpreter, where it came from): the ``.venv`` of ``root``, else of the main
    checkout (the first ``git worktree list`` entry), else the interpreter running ``ck``."""
    roots = [Path(root)]
    try:
        proc = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=str(root),
                              capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.startswith("worktree "):
            roots.append(Path(proc.stdout.splitlines()[0][len("worktree "):]))
    except OSError:
        pass
    for base in roots:
        for cand in (base / ".venv" / "bin" / "python",
                     base / ".venv" / "Scripts" / "python.exe"):
            if cand.exists():
                return str(cand), f"{base}/.venv"
    return sys.executable, "no .venv found; the interpreter running ck"


def slug_for(task):
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:40].rstrip("-")
    return slug or "task"


def run_agent(role, prompt, root, claude_bin, model):
    argv = [claude_bin, "-p", "--agent", role, "--model", model,
            "--allowedTools", AGENTS[role][1], "--output-format", "json"]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                              cwd=str(root))
    except OSError as exc:
        return Phase(role, 127, "", usage_of({}), time.time() - t0, f"{claude_bin}: {exc}")
    data = parse_result_json(proc.stdout)
    text = data.get("result") if isinstance(data.get("result"), str) else proc.stdout
    rc = proc.returncode
    if rc == 0 and data.get("is_error"):
        rc = 1
    return Phase(role, rc, text, usage_of(data), time.time() - t0, proc.stderr)


def run_script(python, script, args, root):
    argv = [python, str(root / SCRIPTS / script)] + [str(a) for a in args]
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(root))
    return proc.returncode, proc.stdout + proc.stderr


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _fmt(n):
    return f"{n:,}"


def usage_table(phases):
    rows = [("Phase", "Turns", "Avg ctx", "Rebilled", "Cost", "Exit")]
    total = {"turns": 0, "rebilled": 0, "cost": 0.0}
    for ph in phases:
        if ph.usage is None:
            rows.append((ph.name, "-", "-", "-", "-", str(ph.rc)))
            continue
        u = ph.usage
        total["turns"] += u["turns"]
        total["rebilled"] += u["rebilled"]
        total["cost"] += u["cost"]
        rows.append((ph.name, _fmt(u["turns"]), _fmt(u["avg_ctx"]), _fmt(u["rebilled"]),
                     f"${u['cost']:.2f}", str(ph.rc)))
    avg = total["rebilled"] // total["turns"] if total["turns"] else 0
    rows.append(("total", _fmt(total["turns"]), _fmt(avg), _fmt(total["rebilled"]),
                 f"${total['cost']:.2f}", ""))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out = []
    for r in rows:
        out.append("  ".join(cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
                             for i, cell in enumerate(r)))
    return "\n".join(out)


def planner_prompt(task, plan_md):
    return (
        "Create an implementation plan for the task below and deliver it on stdout: the plan "
        "document (Task, a Tier line, a `Files:` list naming every path to change, steps, a "
        "`## Validation commands` section holding one fenced bash block, Risks). "
        "Do not try to write under .claude/ (blocked in headless mode); stdout is the "
        f"delivery. The wrapper saves the plan as {plan_md}.\n\n"
        f"Task: {task}\n")


def reviewer_prompt(plan_md):
    return (
        f"Review the plan at {plan_md} per your rubric "
        "(plans need 90/100). End your output with exactly two lines, an integer and one "
        "of APPROVED, CONDITIONAL, REVISE, REJECTED:\nSCORE: <n>\nDECISION: <d>\n")


def run_flow(task, root, python, claude_bin, models, slug, out=sys.stdout):
    """Returns the process exit code: 0 plan approved and recorded, 1 a phase failed,
    2 the review did not approve the plan. Only the plan and review files are written."""
    root = Path(root)
    plan_md = PLANS / f"plan-{slug}.md"
    review = PLANS / f"plan-{slug}.review.md"
    phases: List[Phase] = []

    def finish(code, msg):
        print(usage_table(phases), file=out)
        print(f"RESULT: {msg}", file=out)
        return code

    def agent(role, prompt):
        print(f"[flow] {role} ...", file=out)
        ph = run_agent(role, prompt, root, claude_bin, models.get(role, AGENTS[role][0]))
        phases.append(ph)
        if ph.stderr.strip():
            print(ph.stderr.rstrip(), file=sys.stderr)
        return ph

    # 1. planner -> plan.md
    ph = agent("planner", planner_prompt(task, plan_md))
    if ph.rc != 0:
        return finish(1, f"planner exited {ph.rc}")
    save(root / plan_md, ph.text)
    print(f"[flow] plan {plan_md}", file=out)

    # 2. reviewer -> review file; 3. record the verdict (the plan-gate's input)
    ph = agent("reviewer", reviewer_prompt(plan_md))
    save(root / review, ph.text)
    if ph.rc != 0:
        return finish(1, f"reviewer exited {ph.rc} (output at {review})")
    rc, text = run_script(python, "review-record.py",
                          ["plan-write", "--from-review", review, "--reviewer-role",
                           "reviewer", plan_md], root)
    if rc == 0:
        # plan-write also records non-approving verdicts with exit 0; plan-check is the gate
        rc, check = run_script(python, "review-record.py", ["plan-check", plan_md], root)
        text += check
    phases.append(Phase("record", rc, text))
    print(text.rstrip(), file=out)
    if rc != 0:
        return finish(2, f"review did not approve the plan (review-record exit {rc}; "
                         f"see {review})")
    return finish(0, f"approved: {plan_md} ({review}); the main session implements it")


def parse_models(items):
    models = {}
    for item in items or ():
        role, sep, model = item.partition("=")
        if not sep or role not in AGENTS or not model:
            raise ValueError(f"--model expects ROLE=MODEL with ROLE in {sorted(AGENTS)}: {item!r}")
        models[role] = model
    return models


def cmd_flow(args):
    root = Path.cwd()
    if not (root / SCRIPTS / "review-record.py").exists():
        print(f"ERROR: {SCRIPTS} not found under {root}; run ck flow from a project with "
              "ClaudeKit installed", file=sys.stderr)
        return 1
    try:
        models = parse_models(args.model)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    python, source = (args.python, "--python") if args.python else default_python(root)
    claude_bin = args.claude or os.environ.get("CK_CLAUDE_BIN") or "claude"
    slug = args.slug or slug_for(args.task)
    if (root / PLANS / f"plan-{slug}.md").exists() and not args.slug:
        slug = f"{slug}-{time.strftime('%H%M%S')}"
    print(f"[flow] python {python} ({source}); claude {claude_bin}; slug {slug}")
    return run_flow(args.task, root, python, claude_bin, models, slug)
