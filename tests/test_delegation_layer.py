"""Delegation-by-default layer: delegation-report.py (Stop), delegate-nudge.py (PreToolUse),
route-hint.py (UserPromptSubmit), the model-policy price table and the doctor WARN.

Each test runs the hook as Claude Code would - a subprocess fed a JSON payload - against a
transcript written in the layout Claude Code writes (session .jsonl, subagents/agent-*.jsonl).
Mutants these catch: dedup by message id dropped (tokens double), subagent glob wrong (0 tok),
price read from the wrong key (cost 0), nudge ignoring the Agent count / context floor /
cooldown, `--dispatched` not exiting early (dispatch.sh runs it twice), wiring through
dispatch.sh instead of settings.json (JSON never reaches the model).
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"
REPORT = HOOKS / "delegation-report.py"
NUDGE = HOOKS / "delegate-nudge.py"
ROUTE = HOOKS / "route-hint.py"
POLICY = ROOT / ".claude" / "model-policy.json"
sys.path.insert(0, str(ROOT / "src"))

from claudekit.enforcement import eventlog  # noqa: E402


def _assistant(msg_id, model, tools=(), context=0, output=0):
    content = [{"type": "tool_use", "id": "%s-t%d" % (msg_id, i), "name": name, "input": inp}
               for i, (name, inp) in enumerate(tools)]
    usage = {"input_tokens": 0, "cache_read_input_tokens": context,
             "cache_creation_input_tokens": 0, "output_tokens": output}
    return {"type": "assistant", "message": {"id": msg_id, "model": model, "role": "assistant",
                                             "content": content, "usage": usage}}


def _write(path, records, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def _project(tmp_path):
    """A project dir with the kit's price table, as an installed project has."""
    proj = tmp_path / "proj"
    (proj / ".claude" / "hooks").mkdir(parents=True)
    shutil.copy(POLICY, proj / ".claude" / "model-policy.json")
    return proj


def _run(hook, payload, proj, args=(), env=None):
    environ = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj), ECC_HOOK_PROFILE="standard")
    for key in ("CK_NO_DELEGATION_REPORT", "CK_NO_DELEGATE_NUDGE", "CK_NO_ROUTE_HINT"):
        environ.pop(key, None)
    environ.update(env or {})
    return subprocess.run([sys.executable, str(hook), *args], input=json.dumps(payload),
                          capture_output=True, text=True, env=environ, cwd=str(proj),
                          timeout=30)


# ---- delegation-report.py -------------------------------------------------------------

def _session(tmp_path):
    transcript = tmp_path / "sess.jsonl"
    opus = "claude-opus-5-5"
    first = _assistant("m1", opus, tools=[("Read", {"file_path": "a"}),
                                          ("Grep", {"pattern": "x"})], context=1_000_000, output=0)
    _write(transcript, [
        first, first,  # one message split over two lines repeats its usage: counted once
        _assistant("m2", opus, tools=[("Bash", {"command": "python3 -m pytest -q"}),
                                      ("Bash", {"command": "ls src"}),
                                      ("Agent", {"subagent_type": "explore"})], output=1_000_000),
        {"type": "user", "message": {"role": "user", "content": "hi"}},
    ])
    _write(tmp_path / "sess" / "subagents" / "agent-1.jsonl",
           [_assistant("s1", "claude-haiku-4-5-20251001", context=1_000_000)])
    return transcript


def test_report_counts_prices_and_logs(tmp_path):
    proj = _project(tmp_path)
    transcript = _session(tmp_path)
    r = _run(REPORT, {"session_id": "abc/1", "transcript_path": str(transcript)}, proj)
    assert r.returncode == 0 and r.stdout == ""
    line = r.stderr.strip()
    assert line.startswith("[ck delegation] direct 3 · agent 1 · tests 1 · peak ctx 1.0M"), line
    # opus: 1M cache read @0.2 + 1M output @20; haiku: 1M cache read @0.1
    assert "most-capable $20.20" in line and "fast $0.10" in line and "$20.30" in line, line

    events = proj / ".claude" / "runtime" / "events" / "abc-1.jsonl"
    assert stat.S_IMODE(os.stat(events).st_mode) == 0o600
    (record,) = eventlog.read(str(events))
    assert record["kind"] == "delegation_report"
    for field in eventlog.required_fields("delegation_report"):
        assert field in record, field
    assert record["main_tokens"] == 2_000_000 and record["subagent_tokens"] == 1_000_000
    assert record["cost_by_tier"] == {"most-capable": 20.2, "fast": 0.1}


