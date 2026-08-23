"""Tests for validate-config-json.py"""

import json
import os
import sys
import tempfile

import pytest

# Add scripts to path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

from shared import PROTECTED_PATTERNS, is_protected_file, protected_patterns  # noqa: E402


class TestProtectedFiles:
    """Tests for protected file detection."""

    @pytest.fixture(autouse=True)
    def _no_ambient_extras(self, monkeypatch):
        """CLAUDEKIT_EXTRA_PROTECTED is a supported project setting, so a developer
        or CI runner may legitimately have it set -- and these tests assert what the
        DEFAULTS do. Without this, `CLAUDEKIT_EXTRA_PROTECTED='*.md'` (the documented
        way to restore the old behaviour) turns this file red on a correct tree.
        Same rule CLAUDE.md already states for ECC_HOOK_PROFILE: force it in tests."""
        monkeypatch.delenv("CLAUDEKIT_EXTRA_PROTECTED", raising=False)

    def test_gitignore_protected(self):
        assert is_protected_file(".gitignore")

    def test_markdown_protected(self):
        assert is_protected_file("README.md")
        assert is_protected_file("CHANGELOG.md")

    def test_package_json_protected(self):
        assert is_protected_file("package.json")

    def test_requirements_protected(self):
        assert is_protected_file("requirements.txt")

    def test_pyproject_protected(self):
        assert is_protected_file("pyproject.toml")

    def test_source_not_protected(self):
        assert not is_protected_file("main.py")
        assert not is_protected_file("app.ts")
        assert not is_protected_file("Service.java")

    def test_nested_path_uses_basename(self):
        assert is_protected_file("src/deep/README.md")
        assert not is_protected_file("src/deep/app.py")

    def test_every_identity_document_is_refused_at_any_depth(self):
        """Named one by one. The `*.md` glob used to cover these as a side effect
        of covering everything; now they are the whole of the markdown rule, so a
        name dropped from the list is a silent hole. Depth is asserted because the
        match is on basename and a path-based rewrite would break it."""
        for name in ("README.md", "CHANGELOG.md", "CLAUDE.md", "AGENTS.md",
                     "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
                     "LICENSE", "LICENSE.md", "NOTICE.md", "MAINTAINERS.md",
                     "GOVERNANCE.md", "AUTHORS.md", "SUPPORT.md"):
            assert is_protected_file(name), f"{name} unprotected"
            assert is_protected_file(f"docs/deep/{name}"), f"{name} unprotected at depth"

    def test_protection_does_not_depend_on_casing(self):
        """`fnmatch.fnmatch` normalises case only on Windows, so before this the
        guard gave different answers on Linux CI and on macOS. `readme.md` was
        protected by the old `*.md` glob and must not lose that by being renamed
        into a literal list."""
        for name in ("readme.md", "License.md", "Contributing.MD", "cLaUdE.Md",
                     "makefile", "DOCKERFILE"):
            assert is_protected_file(name), f"{name} unprotected"

    def test_component_prose_is_deletable(self):
        """The narrowing exists so the kit can retire its own components. If this
        goes red the ops engine cannot execute a consolidation plan, which is the
        state that blocked task 008."""
        assert not is_protected_file(".claude/skills/token-optimization/SKILL.md")
        assert not is_protected_file(".claude/agents/python-reviewer.md")
        assert not is_protected_file("templates/commands/analyze.md")

    def test_the_default_list_is_pinned_exactly(self):
        """Equality, not a superset check. A superset assertion passes against a
        mutant that ADDS an unreviewed pattern or reorders the list, and the whole
        point of this change is that the list is now the entire markdown rule."""
        assert PROTECTED_PATTERNS == [
            ".gitignore",
            "README.md",
            "CHANGELOG.md",
            "CLAUDE.md",
            "AGENTS.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "CODE_OF_CONDUCT.md",
            "LICENSE",
            "LICENSE.md",
            "NOTICE.md",
            "MAINTAINERS.md",
            "GOVERNANCE.md",
            "AUTHORS.md",
            "SUPPORT.md",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "requirements.txt",
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "Pipfile.lock",
            "tsconfig.json"
        ]

    def test_extra_protected_widens(self, monkeypatch):
        """The escape hatch for a consumer whose identity documents this kit never
        heard of."""
        monkeypatch.setenv("CLAUDEKIT_EXTRA_PROTECTED", "RUNBOOK.md: ARCHITECTURE.md ")
        assert is_protected_file("docs/RUNBOOK.md")
        assert is_protected_file("ARCHITECTURE.md")
        assert set(PROTECTED_PATTERNS) <= set(protected_patterns())

    @pytest.mark.parametrize("hostile", [
        "!README.md", "-README.md", "^README.md", "README.md=0", "NONE", "none",
        "", "   ", ":::", "\t: \n", "*", "[", "[a-", "README.md",
    ])
    def test_extra_protected_cannot_narrow(self, monkeypatch, hostile):
        """The widen-only claim, exercised against values that would EXERCISE a
        narrowing branch if one existed.

        The previous version of this test set a value with no narrowing token in it
        ("RUNBOOK.md: ARCHITECTURE.md"), so it asserted the property without ever
        reaching the code that could violate it. Review mutation-tested it: three
        separate narrowing implementations -- `!name` removes a default, a `NONE`
        sentinel empties the list, extras shadow defaults -- ALL survived it, 24
        passed. A test that its own bug class walks straight through is not a test.

        `[` and `[a-` are here because an unterminated character class is a known
        fnmatch footgun; CPython treats a dangling `[` as a literal, and this pins
        that no exception escapes.
        """
        monkeypatch.setenv("CLAUDEKIT_EXTRA_PROTECTED", hostile)
        assert is_protected_file("README.md"), (
            f"CLAUDEKIT_EXTRA_PROTECTED={hostile!r} unprotected a default")
        assert is_protected_file("docs/deep/CHANGELOG.md")
        assert set(PROTECTED_PATTERNS) <= set(protected_patterns())

    def test_extra_protected_does_not_outlive_its_setting(self, monkeypatch):
        monkeypatch.setenv("CLAUDEKIT_EXTRA_PROTECTED", "RUNBOOK.md")
        assert is_protected_file("docs/RUNBOOK.md")
        monkeypatch.delenv("CLAUDEKIT_EXTRA_PROTECTED")
        assert not is_protected_file("docs/RUNBOOK.md")


