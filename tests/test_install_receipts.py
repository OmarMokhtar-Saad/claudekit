"""The manifest is an ownership receipt, not an inventory (wave-2 phase 3).

Behavioural: every test runs the real `install.sh` into a real temp project and
then drives the real `ck` CLI against it. Nothing is mocked, because the defect
class here only exists at the boundary between the two.

What the receipt is for: `ck uninstall` may delete a file only if that file's
sha256 still matches what was installed. A digest that no longer matches means
MIXED ownership — the kit's text plus the user's edits — and unknown ownership
means theirs. Before this, uninstall deleted every path the manifest listed
without comparing a single digest.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(ROOT, "install.sh")
MANIFEST = ".claudekit-manifest.json"

#: Imported, never re-listed: `cli/main.py` owns this set and a second copy here
#: would drift the moment it changes.
sys.path.insert(0, os.path.join(ROOT, "src"))
from claudekit.cli.main import PARTIAL_OWNED  # noqa: E402


def ck(*args, cwd=None, stdin=""):
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", *args],
        capture_output=True, text=True, cwd=cwd or ROOT, input=stdin,
        env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")), timeout=300)


class InstalledProject:
    """A real project with a real ClaudeKit install in it."""

    def __init__(self, testcase, mode="--minimal"):
        self.dir = tempfile.mkdtemp(prefix="ck-receipt-")
        testcase.addCleanup(shutil.rmtree, self.dir, True)
        result = subprocess.run(
            ["bash", INSTALLER, self.dir, mode, "--yes", "--force"],
            capture_output=True, text=True, timeout=600,
            env=dict(os.environ, ECC_HOOK_PROFILE="minimal"))
        if result.returncode != 0:
            raise AssertionError(
                "installer failed:\n%s\n%s" % (result.stdout[-2000:], result.stderr[-2000:]))
        self.claude = os.path.join(self.dir, ".claude")

    @property
    def manifest(self):
        with open(os.path.join(self.claude, MANIFEST), encoding="utf-8") as fh:
            return json.load(fh)

    def path(self, rel):
        return os.path.join(self.claude, rel)

    def a_managed_file(self):
        """A real installed file the receipt owns, preferring an agent prompt."""
        files = sorted(self.manifest["files"])
        for rel in files:
            if rel.startswith("agents/") and os.path.isfile(self.path(rel)):
                return rel
        for rel in files:
            if os.path.isfile(self.path(rel)):
                return rel
        raise AssertionError("manifest lists no file that exists on disk")

    def edit(self, rel, text="\n<!-- local edit -->\n"):
        with open(self.path(rel), "a", encoding="utf-8") as fh:
            fh.write(text)


class TheReceiptRecordsOnlyWhatTheKitOwns(unittest.TestCase):
    def setUp(self):
        self.project = InstalledProject(self)

    def reinstall(self, project):
        """Re-run the installer over an existing install — what `ck update` does."""
        result = subprocess.run(
            ["bash", INSTALLER, project.dir, "--minimal", "--yes", "--force"],
            capture_output=True, text=True, timeout=600,
            env=dict(os.environ, ECC_HOOK_PROFILE="minimal"))
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])

    def test_settings_local_is_not_recorded_after_a_reinstall(self):
        """The scenario the defect actually needed, and the reason the first
        version of this test suite did not catch it.

        On a FRESH install `settings.local.json` does not exist yet, so excluding
        it changes nothing and every assertion passes either way. The file only
        reaches the manifest on the SECOND install, once the preserve step has
        restored it into `.claude/`. Reproduced against the pre-fix installer:
        `settings.local.json in manifest: True`.
        """
        with open(self.project.path("settings.local.json"), "w", encoding="utf-8") as fh:
            fh.write('{"env": {"ECC_HOOK_PROFILE": "minimal"}}')
        self.reinstall(self.project)
        self.assertNotIn("settings.local.json", self.project.manifest["files"],
                         "a per-developer settings file became kit-owned, so "
                         "`ck update` would overwrite it and `ck uninstall` delete it")
        self.assertTrue(os.path.isfile(self.project.path("settings.local.json")))

    def test_settings_local_survives_uninstall_after_a_reinstall(self):
        """End to end: the receipt exclusion must actually protect the file."""
        with open(self.project.path("settings.local.json"), "w", encoding="utf-8") as fh:
            fh.write('{"env": {"MINE": "1"}}')
        self.reinstall(self.project)
        result = ck("uninstall", self.project.dir, "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(self.project.path("settings.local.json")),
                        "uninstall deleted the user's own settings")

    def test_user_settings_are_never_recorded_as_kit_owned(self):
        """`settings.local.json` is per-developer and never shipped.

        Recording it made `ck update` overwrite a project's own permission
        allowlist and `ck uninstall` delete it — the defect that forced a
        hand-preservation pass across 17 projects.
        """
        self.assertNotIn("settings.local.json", self.project.manifest["files"])

    def test_runtime_output_is_never_recorded(self):
        self.assertNotIn("hooks.log", self.project.manifest["files"])

    def test_a_user_created_settings_local_survives_uninstall(self):
        """The property the exclusion exists for, driven end to end."""
        local = self.project.path("settings.local.json")
        with open(local, "w", encoding="utf-8") as fh:
            fh.write('{"env": {"ECC_HOOK_PROFILE": "minimal"}}')
        result = ck("uninstall", self.project.dir, "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(local),
                        "uninstall removed a file the user owns")

    def test_the_manifest_does_not_record_itself(self):
        self.assertNotIn(MANIFEST, self.project.manifest["files"])

    def test_the_receipt_is_not_empty(self):
        """Anti-vacuity: exclusions that emptied the receipt would pass every
        other test in this class while removing all protection."""
        self.assertGreater(len(self.project.manifest["files"]), 10)


class TheInstallIsPinnedToAnImmutableCommit(unittest.TestCase):
    def setUp(self):
        self.project = InstalledProject(self)

    def test_the_source_commit_is_recorded(self):
        source = self.project.manifest.get("source")
        self.assertIsInstance(source, dict, "no source provenance in the receipt")
        commit = source.get("commit")
        self.assertIsNotNone(commit, "install from a git checkout must record its commit")
        self.assertRegex(commit, r"^[0-9a-f]{40}$",
                         "provenance must be an immutable 40-char SHA, not a branch name")

    def test_it_matches_the_source_checkout(self):
        head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(self.project.manifest["source"]["commit"], head)

    def test_installing_from_a_non_git_source_still_succeeds(self):
        """The regression the first cut of this feature introduced.

        `git status --porcelain | head -1` is a PIPELINE: under `set -o pipefail`
        a failing git upstream fails the whole pipeline, and under `set -e` that
        aborted the install with rc=128 and no manifest at all. Installing from a
        tarball or a copied tree is a supported case; provenance is best-effort,
        never a precondition. Static review checked the `rev-parse` line and
        missed this one — only executing it found it.
        """
        kit = tempfile.mkdtemp(prefix="ck-nongit-kit-")
        self.addCleanup(shutil.rmtree, kit, True)
        for entry in ("install.sh", ".claude", "templates"):
            src = os.path.join(ROOT, entry)
            dst = os.path.join(kit, entry)
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True)
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
        self.assertFalse(os.path.isdir(os.path.join(kit, ".git")))

        project = tempfile.mkdtemp(prefix="ck-nongit-proj-")
        self.addCleanup(shutil.rmtree, project, True)
        result = subprocess.run(
            ["bash", os.path.join(kit, "install.sh"), project, "--minimal", "--yes", "--force"],
            capture_output=True, text=True, timeout=600,
            env=dict(os.environ, ECC_HOOK_PROFILE="minimal"))
        self.assertEqual(result.returncode, 0,
                         "install from a non-git source aborted:\n%s\n%s"
                         % (result.stdout[-1500:], result.stderr[-1500:]))
        manifest_path = os.path.join(project, ".claude", MANIFEST)
        self.assertTrue(os.path.isfile(manifest_path), "no manifest was written")
        with open(manifest_path, encoding="utf-8") as fh:
            source = json.load(fh)["source"]
        self.assertIsNone(source["commit"], "a non-git source must not claim a commit")
        self.assertFalse(source["pinned"])

    def test_a_dirty_source_is_reported_as_unpinned(self):
        """A dirty checkout does not correspond to its own commit, so claiming a
        pin would imply a reproducibility the artifact does not have."""
        source = self.project.manifest["source"]
        dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            self.assertTrue(source.get("dirty"))
            self.assertFalse(source["pinned"])
        else:
            self.assertTrue(source["pinned"])
            self.assertNotIn("dirty", source)


class UninstallActsOnlyOnReceiptOwnedFiles(unittest.TestCase):
    def setUp(self):
        self.project = InstalledProject(self)
        self.edited = self.project.a_managed_file()
        self.project.edit(self.edited)

    def test_mixed_ownership_fails_closed_and_deletes_nothing(self):
        result = ck("uninstall", self.project.dir, "--yes")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Refusing to uninstall", result.stdout + result.stderr)
        self.assertIn(self.edited, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(self.project.path(self.edited)))
        # Nothing else went either: refusal precedes every side effect.
        for rel in sorted(self.project.manifest["files"]):
            if os.path.dirname(rel) == "agents":
                self.assertTrue(os.path.isfile(self.project.path(rel)),
                                "a refused uninstall removed %s" % rel)
        self.assertFalse(os.path.isdir(os.path.join(self.project.dir, "backups")))

    def test_uninstall_is_not_blocked_by_a_modified_partially_owned_file(self):
        # install.sh closes by telling the user to fill in build/test/lint_cmd, i.e. to
        # modify .claude/hooks/config.json -- a PARTIAL_OWNED file. Deletion can never
        # touch those (they are filtered out of `listed` and `unchanged`), so they must
        # not gate the refusal either: this dead-ended `ck uninstall` on the documented
        # happy path with no flag combination that got past it.
        # --full, not the default --minimal: only a full install receipts
        # hooks/config.json, which is the file the bug report is about.
        project = InstalledProject(self, mode="--full")
        partial = [rel for rel in sorted(project.manifest["files"])
                   if rel in PARTIAL_OWNED and os.path.isfile(project.path(rel))]
        self.assertIn("hooks/config.json", partial)
        project.edit(partial[0])
        result = ck("uninstall", project.dir, "--yes")
        self.assertEqual(result.returncode, 0,
                         "a modified partially-owned file blocked uninstall:\n"
                         + result.stdout + result.stderr)
        self.assertNotIn("Refusing to uninstall", result.stdout + result.stderr)
        # KEPT, not deleted -- the kit only ever owned part of it.
        self.assertTrue(os.path.isfile(project.path(partial[0])))
        # ...and the receipt still describes it, so `ck adapt` keeps working.
        self.assertIn(partial[0], project.manifest["files"])

    def test_the_write_flags_agree_when_only_a_partially_owned_file_changed(self):
        # The new invariant, and the one that fails pre-fix. --force and
        # --keep-modified must AGREE here -- there is nothing for either to decide,
        # because the file is unremovable under both. Pre-fix, no-flags exited 1 while
        # the other two exited 0, so the user was made to "choose explicitly" between
        # two flags with identical effect in order to escape a refusal about a file
        # neither of them could touch.
        outcomes = []
        for flags in ([], ["--force"], ["--keep-modified"]):
            project = InstalledProject(self, mode="--full")
            project.edit("hooks/config.json")
            result = ck("uninstall", project.dir, "--yes", *flags)
            outcomes.append((tuple(flags), result.returncode,
                             os.path.isfile(project.path("hooks/config.json"))))
        self.assertEqual([rc for _, rc, _ in outcomes], [0, 0, 0], outcomes)
        self.assertTrue(all(kept for _, _, kept in outcomes), outcomes)

    def test_dry_run_predicts_the_partially_owned_survivors(self):
        # A dry run that omits them says "N would be removed" and names the survivors
        # nowhere, so a reader concludes their edited config.json is going away.
        project = InstalledProject(self, mode="--full")
        project.edit("hooks/config.json")
        out = ck("uninstall", project.dir, "--dry-run").stdout
        self.assertIn("partially-owned", out)
        self.assertIn("hooks/config.json", out)

    def test_the_refusal_names_both_ways_out(self):
        result = ck("uninstall", self.project.dir, "--yes")
        self.assertIn("--keep-modified", result.stdout + result.stderr)
        self.assertIn("--force", result.stdout + result.stderr)

    def test_keep_modified_removes_owned_files_and_spares_the_edited_one(self):
        result = ck("uninstall", self.project.dir, "--yes", "--keep-modified")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(self.project.path(self.edited)),
                        "--keep-modified deleted a locally-modified file")
        with open(os.path.join(self.project.claude, MANIFEST), encoding="utf-8") as fh:
            remaining = json.load(fh)["files"]
        # The partially-owned files survive too, so "still ours" now includes them.
        expected = sorted({self.edited}
                          | (set(self.project.manifest["files"]) & PARTIAL_OWNED))
        self.assertEqual(sorted(remaining), expected,
                         "the receipt must describe exactly what is still ours")

    def test_force_removes_the_modified_file_but_backs_it_up_first(self):
        result = ck("uninstall", self.project.dir, "--yes", "--force",
                    "--stamp", "fixed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.isfile(self.project.path(self.edited)))
        backup = os.path.join(self.project.dir, "backups", "uninstall-fixed", self.edited)
        self.assertTrue(os.path.isfile(backup), "--force destroyed an edit with no backup")
        with open(backup, encoding="utf-8") as fh:
            self.assertIn("local edit", fh.read())

    def test_keep_modified_when_every_file_is_modified_removes_nothing(self):
        """The degenerate end of the same path: if nothing is still owned,
        `--keep-modified` must remove nothing rather than fall through to a
        blanket delete, and the receipt must still describe every kept file."""
        for rel in sorted(self.project.manifest["files"]):
            if os.path.isfile(self.project.path(rel)):
                self.project.edit(rel, "\n<!-- everything edited -->\n")
        listed = sorted(self.project.manifest["files"])

        result = ck("uninstall", self.project.dir, "--yes", "--keep-modified")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Removed 0 file(s)", result.stdout)
        for rel in listed:
            self.assertTrue(os.path.isfile(self.project.path(rel)),
                            "--keep-modified deleted %s when nothing was owned" % rel)
        with open(os.path.join(self.project.claude, MANIFEST), encoding="utf-8") as fh:
            self.assertEqual(sorted(json.load(fh)["files"]), listed)

    def test_a_second_uninstall_after_keep_modified_still_fails_closed(self):
        """Kept files must stay flagged as modified, not silently re-adopted."""
        ck("uninstall", self.project.dir, "--yes", "--keep-modified")
        result = ck("uninstall", self.project.dir, "--yes")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Refusing to uninstall", result.stdout + result.stderr)

    def test_dry_run_separates_owned_from_modified_and_writes_nothing(self):
        before = sorted(os.listdir(self.project.claude))
        result = ck("uninstall", self.project.dir, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("receipt-owned", result.stdout)
        self.assertIn("would be KEPT", result.stdout)
        self.assertIn(self.edited, result.stdout)
        self.assertEqual(sorted(os.listdir(self.project.claude)), before)

    def test_an_unmodified_install_still_uninstalls_cleanly(self):
        """The happy path must not become collateral damage of the new gate.

        The receipt SURVIVES now, and that is the point rather than a regression.
        `ck adapt` writes into two partially-owned files, so `ck uninstall` keeps
        them; a receipt unlinked while its files are still on disk left them
        undeletable, made `ck adapt` refuse forever with "no usable install
        receipt", made a second uninstall say "nothing to uninstall", and routed
        adapt's own printed remedy into install.sh's `mv .claude .claude.bak-*`.
        So: everything the receipt owned WHOLE is gone, the two partially-owned
        survivors are still there, and the receipt describes exactly those.
        """
        clean = InstalledProject(self)
        listed = sorted(clean.manifest["files"])
        result = ck("uninstall", clean.dir, "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest_path = os.path.join(clean.claude, MANIFEST)
        self.assertTrue(os.path.isfile(manifest_path),
                        "the receipt was unlinked while its files were still on disk")
        with open(manifest_path, encoding="utf-8") as fh:
            remaining = sorted(json.load(fh)["files"])
        # Intersected with what this install actually receipted, never hardcoded:
        # a minimal install receipts only some of PARTIAL_OWNED, and a hardcoded
        # expectation would fail for the install shape rather than for the rule.
        self.assertEqual(remaining, sorted(set(listed) & PARTIAL_OWNED))
        for rel in remaining:
            self.assertTrue(os.path.isfile(clean.path(rel)),
                            "%s is in the receipt but not on disk" % rel)
        for rel in listed:
            if rel in remaining:
                continue
            self.assertFalse(os.path.isfile(clean.path(rel)),
                             "%s was neither removed nor kept" % rel)


class FilesTheReceiptNeverSawAreNotTouched(unittest.TestCase):
    def test_a_user_authored_agent_survives_uninstall(self):
        project = InstalledProject(self)
        mine = project.path("agents/my-own-agent.md")
        os.makedirs(os.path.dirname(mine), exist_ok=True)
        with open(mine, "w", encoding="utf-8") as fh:
            fh.write("---\nname: my-own-agent\n---\n\nMine.\n")
        result = ck("uninstall", project.dir, "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(mine),
                        "uninstall removed a file that was never in the receipt")


if __name__ == "__main__":
    unittest.main()


class TheRegistryDescribesWhatWasInstalled(unittest.TestCase):
    """`ck doctor --strict` exited 1 on a FRESHLY installed tree.

    `skills-registry.json` is generated from `.claude/skills/`
    (scripts/gen-registry.py), but install.sh also copies `templates/skills/*`, and
    `i18n-workflow` lives only there. So every install shipped a skill the registry
    did not list, and the drift check warned on the happy path -- a gate that fails
    when nothing is wrong is a gate people learn to ignore.
    """

    def setUp(self):
        # FULL mode deliberately: `--minimal` installs no skills registry at all,
        # so the drift this covers is unreachable there and a minimal fixture would
        # pass vacuously.
        self.project = InstalledProject(self, mode="--full")

    def _registry(self):
        path = os.path.join(self.project.claude, "skills", "skills-registry.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_every_installed_skill_is_registered(self):
        registered = {row["id"] for row in self._registry()["skills"]}
        skills_dir = os.path.join(self.project.claude, "skills")
        on_disk = {name for name in os.listdir(skills_dir)
                   if os.path.isfile(os.path.join(skills_dir, name, "SKILL.md"))}
        self.assertTrue(on_disk, "the fixture installed no skills at all")
        self.assertEqual(sorted(on_disk - registered), [],
                         "installed skills missing from skills-registry.json")

    def test_the_template_only_skill_is_the_one_this_covers(self):
        """Named, so a reader can see WHICH skill the reconcile exists for. If
        templates/skills/i18n-workflow ever moves into .claude/skills/ this goes
        red rather than passing vacuously against an empty difference."""
        registered = {row["id"] for row in self._registry()["skills"]}
        self.assertIn("i18n-workflow", registered)
        row = [r for r in self._registry()["skills"] if r["id"] == "i18n-workflow"][0]
        self.assertEqual(row["path"], "skills/i18n-workflow/SKILL.md")
        self.assertTrue(row["description"], "registered with no description")

    def test_doctor_strict_is_clean_on_a_fresh_install(self):
        """Exit code measured WITHOUT a pipe: `rc=$?` after one reads `tail`'s."""
        result = ck("doctor", "--strict", cwd=self.project.dir)
        self.assertNotIn("is not registered", result.stdout + result.stderr)
