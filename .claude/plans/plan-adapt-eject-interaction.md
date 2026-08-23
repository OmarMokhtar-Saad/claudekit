# Plan — `ck adapt` on an ejected tree: refuse honestly, and stop pointing at the destructive path

**Status: DELIVERED.** `ck eject` landed as `afc4ba8` while this was being written,
which unblocked it, so the recommended option below is implemented inside
`ops-ck-adapt.json` rather than in a second config — `cmd_adapt` is that config's own
artifact, and two configs editing one new function in sequence is a merge hazard for no
gain. All seven proofs plus six mutation proofs live in `tests/test_adapt.py`
(`TestAdaptOnAnEjectedTree`); every mutant binds. Kept as the design record for a
decision that is easy to get wrong in the safe-looking direction.

## The interaction, measured

`ck eject` (uncommitted, `cli/main.py`) removes `.claudekit-manifest.json` after
copying its full contents — every path and digest — into `.claudekit-ejected.json`
(`EJECT_NAME`, `_load_eject_record`). Its own docstring: "Stop managing this project
as part of the kit, without touching a file … reversible — `ck init`/`ck update` write
a fresh manifest and re-adopt the project."

`cmd_adapt` reads only `_load_manifest`, so an ejected tree hits Rule 0's refusal.
Measured on a real install with the manifest replaced by a record carrying 231 paths:

    ck adapt — /private/tmp/ejx (adopted tree)

      detect     done — stack=none matched; evidence=none; dirty=unknown
      ownership  failed — no usable install receipt (.claudekit-manifest.json is
                          absent or unparseable), so nothing here has known provenance

      note: remedy: `ck diff` to see what differs, or re-run `ck init`

    FAILED — see the steps above    (rc 1)

Three defects, in increasing severity:

1. **It conflates a deliberate state with an accident.** "absent or unparseable" reads
   as a broken install. The tree is not broken: the user ejected it on purpose, and
   231 paths of provenance are on disk in the record.
2. **The remedy is wrong for this state.** `ck init` re-adopts a project the user
   deliberately ejected — a silent undo of an explicit decision.
3. **The remedy points at the destructive path.** `ck init` over an existing
   `.claude/` reaches `install.sh:577-581`, which `mv`s it to `.claude.bak-<ts>` and
   copies back only a heuristic subset (`:678-683`). Decision (A) in
   `plan-ck-adapt.md` exists precisely to make that unreachable from adapt — and
   here adapt *recommends* it, in prose, on a tree whose assets are the whole point
   of ejecting. This is the same shape as F3 in the review that produced this verb:
   the refusal is correct, the printed remedy is the damage.

Defect 3 is the reason this is worth a plan rather than a BACKLOG row.

## Decision to make: refuse, or run read-only

**Recommended: refuse the WRITES, still deliver the REPORT.** Detection, profile
resolution and the MCP budget read files and write nothing, and they are most of the
verb's value. An ejected project is self-managed, not broken, so the useful answer is
"here is what I see; I am not writing to a tree you have taken out of kit management."

    ownership          skipped — this project is ejected (.claudekit-ejected.json,
                                 231 path(s) recorded); adapt writes nothing here
    pre-flight         skipped — ejected: nothing is kit-owned by declaration
    profile/commands   done    — (read-only, as usual)
    hooks/config.json  skipped — ejected: adapt does not write to a self-managed tree
    claude.project.md  skipped — ejected: adapt does not write to a self-managed tree
    re-stamp           skipped — ejected: there is no receipt to stamp

    note: this project was ejected on <date>. To let `ck adapt` configure it again,
          re-adopt it with `ck update` (which rewrites kit assets), or set the four
          commands yourself — see `/adapt` step 2. Do NOT run `ck init` over an
          existing .claude/: it moves the directory aside.

Exit **0**, because nothing failed and every skip is named. The alternative — a hard
`failed` + rc 1 — was considered and is worse: it makes a deliberate, supported state
indistinguishable from a corrupt install in CI, which is defect 1 restated as an exit
code.

**Rejected: treat the eject record as a receipt and write anyway.** The record is
shaped like a manifest, so this is a two-line change and it is wrong. Ejecting means
the user has withdrawn delete/write authority; honouring the record as a licence
returns exactly the authority the command exists to surrender. It would also re-stamp
nothing, leaving the record's digests stale against files adapt had just rewritten —
provenance that lies is worse than provenance that is absent.

## Operations (one file, plus proofs)

- **`src/claudekit/cli/main.py`** — in `cmd_adapt`, when `_load_manifest` is None,
  consult `_load_eject_record` before refusing. Ejected → the skip shape above,
  rc 0. Genuinely absent/unparseable → the existing Rule 0 failure, unchanged.
  Reuse `_load_eject_record`; do not re-read the file, and do not copy `EJECT_NAME`.
- **`tests/test_adapt.py`** — CLI-driven, against a tree ejected by the real
  `ck eject`, never a hand-built record:
  1. `ck init` → `ck eject --yes` → `ck adapt` exits **0** and names ejection.
  2. **Nothing is written.** Tree digest identical before and after, `hooks/config.json`
     and `CLAUDE.project.md` byte-identical, no `.claudekit-manifest.json` appears.
  3. The report does **not** contain `ck init` as a remedy — asserted on the exact
     string, because this is defect 3 and a loose match any warning satisfies is how
     it shipped.
  4. Every step is still named (`TestEveryBranchNamesEveryStep`), so the ejected
     branch cannot omit rows the other branches print.
  5. A **genuinely** missing receipt (no record either) still exits 1 with the Rule 0
     message. Without this the fix silently converts every unprovenanced tree into a
     no-op success — refusing nowhere precisely where provenance is least known.
  6. An **unreadable** record: `_load_eject_record` warns and returns None, so this
     must land on the Rule 0 refusal, not on the ejected branch. Its own docstring
     says a present-but-unreadable receipt is not the same state as an absent one.
  7. Re-adoption: `ck update` → `ck adapt` writes again. Proves the skip is a
     function of the state, not a latch.
- **`CHANGELOG.md`** — `[Unreleased]`, user-visible.

Mutation proofs: (a) drop the `_load_eject_record` call → proof 1 red; (b) return the
ejected branch for a plain missing manifest → proof 5 red; (c) treat an unreadable
record as ejected → proof 6 red; (d) restore the `ck init` remedy text → proof 3 red.

## Out of scope

`ck eject` itself, and whether `ck update` is the right re-adoption verb. Both belong
to the session that owns eject. This plan changes only how adapt READS the state.

## Constraints

Python stdlib only. `ck adapt` issues no deletion operations and, on this branch,
performs no writes at all. Net asset delta 0 — no new command, agent or skill.
