"""Behavioral tests for scripts/check-rule-owners.py and the real .claude/rule-owners.json.

The gate is proven to bind by mutating a planted tree: a second statement of a rule, a
reworded owner, a stale exemption and a malformed map must each fail by name.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check-rule-owners.py"

RULE = {"id": "r1", "owner": "CLAUDE.md", "markers": ["No auto review", "three rounds"], "allowed": []}


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                          capture_output=True, text=True, timeout=30)


def plant(tmp_path, rules=None, files=None):
    (tmp_path / ".claude").mkdir()
    spec = {"scan": ["CLAUDE.md", "docs/*.md"], "rules": rules if rules is not None else [dict(RULE)]}
    (tmp_path / ".claude" / "rule-owners.json").write_text(json.dumps(spec))
    (tmp_path / "docs").mkdir()
    files = {"CLAUDE.md": "No auto review.\nThree  rounds is the ceiling.\n", **(files or {})}
    for rel, body in files.items():
        (tmp_path / rel).write_text(body)
    return tmp_path


def test_real_repo_map_holds():
    p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout


def test_clean_tree_passes_and_matches_case_and_whitespace(tmp_path):
    p = run(plant(tmp_path))
    assert p.returncode == 0 and "OK" in p.stdout


def test_rule_stated_in_a_second_file_fails_by_name(tmp_path):
    root = plant(tmp_path, files={"docs/a.md": "we say: no auto review, three rounds max"})
    p = run(root)
    assert p.returncode == 1 and "docs/a.md" in p.stdout and "r1" in p.stdout


def test_partial_mention_is_not_a_copy(tmp_path):
    root = plant(tmp_path, files={"docs/a.md": "see the No auto review rule"})
    assert run(root).returncode == 0


def test_allowed_file_may_repeat_the_rule(tmp_path):
    rule = {**RULE, "allowed": ["docs/*.md"]}
    root = plant(tmp_path, rules=[rule], files={"docs/a.md": "no auto review three rounds"})
    assert run(root).returncode == 0


def test_stale_allowed_glob_fails(tmp_path):
    rule = {**RULE, "allowed": ["docs/gone-*.md"]}
    p = run(plant(tmp_path, rules=[rule]))
    assert p.returncode == 1 and "stale" in p.stdout


def test_owner_that_lost_a_marker_is_drift(tmp_path):
    root = plant(tmp_path, files={"CLAUDE.md": "No auto review only.\n"})
    p = run(root)
    assert p.returncode == 1 and "three rounds" in p.stdout and "drift" in p.stdout


def test_missing_owner_file_fails(tmp_path):
    rule = {**RULE, "owner": "NOPE.md"}
    p = run(plant(tmp_path, rules=[rule]))
    assert p.returncode == 1 and "NOPE.md" in p.stdout


def test_same_markers_two_owners_fails(tmp_path):
    other = {**RULE, "id": "r2", "owner": "docs/b.md"}
    root = plant(tmp_path, rules=[dict(RULE), other],
                 files={"docs/b.md": "No auto review, three rounds"})
    p = run(root)
    assert p.returncode == 1 and "two owners" in p.stdout


def test_duplicate_id_and_malformed_rule_fail(tmp_path):
    assert "twice" in run(plant(tmp_path, rules=[dict(RULE), dict(RULE)])).stdout
    (tmp_path / "x").mkdir()
    bad = plant(tmp_path / "x", rules=[{"id": "r"}])
    assert run(bad).returncode == 1


def test_malformed_or_missing_map_fails_closed(tmp_path):
    assert run(tmp_path).returncode == 1
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "rule-owners.json").write_text("{nope")
    assert run(tmp_path).returncode == 1


def test_json_output(tmp_path):
    out = json.loads(run(plant(tmp_path), "--json").stdout)
    assert out == {"ok": True, "findings": []}
