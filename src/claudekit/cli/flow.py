"""``ck flow "<task>"``: the headless plan -> review -> record -> implement -> verify chain.

Each agent phase is one ``claude -p --agent <role>`` run with the role's scoped
``--allowedTools`` (``.claude/agents/_shared/INVOCATION.md``) and ``--output-format json``;
the usage block of that JSON is what the per-phase table reports (turns, average context
per turn, rebilled input tokens, cost). Headless agents cannot write under ``.claude/``
(platform gate), so every artifact is saved here from the agent's stdout.

Local phases (record, implementer) run the operations scripts with ``--python``; in a git
worktree that defaults to the main checkout's ``.venv`` interpreter, because worktrees
do not carry a venv of their own.
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
    "verifier": ("sonnet", "Read,Grep,Glob,Bash"),
}
PHASE_ORDER = ("planner", "reviewer", "record", "implementer", "verifier")
IMPL_OUTPUT_CAP = 20000  # chars of implementer output handed to the verifier


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
    """In a git worktree, the main checkout's ``.venv`` interpreter when it exists;
    otherwise the interpreter running ``ck``."""
    try:
        proc = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=str(root),
                              capture_output=True, text=True)
    except OSError:
        return sys.executable
    common = proc.stdout.strip()
    if proc.returncode != 0 or not common:
        return sys.executable
    main_root = (Path(root) / common).resolve().parent
    for cand in (main_root / ".venv" / "bin" / "python",
                 main_root / ".venv" / "Scripts" / "python.exe"):
        if cand.exists():
            return str(cand)
    return sys.executable


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


def planner_prompt(task, plan_md, ops):
    return (
        "Create an implementation plan for the task below and deliver it on stdout: the plan "
        "document (Task, Files, Operations, a `## Validation commands` section holding one "
        "fenced bash block, Risks) followed by the operations config for "
        ".claude/operations/scripts/execute-json-ops.py in exactly ONE fenced ```json block. "
        "Do not try to write under .claude/ (blocked in headless mode); stdout is the "
        f"delivery. The wrapper saves the plan as {plan_md} and the config as {ops}.\n\n"
        f"Task: {task}\n")


def reviewer_prompt(plan_md, ops):
    return (
        f"Review the plan at {plan_md} and its operations config at {ops} per your rubric "
        "(plans need 90/100). End your output with exactly two lines, an integer and one "
        "of APPROVED, CONDITIONAL, REVISE, REJECTED:\nSCORE: <n>\nDECISION: <d>\n")


def verifier_prompt(plan_md, ops, impl_output):
    tail = impl_output[-IMPL_OUTPUT_CAP:]
    return (
        f"Verify the implementation of plan {plan_md} (operations config {ops}). The "
        "implementer already ran the executor and the plan's validation commands; their "
        "captured output follows. Verify against it: read the changed files and this "
        "output, and rerun a command only when its output below is missing or ambiguous. "
        "Score per your rubric and report PASS, RETRY or FAIL.\n\n"
        f"--- implementer output ---\n{tail}\n")


def run_flow(task, root, python, claude_bin, models, slug, validation_commands,
             shell_free_argv, out=sys.stdout):
    """Returns the process exit code: 0 all phases done, 1 a phase failed, 2 the review
    did not authorise execution (nothing was written to the tree)."""
    root = Path(root)
    plan_md = PLANS / f"plan-{slug}.md"
    ops = PLANS / f"plan-{slug}.ops.json"
    review = PLANS / f"plan-{slug}.review.md"
    verify = PLANS / f"plan-{slug}.verify.md"
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

    def local(name, rc, text):
        phases.append(Phase(name, rc, text))
        return rc

    # 1. planner -> plan.md + ops.json (extracted, baseline-stamped)
    ph = agent("planner", planner_prompt(task, plan_md, ops))
    if ph.rc != 0:
        return finish(1, f"planner exited {ph.rc}")
    save(root / plan_md, ph.text)
    rc, text = run_script(python, "extract-json-from-plan.py", [plan_md, "--output", ops], root)
    if rc != 0:
        print(text, file=out)
        return finish(1, f"no ops.json in the planner output (saved at {plan_md})")
    rc, text = run_script(python, "validate-config-json.py", [ops, "--stamp-baseline"], root)
    if rc != 0:
        print(text, file=out)
        return finish(1, f"{ops} failed validation")
    print(f"[flow] plan {plan_md}, ops {ops}", file=out)

    # 2. reviewer -> review file; 3. record the verdict (this is the approval gate's input)
    ph = agent("reviewer", reviewer_prompt(plan_md, ops))
    save(root / review, ph.text)
    if ph.rc != 0:
        return finish(1, f"reviewer exited {ph.rc} (output at {review})")
    rc, text = run_script(python, "review-record.py",
                          ["write", "--from-review", review, "--reviewer-role", "reviewer",
                           plan_md, ops], root)
    print(text.rstrip(), file=out)
    if rc == 0:
        # `write` succeeds for any verdict; `check` is the gate's own question
        rc, text = run_script(python, "review-record.py", ["check", plan_md, ops], root)
    local("record", rc, text)
    if rc != 0:
        print(text.rstrip(), file=out)
        return finish(2, f"review did not authorise execution (review-record exit {rc}; "
                         f"see {review})")

    # 4. implementer: the executor with the gate on, then the plan's own checks
    rc, text = run_script(python, "execute-json-ops.py", [ops], root)
    impl_output = text
    if rc == 0:
        for cmd in validation_commands(root / plan_md):
            argv = shell_free_argv(cmd)
            if argv is None:
                impl_output += f"\n$ {cmd}\n(skipped: needs a shell)\n"
                continue
            proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(root))
            impl_output += f"\n$ {cmd}\n{proc.stdout}{proc.stderr}(exit {proc.returncode})\n"
            if proc.returncode != 0:
                rc = proc.returncode
                break
    local("implementer", rc, impl_output)
    if rc != 0:
        print(impl_output.rstrip(), file=out)
        return finish(1, f"implementer exited {rc}")

    # 5. verifier, fed the captured output so it verifies instead of rerunning
    ph = agent("verifier", verifier_prompt(plan_md, ops, impl_output))
    save(root / verify, ph.text)
    if ph.rc != 0:
        return finish(1, f"verifier exited {ph.rc} (output at {verify})")
    return finish(0, f"done: {plan_md} {ops} {review} {verify}")


def parse_models(items):
    models = {}
    for item in items or ():
        role, sep, model = item.partition("=")
        if not sep or role not in AGENTS or not model:
            raise ValueError(f"--model expects ROLE=MODEL with ROLE in {sorted(AGENTS)}: {item!r}")
        models[role] = model
    return models


def cmd_flow(args, validation_commands, shell_free_argv):
    root = Path.cwd()
    if not (root / SCRIPTS / "execute-json-ops.py").exists():
        print(f"ERROR: {SCRIPTS} not found under {root}; run ck flow from a project with "
              "ClaudeKit installed", file=sys.stderr)
        return 1
    try:
        models = parse_models(args.model)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    python = args.python or default_python(root)
    claude_bin = args.claude or os.environ.get("CK_CLAUDE_BIN") or "claude"
    slug = args.slug or slug_for(args.task)
    if (root / PLANS / f"plan-{slug}.md").exists() and not args.slug:
        slug = f"{slug}-{time.strftime('%H%M%S')}"
    print(f"[flow] python {python}; claude {claude_bin}; slug {slug}")
    return run_flow(args.task, root, python, claude_bin, models, slug,
                    validation_commands, shell_free_argv)
