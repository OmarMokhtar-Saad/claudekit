"""Direct tests for the preserve logic extracted from install.sh's PRESERVE_PY heredoc.

Every case here pins a defect that actually shipped. In the heredoc these could only be
reached by running a whole install; as a module they are ordinary unit tests.
"""
import importlib.util
import json
import os
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "preserve_assets", REPO / ".claude/operations/scripts/preserve_assets.py")
assert _SPEC and _SPEC.loader
preserve_assets = importlib.util.module_from_spec(_SPEC)
sys.modules["preserve_assets"] = preserve_assets
_SPEC.loader.exec_module(preserve_assets)


class PreserveCase(unittest.TestCase):
    """A backup/ and a dest/ side by side under a common project root."""

    def setUp(self):
        import tempfile
        self.project = tempfile.mkdtemp(prefix="ck-preserve-")
        self.addCleanup(self._rm, self.project)
        self.backup = os.path.join(self.project, ".claude.bak")
        self.dest = os.path.join(self.project, ".claude")
        os.makedirs(os.path.join(self.backup, "agents"))
        os.makedirs(os.path.join(self.dest, "agents"))

    @staticmethod
    def _rm(p):
        import shutil
        shutil.rmtree(p, ignore_errors=True)

    def write(self, rel, text="x", where=None):
        p = os.path.join(where or self.backup, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def manifest(self, files):
        with open(os.path.join(self.backup, ".claudekit-manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"files": {f: {} for f in files}}, fh)

    def run_preserve(self):
        return preserve_assets.preserve_tree(self.backup, self.dest)


class TestOneBadEntryCannotAbortTheWalk(PreserveCase):
    """The 656-file loss: a single dangling symlink raised out of the whole loop."""

    def test_an_unreadable_entry_does_not_strand_the_files_after_it(self):
        """Without per-entry isolation the raise leaves preserve_tree entirely, so the
        files the walk had not yet reached are abandoned -- 656 of them, once.

        An UNREADABLE file, not a dangling symlink: a dangling link is refused by the
        link policy and never reaches the try/except, so it pins nothing here."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores chmod 000")
        self.manifest([])
        bad = self.write(os.path.join("plans", "aaa-unreadable.md"))
        os.chmod(bad, 0o000)
        self.addCleanup(os.chmod, bad, 0o644)
        for n in ("bbb.md", "ccc.md", "ddd.md"):
            self.write(os.path.join("plans", n))

        result = self.run_preserve()

        for n in ("bbb.md", "ccc.md", "ddd.md"):
            self.assertTrue(os.path.exists(os.path.join(self.dest, "plans", n)),
                            "%s was stranded behind the unreadable entry" % n)
        self.assertEqual(1, len(result.failed), result.failed)
        self.assertEqual("plans/aaa-unreadable.md", result.failed[0][0])


class TestSymlinksStaySymlinks(PreserveCase):
    """copy2 DEREFERENCES: a working link used to be flattened into a regular file."""

    def test_a_working_symlink_is_recreated_as_a_link(self):
        self.manifest([])
        real = self.write(os.path.join("agents", "real.md"), "content")
        os.symlink(os.path.basename(real), os.path.join(self.backup, "agents", "alias.md"))

        self.run_preserve()

        alias = os.path.join(self.dest, "agents", "alias.md")
        self.assertTrue(os.path.islink(alias), "the link was flattened into a real file")
        self.assertEqual("real.md", os.readlink(alias))


class TestDirectorySymlinksAreNotLost(PreserveCase):
    """A link to an EXISTING dir lands in os.walk's `dirs`, never in `names`."""

    def test_a_link_to_an_existing_directory_is_carried_over(self):
        self.manifest([])
        os.makedirs(os.path.join(self.backup, "knowledge", "realdir"))
        os.symlink("realdir", os.path.join(self.backup, "knowledge", "dirlink"))

        self.run_preserve()

        link = os.path.join(self.dest, "knowledge", "dirlink")
        self.assertTrue(os.path.islink(link),
                        "a directory symlink was dropped by the walk")


class TestRefusalPolicy(PreserveCase):
    def test_a_link_escaping_the_project_is_refused_with_a_reason(self):
        self.manifest([])
        os.symlink("/etc/passwd", os.path.join(self.backup, "agents", "escape.md"))

        result = self.run_preserve()

        self.assertFalse(os.path.lexists(os.path.join(self.dest, "agents", "escape.md")))
        self.assertEqual(1, len(result.refused))
        self.assertIn("escapes the project", result.refused[0][1])

    def test_a_self_referential_directory_link_is_refused(self):
        self.manifest([])
        os.makedirs(os.path.join(self.backup, "plans", "shadow"))
        os.symlink(self.dest, os.path.join(self.backup, "plans", "shadow", ".claude"))

        result = self.run_preserve()

        self.assertEqual(1, len(result.refused), result.refused)
        self.assertIn("self-referential", result.refused[0][1])

    def test_a_legitimate_link_inside_the_project_is_NOT_refused(self):
        """The macOS /var -> /private/var bug: resolving one side ate real files."""
        self.manifest([])
        self.write(os.path.join("agents", "target.md"))
        os.symlink(os.path.join(self.backup, "agents", "target.md"),
                   os.path.join(self.backup, "agents", "abs-link.md"))

        result = self.run_preserve()

        self.assertEqual([], result.refused, "a legitimate in-project link was refused")
        self.assertTrue(os.path.islink(os.path.join(self.dest, "agents", "abs-link.md")))


class TestWhatCountsAsCustom(PreserveCase):
    def test_old_kit_files_are_not_resurrected(self):
        self.manifest(["agents/retired.md"])
        self.write(os.path.join("agents", "retired.md"))
        self.write(os.path.join("agents", "mine.md"))

        self.run_preserve()

        self.assertFalse(os.path.exists(os.path.join(self.dest, "agents", "retired.md")),
                         "a file the OLD KIT owned was resurrected")
        self.assertTrue(os.path.exists(os.path.join(self.dest, "agents", "mine.md")))

    def test_pre_manifest_fallback_covers_hooks_and_operations(self):
        """rest-framework lost two custom hooks to the old ('agents','commands','skills')."""
        self.write(os.path.join("hooks", "format-compile.sh"))
        self.write(os.path.join("operations", "custom.json"))
        self.write(os.path.join("reports", "scratch.md"))

        result = self.run_preserve()

        self.assertTrue(os.path.exists(os.path.join(self.dest, "hooks", "format-compile.sh")))
        self.assertTrue(os.path.exists(os.path.join(self.dest, "operations", "custom.json")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "reports", "scratch.md")),
                         "reports/ is generated and must not be resurrected")
        self.assertFalse(result.had_manifest)

    def test_an_existing_dangling_link_in_dest_is_left_alone(self):
        """lexists, not exists: `exists` reads a dangling link as absent and overwrites."""
        self.manifest([])
        os.symlink("/nonexistent", os.path.join(self.dest, "agents", "keep.md"))
        self.write(os.path.join("agents", "keep.md"), "backup version")

        result = self.run_preserve()

        keep = os.path.join(self.dest, "agents", "keep.md")
        self.assertTrue(os.path.islink(keep), "an existing dangling link was clobbered")
        self.assertEqual("/nonexistent", os.readlink(keep))
        # The entry must be SKIPPED outright. Under `exists` it is treated as absent,
        # and copy2 then writes THROUGH the dangling link and fails -- which leaves the
        # link intact, so the two assertions above alone cannot see the bug.
        self.assertEqual([], result.failed,
                         "the dangling link was treated as absent and written through")

    def test_runtime_noise_is_never_preserved(self):
        self.manifest([])
        self.write(os.path.join("hooks", "hooks.log"), "runtime")
        self.write("settings.local.json", "{}")

        self.run_preserve()

        self.assertFalse(os.path.exists(os.path.join(self.dest, "hooks", "hooks.log")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "settings.local.json")))


class TestReport(PreserveCase):
    def test_failures_are_reported_with_a_count_and_names(self):
        result = preserve_assets.PreserveResult()
        result.failed = [("a/b.md", "PermissionError")]
        lines = "\n".join(preserve_assets.format_report(result))
        self.assertIn("1 file(s) could NOT be preserved", lines)
        self.assertIn("a/b.md", lines)

    def test_pre_manifest_note_only_when_there_was_no_manifest(self):
        result = preserve_assets.PreserveResult()
        result.restored = ["agents/x.md"]
        result.had_manifest = False
        self.assertIn("pre-manifest backup", "\n".join(preserve_assets.format_report(result)))
        result.had_manifest = True
        self.assertNotIn("pre-manifest backup", "\n".join(preserve_assets.format_report(result)))


if __name__ == "__main__":
    unittest.main()
