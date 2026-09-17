"""The always-injected agent prompts stay small, and the moved rules stay findable.

Measured 2026-09-16: every subagent pays ~21-23k tokens before doing any work, of which the
agent file is the only part this repo controls (CLAUDE.md is shared; the skill listing and
MCP schemas are host-controlled). `_shared/INVOCATION.md` is referenced by path, never
injected, so it is deliberately NOT ratcheted here.

This is a ratchet, not a style check: the ceilings sit a few hundred bytes above the real
post-split sizes, so re-inlining a moved block fails. PROVE IT before trusting a green run --
append 1 KB of filler to planner.md and watch `test_agent_prompt_is_under_ceiling` fail. A
ceiling that has never failed measures nothing.

Shrinking is always fine; lowering a ceiling after a deliberate reduction tightens the
ratchet. Raising one needs owner sign-off and a reason recorded here.
"""
import os

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AGENTS = os.path.join(ROOT, '.claude', 'agents')
SHARED = os.path.join(AGENTS, '_shared')

# agent file -> (byte ceiling, companion reference file)
SPLIT = {
    'planner.md': (10000, 'planner-reference.md'),   # post-split: 9779 (was 13644, -28.3%)
    'reviewer.md': (12400, 'reviewer-reference.md'),  # post-split: 12135 (was 17910, -32.2%)
}

# Rules moved out of the agent files. Each must survive SOMEWHERE (agent file or its
# companion) -- this is what makes the split a move and not a deletion.
MOVED_RULES = {
    'planner.md': (
        'Max 3 `file_delete` operations per config (GUARD 26)',
        'PLAN BRIEF (Complex)',
        'HANDOFF TO: reviewer',
        'PLANNER COMPLETE',
        '**Every ops.json MUST pass `validate-config-json.py`**',
        '## Risk Assessment',
    ),
    'reviewer.md': (
        'Separation of concerns',
        'Configuration security',
        'Step 4: Security Review',
        'NEVER approve a plan without ops.json',
        'HANDOFF TO: implementer',
        'Bar width: 25 characters',
    ),
}

# Phrases other gates assert against the AGENT FILE ITSELF. The split must not relocate them.
PINNED_IN_AGENT_FILE = {
    'planner.md': (
        'Headless fallback',          # tests/test_behavior_spec.py
        'Silence is NOT evidence',    # tests/test_rejection_briefs.py (exit-code contract)
        '"operations"',               # tests/test_agent_doc_ops_examples.py MIN_EXAMPLES >= 1
    ),
    'reviewer.md': (
        '=== REVIEW ===',             # review-record.py --from-review parser contract
        'HANDOFF_PROTOCOL.md',        # tests/test_single_source_contracts.py
        'Refute',                     # tests/test_behavior_spec.py
        'orchestrated by the command layer',
    ),
}


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


@pytest.mark.parametrize('agent', sorted(SPLIT))
def test_agent_prompt_is_under_ceiling(agent):
    ceiling = SPLIT[agent][0]
    size = os.path.getsize(os.path.join(AGENTS, agent))
    assert size <= ceiling, (
        '%s is %d bytes, ceiling %d. This prompt is injected into every spawn of this '
        'agent; move reference-grade prose into its _shared companion instead of raising '
        'the ceiling.' % (agent, size, ceiling)
    )


@pytest.mark.parametrize('agent', sorted(SPLIT))
def test_reference_companion_exists_and_is_substantial(agent):
    companion = os.path.join(SHARED, SPLIT[agent][1])
    assert os.path.isfile(companion), '%s: missing companion %s' % (agent, companion)
    assert os.path.getsize(companion) > 2000, \
        '%s: companion is suspiciously small -- content was deleted, not moved' % agent


@pytest.mark.parametrize('agent', sorted(SPLIT))
def test_agent_points_at_its_companion(agent):
    body = _read(os.path.join(AGENTS, agent))
    assert SPLIT[agent][1] in body, \
        '%s never names %s -- the moved rules are unreachable' % (agent, SPLIT[agent][1])


@pytest.mark.parametrize('agent,phrase', [
    (a, p) for a, ps in sorted(MOVED_RULES.items()) for p in ps
])
def test_moved_rule_survives_the_move(agent, phrase):
    combined = _read(os.path.join(AGENTS, agent)) + _read(os.path.join(SHARED, SPLIT[agent][1]))
    assert phrase in combined, \
        '%s: rule text vanished in the split: %r' % (agent, phrase)


@pytest.mark.parametrize('agent,phrase', [
    (a, p) for a, ps in sorted(PINNED_IN_AGENT_FILE.items()) for p in ps
])
def test_gate_pinned_phrase_stays_in_the_agent_file(agent, phrase):
    assert phrase in _read(os.path.join(AGENTS, agent)), (
        '%s: %r must stay in the agent file itself -- another gate asserts it there, and '
        'moving it to the companion breaks that gate.' % (agent, phrase)
    )