def test_report_names_an_unknown_model_unpriced(tmp_path):
    proj = _project(tmp_path)
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_assistant("m1", "some-other-model", context=5000)])
    r = _run(REPORT, {"session_id": "s", "transcript_path": str(transcript)}, proj)
    assert "$0.00 (no priced tier) · unpriced 5k tok (some-other-model)" in r.stderr, r.stderr
    assert "unpriced $" not in r.stderr, "an unpriced model must not read as free"


@pytest.mark.parametrize("payload", ["not json", {"transcript_path": "/nope.jsonl"}, {}])
def test_report_is_silent_and_exit_0_on_bad_input(tmp_path, payload):
    proj = _project(tmp_path)
    environ = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj))
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run([sys.executable, str(REPORT)], input=raw, capture_output=True,
                       text=True, env=environ, cwd=str(proj))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_report_env_switch_silences(tmp_path):
    proj = _project(tmp_path)
    r = _run(REPORT, {"session_id": "s", "transcript_path": str(_session(tmp_path))}, proj,
             env={"CK_NO_DELEGATION_REPORT": "1"})
    assert r.stderr == "" and not (proj / ".claude" / "runtime").exists()


# ---- delegate-nudge.py ----------------------------------------------------------------

def _exploring(transcript, calls, context, tool=("Read", {"file_path": "f"}), start=0):
    _write(transcript, [_assistant("m%d" % (start + i), "claude-opus-5-5", tools=[tool],
                                   context=context) for i in range(calls)], mode="a")


def _nudge(proj, transcript, args=()):
    r = _run(NUDGE, {"session_id": "s1", "tool_name": "Read",
                     "transcript_path": str(transcript)}, proj, args=args)
    assert r.returncode == 0 and r.stderr == ""
    return r.stdout


def test_nudges_past_60k_with_12_direct_calls_and_no_agent(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 11, 70_000)
    assert _nudge(proj, transcript) == ""
    _exploring(transcript, 1, 70_000, start=11)
    out = json.loads(_nudge(proj, transcript))["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert "12 direct exploration calls" in out["additionalContext"]
    assert "subagent_type=explore" in out["additionalContext"]


def test_silent_under_the_context_floor(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 30, 60_000)
    assert _nudge(proj, transcript) == ""


def test_three_test_runs_trigger_it(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 3, 90_000, tool=("Bash", {"command": "cd x && pytest tests/"}))
    assert "3 test runs" in _nudge(proj, transcript)


def test_one_agent_call_disarms_it(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 20, 90_000)
    _exploring(transcript, 1, 90_000, tool=("Agent", {"subagent_type": "explore"}), start=20)
    assert _nudge(proj, transcript) == ""


def test_cooldown_then_renudge(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 12, 90_000)
    assert _nudge(proj, transcript)
    _exploring(transcript, 14, 90_000, start=12)
    assert _nudge(proj, transcript) == ""
    _exploring(transcript, 1, 90_000, start=26)
    assert "27 direct" in _nudge(proj, transcript)


def test_scan_is_incremental_and_restarts_on_a_shorter_transcript(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 5, 90_000)
    _nudge(proj, transcript)
    state_file = proj / ".claude" / "hooks" / ".state" / "delegate-s1"
    state = json.loads(state_file.read_text())
    assert state["offset"] == transcript.stat().st_size and state["direct"] == 5
    transcript.write_text("")
    _exploring(transcript, 2, 90_000)
    _nudge(proj, transcript)
    assert json.loads(state_file.read_text())["direct"] == 2


def test_dispatched_flag_exits_before_reading_anything(tmp_path):
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 12, 90_000)
    assert _nudge(proj, transcript, args=("--dispatched",)) == ""
    assert not (proj / ".claude" / "hooks" / ".state").exists()


