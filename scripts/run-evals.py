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
    python3 scripts/run-evals.py                    # run all (LIVE, costs money)
    python3 scripts/run-evals.py --only <eval-id>   # run one

Record once, replay many — the replay path needs no API key and no network:

    python3 scripts/run-evals.py --record           # LIVE, then save cassettes
    python3 scripts/run-evals.py --replay           # cassettes only, free, CI-safe

A cassette is bound to a fingerprint of everything the model saw, including the
agent's own prompt file and the skills it loads. Edit the corpus and replay
FAILS CLOSED rather than serving a stale pass.

Prove the checks actually bind, with no API calls:

    python3 scripts/run-evals.py --inject refusal   # exits 0 only if EVERY eval fails

Exit codes: 0 all pass · 1 failures · 2 bad invocation/definitions.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS_DIR = (os.environ.get("CK_EVAL_DEFS")
            or os.path.join(ROOT, "evals", "definitions"))
FIXTURES_DIR = os.path.join(ROOT, "evals", "fixtures")

REQUIRED_KEYS = ("id", "description", "agent", "tier", "allowed_tools",
                 "fixture", "prompt", "checks")
CHECK_TYPES = ("regex_present", "regex_absent", "ops_extractable_and_valid",
               "workspace_file_contains")


# ---------------------------------------------------------------------------
# Deterministic replay + fault injection (wave-2 phase 2.1)
#
# An eval suite whose fixtures require live, paid API calls cannot run in CI,
# so it runs never. Record once, replay many: `--record` captures the real
# response, `--replay` serves it with no API key and no network.
#
# The hard part is not caching, it is INVALIDATION. These evals test the prompt
# corpus, so the agent's own .md file and the skills it loads are part of the
# question being asked. A cassette recorded against an older planner.md answers
# a question nobody asked any more. Every input that reaches the model is
# therefore folded into a fingerprint, and replay FAILS CLOSED on a mismatch
# rather than serving a stale pass -- a green CI run off a superseded recording
# is worse than no CI run at all.
# ---------------------------------------------------------------------------

# Overridable so tests can exercise the real replay path against a scratch
# store instead of the repo's own recordings.
CASSETTES_DIR = (os.environ.get("CK_EVAL_CASSETTES")
                 or os.path.join(ROOT, "evals", "cassettes"))
POLICY = os.path.join(ROOT, ".claude", "model-policy.json")

# Deliberate adverse model behaviours. Real models time out, get truncated at a
# token ceiling, emit tool calls that do not parse, and refuse. If an eval's
# checks pass under any of these, the checks are decorative -- so the harness
# can inject each one and assert every eval REJECTS it.
FAULTS = ("timeout", "truncation", "malformed_tool_call", "refusal")


def resolve_model(definition):
    """The concrete model a definition's capability tier resolves to.

    Definitions name a tier, never a vendor model, for the same reason policy
    prose does: `.claude/model-policy.json` is the single table.
    """
    with open(POLICY, encoding="utf-8") as fh:
        policy = json.load(fh)
    tier = definition["tier"]
    if tier not in policy["capability_tiers"]:
        raise ValueError(f"{definition['id']}: unknown capability tier {tier!r}")
    return policy["capability_tiers"][tier]["model"]


def _digest_tree(root):
    """Content digest of a directory: every relative path and its bytes.

    Path-inclusive, so a renamed-but-identical file still changes the digest --
    the agent sees the tree, not just the bytes in it.
    """
    sha = hashlib.sha256()
    if not os.path.isdir(root):
        return "absent"
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fname in sorted(filenames):
            path = os.path.join(dirpath, fname)
            sha.update(os.path.relpath(path, root).replace(os.sep, "/").encode())
            with open(path, "rb") as fh:
                sha.update(fh.read())
    return sha.hexdigest()


