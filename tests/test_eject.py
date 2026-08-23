"""`ck eject` leaves kit management without touching a single asset.

Behavioural: every test installs the real kit into a real temp project with the
real installer, then drives the real CLI against it. The property under test is
a filesystem outcome -- every asset byte-identical, the manifest gone, its
provenance kept -- and that outcome only exists at the installer/CLI boundary,
so nothing here is mocked.
"""
import hashlib
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
EJECTED = ".claudekit-ejected.json"


def ck(*args, cwd=None, stdin=""):
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", *args],
        capture_output=True, text=True, cwd=cwd or ROOT, input=stdin,
        env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")), timeout=300)


def install(testcase, mode="--minimal", language=None):
    """A real project with a real ClaudeKit install in it."""
    target = tempfile.mkdtemp(prefix="ck-eject-")
    testcase.addCleanup(shutil.rmtree, target, True)
    argv = ["bash", INSTALLER, target, mode, "--yes", "--force"]
    if language:
        argv.extend(["--language", language])
    result = subprocess.run(
        argv,
        capture_output=True, text=True, timeout=600,
        env=dict(os.environ, ECC_HOOK_PROFILE="minimal"))
    if result.returncode != 0:
        raise AssertionError("installer failed:\n%s\n%s"
                             % (result.stdout[-2000:], result.stderr[-2000:]))
    return target


