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


def ck(root, *args, env=None):
    return subprocess.run([sys.executable, "-m", "claudekit.cli.main", *args],
                          capture_output=True, text=True, cwd=str(root),
                          env=env if env is not None else ENV, timeout=120)


def isolated_env(tmp_path, registry=True):
    """HOME (and, unless told otherwise, CLAUDEKIT_REGISTRY) forced into tmp_path: a
    test must never read or write the developer's real user-level registry."""
    env = dict(ENV, HOME=str(tmp_path / "home"))
    env.pop("CLAUDEKIT_REGISTRY", None)
    if registry:
        env["CLAUDEKIT_REGISTRY"] = str(tmp_path / "registry")
    return env


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

    def test_a_missing_default_registry_names_it_and_the_remedy(self, project, tmp_path):
        env = isolated_env(tmp_path)
        proc = ck(project, "skill", "match", env=env)
        assert proc.returncode == 1
        assert str(tmp_path / "registry") in proc.stderr
        assert "--publish" in proc.stderr


def local_project(tmp_path, name, skills_by_name, *, manifest=True):
    """A project whose skills are all project-owned (an empty receipt)."""
    root = tmp_path / name
    (root / ".claude" / "skills").mkdir(parents=True)
    for skill, (description, extra_fm) in skills_by_name.items():
        write_skill(root, skill, description, extra_fm=extra_fm)
    if manifest:
        (root / ".claude" / ".claudekit-manifest.json").write_text(
            json.dumps({"files": {}}), encoding="utf-8")
    return root


class TestDerivedStackTags:
    def test_a_local_skill_gets_tags_from_its_text(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "session-setup": ("Use when starting an Appium session on an Android emulator",
                              "")})
        row = by_name(audit_json(root))["session-setup"]
        assert row["stack_tags"] == ["android", "appium"]
        assert row["stack_tags_source"] == "derived"
        assert row["status"] == "relevant"

    def test_derived_tags_union_the_projects_detected_stacks(self, tmp_path):
        root = local_project(tmp_path, "pyproj", {
            "release-notes": ("Use when writing release notes", "")})
        (root / "pyproject.toml").write_text("[project]\nname = 'p'\n", encoding="utf-8")
        row = by_name(audit_json(root))["release-notes"]
        assert row["stack_tags"] == ["python"]

    def test_explicit_frontmatter_wins_even_when_empty(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "pinned": ("Use when driving Appium on Android", "stack_tags: [kotlin]\n"),
            "opted-out": ("Use when driving Appium on Android", "stack_tags: []\n")})
        rows = by_name(audit_json(root))
        assert rows["pinned"]["stack_tags"] == ["kotlin"]
        assert rows["pinned"]["stack_tags_source"] == "frontmatter"
        assert rows["opted-out"]["stack_tags"] == []

    def test_kit_skills_are_never_derived(self, project):
        """A stack-neutral kit skill whose body cites Java must not become java-tagged:
        `profile init` would then disable it in every non-Java project."""
        write_skill(project, "neutral-kit", "Use when reviewing Java or Kotlin diffs")
        manifest = project / ".claude" / ".claudekit-manifest.json"
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        doc["files"]["skills/neutral-kit/SKILL.md"] = "0" * 64
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        row = by_name(audit_json(project))["neutral-kit"]
        assert row["stack_tags"] == []
        assert row["status"] == "relevant"

    def test_vocabulary_refuses_english_collisions(self):
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from claudekit import skill_fit
        assert skill_fit.derive_stack_tags("react to the spring release, go home") == []
        assert skill_fit.derive_stack_tags("JavaScript only") == []
        assert skill_fit.derive_stack_tags("Spring Boot with Gradle and JUnit") == [
            "gradle", "java", "spring"]

    def test_cards_carry_derived_tags_and_stay_sanitized(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "session-setup": ("Use when starting an Appium session on Android", "")})
        proc = ck(root, "skill", "card")
        assert proc.returncode == 0, proc.stderr
        card = json.loads(proc.stdout)["cards"][0]
        assert card["stack_tags"] == ["android", "appium"]
        assert set(card) == {"card_version", "name", "stack_tags", "description", "tokens"}
        assert BODY_SENTINEL not in proc.stdout