def _digest_file(path):
    if not os.path.isfile(path):
        return "absent"
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def prompt_surface(definition):
    """Every input that reaches the model, as a canonical dict.

    Includes the agent's own prompt file and the skills the registry says that
    agent loads: this suite's subject IS the prompt corpus, so a corpus edit
    must invalidate the recording. Excludes anything the model never sees
    (cost budgets, the eval's own checks) -- those may change freely without
    forcing a costly re-record.
    """
    agent_file = os.path.join(ROOT, ".claude", "agents", definition["agent"] + ".md")
    skills = {}
    registry_path = os.path.join(ROOT, ".claude", "skills", "skills-registry.json")
    if os.path.isfile(registry_path):
        with open(registry_path, encoding="utf-8") as fh:
            registry = json.load(fh)
        for skill in registry.get("agentMapping", {}).get(definition["agent"], []):
            skills[skill] = _digest_file(
                os.path.join(ROOT, ".claude", "skills", skill, "SKILL.md"))
    return {
        "agent": definition["agent"],
        "agent_prompt": _digest_file(agent_file),
        # Reachable, not inert. Several definitions grant
        # `Bash(python3 .claude/operations/scripts/*)` and instruct the agent to
        # self-validate or dry-run, so these scripts RUN during generation and
        # their stdout is read by the model before it answers. Change one and the
        # same prompt yields a different response - which is precisely a stale
        # cassette, so the tree belongs in the fingerprint.
        "operations_scripts": _digest_tree(
            os.path.join(ROOT, ".claude", "operations", "scripts")),
        "skills": skills,
        "model": resolve_model(definition),
        "allowed_tools": definition["allowed_tools"],
        "prompt": definition["prompt"],
        "fixture": definition["fixture"],
        "fixture_tree": _digest_tree(os.path.join(FIXTURES_DIR, definition["fixture"])),
        "setup_files": definition.get("setup_files", {}),
    }


