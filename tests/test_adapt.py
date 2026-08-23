"""Behavioural coverage for `ck adapt`'s ownership rules and marker parser.

Every test drives the real module against real files in a temp tree. The parser
tests use the REAL marker lines from this repo's own `CLAUDE.md` as fixtures where
the plan requires it, because a writer and parser sharing a constant can agree with
each other while both disagreeing with the convention on disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from claudekit import adapt  # noqa: E402

#: The real dialect on disk, quoted from CLAUDE.md. If the convention changes, these
#: fixtures fail rather than the writer silently drifting away from it.
REAL_START = "<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 START -->"
REAL_END = "<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 END -->"

#: The OTHER dialect, which all eleven templates/*/CLAUDE.md use and the installer
#: renders into a target. Adapt must ignore it completely.
TEMPLATE_START = "<!-- CLAUDEKIT:PARALLEL-AGENTS-POLICY v1 -->"
TEMPLATE_END = "<!-- /CLAUDEKIT:PARALLEL-AGENTS-POLICY -->"


def test_the_real_repo_markers_are_still_the_dialect_we_parse():
    """Bind the fixtures to the file, so a convention change is loud."""
    text = open(os.path.join(REPO_ROOT, "CLAUDE.md"), encoding="utf-8").read()
    assert REAL_START in text, "CLAUDE.md no longer carries the START form we parse"
    assert REAL_END in text, "CLAUDE.md no longer carries the END form we parse"
    region, fenced = adapt.find_region(text, "TOKEN-MODEL-POLICY")
    assert region is not None, "the parser cannot read the repo's own real region"
    assert region.version == 3
    assert fenced == []


def test_the_writer_emits_the_dialect_on_disk_byte_for_byte():
    """Literal expected bytes — a shared constant cannot satisfy this."""
    block = adapt.render_region("body", region_id="TOKEN-MODEL-POLICY", version=3)
    assert block[0] == REAL_START
    assert block[-1] == REAL_END


class TestTemplateDialectIsLeftAlone:
    """Without this, adapt refuses on every freshly installed project."""

    def test_a_template_region_is_not_a_region(self):
        text = "\n".join(["intro", TEMPLATE_START, "policy", TEMPLATE_END, "outro"])
        region, fenced = adapt.find_region(text, "PARALLEL-AGENTS-POLICY")
        assert region is None
        assert fenced == []

    def test_a_template_region_survives_a_write_byte_for_byte(self):
        text = "\n".join(["intro", TEMPLATE_START, "policy", TEMPLATE_END, ""])
        new_text, action, _prev = adapt.apply_region(text, "\nowned\n")
        assert action == "appended"
        assert TEMPLATE_START in new_text and TEMPLATE_END in new_text
        assert new_text.startswith("intro\n" + TEMPLATE_START)


class TestMalformedMarkersFailClosed:
    """Four shapes, each a refusal that leaves the file untouched."""

    @pytest.mark.parametrize("lines,fragment", [
        ([f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->", "body"], "never closed"),
        ([f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 END -->"], "no START"),
        ([f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->",
          f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->",
          f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 END -->"], "second START"),
        ([f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->",
          f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 END -->",
          f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->",
          f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 END -->"], "more than one region"),
    ])
    def test_shape_refuses(self, lines, fragment):
        with pytest.raises(adapt.AdaptError) as excinfo:
            adapt.find_region("\n".join(lines))
        assert fragment in str(excinfo.value)

    def test_a_refusal_leaves_the_file_byte_identical(self, tmp_path):
        path = tmp_path / "doc.md"
        original = f"keep me\n<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->\nbody\n"
        path.write_text(original, encoding="utf-8")
        with pytest.raises(adapt.AdaptError):
            adapt.apply_region(path.read_text(encoding="utf-8"), "new")
        assert path.read_text(encoding="utf-8") == original


class TestVersionHandling:
    def test_a_versionless_legacy_region_is_recognised_not_duplicated(self):
        """The optional-version rule, which prose alone left unproven.

        A legacy region written without `vN` must be RECOGNISED, or it collects a
        second appended region on every run — the idempotence failure the concession
        exists to prevent.
        """
        text = "\n".join([f"<!-- CLAUDEKIT:{adapt.REGION_ID} START -->", "old",
                          f"<!-- CLAUDEKIT:{adapt.REGION_ID} END -->", ""])
        region, _fenced = adapt.find_region(text)
        assert region is not None, "a version-less region was not recognised"
        assert region.version is None

        once, action, previous = adapt.apply_region(text, "\nnew\n")
        assert action == "replaced"
        assert previous is None
        twice, action2, _p2 = adapt.apply_region(once, "\nnew\n")
        assert action2 == "replaced"
        assert twice == once, "a second run changed the file"
        assert once.count(f"CLAUDEKIT:{adapt.REGION_ID}") == 2, "a region was duplicated"

    def test_a_stale_version_is_reported_not_silently_replaced(self):
        text = "\n".join([f"<!-- CLAUDEKIT:{adapt.REGION_ID} v2 START -->", "old",
                          f"<!-- CLAUDEKIT:{adapt.REGION_ID} v2 END -->", ""])
        _new, action, previous = adapt.apply_region(text, "\nnew\n", version=3)
        assert action == "replaced"
        assert previous == 2, "the previous version was not surfaced to the caller"


class TestIdempotence:
    """Proven twice, because a CRLF file fails in a way an LF file cannot show."""

    def _twice(self, text):
        once, _a, _p = adapt.apply_region(text, "\nowned\n")
        twice, _a2, _p2 = adapt.apply_region(once, "\nowned\n")
        return once, twice

    def test_idempotent_on_an_lf_file(self):
        once, twice = self._twice("intro\n")
        assert once == twice
        assert once.count(f"CLAUDEKIT:{adapt.REGION_ID}") == 2

    def test_idempotent_on_a_crlf_file_and_endings_are_preserved(self):
        once, twice = self._twice("intro\r\nmore\r\n")
        assert once == twice, "a second run appended to a CRLF file"
        assert once.count(f"CLAUDEKIT:{adapt.REGION_ID}") == 2, "region duplicated"
        assert "\r\n" in once
        assert not [ln for ln in once.split("\r\n") if ln.endswith("\r")], \
            "the file acquired mixed line endings"


class TestAppendNeverRewrites:
    def test_bytes_before_the_region_are_preserved_exactly(self):
        original = "line one\n\n\nline two with trailing spaces   \n"
        new_text, action, _p = adapt.apply_region(original, "\nowned\n")
        assert action == "appended"
        assert new_text.startswith(original), \
            "the user's bytes were tidied rather than preserved"


class TestFencedMarkersAreSkipped:
    """Skipped, not refused: refusing would brick the verb for that project."""

    def test_a_fenced_start_is_not_a_region_and_is_reported(self):
        text = "\n".join(["docs:", "```", f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->",
                          "```", "after", ""])
        region, fenced = adapt.find_region(text)
        assert region is None, "a fenced marker was treated as a real region"
        assert fenced == [3], "the fenced line was not reported by line number"

    def test_a_fenced_marker_survives_and_a_real_region_is_appended_below(self):
        text = "\n".join(["```", f"<!-- CLAUDEKIT:{adapt.REGION_ID} v1 START -->",
                          "```", ""])
        new_text, action, _p = adapt.apply_region(text, "\nowned\n")
        assert action == "appended"
        assert new_text.startswith(text.rstrip("\n"))


def test_non_utf8_prose_fails_closed(tmp_path):
    path = tmp_path / "doc.md"
    path.write_bytes(b"valid\n\xff\xfe not utf8\n")
    with pytest.raises(adapt.AdaptError) as excinfo:
        adapt.read_text_strict(path)
    assert "not valid UTF-8" in str(excinfo.value)


class TestAtomicWrite:
    def test_a_failed_replace_leaves_the_original_and_no_tmp_residue(self, tmp_path,
                                                                    monkeypatch):
        """Proven through the real seam, not a described interruption."""
        path = tmp_path / "doc.md"
        path.write_text("original\n", encoding="utf-8")

        def boom(*_a, **_k):
            raise OSError("replace refused")

        monkeypatch.setattr(adapt.os, "replace", boom)
        with pytest.raises(OSError):
            adapt.write_atomic(path, "replacement\n")
        assert path.read_text(encoding="utf-8") == "original\n"
        residue = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert residue == [], f"temp residue survived: {residue}"


class TestOwnershipIsAComplement:
    def test_class1_is_every_receipted_key_minus_the_receipted_class2_members(self):
        manifest = {"files": {
            "agents/a.md": "h1",
            "settings.json": "h2",
            "local/CONSTITUTION.md": "h3",
            "profiles/base.json": "h4",
            "local/CLAUDE.project.md": "h5",
            "hooks/config.json": "h6",
        }}
        own = adapt.classify_ownership(manifest)
        assert own.class1 == ("agents/a.md", "local/CONSTITUTION.md",
                             "profiles/base.json", "settings.json")
        assert own.class2_receipted == ("hooks/config.json",
                                        "local/CLAUDE.project.md")

    def test_a_receipted_file_is_never_in_neither_class(self):
        """The hole the by-name boundary left: receipted but unclassified."""
        manifest = {"files": {name: "h" for name in (
            "settings.json", "local/CONSTITUTION.md", "profiles/base.json",
            "knowledge/issues/README.md", "local/CLAUDE.project.md",
            "hooks/config.json")}}
        own = adapt.classify_ownership(manifest)
        assert set(own.class1) | set(own.class2_receipted) == set(manifest["files"])

    @pytest.mark.parametrize("manifest", [None, {}, {"files": []}])
    def test_no_usable_receipt_refuses(self, manifest):
        with pytest.raises(adapt.AdaptError) as excinfo:
            adapt.classify_ownership(manifest)
        assert "provenance" in str(excinfo.value)


class TestClass1PreFlight:
    def test_a_modified_intended_target_refuses_the_whole_run(self):
        msg = adapt.refuse_on_modified(["agents/a.md"], ["agents/a.md", "settings.json"])
        assert msg is not None and "agents/a.md" in msg

    def test_a_modified_file_adapt_does_not_touch_does_not_refuse(self):
        assert adapt.refuse_on_modified(["skills/x/SKILL.md"], ["settings.json"]) is None


class TestConfigJsonKeySubtree:
    def test_unknown_keys_survive_byte_for_byte(self):
        original = json.dumps({
            "project": {"test_cmd": "mine", "custom": "keep me"},
            "other": {"nested": [1, 2]},
        }, indent=2) + "\n"
        out, kept = adapt.apply_commands(original, {"test_cmd": "pytest -q"})
        parsed = json.loads(out)
        assert parsed["project"]["test_cmd"] == "pytest -q"
        assert parsed["project"]["custom"] == "keep me", "a user key was dropped"
        assert parsed["other"] == {"nested": [1, 2]}
        assert kept == []

    def test_an_absent_command_key_is_written_empty_not_guessed(self):
        out, kept = adapt.apply_commands("{}", {"test_cmd": "pytest -q"})
        project = json.loads(out)["project"]
        assert project["test_cmd"] == "pytest -q"
        assert project["build_cmd"] == "", \
            "an unresolved command must be blank, never ClaudeKit's own"
        assert kept == [], "nothing was there to keep"

    def test_an_existing_value_is_KEPT_when_nothing_evidences_one(self):
        """The inverse, and the one that matters: `install.sh:495-497` writes all
        four keys EMPTY, so a non-empty value on an adopted tree is the USER's.
        Blanking it destroyed their configuration on every run -- and
        `project-adaptation` Phase 2 tells them to set exactly these keys, so the
        documented workflow was undone by the next `ck adapt`."""
        original = json.dumps({"project": {"build_cmd": "make release",
                                           "test_cmd": ""}}, indent=2)
        out, kept = adapt.apply_commands(original, {"test_cmd": "pytest -q"})
        project = json.loads(out)["project"]
        assert project["build_cmd"] == "make release", \
            "a hand-set command was destroyed by a run that could not evidence one"
        assert project["test_cmd"] == "pytest -q", "an evidenced key must overwrite"
        assert kept == ["build_cmd"], (
            "the kept key must be NAMED, or the report cannot say what it left alone")

    def test_invalid_json_refuses_and_writes_nothing(self):
        with pytest.raises(adapt.AdaptError) as excinfo:
            adapt.apply_commands("{not json", {})
        assert "refusing to write" in str(excinfo.value)


class TestDetectionNeverExecutes:
    """Two sentinels, not one: a Makefile target and a workflow `run:` string."""

    def test_neither_a_makefile_target_nor_a_workflow_run_string_executes(self, tmp_path):
        make_sentinel = tmp_path / "MAKE_RAN"
        wf_sentinel = tmp_path / "WORKFLOW_RAN"
        (tmp_path / "Makefile").write_text(
            "test:\n\ttouch %s\n" % make_sentinel, encoding="utf-8")
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "jobs:\n  t:\n    steps:\n      - run: touch %s\n" % wf_sentinel,
            encoding="utf-8")

        found = adapt.detect(tmp_path)
        assert "Makefile" in found.sources
        assert ".github/workflows" in found.sources
        assert not make_sentinel.exists(), "detection executed a Makefile target"
        assert not wf_sentinel.exists(), "detection executed a workflow run: string"

    def test_an_unknown_stack_reports_none_rather_than_guessing(self, tmp_path):
        (tmp_path / "README.md").write_text("nothing familiar\n", encoding="utf-8")
        assert adapt.detect(tmp_path).stack is None

    def test_a_python_project_is_detected_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        assert adapt.detect(tmp_path).stack == "python"

    def test_no_git_is_reported_not_refused(self, tmp_path):
        assert adapt.detect(tmp_path).has_git is False


class TestFreshMeansClaudeDirAbsent:
    def test_a_receiptless_tree_with_a_claude_dir_is_not_fresh(self, tmp_path):
        """The trap: routing this to the installer moves the user's tree aside."""
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        assert adapt.is_fresh(tmp_path) is False

    def test_an_empty_tree_is_fresh(self, tmp_path):
        assert adapt.is_fresh(tmp_path) is True


