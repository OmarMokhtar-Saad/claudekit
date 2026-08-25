# Implementation Plan: round 5 — the sixth axis, and a raise I withdrew

**Status:** EXECUTED 2026-08-25. Tier 3.

Fifth adversarial review of the file-guard allowlist: **3 High, 3 Medium, 1 Low, all
confirmed.** It answered the structural question round 4 posed and the answer was no.

## The claim round 4 made, and the reviewer's verdict on it

Round 4 replaced the hand-written corpus with one that **derives itself from the guard**,
claiming a too-narrow correction would now fail in the round it is written. The reviewer
tested that claim rather than accepting it:

> The derived-corpus claim does NOT hold for this round's change, and there is a sixth axis.

It holds for **branch 8**, whose predicates the extractors read. Round 5's change was to
**branch 12**, and nothing derived anything from there — so branch 12's correction was
covered by twelve hand-picked paths, which is the practice the file's own header calls
"the class". Ten freed paths were found in a minute of probing while 3,623 cases stayed green.

## H1 — the sixth axis: marker POSITION

The export/dump veto matched whole path components, so the marker was invisible in a
basename or a compound directory:

    customer/data/full-dump_model.sql        freed   (literally a dump)
    customer-data/pg_dump/rows_model.sql     freed   (the canonical pg_dump directory)
    customer-data/db-dumps/rows_model.sql    freed   (compound directory)
    customer/data/export-rows_model.json     freed   (marker in the filename)
    extracts/customer_data_model.sql         freed   (the one plural the list omitted)

**And the reviewer named why component-matching was the wrong instinct here**, which is the
part worth keeping: in `public_material()` a component match is *right*, because the path is
being read as a **name assertion** and a substring would over-claim. In branch 12 the marker
is **evidence about content** — "dump" anywhere in the path counts. Opposite semantics, so
opposite matching. Now substrings, plus `archive`.

## H2 — the derived corpus now derives from the branch being changed

The generator learned the lesson one branch too late. It extracts branch 12's
description-format list and its export-marker list the same way it extracts branch 8's
extension set, and crosses the markers with **position** — whole component, plural, compound
directory, prefixed directory, basename prefix, basename infix, dotted directory. The axis
that was missed is now the axis that is varied.

## H3 — my own comment turned the suite red

The comment I wrote explaining the `$_lc` mistake *names* `public_material`, and
`test_the_allowlist_is_applied_to_the_classification_not_ahead_of_it` asserts textually over
`classify()`'s raw body — so a comment documenting the rule read as a violation of it.

**The fix was already in the same diff and I did not apply it here.** `tests/test_hook_paths.py`
gained a `_code_only` helper for exactly this shape, written hours earlier, because its own
banner comment tripped the same trap. Both now strip comments before asserting.

## M1 — the checkpoint registry could name a foreign repository

`CK_ROOT` decided where `auto-checkpoint.sh` writes its registry; the `is-inside-work-tree`
guard tested the **cwd**. With `CLAUDE_PROJECT_DIR` pointing outside the repo, the registry
was created in a non-repo directory while the stash landed in the repo the cwd belonged to —
so the registry recorded `stash@{0}` refs that resolve nowhere. The rework I did widened this
from "wrong subdirectory, right repo" to "possibly a different repo". `CK_ROOT` is now derived
from the git toplevel and required to be inside it. Verified: with
`CLAUDE_PROJECT_DIR` aimed at a non-repo, the registry lands in the repo and nothing is
written to the foreign directory.

## M2 — a stray `.claude/hooks/` in whatever directory the hook stood in

