"""Behavioral tests for `ck fleet` (discovery, list, verify, dry-run update).

The verify test plants real drift and asserts a non-zero exit: a green check that
cannot go red measures nothing.
"""

import json
import os
import sys

import pytest


def _import_fleet():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from claudekit.cli import fleet as f
    return f


def _import_main():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from claudekit.cli import main as m
    return m


def _ns(**kw):
    import argparse
    base = dict(action="list", root=None, include=None, exclude=None,
                yes=True, dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _make_kit(tmp_path):
    """A minimal kit source tree: what find_claudekit_root accepts."""
    kit = tmp_path / "kit"
    (kit / ".claude" / "agents").mkdir(parents=True)
    (kit / ".claude" / "settings.json").write_text('{"hooks": {}}')
    (kit / ".claude" / "agents" / "planner.md").write_text("# planner v2\n")
    return kit


def _make_project(root, name, m, kit, planner_text=None, manifest_matches=True):
    """A kitted project with a manifest. By default byte-identical to the kit."""
    proj = root / name
    base = proj / ".claude"
    (base / "agents").mkdir(parents=True)
    (base / "settings.json").write_text((kit / ".claude" / "settings.json").read_text())
    text = planner_text if planner_text is not None else \
        (kit / ".claude" / "agents" / "planner.md").read_text()
    (base / "agents" / "planner.md").write_text(text)
    files = {
        "settings.json": m._sha256(base / "settings.json"),
        "agents/planner.md": m._sha256(base / "agents" / "planner.md"),
    }
    if not manifest_matches:
        # Pretend the file was installed with different content -> "locally modified".
        files["agents/planner.md"] = "0" * 64
    (base / m.MANIFEST_NAME).write_text(json.dumps(
        {"version": "2.1.0", "mode": "full", "language": "python", "files": files}))
    return proj


@pytest.fixture()
def fleet_env(tmp_path, monkeypatch):
    m = _import_main()
    f = _import_fleet()
    kit = _make_kit(tmp_path)
    monkeypatch.setenv("CLAUDEKIT_HOME", str(kit))
    root = tmp_path / "fleet"
    root.mkdir()
    return f, m, kit, root


class TestDiscovery:
    def test_finds_only_kitted_children(self, fleet_env):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit)
        (root / "not-kitted").mkdir()
        (root / "empty-claude" / ".claude").mkdir(parents=True)
        names = [p.name for p in f.discover(root)]
        assert names == ["alpha"]

    def test_skips_backup_dirs(self, fleet_env):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit)
        _make_project(root, "alpha.bak-20260916", m, kit)
        assert [p.name for p in f.discover(root)] == ["alpha"]

    def test_skips_the_source_repo(self, fleet_env):
        f, m, kit, root = fleet_env
        proj = _make_project(root, "alpha", m, kit)
        assert f.discover(root, source=proj) == []

    def test_does_not_recurse(self, fleet_env):
        f, m, kit, root = fleet_env
        nested = root / "outer"
        nested.mkdir()
        _make_project(nested, "inner", m, kit)
        assert f.discover(root) == []

    def test_include_and_exclude_globs(self, fleet_env):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit)
        _make_project(root, "beta", m, kit)
        assert [p.name for p in f.discover(root, include=["a*"])] == ["alpha"]
        assert [p.name for p in f.discover(root, exclude=["a*"])] == ["beta"]


class TestVerbs:
    def test_list_prints_each_repo(self, fleet_env, capsys):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit)
        _make_project(root, "beta", m, kit)
        assert f.cmd_fleet(_ns(action="list", root=str(root))) == 0
        out = capsys.readouterr().out
        assert "alpha" in out and "beta" in out and "2 kitted project(s)" in out

    def test_empty_root_is_not_a_failure(self, fleet_env, capsys):
        f, m, kit, root = fleet_env
        assert f.cmd_fleet(_ns(action="list", root=str(root))) == 0
        assert "No kitted projects" in capsys.readouterr().out

    def test_verify_clean_fleet_passes(self, fleet_env):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit)
        assert f.cmd_fleet(_ns(action="verify", root=str(root))) == 0

    def test_verify_fails_on_planted_drift(self, fleet_env, capsys):
        f, m, kit, root = fleet_env
        # Untouched downstream (hash == manifest) but stale w.r.t. the kit source.
        _make_project(root, "alpha", m, kit, planner_text="# planner v1\n")
        rc = f.cmd_fleet(_ns(action="verify", root=str(root)))
        assert rc == 1
        assert "agents/planner.md" in capsys.readouterr().out

    def test_verify_does_not_count_an_installer_rendered_file_as_drift(self, fleet_env):
        """hooks/config.json is rewritten per project by install.sh, then recorded in the
        manifest -- it matches the manifest and never the kit. 14/14 real repos were
        flagged on exactly this file before the exemption existed."""
        f, m, kit, root = fleet_env
        proj = _make_project(root, "alpha", m, kit)
        (kit / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        (kit / ".claude" / "hooks" / "config.json").write_text('{"a": 1}\n')
        base = proj / ".claude"
        (base / "hooks").mkdir()
        (base / "hooks" / "config.json").write_text('{\n  "a": 1\n}\n')   # re-serialised
        manifest = json.loads((base / m.MANIFEST_NAME).read_text())
        manifest["files"]["hooks/config.json"] = m._sha256(base / "hooks" / "config.json")
        (base / m.MANIFEST_NAME).write_text(json.dumps(manifest))
        assert f.cmd_fleet(_ns(action="verify", root=str(root))) == 0

    def test_verify_allows_a_locally_modified_file(self, fleet_env):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit, planner_text="# mine\n",
                      manifest_matches=False)
        assert f.cmd_fleet(_ns(action="verify", root=str(root))) == 0

    def test_diff_reports_counts(self, fleet_env, capsys):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit, planner_text="# mine\n",
                      manifest_matches=False)
        assert f.cmd_fleet(_ns(action="diff", root=str(root))) == 0
        assert "locally modified: agents/planner.md" in capsys.readouterr().out

    def test_update_dry_run_writes_nothing_and_never_installs(self, fleet_env,
                                                              monkeypatch, capsys):
        f, m, kit, root = fleet_env
        proj = _make_project(root, "alpha", m, kit, planner_text="# planner v1\n")
        before = (proj / ".claude" / "agents" / "planner.md").read_text()
        called = []
        monkeypatch.setattr(m, "cmd_update", lambda args: called.append(args) or 0)
        rc = f.cmd_fleet(_ns(action="update", root=str(root), dry_run=True))
        assert rc == 0
        assert called == []
        assert (proj / ".claude" / "agents" / "planner.md").read_text() == before
        assert "would overwrite" in capsys.readouterr().out

    def test_update_reports_a_failing_repo(self, fleet_env, monkeypatch):
        f, m, kit, root = fleet_env
        _make_project(root, "alpha", m, kit)
        monkeypatch.setattr(m, "cmd_update", lambda args: 1)
        assert f.cmd_fleet(_ns(action="update", root=str(root))) == 1
