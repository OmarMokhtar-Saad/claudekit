"""Progressive disclosure for skills: `references/*.md` beside SKILL.md.

Wave 1 of the skill slimming moved examples, templates and long checklists out of six
oversized SKILL.md bodies into `references/`, loaded only when SKILL.md says to. That
is only behavior-preserving if three things hold, and each is asserted by running the
thing rather than reading prose:

- a reference nobody links is unreachable text, and a link to nothing is a dead end;
- install.sh used to copy `<skill>/*.md` only, so a references/ directory was silently
  dropped from every install -- the model would be told to read a file that is absent;
- the slimmed bodies stay inside the audit budget, or the move bought nothing.
"""

import filecmp
import glob
import json
import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".claude", "skills")
INSTALL = os.path.join(ROOT, "install.sh")
ENV = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), ECC_HOOK_PROFILE="minimal")

WAVE_1 = [
    "autonomous-loop",
    "context-budget",
    "context-keeper",
    "incident-response",
    "supply-chain-audit",
    "verification-before-completion",
]


def _skills_with_references():
    return sorted(
        os.path.basename(os.path.dirname(d))
        for d in glob.glob(os.path.join(SKILLS, "*", "references"))
        if os.path.isdir(d)
    )


def _skill_md(name):
    with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as fh:
        return fh.read()


class TestReferencesAreReachable:
    def test_wave_one_skills_have_references(self):
        """Guards the parametrised tests below against passing over an empty set."""
        assert set(WAVE_1) <= set(_skills_with_references())

    @pytest.mark.parametrize("name", _skills_with_references())
    def test_every_reference_is_linked_from_skill_md(self, name):
        body = _skill_md(name)
        for path in sorted(glob.glob(os.path.join(SKILLS, name, "references", "*.md"))):
            target = "references/" + os.path.basename(path)
            assert "](" + target + ")" in body, (
                f"{name}: {target} exists but SKILL.md never links it")


class TestWaveOneStaysInBudget:
    def test_links_resolve_and_bodies_are_under_the_audit_budget(self):
        proc = subprocess.run(
            [sys.executable, "-m", "claudekit.cli.main", "skill", "audit", "--json"],
            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        rows = {r["name"]: r for r in report["skills"]}
        # `problems` carries "missing referenced file: <link>" -- a pointer to nothing.
        broken = [(n, rows[n]["problems"]) for n in _skills_with_references()
                  if rows[n]["problems"]]
        assert broken == []
        over = [(n, rows[n]["body_lines"], rows[n]["body_tokens"])
                for n in WAVE_1 if rows[n]["over_budget"]]
        assert over == []


class TestDoctorAliasScanTreatsReferencesAsTheSkill:
    """`ck doctor` warns when a live file still names a merged-away asset, exempting
    only the replacement. Moving the "merged from X" seam into references/ made doctor
    --strict warn on this repo; the exemption must widen to the replacement's own
    references/ and to nothing else."""

    def _tree(self, tmp_path):
        claude = tmp_path / ".claude"
        (claude / "skills" / "new-skill" / "references").mkdir(parents=True)
        (claude / "skills" / "other" / "references").mkdir(parents=True)
        (claude / "skills" / "new-skill" / "SKILL.md").write_text("merged from old-skill\n")
        (claude / "skills" / "new-skill" / "references" / "seam.md").write_text(
            "merged from old-skill\n")
        (claude / "skills" / "other" / "references" / "x.md").write_text("load old-skill\n")
        return claude

    def test_own_references_are_exempt_and_others_are_not(self, tmp_path):
        sys.path.insert(0, os.path.join(ROOT, "src"))
        try:
            from claudekit.cli import main as cli
        finally:
            sys.path.pop(0)
        claude = self._tree(tmp_path)
        stale = cli._stale_alias_references(
            claude, "old-skill", claude / "skills" / "new-skill" / "SKILL.md")
        assert [str(p) for p in stale] == [os.path.join("skills", "other", "references", "x.md")]


class TestInstallShipsReferences:
    def test_full_install_copies_every_reference_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "pyproject.toml"), "w").close()
            proc = subprocess.run(
                ["bash", INSTALL, tmpdir, "--full", "--yes"],
                capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL, env=ENV)
            assert proc.returncode == 0, proc.stderr
            manifest_path = os.path.join(tmpdir, ".claude", ".claudekit-manifest.json")
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            checked = 0
            for name in _skills_with_references():
                for src in sorted(glob.glob(os.path.join(SKILLS, name, "references", "*.md"))):
                    rel = "skills/%s/references/%s" % (name, os.path.basename(src))
                    dst = os.path.join(tmpdir, ".claude", rel)
                    assert os.path.isfile(dst), f"install dropped {rel}"
                    assert filecmp.cmp(src, dst, shallow=False), rel
                    assert rel in manifest["files"], f"{rel} not kit-managed"
                    checked += 1
            assert checked > 0
