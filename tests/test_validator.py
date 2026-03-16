"""Tests for validate-config-json.py"""

import json
import os
import sys
import tempfile
import pytest

# Add scripts to path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

from shared import is_protected_file, PROTECTED_PATTERNS, MAX_FILE_SIZE_BYTES


class TestProtectedFiles:
    """Tests for protected file detection."""

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


class TestConstants:
    """Tests for shared constants."""

    def test_version_format(self):
        from shared import __version__
        parts = __version__.split('.')
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_max_file_size(self):
        assert MAX_FILE_SIZE_BYTES == 2 * 1024 * 1024

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
