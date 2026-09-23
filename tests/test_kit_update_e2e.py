"""`ck update` over a real install: a stale copy is refreshed, a project edit is kept.

The unit layer is tests/test_kit_history.py; this runs install.sh (the kit is this git
checkout, so the history is rebuilt through HEAD) and the CLI surfaces around it:
`ck update --show-kept`, the doctor `.kit-new` WARN, and the fleet log.

Mutants this file kills:
  - reconcile skipped (keep-modified only)  -> the stale copy survives the update
  - report not copied to runtime/            -> no kit-update.json, fleet prints nothing
  - --show-kept installs                     -> the stale copy is replaced by the dry run
  - doctor ignores .kit-new                  -> no WARN line
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
CLI = ROOT / "src" / "claudekit" / "cli" / "main.py"
HISTORY = ROOT / ".claude" / ".claudekit-history.json"
ENV = dict(os.environ, CLAUDEKIT_HOME=str(ROOT), ECC_HOOK_PROFILE="standard",
           PYTHONPATH=str(ROOT / "src"))
FLEET_LOG = ("import sys; from pathlib import Path; from claudekit.cli import fleet; "
             "fleet._print_kit_update(Path(sys.argv[1]))")


def run(*cmd, cwd=None):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=180,
                          stdin=subprocess.DEVNULL, env=ENV, cwd=cwd)


def install(project):
    r = run("bash", INSTALL, project, "--full", "--yes")
    assert r.returncode == 0, r.stderr + r.stdout
    return r


def older_version(claude):
    """(rel, bytes) of an agent file the kit shipped in a version other than today's."""
    files = json.loads(HISTORY.read_text())["files"]
    for rel in sorted(files):
        path = claude / rel
        if not rel.startswith("agents/") or not rel.endswith(".md") or not path.is_file():
            continue
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        for digest, (_, blob) in sorted(files[rel].items()):
            if digest != current:
                old = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", blob],
                                     capture_output=True, check=True).stdout
                return rel, old
    raise AssertionError("no agent file with an older shipped version")


def test_update_refreshes_stale_copy_keeps_edit_and_reports(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    install(tmp_path)
    claude = tmp_path / ".claude"
    rel, old = older_version(claude)
    current = (claude / rel).read_bytes()
    # An older installer kept this copy and receipted the kit hash over its bytes.
    (claude / rel).write_bytes(old)
    planner = claude / "agents" / "planner.md"
    edited = planner.read_text() + "\nproject line\n"
    planner.write_text(edited)

    shown = run(sys.executable, CLI, "update", "--show-kept", tmp_path)
    assert shown.returncode == 0, shown.stderr + shown.stdout
    table = {ln.split()[0]: ln.split()[1:] for ln in shown.stdout.splitlines()
             if ln.startswith("  ") and len(ln.split()) == 4}
    assert table[rel][0] == "stale", shown.stdout
    assert table["agents/planner.md"][:2] == ["edited", "no"], shown.stdout
    assert (claude / rel).read_bytes() == old, "--show-kept must not install"

    r = install(tmp_path)
    assert (claude / rel).read_bytes() == current
    assert "updated %s (was kit v" % rel in r.stdout
    assert planner.read_text() == edited
    assert "Kept locally-modified agents/planner.md (edited" in r.stdout + r.stderr
    rows = {row["path"]: row["status"] for row in
            json.loads((claude / "runtime" / "kit-update.json").read_text())["rows"]}
    assert rows == {rel: "stale", "agents/planner.md": "edited"}

    out = run(sys.executable, "-c", FLEET_LOG, tmp_path).stdout
    assert "updated %s (was kit v" % rel in out
    assert "kept 1, refreshed or merged 1" in out


def test_doctor_warns_on_kit_new(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    install(tmp_path)
    before = run(sys.executable, CLI, "doctor", cwd=tmp_path)
    assert ".kit-new" not in before.stdout + before.stderr
    (tmp_path / ".claude" / "agents" / "planner.md.kit-new").write_text("kit copy\n")
    after = run(sys.executable, CLI, "doctor", cwd=tmp_path)
    out = after.stdout + after.stderr
    assert "Unmerged kit updates: 1 .kit-new file(s)" in out
    assert "agents/planner.md.kit-new" in out
