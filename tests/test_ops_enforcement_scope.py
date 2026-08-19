"""Behavioral tests for the repo-local Iron Law scope override and hook counting.

Two guards are under test, both by *running* the real artifact:

  * `.claude/hooks/ops-enforcement.sh` reclassifies paths listed in a project's
    tracked `.ops-source-globs` as SOURCE, so this repo's actual product -- the
    prompt corpus under `.claude/` -- stops being exempt from the Iron Law.
    The override is opt-in: a project without that file must behave EXACTLY as
    before (that regression is the most important thing here).
  * `scripts/gen-docs.py` counts python hooks too, so the published hook count
    is true now that `reflection-gate.py` ships.

Every hook run forces `ECC_HOOK_PROFILE` explicitly: the maintainer session
default is `minimal`, under which the hook short-circuits at line 1 of its body.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "ops-enforcement.sh"
LIB = REPO / ".claude" / "hooks" / "lib.sh"
GLOBS_FILE = REPO / ".ops-source-globs"


def _make_project(opted_in):
    """Build a throwaway git project that installs the hook.

    NOTE: the temp dir deliberately lives beside the repo, not under $TMPDIR.
    On macOS `tempfile` returns `/var/folders/...`, which the hook exempts as an
    OS scratch path -- every assertion would pass vacuously there.
    """
    root = Path(tempfile.mkdtemp(prefix=".ck-scope-", dir=str(REPO.parent)))
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / ".claude" / "operations" / "scripts").mkdir(parents=True)
    shutil.copy(LIB, root / ".claude" / "hooks" / "lib.sh")
    shutil.copy(HOOK, root / ".claude" / "hooks" / "ops-enforcement.sh")
    # The hook only enforces when the ops executor is present.
    (root / ".claude" / "operations" / "scripts" / "execute-json-ops.py").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    if opted_in:
        shutil.copy(GLOBS_FILE, root / ".ops-source-globs")
    return root


@pytest.fixture(scope="module")
def opted_project():
    root = _make_project(opted_in=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def user_project():
    root = _make_project(opted_in=False)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def run_hook(project, rel_or_abs, profile="standard", env_extra=None):
    """Run the hook from `project` with an Edit payload; return CompletedProcess."""
    target = str(rel_or_abs)
    if not os.path.isabs(target):
        target = str(Path(project) / target)
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": target}})
    env = dict(os.environ, ECC_HOOK_PROFILE=profile)
    env.pop("ECC_OPS_SOURCE_GLOBS", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(Path(project) / ".claude" / "hooks" / "ops-enforcement.sh")],
        input=payload, capture_output=True, text=True,
        cwd=str(project), env=env, timeout=30,
    )


class TestOptedInProjectTreatsClaudeAsSource:
    """With `.ops-source-globs` present, prompt assets are source, not config."""

    @pytest.mark.parametrize("rel", [
        ".claude/agents/planner.md",
        ".claude/agents/_shared/INVOCATION.md",
        ".claude/commands/plan.md",
        ".claude/skills/writing-plans/SKILL.md",
        ".claude/hooks/ops-enforcement.sh",
        ".claude/operations/scripts/execute-json-ops.py",
    ])
    def test_source_asset_is_blocked(self, opted_project, rel):
        p = run_hook(opted_project, rel)
        assert p.returncode == 2, f"{rel} was not blocked: rc={p.returncode} {p.stderr}"
        assert "repo-local source override" in p.stderr, p.stderr

    @pytest.mark.parametrize("rel", [
        ".claude/plans/plan-x.md",
        ".claude/plans/plan-x.ops.json",
        ".claude/reports/review/r.md",
        ".claude/knowledge/k.md",
        ".claude/backups/2026/x.md",
        ".claude/hooks/hooks.log",
        ".claude/settings.local.json",
    ])
    def test_workflow_artifacts_stay_writable(self, opted_project, rel):
        """The ops engine writes its own plans, records and backups -- narrowing
        these would deadlock the repo: no plan could be authored to unblock it."""
        p = run_hook(opted_project, rel)
        assert p.returncode == 0, f"{rel} must stay writable: {p.stderr}"

    @pytest.mark.parametrize("rel", ["README.md", "docs/GUIDE.md", "CHANGELOG.md"])
    def test_docs_outside_claude_remain_exempt(self, opted_project, rel):
        p = run_hook(opted_project, rel)
        assert p.returncode == 0, p.stderr

    def test_ordinary_source_still_blocked(self, opted_project):
        p = run_hook(opted_project, "src/pkg/mod.py")
        assert p.returncode == 2, p.stderr

    def test_os_scratchpad_still_exempt(self, opted_project):
        p = run_hook(opted_project, "/private/tmp/claude-501/scratch/x.py")
        assert p.returncode == 0, p.stderr

    @pytest.mark.parametrize("globs", [".claude/*", "*"])
    @pytest.mark.parametrize("rel", [
        ".claude/plans/plan-x.ops.json",
        ".claude/plans/plan-x.md",
        ".claude/backups/y.md",
        ".claude/reports/review/r.md",
        ".claude/knowledge/k.md",
        ".claude/hooks/hooks.log",
    ])
    def test_denylist_beats_an_over_broad_glob(self, opted_project, globs, rel):
        """Binds the never-source denylist ARM, not just the shipped globs.

        The shipped `.ops-source-globs` never matches these paths, so deleting the
        denylist arm entirely would leave the rest of the suite green. A maintainer
        who writes `.claude/*` (or `*`) into the marker must still be unable to
        deadlock the ops engine: it has to keep writing its own plans, backups and
        review records to unblock anything at all.
        """
        p = run_hook(opted_project, rel, env_extra={"ECC_OPS_SOURCE_GLOBS": globs})
        assert p.returncode == 0, f"{rel} deadlocked under globs={globs!r}: {p.stderr}"

    @pytest.mark.parametrize("globs", [".claude/*", "*"])
    def test_over_broad_glob_still_enforces_real_source(self, opted_project, globs):
        """The denylist must not turn into a blanket allow: ordinary source and the
        product corpus stay blocked under the same over-broad glob."""
        p = run_hook(opted_project, "src/pkg/mod.py", env_extra={"ECC_OPS_SOURCE_GLOBS": globs})
        assert p.returncode == 2, p.stderr
        p2 = run_hook(opted_project, ".claude/agents/planner.md",
                      env_extra={"ECC_OPS_SOURCE_GLOBS": globs})
        assert p2.returncode == 2, p2.stderr

    def test_minimal_profile_disables_the_override(self, opted_project):
        """Dormant under `minimal` BY DESIGN: the profile default is the owner's
        toggle, not this mechanism's business."""
        p = run_hook(opted_project, ".claude/agents/planner.md", profile="minimal")
        assert p.returncode == 0, p.stderr


