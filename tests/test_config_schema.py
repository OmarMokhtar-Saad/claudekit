"""config.schema.json actually constrains the config, not just its root.

The schema shipped with `additionalProperties: false` on the ROOT object only. Every
nested object -- each hook's option block, `global`, `project`, `security` -- accepted
arbitrary keys, so a misspelled option validated clean and then did nothing at runtime.
Measured before the fix: injecting `hooks["pre-commit"]["enabeld"] = True` validated
successfully.

The rejection tests below are the point of this file. `jsonschema` is a TEST dependency
(tests/requirements.txt) and is imported directly rather than via importorskip: a skip
here would restore exactly the silent pass this file exists to remove. It is imported
lazily and optionally by src/claudekit/cli/main.py:170 (inside try/except ImportError)
and must never become a hard runtime dependency.
"""

import copy
import json
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO / "config.schema.json"
CONFIG_PATH = REPO / ".claude" / "hooks" / "config.json"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_schema_is_valid_draft7(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_shipped_config_validates(schema, config):
    """Tightening a schema is only safe if the real config still passes it.

    The shipped config carries keys the schema did not declare before this change
    (`description` on five hooks, `tools` on post-tool-use); a naive tightening
    rejected it. This asserts the declared key set is a superset of the real one.
    """
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(config),
                    key=lambda e: list(e.path))
    assert errors == [], "; ".join(
        f"{'/'.join(str(x) for x in e.path) or '<root>'}: {e.message}" for e in errors)


@pytest.mark.parametrize("path,bad_key", [
    (("hooks", "pre-commit"), "enabeld"),
    (("hooks", "pre-push"), "blockng"),
    (("hooks", "post-tool-use"), "tool"),
    (("global",), "logLvl"),
    (("project",), "buld_cmd"),
    (("security",), "safemode"),
])
def test_misspelled_nested_key_is_rejected(schema, config, path, bad_key):
    """A typo in a NESTED object must fail validation.

    Before the fix every one of these validated clean, so `enabeld: false` read as
    "enabled: true (default)" and the hook ran anyway. Removing
    `additionalProperties: false` from the corresponding object flips this test.
    """
    mutated = copy.deepcopy(config)
    node = mutated
    for part in path:
        node = node.setdefault(part, {})
    node[bad_key] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(mutated, schema)


def test_misspelled_hook_name_is_rejected(schema, config):
    """`hooks` enumerates every hook it configures, so a typo'd hook NAME is a typo,
    not an extension point. Adding a genuinely new hook means declaring it here."""
    mutated = copy.deepcopy(config)
    mutated["hooks"]["pre-comit"] = {"command": "echo hi", "enabled": True}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(mutated, schema)


def test_unknown_root_key_still_rejected(schema, config):
    """Regression guard on the constraint that already worked."""
    mutated = copy.deepcopy(config)
    mutated["hookz"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(mutated, schema)