def _dispatch_sandbox(tmp_path, row):
    box = tmp_path / "box"
    box.mkdir()
    for name in ("dispatch.sh", "lib.sh", "dispatch_resolve.py", "delegate-nudge.py",
                 "delegation-report.py"):
        shutil.copy(HOOKS / name, box / name)
    doc = {"schema_version": 1, "blocking_events": ["PreToolUse"], "events": {"PreToolUse": [row]}}
    (box / "dispatch-registry.json").write_text(json.dumps(doc))
    return box


@pytest.mark.parametrize("with_flag", [True, False])
def test_dispatch_sh_runs_the_registry_row_as_a_no_op(tmp_path, with_flag):
    """The shipped row carries --dispatched; without it (positive control) dispatch.sh would
    run the nudge a second time and prefix its JSON - this test must see that to be worth
    anything."""
    registry = json.loads((HOOKS / "dispatch-registry.json").read_text())
    (row,) = [r for r in registry["events"]["PreToolUse"] if r["id"] == "delegate-nudge"]
    assert row["args"] == ["--dispatched"] and row["tier"] == "advisory"
    if not with_flag:
        row = {k: v for k, v in row.items() if k != "args"}
    box = _dispatch_sandbox(tmp_path, row)
    proj, transcript = _project(tmp_path), tmp_path / "t.jsonl"
    _exploring(transcript, 12, 90_000)
    payload = {"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": "x"},
               "transcript_path": str(transcript)}
    environ = dict(os.environ, ECC_HOOK_PROFILE="standard", CLAUDE_PROJECT_DIR=str(proj),
                   CLAUDEKIT_SESSION_ID="pytest-delegate")
    environ.pop("CK_NO_DELEGATE_NUDGE", None)
    r = subprocess.run(["bash", str(box / "dispatch.sh"), "PreToolUse"], input=json.dumps(payload),
                       capture_output=True, text=True, env=environ, cwd=str(box), timeout=60)
    assert r.returncode == 0, r.stderr
    assert ("[ck delegate]" in r.stdout + r.stderr) is (not with_flag), r.stdout + r.stderr


# ---- route-hint.py --------------------------------------------------------------------

@pytest.mark.parametrize("prompt", ["where is the retry logic?", "Find all callers of save()",
                                    "search for every retry across the repo",
                                    "trace how src/cli.py reaches lib/db/"])
def test_route_hint_on_search_prompts(tmp_path, prompt):
    r = _run(ROUTE, {"prompt": prompt}, _project(tmp_path))
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit" and "explore" in out["additionalContext"]


@pytest.mark.parametrize("prompt", ["rename foo to bar in utils.py", "commit this", "go"])
def test_route_hint_silent_otherwise(tmp_path, prompt):
    r = _run(ROUTE, {"prompt": prompt}, _project(tmp_path))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


SHORT = ["how does the installer work", "which files touch auth", "trace how src/cli.py works"]


@pytest.mark.parametrize("prompt", SHORT)
def test_route_hint_skips_a_short_search_in_a_small_session(tmp_path, prompt):
    """Search-shaped, but one place, no breadth word, <=40k context: answering directly is
    cheaper, so no hint."""
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_assistant("m1", "claude-sonnet-5", context=40_000)])
    r = _run(ROUTE, {"prompt": prompt, "transcript_path": str(transcript)}, _project(tmp_path))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("prompt", SHORT)
