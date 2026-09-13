# Implementation Plan: Agent skill roles (Phase 2)

## Overview
Generic, fleet-synced agents get project-specific stack skills without forking them. The
kit declares skill ROLES for three agents; a project binds a role to an installed skill
in the existing `roles` map of `.claude/skills-profile.json`; `ck skill roles apply`
writes the resolved ids into each role agent's documented `skills:` frontmatter key,
which Claude Code preloads. No hook, no runtime injection.

**Tier 3** (security-relevant: the profile is repository content that now decides what
gets loaded into agent context). Full pipeline: planner -> reviewer -> implementer.

## Phase 0: Design precheck
Ownership model: the profile (`.claude/skills-profile.json`) is project-owned and is the
only input; the role vocabulary (`ROLE_CATALOG`) is kit-owned, in
`src/claudekit/skill_roles.py`; the generated output is the `skills:` key of three
kit-managed agent files, and nothing else. The value lives in exactly those three files
(`.claude/agents/debugger.md`, `code-reviewer.md`, `tester.md` in an installed project)
plus their hashes in `.claude/.claudekit-manifest.json`. Both sit inside the model:
agent files are covered by the existing receipt re-stamp pattern (`cmd_adapt`
already re-stamps partially-owned files), and the manifest is the only other thing
written. No value sits outside it.

Rejection-brief search (`rejections search "skill roles agent profile"`, exit 0, 10
hits). The one validated match is **fleet-skill-phaseA** ("asserts registry rows no
operation produces"). This plan adds no registry rows: role preloads are project-local,
the kit agents are unchanged, and `gen-registry.py --check` passes on the post-state
(verified below). The other hits (agent-memory-learning, e2e-lane-a,
reflection-lifecycle-gates, retro2-backfill) matched only on the words "agent",
"profile" or "skill" and are about different subsystems. The one lesson that carries
over from e2e-lane-a (mutation-proof overclaim): the mutants below were really applied
and re-run, and each result is recorded.

## How agents load skills today (investigation)
- **Prose, not preload.** Every kit agent has a `## Skill Loading` section: a
  "Mandatory" list and an "On demand" list of bold skill ids. No kit agent uses `skills:`
  frontmatter (grep: zero hits). These are model instructions, not loads.
- **gen-registry.py** derives `skills-registry.json` `agentMapping`/`usedBy` from those
  sections only. It never reads frontmatter.
- **skill_fit.protected_skills** already treats both kinds as protected: skills an agent
  preloads through `skills:` (inline or block list, `agent_preloaded_skills`) and skills
  its section marks mandatory.
- **context_floor** charges agent *descriptions* for every agent, but agent *bodies* only
  for planner, reviewer and implementer (42983/43000). debugger, code-reviewer and tester
  are not pipeline agents, and this plan does not touch any agent body, so the floor does
  not move.
- **Claude Code**: sub-agent `skills:` frontmatter preloads the full skill content at
  spawn. `skillOverrides` can only hide skills; it cannot preload one.
- **Frontmatter guards**: `tests/test_behavior_spec.py::TestAgentRegistration` allows only
  `name, description, model, color, tools, memory` keys, and
  `tests/test_agent_frontmatter.py` requires key lines. Both run on the kit tree, which
  keeps shipping no `skills:` key. The generated key is documented Claude Code syntax
  and is a valid key line.

## Mechanism decision (and rejected alternatives)
Chosen: **a deterministic generator writes the documented `skills:` key into the
installed role agents, and re-stamps the install receipt.**

| Option | Why not |
|--------|---------|
| Runtime injection hook (SessionStart / PreToolUse) | Owner preference against it. It is also not deterministic, and it is invisible to `ck diff`. |
| Static pointer in the agent body ("read the resolved roles file and load its skills") | That is prose, not a load: exactly what `test_skill_loading_contract.py` says is not enforcement. It also adds body tokens to every agent. |
| Generated per-project overlay agent (same name, other file) | Claude Code resolves one project agent per name in `.claude/agents/`, so there is no slot for an overlay. A differently named agent would break coordinator routing. |
| New `skill-roles:` frontmatter key in kit agents | Undocumented key. It breaks `TestAgentRegistration.KNOWN_KEYS`, and we have not verified how Claude Code treats unknown keys. The catalog goes in Python instead. |
| Roles catalog as a JSON file under `.claude/agents/_shared/` | install.sh copies only `_shared/*.md`, so the file would never reach a project. |

## Scope
- **In scope:** the role catalog for `debugger`, `code-reviewer` and `tester`; the verbs
  `ck skill roles list|check|apply`; re-apply on `ck init`/`ck update`; a `ck doctor`
  check; install-receipt re-stamping; tests; `docs/cli.md`; CHANGELOG.
- **Out of scope:** roles for the other 19 agents; `profile init` suggesting bindings
  from detected stacks; fleet-sync awareness (a sync overwrites the key, and doctor warns
  about it); binding arbitrary overlay files (a preload names skills only, so the only
  accepted path form is `.claude/skills/<id>/SKILL.md`); `.ai/` SESSION_STATE
  (maintainer updates it after execution); agent-memory writes.

## Prerequisites
- Base: origin/main with PR #42 (`skills-profile.json`, `ck skill apply`,
  `skill_fit.protected_skills`, `agent_preloaded_skills`).