`suggest-compact.sh`'s `COUNTER_FILE` and `LOG` moved to `$SCRIPT_DIR`; the `mkdir -p
.claude/hooks` that supported them did not. It became both dead and polluting — a hook invoked
from `$HOME` created `~/.claude/hooks`. Verified clean from an empty directory.

## M3 — the property test asserted a narrower property than its docstring

`^([A-Z_]+)=("|')\.claude/` catches only an unindented uppercase scalar assignment, while the
docstring claims "no hook assumes its working directory". **Two live offenders it missed:**

- `pre-plan.sh:50` — `local plan_dirs=(".claude/plans" …)`, on a **UserPromptSubmit** hook.
  Run below the repo root, every `[ -d ]` fails, the candidate list is empty, and the hook
  reports **"no duplicate plans found"**. A gate answering "all clear" because it looked in
  the wrong place is worse than one that errors. Verified fixed: it now finds the duplicate
  from a subdirectory.
- `pre-commit.sh:120` — `find .claude/plans/` as a bare argument, so ops validation validated
  nothing from a subdirectory.

The regex now covers `local`/`export`/`declare`, lowercase names, arrays, and a second pattern
for `.claude/` as a bare command argument.

## L1 — I withdrew the context-floor raise

I raised `CLAUDE.md` 31000 → 32000 an hour earlier, justified by "the file landed at 31272,
the overrun was 68 raw characters". **That measurement no longer reproduces:** another session
trimmed `CLAUDE.md` at `42b6ded`, and the floor now reads **30984 / 31000 — passing without
the raise.** So the raise bought 1016 chars of headroom for an overrun that no longer exists,
which is precisely the ratchet relaxation its own comment promised it was not. **Reverted.**

Worth recording as a method point rather than a slip: the raise was defensible when I made it
and indefensible forty minutes later, because a concurrent session changed the input. A budget
decision justified by a measurement has to be re-measured at the moment it lands.

## The held-out fixture I broke, and did not quietly re-freeze

`tests/test_heldout_set.py` had 5 failures. The reviewer recorded them as pre-existing. **They
were mine.** `scripts/heldout-check.py` pins `plan_sha256` for
`plan-fleet-skill-enhancement.md`, and my `check-plan-artifacts` prefix walk made that plan's
config resolve for the first time — which required the plan to name its artifact, which changed
its hash.

Re-frozen through the tool rather than by hand, which prints what moved:

    RE-FROZE fleet-skill-phaseA   .claude/plans/plan-fleet-skill-enhancement.md
             bc116ad3033398cd -> 8ace867d1661a851
    1 artifact(s) re-frozen.

Exactly one artifact, and it is the one my change touched. The tool's docstring is right that
"re-freezing to turn a red run green is the one failure a held-out set exists to prevent", so
the justification is here and in the commit: the plan legitimately gained a section a gate
required, and a replay scoring the old text would be scoring a plan that no longer exists.

## The ratchet, at five entries and counting

`correction-narrower-than-the-predicate-it-corrects`: branch scope (r1) · extension≠category
(r2) · one-suffix strip (r3) · cert-only peel (r4) · component-only marker (r5).

Round 4's answer — derive the corpus — was right and insufficient, because it derived from the
branch the *last* bug lived in. The generalisation this round adds: **derive from the branch
being changed.** Whether that finally closes it is not something I can assert; it is what round
6 would measure.

## Artifacts

| Path | Config |
| --- | --- |
| `.claude/hooks/file-guard.sh` | `ops-review-5-guard` |
| `.claude/hooks/auto-checkpoint.sh`, `.claude/hooks/suggest-compact.sh` | `ops-review-5-guard` |
| `.claude/hooks/pre-plan.sh`, `.claude/hooks/pre-commit.sh` | `ops-review-5-paths` |
| `tests/test_fileguard_allowlist.py`, `tests/test_hook_paths.py` | `ops-review-5-tests` |
| `src/claudekit/context_floor.py` | reverted to HEAD (no config; the raise was withdrawn) |
| `.claude/reports/heldout/manifest.json` (or equivalent) | re-frozen via `heldout-check.py --freeze` |
| `CHANGELOG.md`, `.claude/plans/plan-round-5-sixth-axis.md`, `.claude/plans/archive/README.md` | `ops-round5-docs` |

## Definition of Done

Full gate list, suite output to a file and read from it, `Plan-Id: round-5-sixth-axis`,
configs archived with a README row, `INDEX.md` generated against the committed tree only.

**No sixth review has been run.** Five rounds, five sets of confirmed High findings in the
previous round's fix.