class TestReportHonesty:
    def test_a_skip_is_not_a_failure(self, tmp_path):
        report = adapt.Report(tmp_path, "adopted")
        report.step("mcp", adapt.SKIPPED, "no profiles installed; budget unbounded")
        assert report.failed is False
        assert "skipped" in report.render()

    def test_a_failed_step_makes_the_run_fail(self, tmp_path):
        report = adapt.Report(tmp_path, "adopted")
        report.step("commands", adapt.FAILED, "config.json unparseable")
        assert report.failed is True
        assert "FAILED" in report.render()

    def test_a_skip_is_never_rendered_as_complete(self, tmp_path):
        report = adapt.Report(tmp_path, "adopted")
        report.step("mcp", adapt.SKIPPED, "budget unbounded")
        rendered = report.render()
        assert "adapt complete" not in rendered.lower()


class TestUninstallNeverRemovesAPartiallyOwnedFile:
    """Proof 7. The --force case is the one a naive fix misses.

    Under --force, cli/main.py builds `removable` from every LISTED path that
    exists, so a per-entry skip placed below that branch is bypassed entirely.
    `NEVER_MANAGED` is safe from --force only because it is never listed at all;
    these files ARE listed, so they must be dropped from `listed` AND from the
    classification before anything downstream widens the set again.
    """

    @staticmethod
    def _tree(tmp_path):
        import hashlib
        base = tmp_path / ".claude"
        (base / "local").mkdir(parents=True)
        (base / "hooks").mkdir(parents=True)
        (base / "agents").mkdir(parents=True)
        files = {}
        for rel, body in (("agents/a.md", "kit asset\n"),
                          ("local/CLAUDE.project.md", "user prose\n"),
                          ("hooks/config.json", '{"project": {}}\n')):
            path = base / rel
            path.write_text(body, encoding="utf-8")
            files[rel] = hashlib.sha256(body.encode()).hexdigest()
        (base / ".claudekit-manifest.json").write_text(
            json.dumps({"version": "test", "files": files}), encoding="utf-8")
        return base

    @pytest.mark.parametrize("extra", [[], ["--force"]])
    def test_partially_owned_files_survive(self, tmp_path, extra):
        import subprocess
        base = self._tree(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "uninstall",
             str(tmp_path), "--yes"] + extra,
            capture_output=True, text=True, cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "src")))
        combined = result.stdout + result.stderr
        for rel in adapt.PARTIAL_OWNED_RELS:
            assert (base / rel).exists(), (
                "%s was deleted by `ck uninstall %s` — the kit owns only part of it"
                % (rel, " ".join(extra) or "(no flags)")) + "\n" + combined


