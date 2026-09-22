"""fleet-sync.py B4: carry `autoCompactWindow` into every kitted project's settings.json.

The setting is what holds a session under 200K context (measured 2026-09-19: 85% of billed
tokens were turns already above 200K). install.sh copies settings.json on a fresh install;
fleet-sync never touched it, so an install kitted before the setting existed was missed.

Rules pinned here: insert only when the key is ABSENT; never overwrite a present value, equal
or different; a textual insertion that leaves the rest of the file byte-for-byte as it was;
dry-run writes nothing; a file that is not valid JSON is left alone.
"""
import importlib.util
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "operations" / "scripts" / "fleet-sync.py"


def load():
    spec = importlib.util.spec_from_file_location("fleet_sync_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fs = load()
WINDOW = 100000


def project(tmp_path, text=None):
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    if text is not None:
        (tmp_path / ".claude" / "settings.json").write_text(text, encoding="utf-8")
    return str(tmp_path)


def settings_text(tmp_path):
    return (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")


PRETTY = '{\n  "permissions": {\n    "allow": ["Bash(ls:*)"]\n  },\n  "hooks": {}\n}\n'


def test_the_kit_settings_json_is_the_producer():
    assert fs.read_autocompact_window(str(ROOT / ".claude" / "settings.json")) == WINDOW


def test_absent_settings_file_is_skipped(tmp_path):
    key, line = fs.carry_autocompact_window(project(tmp_path), WINDOW, dry=False)
    assert key == "skipped" and "absent" in line
    assert not (tmp_path / ".claude" / "settings.json").exists(), "never creates a settings.json"


def test_absent_key_is_inserted_first_and_nothing_else_moves(tmp_path):
    key, line = fs.carry_autocompact_window(project(tmp_path, PRETTY), WINDOW, dry=False)
    assert key == "edited" and "+autoCompactWindow=100000" in line
    text = settings_text(tmp_path)
    assert text.startswith('{\n  "autoCompactWindow": 100000,\n  "permissions"'), text
    assert text.endswith("}\n"), "the trailing newline is kept"
    merged = json.loads(text)
    assert merged["autoCompactWindow"] == WINDOW
    assert merged["permissions"] == {"allow": ["Bash(ls:*)"]} and merged["hooks"] == {}
    # everything after the first `{` is the original text, untouched
    assert text[text.index('"permissions"') - 3:] == PRETTY[1:]


def test_indent_follows_the_file(tmp_path):
    fs.carry_autocompact_window(project(tmp_path, '{\n    "hooks": {}\n}\n'), WINDOW, dry=False)
    assert settings_text(tmp_path).startswith('{\n    "autoCompactWindow": 100000,\n    "hooks"')


def test_empty_object_becomes_the_one_key(tmp_path):
    key, _ = fs.carry_autocompact_window(project(tmp_path, "{}\n"), WINDOW, dry=False)
    assert key == "edited"
    assert json.loads(settings_text(tmp_path)) == {"autoCompactWindow": WINDOW}


def test_equal_value_is_skipped_and_the_file_is_untouched(tmp_path):
    before = '{\n  "autoCompactWindow": 100000,\n  "hooks": {}\n}\n'
    key, line = fs.carry_autocompact_window(project(tmp_path, before), WINDOW, dry=False)
    assert key == "skipped" and "already present" in line
    assert settings_text(tmp_path) == before


def test_a_different_value_is_the_operators_and_is_never_overwritten(tmp_path):
    before = '{\n  "autoCompactWindow": 120000,\n  "hooks": {}\n}\n'
    key, line = fs.carry_autocompact_window(project(tmp_path, before), WINDOW, dry=False)
    assert key == "skipped" and "DIFFERS" in line and "120000" in line
    assert settings_text(tmp_path) == before


def test_dry_run_reports_the_edit_but_writes_nothing(tmp_path):
    key, _ = fs.carry_autocompact_window(project(tmp_path, PRETTY), WINDOW, dry=True)
    assert key == "edited"
    assert settings_text(tmp_path) == PRETTY


def test_invalid_json_is_left_alone(tmp_path):
    broken = '{\n  "hooks": {},\n}\n'  # trailing comma
    key, line = fs.carry_autocompact_window(project(tmp_path, broken), WINDOW, dry=False)
    assert key == "skipped" and "not valid JSON" in line
    assert settings_text(tmp_path) == broken


def test_a_non_object_top_level_is_left_alone(tmp_path):
    key, _ = fs.carry_autocompact_window(project(tmp_path, "[]\n"), WINDOW, dry=False)
    assert key == "skipped"
    assert settings_text(tmp_path) == "[]\n"


def test_read_rejects_non_integers(tmp_path):
    for value in ('"200000"', "true", "null", "200000.5"):
        p = tmp_path / f"s{abs(hash(value))}.json"
        p.write_text('{"autoCompactWindow": %s}' % value, encoding="utf-8")
        assert fs.read_autocompact_window(str(p)) is None, value
    assert fs.read_autocompact_window(str(tmp_path / "missing.json")) is None


def test_main_runs_b4_for_every_project():
    src = inspect.getsource(fs.main)
    assert "carry_autocompact_window(" in src, "B4 is defined but main() never calls it"
    assert "read_autocompact_window(" in src
