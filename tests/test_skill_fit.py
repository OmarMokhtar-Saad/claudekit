"""`ck skill audit|profile|card|match` and the doctor check -- behavioural proofs.

Every test builds a real project tree under tmp_path and drives the real CLI, then
asserts on what it printed and on what is (and is not) on disk afterwards. The verbs
are read-only by contract, so several tests hash the whole tree before and after.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"), ECC_HOOK_PROFILE="minimal")

BODY_SENTINEL = "BODY-SENTINEL-never-leaves-the-project"


def ck(root, *args):
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", *args],
                          capture_output=True, text=True, cwd=str(root), env=ENV,
                          timeout=120)


def write_skill(root, name, description, *, extra_fm="", body=None):
    d = root / ".claude" / "skills" / name
    d.mkdir(parents=True)
    text = body if body is not None else f"# {name}\n\n{BODY_SENTINEL}\n"
    (d / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "{description}"\n{extra_fm}---\n\n{text}',
        encoding="utf-8")
    return d


def tree_digest(root):
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


KIT_SKILLS = ("python-review-checklist", "java-review-checklist", "broken-links",
              "no-frontmatter", "big-body")


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    (root / ".claude" / "skills").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'proj'\n", encoding="utf-8")
    (root / ".claude" / "skills" / "skills-registry.json").write_text(json.dumps({
        "version": "2.0", "skills": [], "agentMapping": {},
        "renamed": {"old-helper": "house-style"},
    }), encoding="utf-8")
    write_skill(root, "python-review-checklist", "Use when the diff has .py files")
    write_skill(root, "java-review-checklist", "Use when the diff has .java files")
    write_skill(root, "house-style", "Use when naming things in this project",
                extra_fm="stack_tags: [python]\n")
    write_skill(root, "broken-links", "Use when testing links",
                body="See [the guide](./missing.md).\n\n```\n[example](./example.md)\n```\n")
    nofm = root / ".claude" / "skills" / "no-frontmatter"
    nofm.mkdir()
    (nofm / "SKILL.md").write_text("# no frontmatter here\n", encoding="utf-8")
    write_skill(root, "big-body", "Use when measuring budgets", body="line\n" * 400)
    manifest = {"files": {f"skills/{n}/SKILL.md": "0" * 64 for n in KIT_SKILLS}}
    (root / ".claude" / ".claudekit-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    return root


def audit_json(root, *extra):
    proc = ck(root, "skill", "audit", "--json", *extra)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def by_name(report):
    return {r["name"]: r for r in report["skills"]}


class TestAudit:
    def test_buckets_each_skill_and_writes_nothing(self, project):
        before = tree_digest(project)
        report = audit_json(project)
        rows = by_name(report)
        assert report["stacks"] == ["python"]
        assert rows["python-review-checklist"]["status"] == "relevant"
        assert rows["java-review-checklist"]["status"] == "irrelevant"
        assert rows["house-style"]["status"] == "relevant"
        assert rows["house-style"]["stack_tags"] == ["python"]
        assert rows["house-style"]["owner"] == "local"
        assert rows["python-review-checklist"]["owner"] == "kit"
        assert rows["no-frontmatter"]["status"] == "broken"
        assert rows["broken-links"]["status"] == "broken"
        # The fenced example link is NOT a reference; only the prose link is.
        assert rows["broken-links"]["problems"] == ["missing referenced file: ./missing.md"]
        assert rows["big-body"]["over_budget"] is True
        assert rows["house-style"]["over_budget"] is False
        assert report["totals"]["irrelevant"] == 1
        assert report["totals"]["broken"] == 2
        assert tree_digest(project) == before

    def test_token_estimate_is_chars_over_four_rounded_up(self, project):
        rows = by_name(audit_json(project))
        description = "Use when naming things in this project"
        assert rows["house-style"]["description_tokens"] == (len(description) + 3) // 4

    def test_budget_flags_are_overridable(self, project):
        rows = by_name(audit_json(project, "--max-lines", "1000", "--max-tokens", "100000"))
        assert rows["big-body"]["over_budget"] is False

    def test_save_writes_the_report_and_only_the_report(self, project):
        before = tree_digest(project)
        proc = ck(project, "skill", "audit", "--save", "--json")
        assert proc.returncode == 0, proc.stderr
        saved = project / ".claude" / "reports" / "skills" / "audit.json"
        assert json.loads(saved.read_text(encoding="utf-8")) == json.loads(proc.stdout)
        after = tree_digest(project)
        assert set(after) - set(before) == {".claude/reports/skills/audit.json"}

    def test_human_output_names_buckets(self, project):
        proc = ck(project, "skill", "audit")
        assert proc.returncode == 0, proc.stderr
        assert "irrelevant (1)" in proc.stdout
        assert "missing referenced file: ./missing.md" in proc.stdout

    def test_java_is_detected_from_source_files_at_the_threshold(self, tmp_path):
        root = tmp_path / "javaproj"
        write_skill(root, "java-review-checklist", "Use when the diff has .java files")
        src = root / "src"
        src.mkdir()
        for i in range(19):
            (src / f"A{i}.java").write_text("class A {}\n", encoding="utf-8")
        assert audit_json(root)["stacks"] == []
        (src / "A19.java").write_text("class A {}\n", encoding="utf-8")
        report = audit_json(root)
        assert report["stacks"] == ["java"]
        assert by_name(report)["java-review-checklist"]["status"] == "relevant"

    def test_an_undetected_stack_never_makes_a_skill_irrelevant(self, tmp_path):
        root = tmp_path / "bare"
        write_skill(root, "java-review-checklist", "Use when the diff has .java files")
        report = audit_json(root)
        assert report["stacks"] == []
        assert by_name(report)["java-review-checklist"]["status"] == "relevant"

    def test_the_kit_corpus_audits_with_zero_broken_skills(self):
        """Regression for the link check: without code-fence exclusion the kit's own
        skills report false 'missing file' problems."""
        report = audit_json(REPO_ROOT)
        broken = [(r["name"], r["problems"]) for r in report["skills"]
                  if r["status"] == "broken"]
        assert broken == []


class TestProfileInit:
    def test_init_disables_irrelevant_skills_and_never_overwrites(self, project):
        proc = ck(project, "skill", "profile", "init")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        path = project / ".claude" / "skills-profile.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["disabled"] == ["java-review-checklist"]
        assert set(doc) == {"schema", "packs", "disabled", "overlays", "roles"}
        path.write_text('{"disabled": ["big-body"]}\n', encoding="utf-8")
        again = ck(project, "skill", "profile", "init")
        assert again.returncode == 1
        assert "never overwritten" in again.stderr
        assert path.read_text(encoding="utf-8") == '{"disabled": ["big-body"]}\n'

    def test_audit_reports_the_profile_decision(self, project):
        (project / ".claude" / "skills-profile.json").write_text(
            '{"disabled": ["big-body"]}\n', encoding="utf-8")
        assert by_name(audit_json(project))["big-body"]["disabled"] is True

    def test_unknown_profile_subaction_is_refused(self, project):
        proc = ck(project, "skill", "profile", "wipe")
        assert proc.returncode == 1
        assert not (project / ".claude" / "skills-profile.json").exists()


def doctor(root):
    proc = ck(root, "doctor")
    return proc.returncode, proc.stdout + proc.stderr


class TestDoctorProfileCheck:
    def test_no_profile_means_no_check(self, project):
        _, out = doctor(project)
        assert "Skills profile" not in out

    def test_a_resolving_profile_passes(self, project):
        (project / "overlay.md").write_text("x\n", encoding="utf-8")
        (project / ".claude" / "skills-profile.json").write_text(json.dumps({
            "disabled": ["java-review-checklist"],
            "overlays": {"house-style": "overlay.md"}}), encoding="utf-8")
        _, out = doctor(project)
        assert "Skills profile: every reference resolves" in out

    def test_a_dangling_skill_warns_and_names_the_rename(self, project):
        (project / ".claude" / "skills-profile.json").write_text(json.dumps({
            "disabled": ["old-helper", "never-existed"]}), encoding="utf-8")
        _, out = doctor(project)
        assert "'old-helper', which is not installed (renamed to 'house-style')" in out
        assert "'never-existed', which is not installed" in out

    def test_an_overlay_escaping_the_project_fails(self, project):
        (project / ".claude" / "skills-profile.json").write_text(json.dumps({
            "overlays": {"house-style": "../outside.md"}}), encoding="utf-8")
        code, out = doctor(project)
        assert code == 1
        assert "escapes the project" in out

    def test_a_malformed_profile_fails(self, project):
        (project / ".claude" / "skills-profile.json").write_text(
            '{"disabled": "java-review-checklist"}', encoding="utf-8")
        code, out = doctor(project)
        assert code == 1
        assert "'disabled' must be a list of strings" in out


class TestCard:
    def test_only_local_skills_leave_and_only_as_metadata(self, project):
        proc = ck(project, "skill", "card")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert [c["name"] for c in doc["cards"]] == ["house-style"]
        card = doc["cards"][0]
        assert set(card) == {"card_version", "name", "stack_tags", "description", "tokens"}
        assert card["stack_tags"] == ["python"]
        assert BODY_SENTINEL not in proc.stdout
        assert str(project) not in proc.stdout

    def test_a_secret_shaped_description_is_withheld_without_quoting_it(self, project):
        write_skill(project, "billing-notes",
                    "Use when calling billing password: hunter2hunter2")
        proc = ck(project, "skill", "card")
        assert proc.returncode == 0, proc.stderr
        assert "hunter2" not in proc.stdout + proc.stderr
        assert "billing-notes" in proc.stderr
        assert "billing-notes" not in proc.stdout

    def test_no_manifest_means_no_cards(self, project):
        (project / ".claude" / ".claudekit-manifest.json").unlink()
        proc = ck(project, "skill", "card")
        assert proc.returncode == 1
        assert proc.stdout.strip() == ""


class TestMatch:
    def _registry(self, tmp_path):
        reg = tmp_path / "registry"
        reg.mkdir()
        (reg / "other-project.json").write_text(json.dumps({"cards": [
            {"card_version": 1, "name": "fixture-helper", "stack_tags": ["python"],
             "description": "Use when writing pytest fixtures", "tokens": 900},
            {"card_version": 1, "name": "spring-wiring", "stack_tags": ["java"],
             "description": "Use when wiring Spring beans", "tokens": 700},
            {"card_version": 1, "name": "house-style", "stack_tags": ["python"],
             "description": "Use when naming things", "tokens": 50},
            {"card_version": 1, "name": "leaky", "stack_tags": ["python"],
             "description": "Use with api_key=abc123", "tokens": 10},
        ]}), encoding="utf-8")
        (reg / "garbage.json").write_text("{not json", encoding="utf-8")
        return reg

    def test_suggests_by_stack_overlap_and_installs_nothing(self, project, tmp_path):
        reg = self._registry(tmp_path)
        before = tree_digest(project)
        proc = ck(project, "skill", "match", "--registry", str(reg), "--json")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert [s["name"] for s in doc["suggestions"]] == ["fixture-helper"]
        assert doc["suggestions"][0]["source"] == "other-project"
        assert doc["suggestions"][0]["score"] == 1.0
        assert any("garbage.json" in s for s in doc["skipped"])
        assert any("sanitizer" in s for s in doc["skipped"])
        assert tree_digest(project) == before

    def test_registry_is_required(self, project):
        proc = ck(project, "skill", "match")
        assert proc.returncode == 1


class TestSkillNewStillGuarded:
    def test_new_without_a_description_is_refused(self, project):
        proc = ck(project, "skill", "new", "widget")
        assert proc.returncode == 1
        assert "--description" in proc.stderr
        assert not (project / ".claude" / "skills" / "widget").exists()