def test_route_hint_fires_on_a_short_search_past_40k(tmp_path, prompt):
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_assistant("m1", "claude-sonnet-5", context=90_000),
                        _assistant("m2", "claude-sonnet-5", context=41_000)])
    r = _run(ROUTE, {"prompt": prompt, "transcript_path": str(transcript)}, _project(tmp_path))
    assert "explore" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_route_hint_reads_the_latest_context_not_the_peak(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write(transcript, [_assistant("m1", "claude-sonnet-5", context=90_000),
                        _assistant("m2", "claude-sonnet-5", context=20_000)])  # compacted
    r = _run(ROUTE, {"prompt": SHORT[0], "transcript_path": str(transcript)}, _project(tmp_path))
    assert r.stdout == ""


def test_route_hint_env_switch(tmp_path):
    r = _run(ROUTE, {"prompt": "where is x"}, _project(tmp_path), env={"CK_NO_ROUTE_HINT": "1"})
    assert r.stdout == ""


# ---- wiring, price table, doctor ------------------------------------------------------

def _settings_commands(event):
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    return [(e.get("matcher"), h["command"]) for e in settings["hooks"][event] for h in e["hooks"]]


@pytest.mark.parametrize("event,hook,matcher", [
    ("PreToolUse", "delegate-nudge.py", "Read|Grep|Glob|Bash"),
    ("UserPromptSubmit", "route-hint.py", ""),
    ("Stop", "delegation-report.py", ""),
])
def test_wired_directly_from_settings(event, hook, matcher):
    hits = [(m, c) for m, c in _settings_commands(event) if hook in c]
    assert len(hits) == 1, hits
    assert hits[0][0] == matcher and "dispatch.sh" not in hits[0][1]
    assert "&" not in hits[0][1].split(hook)[1], "backgrounded: stderr would be lost"


def test_every_tier_carries_a_price():
    tiers = json.loads(POLICY.read_text())["capability_tiers"]
    for name, spec in tiers.items():
        prices = spec["usd_per_mtok"]
        assert set(prices) == {"input", "output", "cache_read", "cache_write"}, name
        assert all(isinstance(v, (int, float)) and v > 0 for v in prices.values()), name


def _doctor(cwd):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ECC_HOOK_PROFILE="minimal")
    r = subprocess.run([sys.executable, "-m", "claudekit.cli.main", "doctor"], cwd=str(cwd),
                       capture_output=True, text=True, env=env, timeout=300)
    return r.stdout + r.stderr


def test_doctor_warns_on_an_unpriced_tier(tmp_path):
    proj = _project(tmp_path)
    policy = json.loads(POLICY.read_text())
    del policy["capability_tiers"]["fast"]["usd_per_mtok"]
    (proj / ".claude" / "model-policy.json").write_text(json.dumps(policy))
    out = _doctor(proj)
    assert "capability tiers priced — no usd_per_mtok on fast" in out, out


def test_doctor_quiet_when_every_tier_is_priced(tmp_path):
    out = _doctor(_project(tmp_path))
    assert "capability tiers priced" in out and "no usd_per_mtok" not in out, out


# ---- Stop deferral, Agent-call cap ----------------------------------------------------

def _launch(tool_id):
    return {"type": "user", "toolUseResult": {"status": "async_launched"},
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_id,
                 "content": "Async agent launched successfully"}]}}


def _notice(tool_id):
    return {"type": "user", "message": {"role": "user", "content": (
        "<task-notification>\n<tool-use-id>%s</tool-use-id>\n<status>completed</status>\n"
        "</task-notification>" % tool_id)}}


def test_report_defers_while_a_background_agent_is_open(tmp_path):
    proj = _project(tmp_path)
    transcript = _session(tmp_path)
    events = proj / ".claude" / "runtime" / "events" / "s.jsonl"
    _write(transcript, [_launch("m2-t2")], mode="a")
    r = _run(REPORT, {"session_id": "s", "transcript_path": str(transcript)}, proj)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert not events.exists()

    _write(transcript, [_notice("m2-t2")], mode="a")
    r = _run(REPORT, {"session_id": "s", "transcript_path": str(transcript)}, proj)
    assert r.stderr.startswith("[ck delegation] direct 3 · agent 1"), r.stderr
    assert len(eventlog.read(str(events))) == 1


def test_route_hint_names_the_cap_and_the_ladder_model(tmp_path):
    r = _run(ROUTE, {"prompt": "where is x"}, _project(tmp_path))
    text = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    policy = json.loads(POLICY.read_text())
    tiers, tier = policy["capability_tiers"], policy["roles"]["explore"]["tier"]
    (up,) = [name for name, spec in tiers.items() if spec["degrade_to"] == tier]
    assert "model=%s, maxTurns 12" % tiers[tier]["model"] in text, text
    assert "escalate to model=%s" % tiers[up]["model"] in text, text


def test_explore_frontmatter_caps_turns_at_12():
    head = (ROOT / ".claude" / "agents" / "explore.md").read_text().split("---")[1]
    assert "\nmaxTurns: 12\n" in head


