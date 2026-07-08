"""Tests for international support."""
import os

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
I18N_DIR = os.path.join(PROJECT_DIR, "i18n")
TEMPLATE_DIR = os.path.join(PROJECT_DIR, "templates")

EXPECTED_LANGUAGES = ["ar", "zh", "es", "fr", "ja", "ko"]


class TestI18nDirectory:
    """Verify i18n directory and files exist."""

    def test_i18n_directory_exists(self):
        assert os.path.isdir(I18N_DIR), "i18n/ directory missing"

    @pytest.mark.parametrize("lang", EXPECTED_LANGUAGES)
    def test_readme_translation_exists(self, lang):
        path = os.path.join(I18N_DIR, f"README.{lang}.md")
        assert os.path.isfile(path), f"README.{lang}.md missing"

    @pytest.mark.parametrize("lang", EXPECTED_LANGUAGES)
    def test_readme_not_empty(self, lang):
        path = os.path.join(I18N_DIR, f"README.{lang}.md")
        assert os.path.getsize(path) > 500, f"README.{lang}.md too small"

    def test_language_count(self):
        readmes = [f for f in os.listdir(I18N_DIR) if f.startswith("README.") and f.endswith(".md")]
        assert len(readmes) >= 6, f"Expected >= 6 translations, found {len(readmes)}"


class TestArabicRTL:
    """Verify Arabic README has RTL support."""

    def test_arabic_has_rtl_dir(self):
        path = os.path.join(I18N_DIR, "README.ar.md")
        with open(path) as f:
            content = f.read()
        assert 'dir="rtl"' in content or "dir='rtl'" in content, "Arabic README missing RTL direction"


class TestLanguageSelectors:
    """Verify all READMEs have language selectors."""

    @pytest.mark.parametrize("lang", EXPECTED_LANGUAGES)
    def test_has_language_selector(self, lang):
        path = os.path.join(I18N_DIR, f"README.{lang}.md")
        with open(path) as f:
            content = f.read()
        assert "English" in content, f"README.{lang}.md missing English link"


class TestTranslateCommand:
    """Verify /translate command exists."""

    def test_translate_command_exists(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "translate.md")
        assert os.path.isfile(path)

    def test_translate_has_frontmatter(self):
        path = os.path.join(TEMPLATE_DIR, "commands", "translate.md")
        with open(path) as f:
            content = f.read()
        assert "description:" in content


class TestI18nSkill:
    """Verify i18n workflow skill."""

    def test_i18n_skill_exists(self):
        path = os.path.join(TEMPLATE_DIR, "skills", "i18n-workflow", "SKILL.md")
        assert os.path.isfile(path)

    def test_i18n_skill_covers_rtl(self):
        path = os.path.join(TEMPLATE_DIR, "skills", "i18n-workflow", "SKILL.md")
        with open(path) as f:
            content = f.read()
        assert "RTL" in content or "rtl" in content
