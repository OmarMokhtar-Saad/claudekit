"""`ck doctor`'s alias scan must exempt the rename target's own file.

Batch 1 added the `renamed` alias map and the doctor scan that tells a consumer which
of their files still name a removed skill. Batch 2 is the first batch whose merges are
UNIONS, and a union has to say what it absorbed -- so every survivor names its source
in its own seam, and the scan flagged all five. `ck doctor --strict` exits non-zero on
any warning, so the gate went red on the merges being documented.

The exemption is exactly one file wide: the target of the alias. Any OTHER file naming
the old id is still a real stale reference and still warns -- which is what the second
test here proves, by putting the name somewhere else.
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(__file__))


def _doctor(cwd, *args):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "src"))
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", "doctor", *args],
                          cwd=cwd, capture_output=True, text=True, env=env)


def _fixture(tmp_path, extra_file=None):
    """A minimal installed-looking tree with one alias whose target names the old id."""
    claude = tmp_path / ".claude"
    for sub in ("agents", "commands", "skills"):
        (claude / sub).mkdir(parents=True)
    (claude / "skills" / "survivor").mkdir()
    (claude / "skills" / "survivor" / "SKILL.md").write_text(
        "---\nname: survivor\ndescription: x\n---\n\n"
        "# Survivor\n\nMerged from `gone-away`, which is gone.\n", encoding="utf-8")
    registry = {
        "version": "1.0",
        "renamed": {"gone-away": "survivor"},
        "skills": [{"id": "survivor", "name": "Survivor",
                    "path": "skills/survivor/SKILL.md", "mandatory": False,
                    "usedBy": [], "description": "x"}],
        "agentsWithoutSkills": [],
        "agentMapping": {},
    }
    (claude / "skills" / "skills-registry.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8")
    if extra_file:
        (claude / "commands" / "other.md").write_text(extra_file, encoding="utf-8")
    return tmp_path


class TestTheAliasScanExemptsTheRenameTarget:
    def test_the_survivors_own_seam_does_not_warn(self, tmp_path):
        proc = _doctor(_fixture(tmp_path))
        assert "was renamed to" not in proc.stdout, proc.stdout

    def test_any_other_file_naming_the_old_id_still_warns(self, tmp_path):
        """The narrowing must not become a blanket exemption -- that would turn the
        one half of the scan a consumer can act on into a no-op."""
        proc = _doctor(_fixture(tmp_path, extra_file="Load the gone-away skill.\n"))
        assert "'gone-away' was renamed to 'survivor'" in proc.stdout, proc.stdout
        assert "commands/other.md" in proc.stdout, proc.stdout