class TestPlainUserProjectIsUnchanged:
    """The hook is a shipped artifact. In a user project `.claude/**` really is
    configuration and `.md` really is documentation -- nothing may change."""

    @pytest.mark.parametrize("rel", [
        ".claude/agents/planner.md",
        ".claude/settings.json",
        ".claude/hooks/ops-enforcement.sh",
        ".claude/commands/plan.md",
        "README.md",
        "docs/GUIDE.md",
    ])
    def test_config_and_docs_remain_editable(self, user_project, rel):
        p = run_hook(user_project, rel)
        assert p.returncode == 0, f"user-project regression on {rel}: {p.stderr}"

    def test_source_is_still_blocked(self, user_project):
        p = run_hook(user_project, "src/pkg/mod.py")
        assert p.returncode == 2, p.stderr

    def test_minimal_profile_allows_source(self, user_project):
        p = run_hook(user_project, "src/pkg/mod.py", profile="minimal")
        assert p.returncode == 0, p.stderr

    def test_malformed_payload_still_fails_closed(self, user_project):
        proc = subprocess.run(
            ["bash", str(Path(user_project) / ".claude" / "hooks" / "ops-enforcement.sh")],
            input="{not valid json", capture_output=True, text=True,
            cwd=str(user_project), env=dict(os.environ, ECC_HOOK_PROFILE="standard"),
            timeout=30,
        )
        assert proc.returncode == 2, proc.stderr

    def test_env_var_can_opt_in_without_the_file(self, user_project):
        """`ECC_OPS_SOURCE_GLOBS` is the advanced/test entry point; unset by
        default, so it cannot affect an ordinary install."""
        p = run_hook(user_project, ".claude/agents/planner.md",
                     env_extra={"ECC_OPS_SOURCE_GLOBS": ".claude/agents/*"})
        assert p.returncode == 2, p.stderr
        p2 = run_hook(user_project, ".claude/commands/plan.md",
                      env_extra={"ECC_OPS_SOURCE_GLOBS": ".claude/agents/*"})
        assert p2.returncode == 0, p2.stderr