## Implementation Steps

### Step 1: Role resolver and generator
- **File:** `src/claudekit/skill_roles.py`
- **Action:** Create
- **Details:**
  - `ROLE_CATALOG` maps each agent to its roles, in preload order:
    - debugger: debugging-method, stack-debugging, project-gotchas
    - code-reviewer: review-checklist, project-gotchas
    - tester: test-framework, project-gotchas
  - `ROLE_DESCRIPTIONS` describes each role.
  - `resolve(root)` validates every binding before anything is written. It refuses:
    - an unknown role
    - a non-string or empty value, or more than `MAX_SKILLS_PER_ROLE`=2 skills
    - a path other than exactly `.claude/skills/<id>/SKILL.md`: absolute paths, `..`,
      and other files are all refused
    - a skill that is not installed, or whose resolved path (through symlinks) is
      outside `.claude/skills/`
    - a skill with `disable-model-invocation`
    - a skill in the profile's `disabled` list
    - more than `MAX_SKILLS_PER_AGENT`=4 skills for one agent
  - `with_skills(text, names)` replaces only the frontmatter `skills:` key (inline or
    block form) and appends `skills: [a, b]`. With `[]` the key is removed, and a kit
    agent comes back byte-identical.
  - `apply(root)` checks everything first, then writes each agent atomically. It
    re-stamps `agents/<a>.md` in the manifest only when the recorded hash equals the
    found file's hash, or that hash with the key stripped (this also recovers from a
    lost receipt write). Otherwise the agent is reported `not_restamped`. `apply` is
    refused in the kit source tree.
  - `findings(root)` returns errors, drift warnings and the bound count, for `check` and
    doctor.

### Step 2: CLI, re-apply, doctor
- **File:** `src/claudekit/cli/main.py`
- **Action:** Modify (5 edits in one op)
- **Details:**
  - `_reapply_skill_profile` runs `skill_roles.apply` before the disabled pass. A
    preloaded skill is then protected, so the two passes agree on conflicts. It prints
    only when something is bound or written, and never fails the install.
  - doctor gets a "Skill roles" check between "Skills profile" and "Skill visibility".
    It is reported only when a binding exists or an agent drifted, and it is skipped
    when the profile itself failed.
  - `_cmd_skill_fit` dispatches `roles` to the new `_cmd_skill_roles`, which sits inside
    the existing `try`, so a `SkillFitError` exits 1 with the cause.
  - argparse: the `action` choices gain `roles`, and the `name` help lists
    `list|check|apply`.

### Step 3: Behavioral tests
- **File:** `tests/test_skill_roles.py`
- **Action:** Create (30 tests)
- **Details:** Tests build real tmp projects from the kit's own role agent files and
  drive the real CLI.
  - **Kit contract:** role agents ship no `skills:` key; every declared role is
    described; a block-sequence `skills:` key is replaced whole.
  - **Apply:** binding by id and by path; bodies unchanged; manifest re-stamped;
    `ck diff` clean; `protected_skills` only grows; a bound skill cannot then be
    disabled; idempotent; unbinding restores the kit bytes and the original receipt; a
    local edit keeps its old receipt; recovery from a lost receipt write; refusal in the
    source tree.
  - **Hostile profiles (12 cases):** each is refused with the tree digest unchanged,
    including a symlink escape and a disabled binding.
  - **check and doctor:** pass, warn and fail; a profile with no roles adds no check;
    `list`.
  - **Real install:** `install.sh`, bind, `ck update`; the preloads survive and
    `ck diff` stays clean.

