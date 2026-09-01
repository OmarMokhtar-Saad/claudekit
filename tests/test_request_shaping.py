"""Behavioral tests for the request-shaping skill and its /ask command.

Three things can silently break this pair:

1. The skill loses `disable-model-invocation: true`. It would then start
   charging the "skill descriptions" floor category, which had 183 chars of
   headroom when this shipped -- so the charge would land as a confusing
   floor-gate failure in an unrelated commit rather than here.
2. The block format drifts between the skill that defines it and the command
   that emits it. Nothing else compares the two.
3. /ask grows a step that runs the next command, which would move a code change
   in front of the approval gate.
4. The skill directory is created without a skills-registry.json entry, which fails
   `gen-registry.py --check`. That is not hypothetical -- it is exactly what review
   round 1 caught, so the gate is asserted here rather than left to CI.

The first four are asserted by executing the real functions and the real gates. The
last two tests are unavoidably prose assertions: these artifacts ARE prompts, and the
only executable property of a prompt is its text. They are documented as weak rather
than dressed up as behavioral.
"""
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SKILL = os.path.join(REPO_ROOT, '.claude', 'skills', 'request-shaping', 'SKILL.md')
COMMAND = os.path.join(REPO_ROOT, '.claude', 'commands', 'ask.md')
FLOOR_GATE = os.path.join(REPO_ROOT, 'scripts', 'check-context-floor.py')
REGISTRY_GATE = os.path.join(REPO_ROOT, 'scripts', 'gen-registry.py')
DOCS_GATE = os.path.join(REPO_ROOT, 'scripts', 'gen-docs.py')
PLAN_INDEX_GATE = os.path.join(REPO_ROOT, 'scripts', 'gen-plan-index.py')
REGISTRY = os.path.join(REPO_ROOT, '.claude', 'skills', 'skills-registry.json')

sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))
from claudekit import context_floor  # noqa: E402

#: The Shaped Request block contract. Both files must agree on every field.
BLOCK_FIELDS = (
    'TASK:', 'SCOPE:', 'TIER:', 'CONSTRAINTS:', 'DONE WHEN:', 'READ FIRST:', 'ASSUMED:',
)


def run(script, *args):
    return subprocess.run([sys.executable, script, *args], capture_output=True,
                          text=True, cwd=REPO_ROOT)


def read(path):
    with open(path) as f:
        return f.read()


def test_skill_is_model_invisible():
    """Invisible => zero always-on cost. See context_floor.model_invisible()."""
    fm = context_floor.frontmatter(read(SKILL))
    assert context_floor.model_invisible(fm), (
        'request-shaping must keep `disable-model-invocation: true`; without it the '
        'skill charges the "skill descriptions" floor category, which is near budget.'
    )


def test_skill_costs_the_floor_nothing():
    """The measurement itself must exclude it, not just the frontmatter flag."""
    sizes = context_floor.measure(REPO_ROOT)
    desc = context_floor.description_span(context_floor.frontmatter(read(SKILL)))
    assert desc, 'skill must still have a description for humans and docs'
    assert sizes[context_floor.SKILL_CATEGORY] <= \
        context_floor.BUDGETS[context_floor.SKILL_CATEGORY]
    # Charged nothing: removing its length changes no verdict because it was never added.
    admitted, _ = context_floor.check_new_skill(REPO_ROOT, desc, invisible=True)
    assert admitted is None, admitted


def test_floor_gate_still_passes():
    r = run(FLOOR_GATE)
    assert r.returncode == 0, r.stdout + r.stderr


def test_skill_is_registered():
    """Creating the SKILL.md registers nothing; the generator must have been run.

    gen-registry.py --check emits UNREGISTERED for any skill directory with no
    registry entry. Review round 1 rejected this plan for exactly that gap, so the
    gate is asserted in the suite instead of being discovered at commit time.
    """
    entries = json.load(open(REGISTRY)).get('skills', [])
    ids = {e['id'] for e in entries}
    assert 'request-shaping' in ids, (
        'request-shaping is on disk but absent from skills-registry.json. '
        'Run: python3 scripts/gen-registry.py'
    )


def test_registry_gate_still_passes():
    r = run(REGISTRY_GATE, '--check')
    assert r.returncode == 0, r.stdout + r.stderr