# =====================================================================  CLI PROOFS
#
# The plan says twenty-one times that "every proof drives the real CLI against a
# real temp project; structural assertions do not count." Review measured that only
# ONE of the twenty-one did, and that is exactly how `apply_commands` -- a function
# NOTHING called -- passed three green unit tests while the verb's headline value did
# not exist. Everything below drives `python -m claudekit.cli.main` as a subprocess
# against a tree a real `ck init` produced, and asserts on the process's exit code
# and printed report, because those are the only two things a user sees.

#: ECC_HOOK_PROFILE is forced rather than inherited: the caller's shell sets it in
#: this repo, so an inherited value made `posture=` vary between developer machines
#: and CI.
CLI_ENV = dict(os.environ,
               PYTHONPATH=os.path.join(REPO_ROOT, "src"),
               ECC_HOOK_PROFILE="standard")


def ck(*argv):
    """Run the real CLI. Exit code measured WITHOUT a pipe, deliberately."""
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main"] + list(argv),
                          capture_output=True, text=True, cwd=REPO_ROOT, env=CLI_ENV)


def out(proc):
    return proc.stdout + proc.stderr


#: Excluded from the idempotence digest because each is regenerated or appended on
#: every run by something OTHER than adapt: `installed_at` in the receipt
#: (install.sh:637), the hook log, the per-run backup directory, the operations
#: engine's state, and the lock directory. A naive whole-tree hash always differs, so
#: an idempotence proof written against one would pass or fail for the wrong reason.
_VOLATILE_PARTS = ("backups", "locks", "state")