class TestOpsSourceGlobsManifest:
    def test_file_is_not_git_ignored(self):
        """It must travel with a fresh clone -- unlike settings.local.json, which
        is gitignored and per-developer, so a clone would silently stop dogfooding."""
        out = subprocess.run(["git", "check-ignore", "-q", ".ops-source-globs"],
                             cwd=str(REPO), capture_output=True, text=True)
        assert out.returncode != 0, ".ops-source-globs must not be gitignored"
        assert GLOBS_FILE.exists()

    def test_lists_the_product_directories(self):
        pats = {ln.strip() for ln in GLOBS_FILE.read_text().splitlines()
                if ln.strip() and not ln.strip().startswith("#")}
        for expected in (".claude/agents/*", ".claude/commands/*", ".claude/skills/*",
                         ".claude/hooks/*", ".claude/operations/*"):
            assert expected in pats, f"missing source glob {expected}"

    def test_never_claims_workflow_artifact_dirs(self):
        text = GLOBS_FILE.read_text()
        for forbidden in ("plans", "reports", "knowledge", "backups"):
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    assert forbidden not in stripped, \
                        f"{stripped!r} would deadlock the ops engine"


def _gen_docs():
    spec = importlib.util.spec_from_file_location(
        "gen_docs_under_test", REPO / "scripts" / "gen-docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHookCountIsTrue:
    def test_python_hooks_are_counted(self):
        g = _gen_docs()
        counted = {p.name for p in g._hook_files() if not g._is_helper_module(p, g._hook_files())}
        assert "reflection-gate.py" in counted, "python hooks must count"
        assert "ops-enforcement.sh" in counted
        assert g.count_hooks() == len(counted)

    def test_sourced_and_imported_helpers_are_not_hooks(self):
        g = _gen_docs()
        files = g._hook_files()
        by_name = {p.name: p for p in files}
        assert g._is_helper_module(by_name["lib.sh"], files), "lib.sh is sourced, not a hook"
        assert g._is_helper_module(by_name["reflection.py"], files), \
            "reflection.py is imported by reflection-gate.py, not wired as a hook"

    def test_every_wired_hook_is_counted(self):
        g = _gen_docs()
        settings = (REPO / ".claude" / "settings.json").read_text()
        wired = set(re.findall(r"([A-Za-z0-9_.-]+\.(?:sh|py))", settings))
        files = g._hook_files()
        counted = {p.name for p in files if not g._is_helper_module(p, files)}
        assert wired - counted == set(), f"wired but uncounted: {sorted(wired - counted)}"

    def test_docs_drift_gate_passes(self):
        proc = subprocess.run([sys.executable, str(REPO / "scripts" / "gen-docs.py"), "--check"],
                              cwd=str(REPO), capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr
