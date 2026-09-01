"""Behavioural contract of `validate-config-json.py --after`.

GUARD 10/11 already simulate edits cumulatively *within* one config, so a
missing or ambiguous anchor is caught there. The case that escaped is a
SEQUENCE of configs: each was measured against the file on disk, so an anchor
that is unique against HEAD but duplicated, rewritten or deleted by an earlier
config in the same run validated green and then failed in the executor.

These tests pin both directions: without `--after` the old (wrong) verdict is
reproduced, with it the validator agrees with the executor. Every invocation
runs the real script as a subprocess against a temp project and asserts the
verdict, not prose.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VALIDATOR = REPO / ".claude" / "operations" / "scripts" / "validate-config-json.py"
EXECUTOR = REPO / ".claude" / "operations" / "scripts" / "execute-json-ops.py"


def write_config(path, operations, plan="t"):
    path.write_text(json.dumps({"plan": plan, "operations": operations}), encoding="utf-8")
    return path


def run_validator(config, project, after=()):
    args = [sys.executable, str(VALIDATOR)]
    for predecessor in after:
        args += ["--after", str(predecessor)]
    args.append(str(config))
    return subprocess.run(args, capture_output=True, text=True, cwd=str(project), timeout=60)


def verdict(result):
    if "-> APPROVED" in result.stdout:
        return "APPROVED"
    if "-> REJECTED" in result.stdout:
        return "REJECTED"
    return "UNKNOWN:" + result.stdout[-200:]


def make_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=str(project), check=False)
    (project / "code.py").write_text("header\n    return 1\nfooter\n", encoding="utf-8")
    return project


def edit_op(path, edits, description="d"):
    return [{"type": "code_edit", "path": path, "description": description, "edits": edits}]


class TestSequenceProjection:
    def test_predecessor_that_duplicates_an_anchor_makes_the_next_config_ambiguous(self, tmp_path):
        """The p1/p3 mechanism: A copies the line B relies on being unique."""
        project = make_project(tmp_path)
        a = write_config(project / "A.json",
                         edit_op("code.py", [{"find": "footer", "replace": "footer\n    return 1\n"}]))
        b = write_config(project / "B.json",
                         edit_op("code.py", [{"find": "    return 1", "add_after": "\n    # B"}]))
        assert verdict(run_validator(b, project)) == "APPROVED"
        assert verdict(run_validator(b, project, after=[a])) == "REJECTED"

    def test_predecessor_that_rewrites_an_anchor_makes_the_next_config_stale(self, tmp_path):
        """The p1/p2 mechanism: C rewrites the line D anchors on."""
        project = make_project(tmp_path)
        c = write_config(project / "C.json", edit_op("code.py", [{"find": "header", "replace": "HEADER"}]))
        d = write_config(project / "D.json", edit_op("code.py", [{"find": "header", "replace": "header2"}]))
        assert verdict(run_validator(d, project)) == "APPROVED"
        assert verdict(run_validator(d, project, after=[c])) == "REJECTED"

    def test_projected_verdict_agrees_with_the_executor(self, tmp_path):
        """The whole point: the gate must not green-light what the engine refuses."""
        project = make_project(tmp_path)
        a = write_config(project / "A.json",
                         edit_op("code.py", [{"find": "footer", "replace": "footer\n    return 1\n"}]))
        b = write_config(project / "B.json",
                         edit_op("code.py", [{"find": "    return 1", "add_after": "\n    # B"}]))
        assert verdict(run_validator(b, project, after=[a])) == "REJECTED"
        subprocess.run([sys.executable, str(EXECUTOR), str(a), "--no-approval"],
                       capture_output=True, text=True, cwd=str(project), timeout=60)
        applied = subprocess.run([sys.executable, str(EXECUTOR), str(b), "--no-approval"],
                                 capture_output=True, text=True, cwd=str(project), timeout=60)
        assert "ambiguous match" in applied.stdout, applied.stdout[-400:]

    def test_a_clean_sequence_still_passes(self, tmp_path):
        """Vacuity guard: --after must not reject everything it is handed."""
        project = make_project(tmp_path)
        a = write_config(project / "A.json", edit_op("code.py", [{"find": "header", "replace": "HEADER"}]))
        b = write_config(project / "B.json", edit_op("code.py", [{"find": "footer", "replace": "FOOTER"}]))
        assert verdict(run_validator(b, project, after=[a])) == "APPROVED"

    def test_order_matters(self, tmp_path):
        """Projection applies predecessors in the order given, like the executor."""
        project = make_project(tmp_path)
        a = write_config(project / "A.json", edit_op("code.py", [{"find": "header", "replace": "MID"}]))
        b = write_config(project / "B.json", edit_op("code.py", [{"find": "MID", "replace": "END"}]))
        assert verdict(run_validator(b, project, after=[a])) == "APPROVED"
        assert verdict(run_validator(b, project)) == "REJECTED"

    def test_file_create_by_a_predecessor_is_visible(self, tmp_path):
        """A config may edit a file an earlier config creates."""
        project = make_project(tmp_path)
        a = write_config(project / "A.json",
                         [{"type": "file_create", "path": "new.py",
                           "description": "d", "content": "alpha\nbeta\n"}])
        b = write_config(project / "B.json", edit_op("new.py", [{"find": "alpha", "replace": "ALPHA"}]))
        assert verdict(run_validator(b, project, after=[a])) == "APPROVED"

    def test_an_unreadable_predecessor_warns_without_crashing(self, tmp_path):
        project = make_project(tmp_path)
        bad = project / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        b = write_config(project / "B.json", edit_op("code.py", [{"find": "footer", "replace": "FOOTER"}]))
        result = run_validator(b, project, after=[bad])
        assert "cannot read" in result.stdout
        assert verdict(result) == "APPROVED"