# ---- gen-docs reachable-hook count ----------------------------------------------------

def _docs_tree(tmp_path):
    """The files gen-docs.py reads, copied so --check can be reddened without touching ROOT."""
    tree = tmp_path / "kit"
    for rel in ("agents", "commands", "skills", "hooks"):
        shutil.copytree(ROOT / ".claude" / rel, tree / ".claude" / rel,
                        ignore=shutil.ignore_patterns("*.log", "__pycache__"))
    shutil.copy(ROOT / ".claude" / "settings.json", tree / ".claude" / "settings.json")
    for rel in ("README.md", "AGENTS.md", "docs", "src/claudekit/cli/main.py",
                "scripts/gen-docs.py"):
        src, dst = ROOT / rel, tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)
    return tree


def _gen_docs_check(tree):
    r = subprocess.run([sys.executable, str(tree / "scripts" / "gen-docs.py"), "--check"],
                       capture_output=True, text=True, cwd=str(tree), timeout=60)
    return r.returncode, r.stdout + r.stderr


def test_gen_docs_check_fails_on_a_hand_edited_reachable_count(tmp_path):
    tree = _docs_tree(tmp_path)
    assert _gen_docs_check(tree)[0] == 0
    hooks_md = tree / "docs" / "HOOKS.md"
    text = hooks_md.read_text()
    (n,) = set(re.findall(r"(\d+) are reachable", text))
    hooks_md.write_text(text.replace("%s are reachable" % n, "%d are reachable" % (int(n) + 1)))
    rc, out = _gen_docs_check(tree)
    assert rc != 0 and "HOOKS.md" in out, out


def test_gen_docs_check_fails_when_the_reachable_phrase_is_deleted(tmp_path):
    tree = _docs_tree(tmp_path)
    readme = tree / "README.md"
    readme.write_text(re.sub(r"\d+ are reachable", "several are wired", readme.read_text()))
    rc, out = _gen_docs_check(tree)
    assert rc != 0 and "README.md" in out, out


# ---- enforcement on the top two tiers -------------------------------------------------

LEDGER = HOOKS / "session-model.py"
MODELS = {"fable": "claude-fable-5-1", "opus": "claude-opus-5-5",
          "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5-20251001"}


def _hinted(proj, prompt="where is the retry logic? see src/retry.py", pid="p1"):
    r = _run(ROUTE, {"session_id": "s1", "prompt_id": pid, "prompt": prompt}, proj)
    assert "explore" in r.stdout


def _ledger(proj, model):
    path = proj / ".claude" / "runtime" / "session-model" / "s1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, "source": "argv"}))


def _call(proj, tool="Read", path=None, pid="p1", extra=None):
    tool_input = {"file_path": path} if tool == "Read" else {"pattern": path or "x"}
    payload = {"session_id": "s1", "prompt_id": pid, "tool_name": tool,
               "tool_input": tool_input, "transcript_path": str(proj / "absent.jsonl")}
    payload.update(extra or {})
    return _run(NUDGE, payload, proj)


def _four(proj, tools=("Read", "Grep", "Glob", "Read")):
    return [_call(proj, tool, "f%d.py" % i) for i, tool in enumerate(tools)]


@pytest.mark.parametrize("tier", ["fable", "opus"])
def test_top_two_tiers_deny_the_4th_direct_call(tmp_path, tier):
    proj = _project(tmp_path)
    _ledger(proj, MODELS[tier])
    _hinted(proj)
    *allowed, denied = _four(proj)
    assert [r.returncode for r in allowed] == [0, 0, 0]
    assert denied.returncode == 2
    call = subprocess.run([sys.executable, "-c",
                           "import importlib.util as u;s=u.spec_from_file_location('r',%r);"
                           "m=u.module_from_spec(s);s.loader.exec_module(m);"
                           "print(m.explore_call(%r))" % (str(REPORT), str(proj))],
                          capture_output=True, text=True).stdout.strip()
    assert call.startswith("Agent(subagent_type=explore") and "maxTurns 12" in call
    assert call in denied.stderr


@pytest.mark.parametrize("tier", ["sonnet", "haiku"])
def test_lower_tiers_stay_advisory(tmp_path, tier):
    proj = _project(tmp_path)
    _ledger(proj, MODELS[tier])
    _hinted(proj)
    assert [r.returncode for r in _four(proj, ("Read",) * 6)] == [0] * 6