def fingerprint(definition):
    surface = prompt_surface(definition)
    canonical = json.dumps(surface, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cassette_path(definition):
    return os.path.join(CASSETTES_DIR, definition["id"] + ".json")


def write_cassette(definition, payload):
    os.makedirs(CASSETTES_DIR, exist_ok=True)
    cassette = {
        "eval_id": definition["id"],
        "fingerprint": fingerprint(definition),
        "prompt_surface": prompt_surface(definition),
        "response": payload,
    }
    path = cassette_path(definition)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cassette, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def _explain_drift(recorded, current):
    """Name what changed, so a stale cassette is actionable rather than a wall."""
    changed = []
    for key in sorted(set(recorded) | set(current)):
        if recorded.get(key) != current.get(key):
            if key == "skills":
                moved = sorted(
                    name for name in set(recorded.get(key, {})) | set(current.get(key, {}))
                    if recorded.get(key, {}).get(name) != current.get(key, {}).get(name))
                changed.append("skills(%s)" % ", ".join(moved))
            else:
                changed.append(key)
    return ", ".join(changed) or "unknown"


def load_cassette(definition):
    """(payload, error). A stale or absent cassette is an ERROR, never a pass."""
    path = cassette_path(definition)
    if not os.path.isfile(path):
        return None, ("no cassette at %s — record one with: "
                      "python3 scripts/run-evals.py --record --only %s"
                      % (os.path.relpath(path, ROOT), definition["id"]))
    try:
        with open(path, encoding="utf-8") as fh:
            cassette = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"cassette unreadable: {exc}"
    current = fingerprint(definition)
    if cassette.get("fingerprint") != current:
        return None, (
            "cassette is STALE — the inputs changed since it was recorded (%s). "
            "Re-record with: python3 scripts/run-evals.py --record --only %s"
            % (_explain_drift(cassette.get("prompt_surface", {}), prompt_surface(definition)),
               definition["id"]))
    if "response" not in cassette:
        return None, "cassette has no recorded response"
    return cassette["response"], None


def inject_fault(fault, definition):
    """Synthesize an adverse model response. Returns (payload, error).

    These are the four failure shapes a real model actually produces, and each
    is a distinct hazard for the checks: a timeout yields no output at all, a
    truncation yields output that STARTS correct (so prefix-matching checks
    pass), a malformed tool call yields plausible prose around unparseable
    JSON, and a refusal yields fluent text containing none of the artifacts.
    """
    if fault == "timeout":
        return None, "claude timed out after 900s (injected)"
    if fault == "truncation":
        head = (definition.get("prompt", "")[:80] +
                "\n\n## Plan\n\nI will begin by reading the fixture and identif")
        return {"result": head, "total_cost_usd": 0.0}, None
    if fault == "malformed_tool_call":
        body = ("Here is the operations config:\n\n```json\n"
                '{"plan": "x", "operations": [{"type": "code_edit", "path": '
                '"src/calc/basic.py", "edits": [{"find": "a", "replace": }]}\n'
                "```\n")
        return {"result": body, "total_cost_usd": 0.0}, None
    if fault == "refusal":
        return ({"result": "I'm not able to help with that request.",
                 "total_cost_usd": 0.0}, None)
    raise ValueError(f"unknown fault {fault!r}; known: {', '.join(FAULTS)}")


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
        if "model" in d:
            raise ValueError(
                f"{fname}: definitions name a capability `tier`, never a vendor `model` "
                f"(see .claude/model-policy.json)")
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
           "--model", resolve_model(definition),
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
            print(f"{d['id']:32} {d['agent']}/{d['tier']:13} — {d['description']}")
        return 0
    if "--only" in argv:
        wanted = argv[argv.index("--only") + 1]
        defs = [d for d in defs if d["id"] == wanted]
        if not defs:
            print(f"no eval named {wanted!r}", file=sys.stderr)
            return 2
    if not defs:
        print("no eval definitions matched — refusing to report a vacuous pass",
              file=sys.stderr)
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

    replay = "--replay" in argv
    record = "--record" in argv
    fault = argv[argv.index("--inject") + 1] if "--inject" in argv else None
    if replay and record:
        print("--replay and --record are mutually exclusive", file=sys.stderr)
        return 2
    if fault and fault not in FAULTS:
        print(f"unknown fault {fault!r}; known: {', '.join(FAULTS)}", file=sys.stderr)
        return 2
    if fault and (replay or record):
        print("--inject runs no model; drop --replay/--record", file=sys.stderr)
        return 2

    results, total_cost = [], 0.0
    for d in defs:
        ws = build_workspace(d)
        label = fault and f"inject:{fault}" or (replay and "replay") or (
            record and "record") or d["tier"]
        print(f"→ {d['id']} ({d['agent']}/{label}) ...", flush=True)
        try:
            if fault:
                payload, err = inject_fault(fault, d)
            elif replay:
                payload, err = load_cassette(d)
            else:
                payload, err = run_agent(d, ws)
            if err:
                results.append((d["id"], [f"agent run failed: {err}"], 0.0))
                continue
            if record:
                path = write_cassette(d, payload)
                print(f"   recorded {os.path.relpath(path, ROOT)}")
            cost = payload.get("total_cost_usd") or 0.0
            total_cost += cost
            failures = apply_checks(d, payload.get("result") or "", ws)
            if cost > d.get("max_cost_usd", 10):
                failures.append(f"cost {cost:.2f} exceeded budget {d['max_cost_usd']}")
            results.append((d["id"], failures, cost))
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    if fault:
        # Inverted on purpose: injecting a broken model response and still
        # PASSING means the checks do not bind. Green here == every eval
        # correctly rejected the fault.
        print(f"\n===== FAULT INJECTION: {fault} =====")
        survived = [eid for eid, failures, _c in results if not failures]
        for eid, failures, _c in results:
            verdict = "REJECTED (good)" if failures else "PASSED DESPITE FAULT (bad)"
            print(f"[{verdict}] {eid}")
            for f in failures[:2]:
                print(f"    · {f}")
        if survived:
            print(f"\n{len(survived)} eval(s) passed a deliberately broken response: "
                  f"{', '.join(survived)}")
            print("Their checks do not bind. Tighten them before trusting this suite.")
            return 1
        print(f"\nAll {len(results)} eval(s) rejected the injected {fault}.")
        return 0

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