def tree_digest(root):
    """sha256 per file, keyed by relative path, skipping the volatile set."""
    root = Path(root)
    digest = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames
                       if d not in _VOLATILE_PARTS and not d.startswith(".claude.bak-")]
        for name in filenames:
            if name in ("hooks.log", ".claudekit-manifest.json") or name.endswith(".pyc"):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            digest[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


@pytest.fixture(scope="session")
def pristine_kit(tmp_path_factory):
    """ONE real `ck init`, copied per test. Installing per test costs ~1.6s each."""
    root = tmp_path_factory.mktemp("pristine") / "kit"
    root.mkdir()
    proc = ck("init", str(root), "--yes")
    assert proc.returncode == 0, "the fixture's own `ck init` failed\n" + out(proc)
    assert (root / ".claude" / ".claudekit-manifest.json").is_file(), out(proc)
    return root


@pytest.fixture
def project(pristine_kit, tmp_path):
    dest = tmp_path / "project"
    shutil.copytree(str(pristine_kit), str(dest), symlinks=True)
    return dest


def doc_of(project):
    return project / ".claude" / "local" / "CLAUDE.project.md"


def config_of(project):
    return project / ".claude" / "hooks" / "config.json"


def make_python(project):
    """Evidence a python stack, so the `python` stack profile resolves."""
    (project / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n[tool.ruff]\n", encoding="utf-8")


class TestTheVerbActuallyDoesTheWork:
    """F5. The headline value: `apply_commands` was never called from anywhere.

    `grep -rn apply_commands src tests` found a definition and three unit tests and
    nothing else, so on a real install the `project` subtree still held install.sh's
    values verbatim while the report printed "OK -- every step either completed or is
    reported as skipped". These assert the observable effects, one per wired step.
    """

    def test_the_four_command_keys_reach_hooks_config_json(self, project):
        make_python(project)
        before = json.loads(config_of(project).read_text(encoding="utf-8"))
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        after = json.loads(config_of(project).read_text(encoding="utf-8"))
        for key in adapt.COMMAND_KEYS:
            assert key in after["project"], out(proc)
        assert after["project"]["test_cmd"], (
            "adapt reported success and wrote no test command\n" + out(proc))
        assert after["project"] != before["project"] or before["project"] == after["project"]

    def test_commands_are_derived_ci_first_with_their_provenance_named(self, project):
        workflows = project / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "jobs:\n  t:\n    steps:\n      - run: pytest -q --ci\n", encoding="utf-8")
        (project / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert config["project"]["test_cmd"] == "pytest -q --ci", (
            "CI must beat the Makefile\n" + out(proc))
        assert ".github/workflows" in proc.stdout, out(proc)

    def test_the_posture_profile_is_resolved_not_written_as_unresolved(self, project):
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        body = doc_of(project).read_text(encoding="utf-8")
        assert "- Posture profile: unresolved" not in body, (
            "the region still says 'unresolved', so nothing resolved a profile\n" + body)
        assert "- Posture profile: standard" in body, body

    def test_every_step_appears_in_the_report(self, project):
        make_python(project)
        proc = ck("adapt", str(project))
        for step in ("detect", "ownership", "pre-flight", "profile", "commands",
                     "hooks/config.json", "mcp", "memory", "claude.project.md",
                     "re-stamp"):
            assert step in proc.stdout, (
                "step %r is missing entirely, so the report cannot be read as "
                "complete" % step) + "\n" + out(proc)

    def test_the_memory_step_records_the_decision_once(self, project):
        first = ck("adapt", str(project))
        second = ck("adapt", str(project))
        assert "memory" in first.stdout and "memory" in second.stdout
        assert "recorded the adapt decision" in first.stdout, out(first)
        assert "already recorded" in second.stdout, out(second)

    def test_the_mcp_step_quotes_a_real_budget(self, project):
        make_python(project)
        proc = ck("adapt", str(project))
        assert "budget 'python'" in proc.stdout, out(proc)
        assert "/3 server(s)" in proc.stdout and "/40 tool(s)" in proc.stdout, out(proc)


class TestUnbalancedFenceDoesNotAppendForever:
    """F1. `in_fence = not in_fence` desynchronises on ONE unmatched fence.

    Measured through the CLI before the fix: 1 -> 2 -> 3 regions across three runs,
    because the region adapt had just written was itself classified "fenced". No
    shipped test used an unbalanced fence, which is precisely why it got through.
    """

    @pytest.mark.parametrize("planted", [
        "\n```\nan unclosed fence\n",
        "\n    ```\nfour spaces is literal text, not a fence\n",
        "\n~~~\nan unclosed tilde fence\n",
    ])
    def test_three_runs_leave_exactly_one_region(self, project, planted):
        doc = doc_of(project)
        doc.write_text(doc.read_text(encoding="utf-8") + planted, encoding="utf-8")
        for _ in range(3):
            proc = ck("adapt", str(project))
            assert proc.returncode == 0, out(proc)
        body = doc.read_text(encoding="utf-8")
        assert body.count("CLAUDEKIT:PROJECT-ADAPT v1 START -->") == 1, (
            "a new region was appended on each run\n" + body)


class TestOutsideTheRegionIsNeverRewritten:
    """F2. `splitlines()` + `newline.join()` rewrote EVERY non-conforming line.

    The contract is "outside is the user's and is never touched", and a mixed-ending
    file broke it on the append path as well as the replace path. The shipped tests
    used pure LF and pure CRLF only, so neither could see it.
    """

    MIXED = "lf line\ncrlf line\r\nlf again\n"

    def test_mixed_endings_outside_the_region_survive_byte_for_byte(self, project):
        doc = doc_of(project)
        doc.write_bytes(self.MIXED.encode("utf-8"))
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        body = doc.read_bytes().decode("utf-8")
        assert body.startswith(self.MIXED), (
            "the user's bytes before the region were rewritten\n%r" % body[:120])

    def test_mixed_endings_survive_a_replace_too(self, project):
        doc = doc_of(project)
        doc.write_bytes(self.MIXED.encode("utf-8"))
        assert ck("adapt", str(project)).returncode == 0
        assert ck("adapt", str(project)).returncode == 0
        body = doc.read_bytes().decode("utf-8")
        assert body.startswith(self.MIXED), (
            "the replace path rewrote the user's bytes\n%r" % body[:120])


class TestIdempotenceThroughTheCLI:
    """Proofs 1 and 3, driven by the CLI rather than by the module."""

    def test_the_second_run_changes_nothing(self, project):
        make_python(project)
        assert ck("adapt", str(project)).returncode == 0
        before = tree_digest(project)
        assert ck("adapt", str(project)).returncode == 0
        assert tree_digest(project) == before

    def test_a_crlf_project_doc_is_idempotent(self, project):
        doc = doc_of(project)
        doc.write_bytes("# heading\r\n\r\nuser prose\r\n".encode("utf-8"))
        assert ck("adapt", str(project)).returncode == 0
        first = doc.read_bytes()
        assert ck("adapt", str(project)).returncode == 0
        assert doc.read_bytes() == first
        assert first.count(b"CLAUDEKIT:PROJECT-ADAPT v1 START -->") == 1

    def test_a_versionless_legacy_region_is_rewritten_in_place(self, project):
        doc = doc_of(project)
        doc.write_text(
            "user prose\n<!-- CLAUDEKIT:PROJECT-ADAPT START -->\nstale\n"
            "<!-- CLAUDEKIT:PROJECT-ADAPT END -->\n", encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert "region present, version absent" in proc.stdout, out(proc)
        assert ck("adapt", str(project)).returncode == 0
        body = doc.read_text(encoding="utf-8")
        assert body.count("CLAUDEKIT:PROJECT-ADAPT") == 2, body
        assert body.startswith("user prose\n"), body


class TestClass1RefusalWritesNothing:
    """Proof 5, and proof 19's exit-code half."""

    def test_a_modified_kit_asset_refuses_and_the_tree_is_unchanged(self, project):
        victim = project / ".claude" / "agents" / "planner.md"
        assert victim.is_file()
        victim.write_text(victim.read_text(encoding="utf-8") + "\nedited\n",
                          encoding="utf-8")
        before = tree_digest(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "refusing" in proc.stdout, out(proc)
        assert "agents/planner.md" in proc.stdout, out(proc)
        assert tree_digest(project) == before, "the refusal wrote something"
        assert "FAILED" in proc.stdout, out(proc)

    def test_a_missing_receipt_fails_rather_than_licensing_a_write(self, project):
        (project / ".claude" / ".claudekit-manifest.json").unlink()
        before = tree_digest(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "no usable install receipt" in proc.stdout, out(proc)
        assert tree_digest(project) == before

    def test_a_skip_exits_zero_and_is_not_a_failure(self, tmp_path):
        bare = tmp_path / "bare"
        bare.mkdir()
        proc = ck("adapt", str(bare))
        assert proc.returncode == 0, out(proc)
        assert "skipped" in proc.stdout and "FAILED" not in proc.stdout, out(proc)


class TestNeverManagedSurvivesAdapt:
    """Proof 14 -- the plan calls this "the single highest-value test here", and it
    had no test at all. The exact 17-project regression at install.sh:604-609.

    Satisfiable only because decision (A) is settled: with the installer unreachable
    on an adopted tree there is no `mv .claude .claude.bak-*`, so `hooks.log` is
    never relocated.
    """

    def test_settings_local_and_hooks_log_are_byte_identical_after_adapt(self, project):
        base = project / ".claude"
        local = base / "settings.local.json"
        log = base / "hooks" / "hooks.log"
        local.write_text('{"env": {"MINE": "1"}}\n', encoding="utf-8")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("a log line the user cares about\n", encoding="utf-8")
        expected = (local.read_bytes(), log.read_bytes())
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert local.read_bytes() == expected[0], "settings.local.json was rewritten"
        assert log.read_bytes() == expected[1], "hooks.log was rewritten or relocated"
        assert not list(project.glob(".claude.bak-*")), (
            "adapt reached the installer's swap\n" + out(proc))


class TestHandTunedConfigIsNotClobbered:
    """Proof 6. The failure the by-name ownership boundary would have shipped."""

    def test_unowned_keys_survive_and_the_second_run_does_not_refuse(self, project):
        make_python(project)
        assert ck("adapt", str(project)).returncode == 0
        config = config_of(project)
        doc = json.loads(config.read_text(encoding="utf-8"))
        doc["project"]["test_cmd"] = "my own test command"
        doc["project"]["a_key_adapt_does_not_own"] = "keep me"
        doc["my_own_section"] = {"nested": [1, 2, 3]}
        config.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, (
            "a hand-tuned Class 2 file must not refuse the run\n" + out(proc))
        after = json.loads(config.read_text(encoding="utf-8"))
        assert after["my_own_section"] == {"nested": [1, 2, 3]}
        assert after["project"]["a_key_adapt_does_not_own"] == "keep me"


class TestAdaptThenUninstall:
    """F4. Without the re-stamp, one successful adapt made a previously-working
    `ck uninstall` exit 1, blocked by a file uninstall had already declared KEPT."""

    def test_uninstall_still_succeeds_after_adapt(self, project):
        assert ck("adapt", str(project)).returncode == 0
        proc = ck("uninstall", str(project), "--yes")
        assert proc.returncode == 0, (
            "adapt broke uninstall: it is blocked by a file it declares KEPT\n"
            + out(proc))
        assert "partially-owned file(s) KEPT" in out(proc), out(proc)

    def test_the_receipt_survives_and_a_second_uninstall_is_not_lost(self, project):
        """F3. `kept = modified & exists` left unchanged survivors receipt-less."""
        assert ck("uninstall", str(project), "--yes").returncode == 0
        manifest = project / ".claude" / ".claudekit-manifest.json"
        assert manifest.is_file(), (
            "the receipt was unlinked while its files were still on disk, so "
            "`ck adapt` refuses forever and `ck init` routes into the destructive "
            "installer swap")
        listed = sorted(json.loads(manifest.read_text(encoding="utf-8"))["files"])
        assert listed == sorted(adapt.PARTIAL_OWNED_RELS), listed
        for rel in adapt.PARTIAL_OWNED_RELS:
            assert (project / ".claude" / rel).exists()
        again = ck("uninstall", str(project), "--yes")
        assert again.returncode == 0, out(again)
        assert "Nothing to uninstall" not in out(again), out(again)

    @pytest.mark.parametrize("extra", [[], ["--force"], ["--keep-modified"]])
    def test_no_uninstall_path_orphans_a_partially_owned_file(self, project, extra):
        assert ck("adapt", str(project)).returncode == 0
        proc = ck(*(["uninstall", str(project), "--yes"] + extra))
        assert proc.returncode == 0, out(proc)
        manifest = project / ".claude" / ".claudekit-manifest.json"
        for rel in adapt.PARTIAL_OWNED_RELS:
            assert (project / ".claude" / rel).exists(), rel + "\n" + out(proc)
        assert manifest.is_file(), (
            "%s: survivors on disk with no receipt\n" % (" ".join(extra) or "(no flags)")
            + out(proc))


class TestReportContractThroughTheCLI:
    """Proofs 10(c), 12, 18, 19, 20 -- each asserted on the printed report."""

    def test_a_fenced_marker_is_named_by_file_and_line(self, project):
        doc = doc_of(project)
        doc.write_text(
            "prose\n\n```\n<!-- CLAUDEKIT:PROJECT-ADAPT v1 START -->\nquoted\n"
            "<!-- CLAUDEKIT:PROJECT-ADAPT v1 END -->\n```\n\nmore prose\n",
            encoding="utf-8")
        before = doc.read_text(encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert "fenced marker(s) recognised and ignored at" in proc.stdout, out(proc)
        assert "%s:4" % doc in proc.stdout, out(proc)
        assert before in doc.read_text(encoding="utf-8"), "the fenced bytes changed"

    def test_non_utf8_prose_fails_closed_and_writes_nothing(self, project):
        doc = doc_of(project)
        doc.write_bytes(b"valid\n\xff\xfe not utf-8\n")
        before = doc.read_bytes()
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "not valid UTF-8" in proc.stdout, out(proc)
        assert doc.read_bytes() == before

    def test_an_unknown_stack_falls_back_and_says_so(self, project):
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert "no stack profile matched; MCP budget unbounded" in proc.stdout, out(proc)
        assert "wrote no build/test commands" in proc.stdout, out(proc)

    def test_no_git_prints_the_exact_line_and_still_writes_a_receipt(self, project):
        assert not (project / ".git").exists()
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert ("note: no git repository: there is no VCS safety net for these writes"
                in proc.stdout), out(proc)
        manifest = project / ".claude" / ".claudekit-manifest.json"
        assert manifest.is_file() and manifest.stat().st_size > 0

    def test_an_invalid_config_json_fails_and_leaves_the_users_bytes(self, project):
        config = config_of(project)
        config.write_text("{ this is not json", encoding="utf-8")
        before = config.read_bytes()
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "not valid JSON" in proc.stdout, out(proc)
        assert "no pristine source to blank from" in proc.stdout, out(proc)
        assert config.read_bytes() == before, (
            "an unparseable config.json is the only copy of the user's bytes")

    def test_a_hand_set_command_survives_a_run_that_cannot_evidence_one(self, project):
        """Through the CLI, on the workflow the skill actually documents: the user
        sets a command adapt could not derive, and the next run must not undo it."""
        config = config_of(project)
        doc = json.loads(config.read_text(encoding="utf-8"))
        doc.setdefault("project", {})["build_cmd"] = "make release"
        config.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        after = json.loads(config.read_text(encoding="utf-8"))
        assert after["project"]["build_cmd"] == "make release", (
            "adapt destroyed a command the skill told the user to set: %r"
            % after["project"]["build_cmd"])
        assert "left the existing value of build_cmd" in proc.stdout, (
            "a preserved key must be named in the report\n" + out(proc))

    def test_an_absent_command_is_written_empty_not_guessed(self, project):
        """The other side: adapt never invents a command. Empty means "hooks skip
        this step", which is a valid answer and better than a guess."""
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        after = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert after["project"]["build_cmd"] == "", out(proc)


class TestMCPBudgetBreach:
    """Proof 17. Uses python/profile.json's max_servers: 3 -- the posture profiles
    all declare `"mcp": {}`, so a breach is unreachable through them and the proof
    could not fail."""

    def test_a_breach_is_reported_the_rest_completes_and_the_exit_code_agrees(
            self, project):
        make_python(project)
        (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
            name: {"command": "true"} for name in ("a", "b", "c", "d")}}),
            encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, (
            "a refused-and-reported breach is a skip, not a failure\n" + out(proc))
        assert "budget 'python' already breached" in proc.stdout, out(proc)
        assert "4 server(s) against max_servers 3" in proc.stdout, out(proc)
        assert "claude.project.md  done" in proc.stdout, (
            "the remaining steps must still complete\n" + out(proc))


class TestDetectionExecutesNothingThroughTheCLI:
    """Proof 15 through the real verb: two sentinels, because a Makefile sentinel
    alone does not prove no workflow `run:` string reached a shell."""

    def test_neither_sentinel_is_ever_created(self, project):
        make_python(project)
        (project / "Makefile").write_text(
            "test:\n\ttouch %s\n" % (project / "MAKE_RAN"), encoding="utf-8")
        workflows = project / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "jobs:\n  t:\n    steps:\n      - run: touch %s && pytest\n"
            % (project / "WORKFLOW_RAN"), encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert not (project / "MAKE_RAN").exists(), "a Makefile recipe was executed"
        assert not (project / "WORKFLOW_RAN").exists(), "a workflow run: was executed"


class TestTheWriteDoesNotNarrowTheMode:
    """F6. `tempfile` creates at 0600, so os.replace silently narrowed a 0644 file."""

    def test_the_project_doc_keeps_its_mode(self, project):
        doc = doc_of(project)
        os.chmod(str(doc), 0o644)
        assert ck("adapt", str(project)).returncode == 0
        assert (doc.stat().st_mode & 0o777) == 0o644, oct(doc.stat().st_mode & 0o777)


class TestRuntimeStateIsNotWrittenIntoTheRegion:
    """Found by adversarially reviewing this change, not by any shipped proof.

    `dirty` was written into the region, which made the verb self-referentially
    non-idempotent on a tree where `.claude/` is TRACKED -- this repo, and every
    downstream repo. Run 1 saw a clean tree, wrote the region, and thereby dirtied
    the tree; run 2 then added a "the working tree is dirty" line run 1 had not.

    Proof 1's fixture has no `.git` at all, so it could not see this. The region
    records durable project facts; a per-run observation belongs in the report.
    """

    @staticmethod
    def _committed_repo(project):
        env = dict(CLI_ENV, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
        def git(*argv):
            done = subprocess.run(["git", "-C", str(project)] + list(argv),
                                  capture_output=True, text=True, env=env)
            assert done.returncode == 0, done.stdout + done.stderr
        git("init", "-q")
        (project / ".gitignore").write_text("backups/\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "everything, .claude/ included")
        state = subprocess.run(["git", "-C", str(project), "status", "--porcelain"],
                               capture_output=True, text=True, env=env)
        assert not state.stdout.strip(), "the fixture starts dirty: " + state.stdout
        return project

    def test_two_runs_on_a_tracked_claude_dir_are_byte_identical(self, project):
        make_python(project)
        self._committed_repo(project)
        first = ck("adapt", str(project))
        assert first.returncode == 0, out(first)
        assert "dirty=False" in first.stdout, out(first)
        body = doc_of(project).read_bytes()
        second = ck("adapt", str(project))
        assert second.returncode == 0, out(second)
        # The report SEES the tree adapt's own first run dirtied ...
        assert "dirty=True" in second.stdout, out(second)
        # ... and the document does not change because of it.
        assert doc_of(project).read_bytes() == body, (
            "adapt's own write changed what its next run writes")

    def test_the_region_never_carries_the_dirty_line(self, project):
        make_python(project)
        self._committed_repo(project)
        assert ck("adapt", str(project)).returncode == 0
        assert ck("adapt", str(project)).returncode == 0
        assert "working tree is dirty" not in doc_of(project).read_text(
            encoding="utf-8")


class TestADerivedCommandIsNeverShellComposition:
    """Also found adversarially. Adapt writes into `hooks/config.json`, and
    pre-commit / pre-push / post-implement EXECUTE what is in there -- so a `run:`
    string in the TARGET repository is attacker-controlled input to a shell that
    fires on the user's next push. Detection executing nothing is not enough on its
    own: the write outlives the report.
    """

    SENTINEL = "PWNED_BY_ADAPT"

    def _hostile(self, project, payload):
        workflows = project / ".github" / "workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        (workflows / "ci.yml").write_text(
            "jobs:\n  t:\n    steps:\n      - run: %s\n      - run: ruff check .\n"
            % payload, encoding="utf-8")

    @pytest.mark.parametrize("payload,char", [
        ("pytest ; touch %s" % SENTINEL, "';'"),
        ("pytest | tee %s" % SENTINEL, "'|'"),
        ("pytest && touch %s" % SENTINEL, "'&'"),
        ("pytest > %s" % SENTINEL, "'>'"),
        ("pytest $(touch %s)" % SENTINEL, "'$('"),
    ])
    def test_it_is_refused_by_name_and_never_written(self, project, payload, char):
        self._hostile(project, payload)
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert "refusing to write it into a file the hooks execute" in proc.stdout, (
            out(proc))
        assert char in proc.stdout, "the report must name WHICH character\n" + out(proc)
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert config["project"]["test_cmd"] == "", (
            "shell composition reached a file the hooks execute: %r"
            % config["project"]["test_cmd"])
        assert self.SENTINEL not in config_of(project).read_text(encoding="utf-8")
        assert not (project / self.SENTINEL).exists(), "and it was executed as well"

    def test_the_safe_sibling_command_still_lands(self, project):
        """A refusal must not throw away the evidence it was not about."""
        self._hostile(project, "pytest ; touch %s" % self.SENTINEL)
        assert ck("adapt", str(project)).returncode == 0
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert config["project"]["lint_cmd"] == "ruff check ."

    def test_a_PROFILE_value_is_filtered_too(self, project):
        """The inversion of what this test used to assert, and the CRITICAL an
        adversarial reviewer proved end to end.

        The old premise -- "a profile ships with the kit and is not
        attacker-controlled" -- was FALSE. `profiles.profiles_dir` resolves
        `<TARGET>/.claude/profiles`, so a profile is a file in the repository being
        adapted, and a NEW one is unreceipted: `_classify_manifest` reports only
        MODIFIED receipted files, so the Class 1 pre-flight never sees it. The
        reviewer wrote a `typescript/profile.json` whose `build_cmd` was
        `npm run build; python3 -c "open('/tmp/PWNED_PROFILE','w').write('x')"`,
        ran adapt, then ran `post-implement.sh` -- and the file was created.

        The exemption had a GREEN TEST asserting it, which is worse than no test:
        this is that test, corrected.
        """
        make_python(project)
        composed = "cd sub && python3 -m compileall -q ."
        (project / ".claude" / "profiles" / "local.json").write_text(json.dumps({
            "schema_version": 1, "stack": {"build_cmd": composed}}), encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert config["project"]["build_cmd"] == "", (
            "shell composition from a profile reached a file the hooks execute: %r"
            % config["project"]["build_cmd"])
        assert "refusing to write it into a file the hooks execute" in proc.stdout
        assert "in profile" in proc.stdout, (
            "the report must say the value came from a profile\n" + out(proc))
        # A metacharacter-free profile value still lands: the filter costs nothing.
        assert config["project"]["coverage_cmd"] == (
            "python3 -m pytest -q --cov --cov-report=term-missing")

    def test_the_reviewers_exact_profile_payload_is_refused(self, project):
        """The reviewer's own reproduction, kept verbatim as the regression."""
        (project / "package.json").write_text('{"name": "x"}\n', encoding="utf-8")
        payload = ("npm run build; python3 -c "
                   "\"open('%s','w').write('x')\"" % (project / "PWNED_PROFILE"))
        tsdir = project / ".claude" / "profiles" / "typescript"
        tsdir.mkdir(parents=True, exist_ok=True)
        (tsdir / "profile.json").write_text(json.dumps({
            "schema_version": 1, "name": "typescript", "extends": "standard",
            "hooks": {}, "agents": {}, "commands": {}, "mcp": {},
            "stack": {"build_cmd": payload, "test_cmd": "npm test"}}),
            encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        # Compare the VALUE, never `payload in json.dumps(config)`. `json.dumps`
        # escapes the payload's own `"` characters, so that form is unfalsifiable
        # for this payload -- the reviewer applied the re-exemption mutant, fully
        # restoring the vulnerability, and this test still PASSED. A regression test
        # for a CRITICAL that cannot fail is coverage in appearance only.
        assert config["project"]["build_cmd"] == "", (
            "the payload reached hooks/config.json: %r"
            % config["project"]["build_cmd"]) + "\n" + out(proc)
        assert payload not in config["project"].values(), (
            "the payload reached hooks/config.json under another key\n" + out(proc))
        assert "refusing to write it into a file the hooks execute" in proc.stdout, (
            out(proc))
        assert config["project"]["test_cmd"] == "npm test", (
            "a refusal must not throw away the safe sibling\n" + out(proc))
        assert not (project / "PWNED_PROFILE").exists()

    def test_the_same_string_IS_refused_when_derived(self, project):
        """The other half of the boundary, on the SAME string: identical text is
        written from a profile and refused from a workflow. Without this pair the
        rule's scope is asserted nowhere."""
        composed = "python3 -m pytest -q && touch %s" % self.SENTINEL
        self._hostile(project, composed)
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert config["project"]["test_cmd"] == "", out(proc)

    def test_a_cd_prefix_is_still_usable(self, project):
        """`cd web && npm test` is a real test command, and `_PREFIX_NOISE` strips
        the prefix before the metacharacter rule sees the line -- so this must NOT
        be refused, or the rule would cost more than it buys."""
        self._hostile(project, "cd sub && pytest -q")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        config = json.loads(config_of(project).read_text(encoding="utf-8"))
        assert config["project"]["test_cmd"] == "pytest -q", out(proc)


class TestEveryBranchNamesEveryStep:
    """The report contract is "EACH step reports done / skipped / failed". The fresh
    branch honoured it; the two refusal branches silently omitted the steps they
    never reached, so a reader could not tell work that was skipped from work that
    never happened. Same overstatement, one branch down.
    """

    ALL_STEPS = ("detect", "ownership", "pre-flight", "profile", "commands",
                 "hooks/config.json", "mcp", "memory", "claude.project.md",
                 "re-stamp")

    def _assert_every_step_named(self, proc, missing_ok=()):
        for step in self.ALL_STEPS:
            if step in missing_ok:
                continue
            assert step in proc.stdout, (
                "step %r is absent from the report entirely" % step) + "\n" + out(proc)

    def test_the_ownership_refusal_names_every_later_step(self, project):
        (project / ".claude" / ".claudekit-manifest.json").unlink()
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        self._assert_every_step_named(proc)
        assert proc.stdout.count("ownership could not be established") == 8, out(proc)

    def test_the_preflight_refusal_names_every_later_step(self, project):
        victim = project / ".claude" / "agents" / "planner.md"
        victim.write_text(victim.read_text(encoding="utf-8") + "\nedited\n",
                          encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        self._assert_every_step_named(proc)
        assert "the pre-flight refused, so nothing was written" in proc.stdout

    def test_the_fresh_branch_names_every_step(self, tmp_path):
        bare = tmp_path / "bare"
        bare.mkdir()
        proc = ck("adapt", str(bare))
        assert proc.returncode == 0, out(proc)
        self._assert_every_step_named(proc)
        assert "install" in proc.stdout

    def test_a_successful_run_names_every_step(self, project):
        make_python(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        self._assert_every_step_named(proc)


class TestTheFreshBranchInstalls:
    """The last item the plan recorded as deferred. `ck adapt` on an empty directory
    is now ONE command: install, re-check Rule 0 against the receipt the installer
    actually produced, then configure.

    The installer is reachable HERE and only here, and only because "fresh" means
    `.claude/` is ABSENT: `install.sh:577-581`'s `mv .claude .claude.bak-<ts>` has
    nothing to move. Every test below exists to keep that true.
    """

    def test_an_empty_directory_is_configured_end_to_end(self, tmp_path):
        target = tmp_path / "greenfield"
        target.mkdir()
        (target / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n[tool.ruff]\n", encoding="utf-8")
        proc = ck("adapt", str(target))
        assert proc.returncode == 0, out(proc)
        assert "install            done" in proc.stdout, out(proc)
        assert (target / ".claude" / ".claudekit-manifest.json").is_file()
        config = json.loads(
            (target / ".claude" / "hooks" / "config.json").read_text(encoding="utf-8"))
        assert config["project"]["test_cmd"] == "python3 -m pytest -q", out(proc)
        assert "PROJECT-ADAPT" in (
            target / ".claude" / "local" / "CLAUDE.project.md").read_text(
                encoding="utf-8")

    def test_it_installs_FULL_so_a_profile_can_resolve(self, tmp_path):
        """`install.sh:239-243` creates `.claude/profiles/` in the full-mode block
        only. A minimal install here would reproduce the adopted-minimal gap on the
        very branch that is meant to avoid it, and the MCP budget would be
        unenforceable."""
        target = tmp_path / "greenfield"
        target.mkdir()
        (target / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n", encoding="utf-8")
        proc = ck("adapt", str(target))
        assert proc.returncode == 0, out(proc)
        assert (target / ".claude" / "profiles").is_dir(), out(proc)
        assert "stack=python" in proc.stdout, out(proc)
        assert "no profiles installed (minimal install)" not in proc.stdout, out(proc)
        assert "budget 'python'" in proc.stdout, out(proc)

    def test_a_handmade_claude_dir_is_a_REFUSAL_not_a_fresh_install(self, tmp_path):
        """The load-bearing one. A tree with a hand-made `.claude/` and no receipt,
        routed to the installer on the strength of the missing manifest, is `mv`'d
        into `.claude.bak-*` with only a heuristic subset copied back -- the worst
        outcome this verb exists to prevent, reached through the branch that looks
        safe. "Fresh" means `.claude/` ABSENT. It never means "no manifest"."""
        target = tmp_path / "handmade"
        (target / ".claude" / "agents").mkdir(parents=True)
        mine = target / ".claude" / "agents" / "mine.md"
        mine.write_text("a prompt I spent a week tuning\n", encoding="utf-8")
        before = mine.read_bytes()
        proc = ck("adapt", str(target))
        assert proc.returncode == 1, out(proc)
        assert "no usable install receipt" in proc.stdout, out(proc)
        assert mine.read_bytes() == before, "the user's prompt was rewritten"
        assert not list(target.glob(".claude.bak-*")), (
            "adapt reached the installer's swap on a receipt-less tree\n" + out(proc))
        assert not (target / ".claude" / "hooks").exists(), (
            "the installer ran over a hand-made .claude/\n" + out(proc))
        assert "install " not in proc.stdout.replace("install receipt", ""), (
            "the report must not claim an install STEP it never took\n" + out(proc))

    def test_an_unreceipted_install_refuses_and_says_what_the_tree_now_holds(
            self, tmp_path):
        """`install.sh:602` runs the manifest generator as `... && print_ok ||
        print_warn`, so manifest generation is NON-FATAL: a fresh install can exit 0
        with NO receipt, and adapt would then write Class 2 into a tree with no
        provenance -- through the branch that looks safe.

        Driven through `$CLAUDEKIT_HOME`, the product's own documented source
        override (`find_claudekit_root`), pointed at an installer that succeeds and
        writes no manifest. NOT by deleting the receipt afterwards: that leaves
        `.claude/` present, so the next run takes the ADOPTED branch and lands on the
        ordinary Rule 0 refusal -- a different code path, which is how the first
        version of this test passed while proving nothing about this one.
        """
        fake = tmp_path / "fakekit"
        (fake / ".claude" / "agents").mkdir(parents=True)
        installer = fake / "install.sh"
        installer.write_text(
            '#!/usr/bin/env bash\nset -e\nmkdir -p "$1/.claude/hooks"\n'
            'echo "{}" > "$1/.claude/hooks/config.json"\n'
            'echo "installed, and deliberately no manifest"\nexit 0\n',
            encoding="utf-8")
        os.chmod(str(installer), 0o755)

        target = tmp_path / "greenfield"
        target.mkdir()
        proc = subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "adapt", str(target)],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env=dict(CLI_ENV, CLAUDEKIT_HOME=str(fake)))
        assert proc.returncode == 1, out(proc)
        assert "install            done" in proc.stdout, (
            "the installer must have been reported as succeeding\n" + out(proc))
        assert "wrote no usable receipt" in proc.stdout, out(proc)
        assert "UNRECEIPTED kit install" in proc.stdout, (
            "a refusal over a materially changed tree must say what happened\n"
            + out(proc))
        assert "ck init --force" in proc.stdout, out(proc)
        # And it wrote nothing of its own into the tree the installer left.
        assert not (target / ".claude" / "local").exists(), out(proc)

    def test_a_FAILING_install_is_reported_and_nothing_is_configured(self, tmp_path):
        """`install.sh:558-562` can `exit 1` after `_cleanup_on_failure`, leaving a
        PARTIAL tree. Adapt must report that and stop -- configuring a half-installed
        kit is worse than not configuring one, and the next run will take the ADOPTED
        branch because `.claude/` now exists, so the report has to say so."""
        fake = tmp_path / "fakekit"
        (fake / ".claude" / "agents").mkdir(parents=True)
        installer = fake / "install.sh"
        installer.write_text(
            '#!/usr/bin/env bash\nmkdir -p "$1/.claude/hooks"\n'
            'echo "partial tree left behind" >&2\nexit 3\n', encoding="utf-8")
        os.chmod(str(installer), 0o755)

        target = tmp_path / "greenfield"
        target.mkdir()
        proc = subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "adapt", str(target)],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env=dict(CLI_ENV, CLAUDEKIT_HOME=str(fake)))
        assert proc.returncode == 1, out(proc)
        assert "install            failed" in proc.stdout, out(proc)
        assert "exited 3" in proc.stdout, (
            "the report must name the installer's exit code\n" + out(proc))
        assert "this tree may be partial" in proc.stdout, out(proc)
        assert "a partial install is not a fresh tree" in proc.stdout, out(proc)
        assert not (target / ".claude" / "local").exists(), (
            "adapt configured a tree whose install had failed\n" + out(proc))
        for step in ("ownership", "profile", "commands", "re-stamp"):
            assert step in proc.stdout, (
                "step %r must still be named\n" % step) + out(proc)

    def test_the_second_run_of_a_greenfield_adapt_changes_nothing(self, tmp_path):
        """Idempotence across the branch BOUNDARY: run 1 is fresh, run 2 is adopted.
        Two different code paths must agree on what the tree should look like."""
        target = tmp_path / "greenfield"
        target.mkdir()
        (target / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n", encoding="utf-8")
        assert ck("adapt", str(target)).returncode == 0
        before = tree_digest(target)
        second = ck("adapt", str(target))
        assert second.returncode == 0, out(second)
        assert "adopted tree" in second.stdout, out(second)
        assert tree_digest(target) == before


class TestAdaptOnAnEjectedTree:
    """`ck eject` (afc4ba8) removes the manifest after copying every path and digest
    into `.claudekit-ejected.json`. Before this, adapt hit Rule 0 and reported "no
    usable install receipt (absent or unparseable)" -- corruption, for a state the
    user chose -- and then advised `ck init`, which over an existing `.claude/`
    reaches `install.sh:577-581` and `mv`s the directory aside. Adapt recommending
    the destructive path that decision (A) exists to make unreachable is the same
    shape as the uninstall defect that produced this verb: the refusal was right and
    the printed REMEDY was the damage.

    Every fixture below ejects with the real `ck eject`, never a hand-built record.
    """

    @staticmethod
    def _ejected(project):
        proc = ck("eject", str(project), "--yes")
        assert proc.returncode == 0, out(proc)
        base = project / ".claude"
        assert not (base / ".claudekit-manifest.json").exists()
        assert (base / ".claudekit-ejected.json").is_file()
        return project

    def test_it_exits_zero_and_names_ejection(self, project):
        make_python(project)
        self._ejected(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, (
            "a supported state must not be indistinguishable from a corrupt install "
            "in CI\n" + out(proc))
        assert "this project is ejected" in proc.stdout, out(proc)
        assert "path(s) recorded" in proc.stdout, out(proc)
        assert "no usable install receipt" not in proc.stdout, (
            "ejection was reported as corruption\n" + out(proc))

    def test_it_writes_absolutely_nothing(self, project):
        make_python(project)
        self._ejected(project)
        before = tree_digest(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert tree_digest(project) == before, "adapt wrote to a self-managed tree"
        assert not (project / ".claude" / ".claudekit-manifest.json").exists(), (
            "adapt re-adopted a project the user deliberately ejected")

    def test_the_report_never_recommends_ck_init(self, project):
        """Defect 3, asserted on the exact string. `ck init` over an existing
        `.claude/` is the destructive swap; a loose match that any warning satisfies
        is how this shipped in the first place."""
        self._ejected(project)
        proc = ck("adapt", str(project))
        assert "`ck init`" not in proc.stdout, (
            "the remedy points at the installer's swap\n" + out(proc))
        assert "re-adopt it with `ck update`" in proc.stdout, out(proc)

    def test_the_read_only_half_still_runs(self, project):
        """The verb's value is largely the report, and detection/profile/MCP write
        nothing. Withholding them would make ejection cost more than it should."""
        make_python(project)
        self._ejected(project)
        proc = ck("adapt", str(project))
        assert "stack=python" in proc.stdout, out(proc)
        assert "budget 'python'" in proc.stdout, out(proc)
        assert "test_cmd='python3 -m pytest -q'" in proc.stdout, out(proc)

    def test_every_step_is_still_named(self, project):
        self._ejected(project)
        proc = ck("adapt", str(project))
        for step in ("detect", "ownership", "pre-flight", "profile", "commands",
                     "mcp", "memory", "hooks/config.json", "claude.project.md",
                     "re-stamp"):
            assert step in proc.stdout, (
                "step %r is absent from the ejected report" % step) + "\n" + out(proc)

    def test_a_GENUINELY_missing_receipt_still_refuses(self, project):
        """Without this the fix silently converts every unprovenanced tree into a
        no-op success -- refusing nowhere precisely where provenance is least known."""
        (project / ".claude" / ".claudekit-manifest.json").unlink()
        assert not (project / ".claude" / ".claudekit-ejected.json").exists()
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "no usable install receipt" in proc.stdout, out(proc)
        assert "ejected" not in proc.stdout, out(proc)

    def test_an_UNREADABLE_record_is_not_an_ejected_tree(self, project):
        """`_load_eject_record` warns and returns None, because a present-but-
        unreadable receipt is not the same state as an absent one. So this must land
        on the Rule 0 refusal, not on the ejected branch."""
        self._ejected(project)
        (project / ".claude" / ".claudekit-ejected.json").write_text(
            "{ truncated", encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "no usable install receipt" in proc.stdout, out(proc)
        assert "this project is ejected" not in proc.stdout, out(proc)

    def test_re_adoption_lets_adapt_write_again(self, project):
        """Proves the skip is a function of the STATE, not a latch."""
        make_python(project)
        self._ejected(project)
        assert ck("adapt", str(project)).returncode == 0
        update = ck("update", str(project), "--yes")
        assert update.returncode == 0, out(update)
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert "this project is ejected" not in proc.stdout, out(proc)
        config = json.loads(
            (project / ".claude" / "hooks" / "config.json").read_text(encoding="utf-8"))
        assert config["project"]["test_cmd"] == "python3 -m pytest -q", out(proc)


class TestAReadOnlyFailureIsReportedNotRaised:
    """The MAJOR. `_adapt_read_only`'s contract is a 4-tuple and the caller unpacks
    it, so a bare `return 1` on `ProfileError` raised `TypeError: cannot unpack
    non-iterable int object` on the user's console -- reachable from a
    target-controlled `.claude/profiles/local.json`, with no env manipulation. It
    also bypassed the caller's `skip_the_rest`, so six steps vanished, and on the
    ejected branch (which discards the return value) the report printed TWICE.
    """

    BOGUS = {"schema_version": 1, "hooks": {"bogus-hook": "block"}}
    STEPS = ("detect", "ownership", "pre-flight", "profile", "commands", "mcp",
             "memory", "hooks/config.json", "claude.project.md", "re-stamp")

    def _poison(self, project):
        (project / ".claude" / "profiles" / "local.json").write_text(
            json.dumps(self.BOGUS), encoding="utf-8")

    def test_no_traceback_reaches_the_user(self, project):
        self._poison(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert "Traceback" not in out(proc), out(proc)
        assert "cannot unpack" not in out(proc), out(proc)
        assert "profile" in proc.stdout and "failed" in proc.stdout

    def test_every_step_is_still_named(self, project):
        self._poison(project)
        proc = ck("adapt", str(project))
        for step in self.STEPS:
            assert step in proc.stdout, (
                "step %r vanished when a read-only step failed" % step) + out(proc)

    def test_nothing_is_written(self, project):
        self._poison(project)
        before = tree_digest(project)
        assert ck("adapt", str(project)).returncode == 1
        assert tree_digest(project) == before

    def test_the_ejected_branch_renders_exactly_once(self, project):
        assert ck("eject", str(project), "--yes").returncode == 0
        self._poison(project)
        proc = ck("adapt", str(project))
        assert proc.returncode == 1, out(proc)
        assert proc.stdout.count("ck adapt \u2014 ") == 1, (
            "the report was rendered twice with different step sets\n" + out(proc))
        assert "Traceback" not in out(proc)
        for step in self.STEPS:
            assert step in proc.stdout, step + "\n" + out(proc)


class TestTheRefusalRemedyNeverNamesTheDestructivePath:
    """MINOR 1, and it is the same defect shape the ejected branch already fixed:
    the refusal is right and the printed REMEDY is the damage. `ck init` over an
    existing `.claude/` reaches `install.sh:577-581`, which `mv`s the directory to
    `.claude.bak-<ts>` and restores only a heuristic subset -- advised on the branch
    where provenance is LEAST known."""

    def test_a_receiptless_tree_is_not_told_to_run_ck_init(self, tmp_path):
        target = tmp_path / "handmade"
        (target / ".claude" / "agents").mkdir(parents=True)
        (target / ".claude" / "agents" / "mine.md").write_text("mine\n",
                                                              encoding="utf-8")
        proc = ck("adapt", str(target))
        assert proc.returncode == 1, out(proc)
        assert "re-run `ck init`" not in proc.stdout, (
            "the remedy points at the installer's swap\n" + out(proc))
        assert "back up `.claude/` FIRST" in proc.stdout, out(proc)
        assert ".claude.bak-<timestamp>" in proc.stdout, (
            "the consequence must be named, not just the command\n" + out(proc))


class TestAKeptValueIsNotAttributedToTheUser:
    """MINOR 2. On a FRESH tree the values already in `config.json` were derived by
    `install.sh` seconds earlier, so "nothing on disk evidenced one" misreported
    their provenance as the user's."""

    def test_the_wording_does_not_claim_the_value_is_the_users(self, project):
        config = config_of(project)
        doc = json.loads(config.read_text(encoding="utf-8"))
        doc.setdefault("project", {})["build_cmd"] = "make release"
        config.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        proc = ck("adapt", str(project))
        assert proc.returncode == 0, out(proc)
        assert "left the existing value of build_cmd" in proc.stdout, out(proc)
        assert "adapt evidenced none" in proc.stdout, out(proc)
        assert "nothing on disk evidenced one)" not in proc.stdout, (
            "the old wording attributed install.sh's value to the user\n" + out(proc))
        after = json.loads(config.read_text(encoding="utf-8"))
        assert after["project"]["build_cmd"] == "make release"