### Step 4: User docs
- **File:** `docs/cli.md`
- **Action:** Modify. A new section, `claudekit skill roles list / check / apply`, goes
  before the `mcp add` section.

### Step 5: Changelog
- **File:** `CHANGELOG.md`
- **Action:** Modify. A new entry at the top of `[Unreleased]`.

## Ops mapping
`.claude/plans/ops-agent-skill-roles.json`: 5 operations, one phase (under 15, no split).
1. file_create `src/claudekit/skill_roles.py` (Step 1)
2. code_edit `src/claudekit/cli/main.py`, 5 edits (Step 2)
3. file_create `tests/test_skill_roles.py` (Step 3)
4. code_edit `docs/cli.md` (Step 4)
5. code_edit `CHANGELOG.md` (Step 5)

## Testing Strategy (executed on a scratch copy, 2026-09-13)
Scratch copy: the worktree rsynced to the session scratchpad. The ops were applied with
`execute-json-ops.py --no-approval`: 5/5 successful.
- `pytest tests/test_skill_roles.py`: all pass, including the real install/update test.
- **Mutation proofs.** Each mutant was applied with sed and the suite re-run (without the
  install test). Every one was killed:
  - symlink containment check -> 1 failed
  - disabled-skill refusal -> 2 failed
  - restamp condition forced true -> 1 failed
  - `disable-model-invocation` refusal -> 1 failed
  - block-item stripping -> survived at first, so a test was added -> 1 failed
  - `SKILL.md` filename check -> survived at first, so a test was added -> 1 failed
- Gates on the post-state:
  - `ruff check` passed
  - `mypy`: no issues
  - `gen-docs --check`, `gen-registry --check`, `gen-model-policy --check` and
    `check-context-floor --check` were all OK
- Full suite: see the report accompanying this plan.
- Validation commands for the implementer after execution: every command in CLAUDE.md
  "Commands", plus `ck skill roles list`.

## Rollback Plan
- Code: the engine backup (`backups/agent-skill-roles-<ts>/`), or `git revert` of the
  commit. The change is purely additive, and deleting `skill_roles.py` plus reverting
  the 5 main.py edits restores the previous behavior.
- Projects that already ran `apply`: bind nothing (`"roles": {}`) and run
  `ck skill roles apply`. This restores the kit bytes and the original receipt hashes
  (tested). `ck update` also restores kit agents.

## Risk Assessment
- **High:**
  - **The profile controls what enters agent context.** Mitigations: bindings can only
    add, and only installed, model-visible skills inside `.claude/skills/`. Refusal is
    whole and happens before any write. Mandatory prose is untouched, and a bound skill
    becomes protected. Still, a hostile PR can bind a *malicious project skill*: a new
    `.claude/skills/evil/SKILL.md` in the same PR is "installed". That is the same trust
    as any committed project skill, which the model can already invoke. The difference
    is that a preload loads it without a trigger. It stays a speed bump, not a sandbox
    (hard rule 6).
  - **Writing kit-managed files plus the receipt.** A wrong re-stamp would hide a local
    edit from `ck diff`. Mitigation: re-stamp only when the file matches its receipt, or
    matches it with the generated key stripped. Covered by the tests and a mutant.
- **Medium:**
  - `cli/main.py` is a hub (2.8k lines, every verb), but the edits are local.
  - A fleet sync or a manual copy clobbers the key, and doctor warns.
  - Preloads cost full skill bodies on every spawn. Capped at 4 per agent, and `apply`
    prints the tokens.
  - The key is appended at the end of the frontmatter.
- **Low:** docs and changelog text; context floor unchanged (non-pipeline agents, no
  body change).

## Uncertainties (surface to owner)
1. We have not verified against current Claude Code docs whether a
   `disable-model-invocation` skill can be preloaded through `skills:`. The plan refuses
   it (fail closed), and relaxing that is a one-line change.
2. The role catalog lives in Python, not in the agent files. The owner's phrasing was
   "agents declare roles". Moving the declaration into frontmatter needs the
   unknown-key question answered first, and `KNOWN_KEYS` widened.
3. Overlay *files* cannot be preloaded (`skills:` takes names). Only the
   `.claude/skills/<id>/SKILL.md` form is accepted, so the existing `overlays` map stays
   separate.
4. A block-form `skills:` a user adds by hand to a role agent is owned and overwritten by
   the generator (documented in the module docstring).