def test_docs_gate_still_passes():
    r = run(DOCS_GATE, '--check')
    assert r.returncode == 0, r.stdout + r.stderr


def test_plan_index_gate_still_passes():
    """CI runs this (.github/workflows/ci.yml) and the suite did not.

    Adding plan-request-shaping.md left .claude/plans/INDEX.md stale, which turns CI red
    while all 7061 tests pass -- a fifth generator gate escaping review after three
    others already had. Asserted here so the suite carries the signal.
    """
    r = run(PLAN_INDEX_GATE, '--check')
    assert r.returncode == 0, r.stdout + r.stderr


def test_command_description_is_within_its_budget():
    sizes = context_floor.measure(REPO_ROOT)
    assert sizes['command descriptions'] <= context_floor.BUDGETS['command descriptions']


def test_block_contract_is_defined_in_the_skill():
    text = read(SKILL)
    missing = [f for f in BLOCK_FIELDS if f not in text]
    assert not missing, f'skill omits Shaped Request fields: {missing}'


def _fenced_blocks(text):
    """Every ``` fenced block in `text`, bodies only."""
    return re.findall(r'(?ms)^```[^\n]*\n(.*?)^```', text)


def test_command_and_skill_agree_on_the_block():
    """Any block ask.md restates must carry the full field set, not a subset.

    The first version of this test was `delegates or restates_fully`, where
    `delegates` merely checked that the strings 'request-shaping' and 'Shaped Request
    block' appear in ask.md. Both appear permanently, so the left side was always True
    and the right side was never evaluated -- the test could not fail for the reason
    its own message gave. Mutation-proved: a fenced block restating four fields with
    DONE WHEN renamed to SUCCESS passed it.

    Now the check is unconditional. Delegation is still allowed (ask.md may name the
    skill and print no block of its own), but any fenced block that looks like the
    Shaped Request block -- it mentions TASK: -- must carry every field.
    """
    cmd = read(COMMAND)
    assert 'request-shaping' in cmd, 'ask.md must name the skill that defines the block'
    for body in _fenced_blocks(cmd):
        if 'TASK:' not in body:
            continue
        missing = [f for f in BLOCK_FIELDS if f not in body]
        assert not missing, (
            f'ask.md restates the Shaped Request block but omits {missing}; a partial '
            f'restatement is how the two drift apart. Either list every field or drop '
            f'the block and delegate to request-shaping.'
        )


def test_question_budget_is_three():
    """Both files must state the same cap, and no larger one anywhere.

    A prose assertion, and a weak one -- but the cap exists only as prose, so the
    alternative is not asserting it at all. Scanning for a *competing* number is what
    makes it more than a keyword check: raising the cap in one file trips this even
    if the word "three" survives elsewhere in the same file.
    """
    competing = re.compile(r'(?i)(?:maximum|at most|up to)\s+'
                           r'(?!three\b)(\w+)\s+questions?')
    for path in (SKILL, COMMAND):
        text = read(path)
        assert re.search(r'(?i)(?:maximum|at most)\s+three\s+questions?', text), (
            f'{path} must state the three-question cap explicitly')
        assert not competing.search(text), (
            f'{path} states a question cap other than three: '
            f'{competing.search(text).group(0)!r}')


def test_ask_names_the_next_step_without_running_it():
    cmd = read(COMMAND).lower()
    assert 'do not run it' in cmd, (
        '/ask must hand back after naming the next step; running it would put a code '
        'change in front of the approval gate (hard rule 5).'
    )


def test_tier_is_derived_not_asked():
    """The tier must be stated as derived in both files, with the routing table that
    makes derivation possible. Asserting the table too means deleting it fails here,
    rather than silently leaving the instruction unfollowable."""
    for path in (SKILL, COMMAND):
        text = read(path)
        assert re.search(r'(?i)never ask.{0,40}tier|tier.{0,40}never ask', text), (
            f'{path} must say the tier is never asked for')
    skill = read(SKILL)
    for tier in ('Tier 1', 'Tier 2', 'Tier 3'):
        assert tier in skill, f'skill must define {tier} for the tier to be derivable'


def test_skill_frontmatter_parses():
    fm = context_floor.frontmatter(read(SKILL))
    assert re.search(r'(?m)^name:[ \t]*request-shaping[ \t]*$', fm)
