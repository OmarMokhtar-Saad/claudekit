#!/usr/bin/env python3
"""ClaudeKit eval harness (task 010) — behavioral evals for the prompt corpus.

Structural tests assert the prompt TEXT; evals assert the BEHAVIOR: each eval
spawns a real agent (`claude -p --agent <name>`) in an isolated fixture
workspace and applies checks to its output and to the workspace state.
Derived from the 2026-07-08 end-to-end pipeline run.

Evals cost real API money (~$0.2–1.5 each) — they are NOT part of pytest.
Run them deliberately:

    python3 scripts/run-evals.py --list
    python3 scripts/run-evals.py --dry-run          # validate definitions, no API calls
    python3 scripts/run-evals.py                    # run all
    python3 scripts/run-evals.py --only <eval-id>   # run one

Exit codes: 0 all pass · 1 failures · 2 bad invocation/definitions.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS_DIR = os.path.join(ROOT, "evals", "definitions")
FIXTURES_DIR = os.path.join(ROOT, "evals", "fixtures")

REQUIRED_KEYS = ("id", "description", "agent", "model", "allowed_tools",
                 "fixture", "prompt", "checks")
CHECK_TYPES = ("regex_present", "regex_absent", "ops_extractable_and_valid",
               "workspace_file_contains")


def load_definitions():
    defs = []
    for fname in sorted(os.listdir(DEFS_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(DEFS_DIR, fname)) as fh:
            d = json.load(fh)
        missing = [k for k in REQUIRED_KEYS if k not in d]
        if missing:
            raise ValueError(f"{fname}: missing keys {missing}")
        agent_file = os.path.join(ROOT, ".claude", "agents", d["agent"] + ".md")
        if not os.path.isfile(agent_file):
            raise ValueError(f"{fname}: unknown agent {d['agent']!r}")
        if not os.path.isdir(os.path.join(FIXTURES_DIR, d["fixture"])):
            raise ValueError(f"{fname}: unknown fixture {d['fixture']!r}")
        for c in d["checks"]:
            if c.get("type") not in CHECK_TYPES:
                raise ValueError(f"{fname}: unknown check type {c.get('type')!r}")
        defs.append(d)
    return defs


def build_workspace(definition):
    """Fixture copy + the kit's prompt assets (no hooks/settings — evals judge
    prompts, not hook behavior) in a temp dir with its own git repo."""
    ws = tempfile.mkdtemp(prefix=f"ckeval-{definition['id']}-")
    fixture = os.path.join(FIXTURES_DIR, definition["fixture"])
    for entry in os.listdir(fixture):
        src = os.path.join(fixture, entry)
        dst = os.path.join(ws, entry)
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)
    claude_dir = os.path.join(ws, ".claude")
    for sub in ("agents", "skills", "operations"):
        shutil.copytree(os.path.join(ROOT, ".claude", sub),
                        os.path.join(claude_dir, sub))
    os.makedirs(os.path.join(claude_dir, "plans"), exist_ok=True)
    for rel, content in definition.get("setup_files", {}).items():
        path = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.email=eval@claudekit", "-c",
                    "user.name=ckeval", "commit", "-qm", "fixture"],
                   cwd=ws, check=True)
    return ws


def run_agent(definition, workspace):
    cmd = ["claude", "-p", "--agent", definition["agent"],
           "--model", definition["model"],
           "--allowedTools", definition["allowed_tools"],
           "--output-format", "json"]
    proc = subprocess.run(cmd, input=definition["prompt"], cwd=workspace,
                          capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        return None, f"claude exited {proc.returncode}: {proc.stderr[-300:]}"
    try:
        return json.loads(proc.stdout), None
    except ValueError:
        return None, f"non-JSON output: {proc.stdout[-300:]}"


def apply_checks(definition, result_text, workspace):
    failures = []
    for check in definition["checks"]:
        ctype, why = check["type"], check.get("why", "")
        if ctype == "regex_present":
            if not re.search(check["pattern"], result_text):
                failures.append(f"regex_present {check['pattern']!r} — {why}")
        elif ctype == "regex_absent":
            if re.search(check["pattern"], result_text):
                failures.append(f"regex_absent {check['pattern']!r} matched — {why}")
        elif ctype == "workspace_file_contains":
            path = os.path.join(workspace, check["path"])
            if not os.path.isfile(path):
                failures.append(f"missing workspace file {check['path']} — {why}")
            elif not re.search(check["pattern"], open(path).read()):
                failures.append(f"{check['path']} lacks {check['pattern']!r} — {why}")
        elif ctype == "ops_extractable_and_valid":
            out_txt = os.path.join(workspace, "_eval_agent_output.md")
            with open(out_txt, "w") as fh:
                fh.write(result_text)
            ops = os.path.join(workspace, "_eval_extracted_ops.json")
            scripts = os.path.join(workspace, ".claude", "operations", "scripts")
            ext = subprocess.run(
                [sys.executable, os.path.join(scripts, "extract-json-from-plan.py"),
                 out_txt, "--output", ops],
                capture_output=True, text=True, cwd=workspace)
            if ext.returncode != 0:
                failures.append(f"ops not extractable — {ext.stderr.strip()[-150:]}")
                continue
            val = subprocess.run(
                [sys.executable, os.path.join(scripts, "validate-config-json.py"), ops],
                capture_output=True, text=True, cwd=workspace)
            if val.returncode != 0 or "APPROVED" not in val.stdout:
                failures.append(f"extracted ops not APPROVED — {val.stdout.strip()[-150:]}")
    return failures


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    try:
        defs = load_definitions()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"DEFINITION ERROR: {exc}", file=sys.stderr)
        return 2
    if "--list" in argv:
        for d in defs:
            print(f"{d['id']:32} {d['agent']}/{d['model']:7} — {d['description']}")
        return 0
    if "--only" in argv:
        wanted = argv[argv.index("--only") + 1]
        defs = [d for d in defs if d["id"] == wanted]
        if not defs:
            print(f"no eval named {wanted!r}", file=sys.stderr)
            return 2
    if "--dry-run" in argv:
        for d in defs:
            ws = build_workspace(d)
            ok = os.path.isdir(os.path.join(ws, ".claude", "agents"))
            shutil.rmtree(ws, ignore_errors=True)
            print(f"OK {d['id']} (definition + workspace build)" if ok
                  else f"FAIL {d['id']}: workspace build")
        print(f"\n{len(defs)} definition(s) valid. No agents were run.")
        return 0

    results, total_cost = [], 0.0
    for d in defs:
        ws = build_workspace(d)
        print(f"→ {d['id']} ({d['agent']}/{d['model']}) ...", flush=True)
        try:
            payload, err = run_agent(d, ws)
            if err:
                results.append((d["id"], [f"agent run failed: {err}"], 0.0))
                continue
            cost = payload.get("total_cost_usd") or 0.0
            total_cost += cost
            failures = apply_checks(d, payload.get("result") or "", ws)
            if cost > d.get("max_cost_usd", 10):
                failures.append(f"cost {cost:.2f} exceeded budget {d['max_cost_usd']}")
            results.append((d["id"], failures, cost))
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    print("\n===== EVAL REPORT =====")
    failed = 0
    for eid, failures, cost in results:
        status = "PASS" if not failures else "FAIL"
        failed += bool(failures)
        print(f"[{status}] {eid}  (${cost:.2f})")
        for f in failures:
            print(f"    ✗ {f}")
    print(f"\n{len(results) - failed}/{len(results)} passed · total cost ${total_cost:.2f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
