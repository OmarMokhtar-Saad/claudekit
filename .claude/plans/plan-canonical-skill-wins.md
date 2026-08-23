# plan-canonical-skill-wins — install.sh must not overwrite a canonical skill with a templates/ copy

## The bug (measured, not inferred)

`install.sh --full` copies skills in two passes: `.claude/skills/*/` first (lines 210-217),
then `templates/skills/*/` (lines 218-227) into the **same** destination. The second pass wins.

13 skill names exist in both trees. Three have diverged. For two of them the
`templates/` copy is the newer one, so the race is benign by luck. For
`token-optimization` it is not:

| skill | `.claude/skills` | `templates/skills` | ships |
|---|---|---|---|
| incident-response | 180 lines, 2026-03-16 | 350 lines, 2026-04-12 | templates (newer) |
| spec-driven-development | 214 lines, 2026-03-16 | 221 lines, 2026-04-12 | templates (newer) |
| **token-optimization** | **219 lines, 2026-08-19** | **147 lines, 2026-04-12** | **templates (STALE)** |

Proof, on a real install rather than by reading the script:

```
$ T=$(mktemp -d); bash install.sh --full "$T"
$ wc -l "$T"/.claude/skills/token-optimization/SKILL.md   # 147
$ diff -q "$T"/.claude/... templates/skills/token-optimization/SKILL.md   # identical
$ diff -q "$T"/.claude/... .claude/skills/token-optimization/SKILL.md     # differ
```

So every `--full` install since 2026-08-19 has shipped the April
`token-optimization`, silently discarding the token-efficiency pass. The repo's own
gates cannot see this: `gen-registry.py`, `gen-docs.py` and `check-context-floor.py`
all read `.claude/skills/`, which is the copy that loses.

This is arch finding F-11 ("which version wins depends on copy order") turning from a
hazard into a live regression. It is a subset of task 008, but 008 is a 1.5-2 week
epic gated on an owner sign-off; the copy-order fix is neither.

## Fix

The canonical tree wins. In the `templates/skills` pass, skip any skill name that
`.claude/skills/` already provided. `templates/skills` keeps its one genuinely unique
entry (`i18n-workflow`), so the installer still delivers everything it delivers today
— only the 13 overwrites stop.

Deliberately NOT in scope (both owner-gated, both task 008):
- deleting `templates/skills/`, or the 13 duplicate directories;
- reconciling the three diverged bodies — `incident-response` and
  `spec-driven-development` would REGRESS under this fix, because the newer text lives
  on the losing side. This plan does not touch their content; it makes the winner
  deterministic and names the two files whose canonical copy is now the stale one.
  Recorded in .ai/BACKLOG.md as the follow-up, because a content merge is a judgement
  about prose, not a copy-order fix.

## Files

- `install.sh` — one guard in the templates/skills loop.
- `tests/test_install.py` — a test that fails on the shipped installer.

## Mutation proof

The test asserts the installed `token-optimization/SKILL.md` is byte-identical to
`.claude/skills/token-optimization/SKILL.md`. Reverting the guard makes it fail
(installed copy is the 147-line templates one). It binds on content, not on presence:
a presence assertion passes both before and after, which is the vacuous-gate shape
this repo has shipped twice.

---

## Review round 1: REJECTED — 62/100 (adversarial, verified by execution)

The diagnosis and the mechanism survived: guard clean under shellcheck and bash 3.2.57,
`CLAUDE_SRC` correctly in scope, `--minimal` unaffected, `i18n-workflow` still installed and
reconciled, `ck doctor --strict` 26/26 100/100 on the patched install, all four gates green,
and the mutation proof is real (test-only arm RED, guard arm GREEN). The reviewer could not
break the guard.

**Rejected on payload, not engineering.** The plan waved the other two diverged skills through
as "older prose". They are not prose:

- **[BLOCKING] `spec-driven-development`.** `install.sh:194-197` copies `templates/commands/*.md`
  UNCONDITIONALLY, so `/specify`, `/clarify`, `/checklist`, `/analyze` ship in every install and
  all four read and write `.specify/`. The only non-command file documenting `.specify/` and the
  8-step command mapping is the **templates** skill body — the one this guard stops shipping. The
  canonical body directs the model to `.claude/specs/<feature>.md`, a path no shipped command
  touches, and never names the four commands. Measured on the patched install: `.specify/` → 0
  occurrences, `/specify` → 0. So the fix trades a silent staleness in one skill for a silent
  command/skill contract break in another. New class: `fix-trades-one-silent-staleness-for-another`.
- **[MAJOR] `incident-response`.** Not 170 fewer lines of the same document — a structurally
  different one. Lost from the installed tree: the 6-phase lifecycle, SEV-1..SEV-4 definitions,
  three comms templates, and the whole **`## Rollback Procedures`** section with its concrete
  `kubectl rollout undo` / `aws ecs update-service` / `heroku releases:rollback` steps. Gained:
  War Room Coordination, On-Call Runbook Patterns, Escalation Triggers (canonical-only). Dropping
  the executable half of an incident skill is the wrong direction.
