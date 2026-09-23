"""Stale copies vs real edits on `ck update` (install_overrides.py `reconcile`).

A fake kit (a git repo with two releases) and a fake project installed from its first
release: a stale copy is replaced, a clean 3-way merge is applied, a conflict keeps the
project file with `<file>.kit-new` beside it, an untouched file is not reported, and a
refreshed script that needs a name its kept sibling lacks is held back.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "scripts" / "gen-kit-history.py"
OVERRIDES = REPO / ".claude" / "operations" / "scripts" / "install_overrides.py"

LINES = "one\ntwo\nthree\nfour\nfive\n"
V1 = {
    "agents/stale.md": "stale v1\n",
    "agents/merge.md": LINES,
    "agents/conflict.md": LINES,
    "agents/same.md": "same\n",
    "agents/edited.md": "edited v1\n",
    "operations/scripts/lib.py": "def old_fn():\n    return 1\n",
    "operations/scripts/tool.py": "from lib import old_fn\n",
}
V2 = dict(V1, **{
    "agents/stale.md": "stale v2\n",
    "agents/merge.md": LINES.replace("five", "FIVE (kit)"),
    "agents/conflict.md": LINES.replace("three", "THREE (kit)"),
    "operations/scripts/lib.py": "def old_fn():\n    return 1\n\n\ndef new_fn():\n    return 2\n",
    "operations/scripts/tool.py": "from lib import new_fn\n",
})


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd)] + list(args), check=True, capture_output=True)


def write_tree(base, files):
    for rel, text in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class KitHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.kit = self.tmp / "kit"
        self.kit.mkdir()
        git(self.kit, "init", "-q")
        git(self.kit, "config", "user.email", "t@example.com")
        git(self.kit, "config", "user.name", "t")
        for version, files in (("1.0.0", V1), ("1.1.0", V2)):
            write_tree(self.kit / ".claude", files)
            (self.kit / "pyproject.toml").write_text('[project]\nversion = "%s"\n' % version)
            git(self.kit, "add", "-A")
            git(self.kit, "commit", "-q", "-m", version)
        self.history = self.tmp / "history.json"
        subprocess.run([sys.executable, str(GEN), "--root", str(self.kit), "--through", "HEAD",
                        "--out", str(self.history)], check=True, capture_output=True)
        self.staging = self.tmp / "staging"
        shutil.copytree(str(self.kit / ".claude"), str(self.staging))
        # The project: installed from 1.0.0, then edited; stale.md was kept by an older
        # installer, which receipted the 1.1.0 hash over the 1.0.0 bytes.
        self.dest = self.tmp / "project" / ".claude"
        write_tree(self.dest, V1)
        receipt = {rel: sha(text) for rel, text in V1.items()}
        receipt["agents/stale.md"] = sha(V2["agents/stale.md"])
        receipt["agents/edited.md"] = sha(V2["agents/edited.md"])
        (self.dest / "agents/merge.md").write_text(LINES.replace("one", "ONE (project)"))
        (self.dest / "agents/conflict.md").write_text(LINES.replace("three", "THREE (project)"))
        (self.dest / "agents/edited.md").write_text("edited by the project\n")
        # lib.py: the project appended where the kit did, so the merge conflicts.
        (self.dest / "operations/scripts/lib.py").write_text(
            V1["operations/scripts/lib.py"] + "\n\ndef project_fn():\n    return 3\n")
        (self.dest / ".claudekit-manifest.json").write_text(json.dumps({"files": receipt}))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def reconcile(self, kit_git=None):
        kept, report = self.tmp / "kept.json", self.tmp / "report.json"
        proc = subprocess.run(
            [sys.executable, str(OVERRIDES), "reconcile", str(self.dest), str(self.staging),
             str(self.history), str(self.kit) if kit_git is None else kit_git, str(kept),
             str(report)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = {r["path"]: r for r in json.loads(report.read_text())["rows"]}
        return json.loads(kept.read_text()), rows, proc.stdout

    def test_history_labels_each_version_with_the_release_that_shipped_it(self):
        files = json.loads(self.history.read_text())["files"]
        self.assertEqual(files["agents/stale.md"][sha("stale v1\n")][0], "1.0.0")
        self.assertEqual(files["agents/stale.md"][sha("stale v2\n")][0], "1.1.0")

    def test_stale_copy_is_replaced_and_logged_with_its_version(self):
        kept, rows, out = self.reconcile()
        self.assertEqual(rows["agents/stale.md"]["status"], "stale")
        self.assertNotIn("agents/stale.md", kept)
        self.assertEqual((self.staging / "agents/stale.md").read_text(), "stale v2\n")
        self.assertIn("updated agents/stale.md (was kit v1.0.0)", out)

    def test_clean_merge_carries_both_sides(self):
        kept, rows, out = self.reconcile()
        self.assertEqual(rows["agents/merge.md"]["status"], "merged")
        merged = (self.staging / "agents/merge.md").read_text()
        self.assertIn("ONE (project)", merged)
        self.assertIn("FIVE (kit)", merged)
        self.assertFalse((self.staging / "agents/merge.md.kit-new").exists())
        self.assertIn("merged agents/merge.md", out)

    def test_conflict_keeps_the_project_file_and_writes_kit_new(self):
        kept, rows, out = self.reconcile()
        row = rows["agents/conflict.md"]
        self.assertEqual((row["status"], row["release_changed"]), ("conflict", True))
        self.assertGreater(row["diff"], 0)
        self.assertEqual((self.staging / "agents/conflict.md").read_text(),
                         LINES.replace("three", "THREE (project)"))
        self.assertEqual((self.staging / "agents/conflict.md.kit-new").read_text(),
                         V2["agents/conflict.md"])
        self.assertIn("agents/conflict.md", kept)

    def test_without_the_kit_git_an_edit_is_a_conflict_not_an_overwrite(self):
        _, rows, _ = self.reconcile(kit_git="")
        self.assertEqual(rows["agents/merge.md"]["status"], "conflict")
        self.assertIn("no base", rows["agents/merge.md"]["reason"])
        self.assertEqual(rows["agents/stale.md"]["status"], "stale")

    def test_untouched_file_is_not_reported_and_an_unchanged_release_is_kept(self):
        _, rows, _ = self.reconcile()
        self.assertNotIn("agents/same.md", rows)
        self.assertEqual(rows["agents/edited.md"]["status"], "edited")
        self.assertFalse(rows["agents/edited.md"]["release_changed"])
        self.assertEqual((self.staging / "agents/edited.md").read_text(),
                         "edited by the project\n")

    def test_refreshed_script_needing_a_kept_siblings_new_name_is_held(self):
        kept, rows, out = self.reconcile()
        self.assertEqual(rows["operations/scripts/lib.py"]["status"], "conflict")
        row = rows["operations/scripts/tool.py"]
        self.assertEqual(row["status"], "held")
        self.assertIn("lib.new_fn", row["reason"])
        self.assertEqual((self.staging / "operations/scripts/tool.py").read_text(),
                         V1["operations/scripts/tool.py"])
        self.assertEqual((self.staging / "operations/scripts/tool.py.kit-new").read_text(),
                         V2["operations/scripts/tool.py"])

    def test_refreshed_script_is_not_held_when_the_merge_brings_the_name(self):
        (self.dest / "operations/scripts/lib.py").write_text(
            "# project note\n" + V1["operations/scripts/lib.py"])
        _, rows, _ = self.reconcile()
        self.assertEqual(rows["operations/scripts/lib.py"]["status"], "merged")
        self.assertNotIn("operations/scripts/tool.py", rows)
        self.assertEqual((self.staging / "operations/scripts/tool.py").read_text(),
                         V2["operations/scripts/tool.py"])


if __name__ == "__main__":
    unittest.main()