class TestRegistry:
    def test_publish_writes_the_user_level_default_under_home(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "session-setup": ("Use when starting an Appium session on Android", "")})
        env = isolated_env(tmp_path, registry=False)
        proc = ck(root, "skill", "card", "--publish", env=env)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        path = tmp_path / "home" / ".claudekit" / "registry" / "cards" / "mobile.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["project"] == "mobile"
        assert [c["name"] for c in doc["cards"]] == ["session-setup"]
        assert not list((root / ".claude").rglob("*registry*"))

    def test_republish_replaces_atomically_without_residue(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "session-setup": ("Use when starting an Appium session on Android", "")})
        env = isolated_env(tmp_path)
        assert ck(root, "skill", "card", "--publish", env=env).returncode == 0
        (root / ".claude" / "skills" / "session-setup" / "SKILL.md").unlink()
        (root / ".claude" / "skills" / "session-setup").rmdir()
        write_skill(root, "locators", "Use when writing Appium locators")
        assert ck(root, "skill", "card", "--publish", env=env).returncode == 0
        reg = tmp_path / "registry"
        assert sorted(p.name for p in reg.iterdir()) == ["mobile.json"]
        doc = json.loads((reg / "mobile.json").read_text(encoding="utf-8"))
        assert [c["name"] for c in doc["cards"]] == ["locators"]

    def test_a_relative_registry_override_is_refused(self, tmp_path):
        root = local_project(tmp_path, "mobile", {"x-skill": ("Use when testing", "")})
        env = dict(isolated_env(tmp_path), CLAUDEKIT_REGISTRY="cards")
        proc = ck(root, "skill", "card", "--publish", env=env)
        assert proc.returncode == 1
        assert "absolute" in proc.stderr
        assert not (root / "cards").exists()

    def test_a_withheld_card_is_not_published(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "leaky": ("Use with password: hunter2hunter2", "")})
        env = isolated_env(tmp_path)
        proc = ck(root, "skill", "card", "--publish", env=env)
        assert proc.returncode == 0, proc.stderr
        text = (tmp_path / "registry" / "mobile.json").read_text(encoding="utf-8")
        assert "hunter2" not in text
        assert "leaky" in proc.stderr

    def test_match_skips_its_own_card_and_prints_score_and_source(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "session-setup": ("Use when starting an Appium session on Android", "")})
        reg = tmp_path / "registry"
        reg.mkdir()
        card = {"card_version": 1, "stack_tags": ["android", "appium"],
                "description": "Use when stabilising Appium waits", "tokens": 40}
        (reg / "mobile.json").write_text(json.dumps(
            {"cards": [dict(card, name="own-only")]}), encoding="utf-8")
        (reg / "other.json").write_text(json.dumps(
            {"cards": [dict(card, name="appium-waits")]}), encoding="utf-8")
        env = isolated_env(tmp_path)
        doc = json.loads(ck(root, "skill", "match", "--json", env=env).stdout)
        assert [s["name"] for s in doc["suggestions"]] == ["appium-waits"]
        human = ck(root, "skill", "match", env=env)
        assert "score 1.0" in human.stdout and "from other" in human.stdout

    def test_jaccard_floor_hides_weak_overlap_until_lowered(self, tmp_path):
        root = local_project(tmp_path, "mobile", {
            "session-setup": ("Use when starting an Appium session", "")})
        reg = tmp_path / "registry"
        reg.mkdir()
        tags = ["appium"] + [f"t{i}" for i in range(10)]
        (reg / "wide.json").write_text(json.dumps({"cards": [
            {"card_version": 1, "name": "wide", "stack_tags": tags,
             "description": "Use when doing many things", "tokens": 5}]}), encoding="utf-8")
        env = isolated_env(tmp_path)
        doc = json.loads(ck(root, "skill", "match", "--json", env=env).stdout)
        assert doc["suggestions"] == []
        low = ck(root, "skill", "match", "--json", "--min-score", "0.05", env=env)
        assert [s["score"] for s in json.loads(low.stdout)["suggestions"]] == [0.091]
        assert ck(root, "skill", "match", "--min-score", "2", env=env).returncode == 1


class TestFleetMissRegression:
    def test_two_appium_projects_with_untagged_local_skills_match(self, tmp_path):
        """2026-09 fleet run: `ck skill match` printed <none> for AppiumLens against 13
        projects, because local skills carried no stack_tags and neither project cleared
        the 20-source-file stack threshold. Neither skill here declares stack_tags."""
        lens = local_project(tmp_path, "appiumlens", {
            "appium-session-setup": (
                "Use when starting an Appium session on an Android emulator", "")})
        suite = local_project(tmp_path, "mobile-suite", {
            "android-locator-strategy": (
                "Use when writing Appium locators for Android screens", "")})
        env = isolated_env(tmp_path)
        for root in (lens, suite):
            proc = ck(root, "skill", "card", "--publish", env=env)
            assert proc.returncode == 0, proc.stdout + proc.stderr
        from_suite = json.loads(ck(suite, "skill", "match", "--json", env=env).stdout)
        assert [(s["name"], s["source"], s["score"]) for s in from_suite["suggestions"]] == [
            ("appium-session-setup", "appiumlens", 1.0)]
        from_lens = json.loads(ck(lens, "skill", "match", "--json", env=env).stdout)
        assert [s["name"] for s in from_lens["suggestions"]] == ["android-locator-strategy"]


class TestSkillNewStillGuarded:
    def test_new_without_a_description_is_refused(self, project):
        proc = ck(project, "skill", "new", "widget")
        assert proc.returncode == 1
        assert "--description" in proc.stderr
        assert not (project / ".claude" / "skills" / "widget").exists()
