"""Every project template ships the Token & Model Policy region, identical to the kit root's.

A new project gets its CLAUDE.md from `templates/<stack>/CLAUDE.md`; before 2026-09-19 the
policy that keeps a session cheap (tiers, no auto review, batched and windowed reads, delegate
broad searches, no wait-for-OK) lived only in the kit root, so every new project started
without it. The region uses the `ck adapt` marker dialect so a later bump can be carried by
the same machinery; its VERSION is pinned to the root's so the two cannot drift silently.
"""
import re
from pathlib import Path

import pytest

from claudekit import adapt as adaptmod

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = sorted((ROOT / "templates").glob("*/CLAUDE.md"))
REGION_ID = "TOKEN-MODEL-POLICY"
START = re.compile(r"<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v(\d+) START -->")
END = re.compile(r"<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v(\d+) END -->")


def region(text):
    starts, ends = START.findall(text), END.findall(text)
    assert len(starts) == 1 and len(ends) == 1, (starts, ends)
    assert starts[0] == ends[0]
    body = text[START.search(text).end():END.search(text).start()]
    return int(starts[0]), body


def bullets(body):
    return [ln for ln in body.splitlines() if ln.startswith("- **")]


ROOT_VERSION, ROOT_BODY = region((ROOT / "CLAUDE.md").read_text(encoding="utf-8"))


def test_the_kit_root_carries_the_current_policy():
    assert ROOT_VERSION == 7
    text = "\n".join(bullets(ROOT_BODY))
    assert "searches go to `explore` (fast tier)" in text, "v7 is the delegate clause"
    assert "batch independent commands in one call" in text
    assert "read files in windows, never whole" in text
    assert '"wait for OK"' in text
    assert len(bullets(ROOT_BODY)) == 5


def test_there_are_templates():
    assert len(TEMPLATES) >= 10, [p.parent.name for p in TEMPLATES]


@pytest.mark.parametrize("path", TEMPLATES, ids=[p.parent.name for p in TEMPLATES])
def test_template_region_equals_the_root_region(path):
    text = path.read_text(encoding="utf-8")
    version, body = region(text)
    assert version == ROOT_VERSION, f"{path.parent.name} is at v{version}, root at v{ROOT_VERSION}"
    assert bullets(body) == bullets(ROOT_BODY), path.parent.name
    assert ".ai/TOKEN_MODEL_POLICY.md" not in body or "ClaudeKit repo" in body, (
        "a template must not point at a file the kit does not install")
    # the region sits before the parallel-agents block, which stays the file's tail
    assert text.index("CLAUDEKIT:TOKEN-MODEL-POLICY") < text.index("CLAUDEKIT:PARALLEL-AGENTS-POLICY")


@pytest.mark.parametrize("path", TEMPLATES, ids=[p.parent.name for p in TEMPLATES])
def test_ck_adapt_parses_the_template_region(path):
    found, _fenced = adaptmod.find_region(path.read_text(encoding="utf-8"), REGION_ID)
    assert found is not None, path.parent.name
    assert found.version == ROOT_VERSION