def tree_digests(target):
    """sha256 of every file under .claude/, minus the two receipt files.

    The receipts are exactly what eject is allowed to change; everything else
    must come out the other side identical, and this is what proves it.
    """
    base = os.path.join(target, ".claude")
    out = {}
    for root, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name in (MANIFEST, EJECTED) or name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, base)
            with open(path, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


class TestEject(unittest.TestCase):

    def test_every_asset_survives_and_only_the_receipt_changes(self):
        target = install(self)
        before = tree_digests(target)
        self.assertTrue(before, "installer produced no assets to protect")

        result = ck("eject", target, "--yes")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        self.assertEqual(before, tree_digests(target),
                         "eject altered an asset; it must only swap the receipt")
        self.assertFalse(os.path.exists(os.path.join(target, ".claude", MANIFEST)))
        self.assertTrue(os.path.exists(os.path.join(target, ".claude", EJECTED)))

    def test_record_carries_the_manifest_digests_and_version(self):
        target = install(self)
        with open(os.path.join(target, ".claude", MANIFEST)) as fh:
            manifest = json.load(fh)

        self.assertEqual(0, ck("eject", target, "--yes").returncode)

        with open(os.path.join(target, ".claude", EJECTED)) as fh:
            record = json.load(fh)
        self.assertEqual(manifest.get("files"), record["files"],
                         "provenance lost: the record must reproduce the receipt")
        self.assertEqual(manifest, record["manifest"],
                         "the record must carry the WHOLE receipt, not a summary "
                         "of the fields we happened to pick")
        self.assertEqual(manifest.get("version"), record["ejected_from_version"])
        self.assertEqual(len(manifest.get("files", {})), record["file_count"])
        self.assertTrue(record["ejected_utc"])

    def test_locally_modified_file_is_preserved_and_recorded(self):
        target = install(self)
        with open(os.path.join(target, ".claude", MANIFEST)) as fh:
            rel = sorted(json.load(fh)["files"])[0]
        victim = os.path.join(target, ".claude", rel)
        with open(victim, "a") as fh:
            fh.write("\n# a week of tuning lives here\n")
        with open(victim, "rb") as fh:
            edited = fh.read()

        self.assertEqual(0, ck("eject", target, "--yes").returncode)

        with open(victim, "rb") as fh:
            self.assertEqual(edited, fh.read(), "eject clobbered a local edit")
        with open(os.path.join(target, ".claude", EJECTED)) as fh:
            self.assertIn(rel, json.load(fh)["modified_at_eject"])

    def test_dry_run_writes_nothing(self):
        target = install(self)
        result = ck("eject", target, "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(os.path.exists(os.path.join(target, ".claude", MANIFEST)))
        self.assertFalse(os.path.exists(os.path.join(target, ".claude", EJECTED)))

    def test_declining_the_prompt_writes_nothing(self):
        target = install(self)
        result = ck("eject", target, stdin="n\n")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(os.path.exists(os.path.join(target, ".claude", MANIFEST)))
        self.assertFalse(os.path.exists(os.path.join(target, ".claude", EJECTED)))

    def test_second_eject_refuses_and_says_why(self):
        target = install(self)
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        result = ck("eject", target, "--yes")
        self.assertEqual(1, result.returncode)
        self.assertIn("already ejected", result.stderr)

    def test_prompt_on_closed_stdin_declines_instead_of_crashing(self):
        target = install(self)
        result = subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "eject", target],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")), timeout=300)
        self.assertEqual(0, result.returncode)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(os.path.exists(os.path.join(target, ".claude", MANIFEST)))

    def test_an_unreadable_receipt_is_announced_not_swallowed(self):
        target = install(self)
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        with open(os.path.join(target, ".claude", EJECTED), "w") as fh:
            fh.write("{ truncated")
        result = ck("update", target, "--yes")
        self.assertIn("unreadable", result.stdout + result.stderr)

    def test_eject_without_a_manifest_refuses(self):
        target = tempfile.mkdtemp(prefix="ck-eject-bare-")
        self.addCleanup(shutil.rmtree, target, True)
        os.makedirs(os.path.join(target, ".claude"))
        result = ck("eject", target, "--yes")
        self.assertEqual(1, result.returncode)
        self.assertIn("Nothing to eject", result.stderr)

    def test_uninstall_after_eject_has_nothing_to_own(self):
        target = install(self)
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        result = ck("uninstall", target, "--yes")
        self.assertEqual(1, result.returncode)
        self.assertTrue(tree_digests(target), "uninstall deleted ejected assets")

    def test_doctor_reports_the_ejected_install(self):
        target = install(self)
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        result = ck("doctor", cwd=target)
        self.assertIn("Install ejected", result.stdout)
        # The eject record carries `mode`, so the --minimal excuse for absent
        # skills/hooks survives the ejection. Without that fallback doctor would
        # report the install as healthy-by-design and hard-fail it in one breath.
        self.assertEqual(0, result.returncode,
                         "ejecting a --minimal install must not turn its excused "
                         "absences into failures:\n" + result.stdout)
        # The eject check reports "skip", and a skip must not be able to redden
        # --strict. Asserted on the SKIP MARKER and the tally, not on the global
        # exit code: doctor also warns when `shellcheck` is not on PATH, and
        # --strict turns any warning into rc 1. GitHub's ubuntu images ship
        # shellcheck and its macOS images do not, so the exit-code form of this
        # assertion passed here and on ubuntu CI while failing every macOS job --
        # a test whose verdict depended on the runner rather than on the code.
        strict = ck("doctor", "--strict", cwd=target)
        ejected_lines = [ln for ln in strict.stdout.splitlines()
                         if "Install ejected" in ln]
        self.assertEqual(1, len(ejected_lines), strict.stdout)
        self.assertIn("[-]", ejected_lines[0],
                      "the ejected-install check must render as a SKIP, not a "
                      "warning or a pass:\n" + ejected_lines[0])
        self.assertIn("Skipped:", strict.stdout, strict.stdout)
        if shutil.which("shellcheck") is not None:
            # With the one environment-dependent warning out of the way, the whole
            # run must be strict-clean -- that is the half the marker cannot prove.
            self.assertEqual(0, strict.returncode,
                             "the ejected-install check must not redden --strict:\n"
                             + strict.stdout)
        # Binds the SCORE CALL SITE, not just the helper's signature: an ejected
        # minimal install is all passes and skips, so letting skipped DEPRESS the
        # score (counting it toward the denominator) moves this off 100 and fails
        # here -- verified by mutation. The mirror mutation, folding skipped into
        # the numerator as well, is arithmetically inert while warned and failed
        # are both zero, so no assertion on this tree can detect it; the helper's
        # signature test is what closes that half.
        if shutil.which("shellcheck") is not None:
            self.assertIn("Readiness: 100/100", strict.stdout)

    def test_re_adopting_an_ejected_project_restores_its_original_mode(self):
        # The receipt records the mode. Without reading it back, cmd_update sees
        # no manifest, falls through to its `or "full"` default, and silently
        # reinstalls a --minimal project as a full one -- changing what the
        # project ships as a side effect of a round trip that promised to be
        # reversible.
        target = install(self, mode="--minimal")
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        result = ck("update", target, "--yes")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        with open(os.path.join(target, ".claude", MANIFEST)) as fh:
            self.assertEqual("minimal", json.load(fh)["mode"])

    def test_re_adopting_an_ejected_project_restores_its_language(self):
        # Exactly the mode bug one field over: install.sh applies a language
        # template, so dropping `language` from the receipt silently reinstalls
        # a rust project as generic.
        target = install(self, mode="--minimal", language="rust")
        with open(os.path.join(target, ".claude", MANIFEST)) as fh:
            self.assertEqual("rust", json.load(fh)["language"])
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        result = ck("update", target, "--yes")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        with open(os.path.join(target, ".claude", MANIFEST)) as fh:
            self.assertEqual("rust", json.load(fh)["language"])

    def test_re_adopting_clears_the_eject_receipt(self):
        # Once a project is managed again the receipt is stale: leaving it behind
        # would make `ck doctor` report a managed install as ejected. install.sh
        # gets this for free -- it backs up and replaces .claude/ wholesale and
        # restores only ASSET_DIRS (agents, commands, skills), and the receipt
        # sits at the .claude/ root -- so this test guards the property, not any
        # one mechanism.
        target = install(self)
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        self.assertEqual(0, ck("update", target, "--yes").returncode)
        self.assertFalse(os.path.exists(os.path.join(target, ".claude", EJECTED)))
        with open(os.path.join(target, ".claude", MANIFEST)) as fh:
            files = json.load(fh)["files"]
        self.assertNotIn(EJECTED, files)
        self.assertNotIn(MANIFEST, files)

    def test_update_re_adopts_an_ejected_project(self):
        target = install(self)
        self.assertEqual(0, ck("eject", target, "--yes").returncode)
        result = ck("update", target, "--yes")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(os.path.exists(os.path.join(target, ".claude", MANIFEST)),
                        "eject must be reversible: update re-writes the receipt")


if __name__ == "__main__":
    unittest.main()