class TestConstants:
    """Tests for shared constants."""

    def test_version_format(self):
        from shared import __version__
        parts = __version__.split('.')
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_protected_patterns_not_empty(self):
        assert len(PROTECTED_PATTERNS) > 0


class TestValidatorImport:
    """Tests that the validator module can be imported."""

    def test_import_validator(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, 'validate_json_config')
        assert hasattr(mod, 'detect_config_format')

    def test_detect_modern_format(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.detect_config_format({"operations": []}) == "modern"
        assert mod.detect_config_format({"files": []}) == "legacy"
        assert mod.detect_config_format({}) == "unknown"


class TestSchemaValidation:
    """Tests for JSON schema validation."""

    def test_schema_file_exists(self):
        schema_path = os.path.join(SCRIPTS_DIR, "operations-schema.json")
        assert os.path.exists(schema_path)

    def test_schema_valid_json(self):
        schema_path = os.path.join(SCRIPTS_DIR, "operations-schema.json")
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        assert "$schema" in schema
        assert schema["type"] == "object"

    def test_schema_supports_both_formats(self):
        schema_path = os.path.join(SCRIPTS_DIR, "operations-schema.json")
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        assert "oneOf" in schema
        formats = schema["oneOf"]
        assert len(formats) == 2
        # Check legacy has "files"
        assert any("files" in f.get("properties", {}) for f in formats)
        # Check modern has "operations"
        assert any("operations" in f.get("properties", {}) for f in formats)


class TestConfigValidation:
    """Tests for config file validation."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_config(self, config, filename="ops.json"):
        path = os.path.join(self.tmpdir, filename)
        with open(path, 'w') as f:
            json.dump(config, f)
        return path

    def _write_file(self, content, filename):
        path = os.path.join(self.tmpdir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_missing_config_file(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        valid, errors = mod.validate_json_config("/nonexistent/ops.json")
        assert not valid
        assert any("does not exist" in e for e in errors)

    def test_invalid_json(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        path = os.path.join(self.tmpdir, "bad.json")
        with open(path, 'w') as f:
            f.write("not json")

        valid, errors = mod.validate_json_config(path)
        assert not valid
        assert any("JSON syntax" in e for e in errors)


class TestFileOperationsValidation:
    """Tests for file operation guards."""

    def test_protected_file_deletion_blocked(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        operations = [
            {"type": "file_delete", "path": "README.md", "reason": "Want to delete this markdown file"}
        ]
        valid, errors = mod.validate_file_operations(operations)
        assert not valid
        assert any("protected" in e.lower() for e in errors)

    def test_deletion_reason_too_short(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        operations = [
            {"type": "file_delete", "path": "test.txt", "reason": "short"}
        ]
        valid, errors = mod.validate_file_operations(operations)
        assert not valid
        assert any("too short" in e.lower() for e in errors)

    def test_max_deletions_exceeded(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "validate_config_json",
            os.path.join(SCRIPTS_DIR, "validate-config-json.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        operations = [
            {"type": "file_delete", "path": f"file{i}.txt", "reason": "Removing unused test file number " + str(i)}
            for i in range(4)
        ]
        valid, errors = mod.validate_file_operations(operations)
        assert not valid
        assert any("too many" in e.lower() for e in errors)