def test_transcript_model_overrides_the_ledger(tmp_path):
    """A /model switch shows in the transcript before any ledger could know it."""
    proj = _project(tmp_path)
    _ledger(proj, MODELS["sonnet"])
    _write(proj / "absent.jsonl", [_assistant("m1", MODELS["opus"])])
    _hinted(proj)
    assert _four(proj)[-1].returncode == 2


def test_no_deny_when_the_hint_did_not_fire_for_this_prompt(tmp_path):
    proj = _project(tmp_path)
    _ledger(proj, MODELS["opus"])
    _hinted(proj, pid="p0")
    assert [r.returncode for r in [_call(proj, "Read", "f%d" % i) for i in range(5)]] == [0] * 5


def test_short_prompt_leaves_no_hint_so_no_deny(tmp_path):
    proj = _project(tmp_path)
    _ledger(proj, MODELS["opus"])
    _run(ROUTE, {"session_id": "s1", "prompt_id": "p1", "prompt": "commit this"}, proj)
    assert all(r.returncode == 0 for r in _four(proj))


def test_exemptions(tmp_path):
    proj = _project(tmp_path)
    _ledger(proj, MODELS["opus"])
    _hinted(proj, "where is the retry logic? start at src/retry.py")
    assert all(r.returncode == 0 for r in _four(proj, ("Read", "Grep", "Glob")))
    assert _call(proj, "Read", str(proj / "src" / "retry.py")).returncode == 0  # named file
    assert _call(proj, "Read", "f0.py").returncode == 0  # opened this turn
    assert _call(proj, "Read", "other.py").returncode == 2


def test_subagent_calls_are_never_denied(tmp_path):
    proj = _project(tmp_path)
    _ledger(proj, MODELS["opus"])
    _hinted(proj)
    extra = {"agent_id": "a1", "agent_type": "explore"}
    assert all(_call(proj, "Grep", "p%d" % i, extra=extra).returncode == 0 for i in range(6))


def test_a_new_prompt_resets_the_turn(tmp_path):
    proj = _project(tmp_path)
    _ledger(proj, MODELS["opus"])
    _hinted(proj, pid="p1")
    _four(proj, ("Grep",) * 3)
    _hinted(proj, pid="p2")
    assert _call(proj, "Grep", "y", pid="p2").returncode == 0


@pytest.mark.parametrize("where", ["settings.json", "settings.local.json"])
def test_delegation_enforce_false_turns_it_off(tmp_path, where):
    proj = _project(tmp_path)
    (proj / ".claude" / where).write_text(json.dumps({"delegation": {"enforce": False}}))
    _ledger(proj, MODELS["opus"])
    _hinted(proj)
    assert all(r.returncode == 0 for r in _four(proj))


def test_unknown_model_stays_advisory(tmp_path):
    proj = _project(tmp_path)
    _hinted(proj)
    assert all(r.returncode == 0 for r in _four(proj))


def test_ledger_reads_the_model_from_settings(tmp_path):
    proj = _project(tmp_path)
    (proj / ".claude" / "settings.json").write_text(json.dumps({"model": "opus"}))
    env = {"CLAUDE_PID": "", "ANTHROPIC_MODEL": "", "CLAUDE_CONFIG_DIR": str(tmp_path / "home")}
    r = _run(LEDGER, {"session_id": "s1"}, proj, env=env)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    ledger = proj / ".claude" / "runtime" / "session-model" / "s1.json"
    assert json.loads(ledger.read_text()) == {"model": "opus", "source": "settings"}


def test_ledger_reads_model_from_the_claude_process_argv(tmp_path):
    proj = _project(tmp_path)
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)",
                                "--model", "fable"])
    try:
        r = _run(LEDGER, {"session_id": "s1"}, proj, env={"CLAUDE_PID": str(sleeper.pid)})
    finally:
        sleeper.kill()
    ledger = proj / ".claude" / "runtime" / "session-model" / "s1.json"
    assert r.returncode == 0
    assert json.loads(ledger.read_text()) == {"model": "fable", "source": "argv"}