- **[MAJOR] No CHANGELOG op.** This change alters the CONTENTS of installed skills, which is
  user-visible; `.ai/BACKLOG.md` is maintainer-facing and the audience split is strict.
- **[MINOR]** ×3: the test's `if not os.path.isfile(canonical): continue` hides exactly the
  failure the test exists to catch (assert instead); the guard should key on
  `-f "$CLAUDE_SRC/skills/$name/SKILL.md"` rather than the directory, since a canonical dir with
  no `*.md` would suppress the templates copy AND install nothing; `dupes` should also check the
  templates side is a directory.

**Route to approval** (reviewer expects to approve): promote the already-shipping templates
bodies into `.claude/skills/` in this same change, so canonical genuinely IS canonical and the
guard is correct by construction. That is preserving the status quo of what every install has
delivered since April, not a prose judgement — with one open question the reviewer did not
address: a straight copy DISCARDS the canonical-only sections (War Room Coordination, On-Call
Runbook Patterns, Escalation Triggers), which today ship nowhere because templates wins the
race. Union-append them instead of overwriting, or lose them deliberately. **Owner call.**

## Round 2 — what changed, and the one place I did not take the reviewer's advice

- **B1 / M1 resolved by promotion, as asked.** `.claude/skills/` becomes genuinely canonical:
  both bodies are replaced with the text every install has actually shipped since April, so
  the guard is correct by construction rather than by exemption.
- **`incident-response` is a UNION, not a copy.** A straight copy would have discarded War Room
  Coordination and On-Call Runbook Patterns (with its Escalation Triggers) — canonical-only
  sections that ship nowhere today precisely *because* templates wins the race. The promoted
  body is the templates text (phases, severities, comms templates, `## Rollback Procedures`)
  plus those canonical-only sections. 180 → 440 lines.

  Round 3 retracts this bullet's earlier claim of "nothing lost from either side" — the
  first union DID silently drop three canonical sections, and the review caught what I
  had asserted without diffing heading sets. One was load-bearing: the four-role
  response table (IC / Technical Lead / Communications Lead / Scribe). Without it the
  appended war-room rules ("IC moderates", "no production changes without IC approval")
  referenced a role the merged body never defined, and three of the four roles vanished
  entirely — so the skill no longer said what an incident response team IS. Also
  restored: the Post-Mortem Rules, whose **Blameless** norm is the load-bearing cultural
  rule of an incident skill and which the promoted body has no equivalent for.

  Two escalation clocks were reconciled at the same time: the promoted severity table
  engages engineering leadership immediately for SEV-1, while the appended Escalation
  Triggers table engaged them only after 60 unresolved minutes — two incompatible
  instructions for the same page. The trigger row now reads SEV-2, and the appended
  duplicate status template is a cross-reference to the one the promoted body defines,
  keeping only the cadence rule. `SEV1`/`SEV2` spellings normalised to `SEV-N`.

  The durable lesson: a union preserves TEXT, not CONSISTENCY, and "nothing lost" is a
  claim that requires diffing heading sets rather than comparing line counts.
- **`spec-driven-development` is a straight promotion, deliberately NOT a union.** The canonical
  body's distinctive content is a competing `## Spec Format` (Actors/Inputs/Outputs/Behavior/
  Invariants) built around `.claude/specs/`. Appending it would reinstate the contradiction this
  change exists to remove — two spec formats and two directory conventions in one skill. The
  whole finding was that the installed workflow must have exactly one shape.
- **Frontmatter is preserved from the canonical copy in both** (`user-invocable: false` on
  incident-response, `disable-model-invocation`/`argument-hint`/`allowed-tools` on
  spec-driven-development, and both descriptions). That is the registry contract —
  `gen-registry.py` reads it — so promoting the body must not smuggle in a frontmatter change.
- **M2:** CHANGELOG `### Fixed` op added, naming both the skill that improves and the two whose
  bodies change.
- **m1/m2/m3:** the test's `continue` is now an `assert` with the canonical-dir-without-SKILL.md
  reason spelled out; the guard keys on `-f "$CLAUDE_SRC/skills/$name/SKILL.md"`; `dupes` checks
  both sides are directories.

## Artifacts this change writes

- `install.sh` — the copy-order guard
- `.claude/skills/incident-response/SKILL.md` — promoted body, unioned with the canonical-only sections
- `.claude/skills/spec-driven-development/SKILL.md` — promoted body, no union
- `tests/test_install.py` — the content-asserting regression
- `CHANGELOG.md` — `[Unreleased] ### Fixed`, because the contents of installed skills change
