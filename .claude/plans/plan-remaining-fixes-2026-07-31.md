# Plan: Remaining Fixes & Enhancements (post token-waste-workflow-fixes)

**Status:** Ready for review
**Created:** 2026-07-31
**Owner approval required:** yes (Golden Rule; touches a managed agent contract, CI-adjacent
tooling, and git history across multiple repos)
**Baseline verified at plan time:** `python3 -m pytest tests/ -q` → **595 passed**. Working
tree has 10 modified files + 5 untracked files (see Item 1). Branch `main` is 11 commits ahead
of `origin/main`, unpushed. `shellcheck` was NOT installed on this machine at plan time — it
now is (see Item 3); `shellcheck install.sh .claude/hooks/*.sh` is clean, zero findings.

---

## 0. How this plan is organized

Five items, each self-contained with exact file/line targets, acceptance criteria, and a
rollback note. **Items are sequenced by dependency, not by the order they were requested in** —
Item 1 unblocks everything else (it is the only item touching files the others also touch), so
it must land first. Items 3, 4, 5 have no dependency on 1/2 and could be done in parallel by a
separate session in principle, but per the task's constraint that only one session touches this
repo, they are sequenced after 1–2 below.

**Order:** 1 → 2 → 3 → 5 → 4 (4 last: it depends on 1–3 being committed on `main`, since it
distributes the current state of this repo to other repos). Item 1 unblocks everything else,
so it must land first — but it is NOT the only cross-item file overlap: `src/claudekit/cli/
main.py` is also edited by both Item 2 (§2.7, appends `"review-record.py"` to the doctor
script list) and Item 3 (§3.2, adds a shellcheck-availability check). These two do not
collide — they target different, uniquely-findable text blocks (the `for script in [...]`
list vs. the Bash-version check block) — but that safety is a property of *ordering* (2
before 3, both after 1), not of the edits being independent. Do Item 2's `main.py` edit
first; re-read the file before Item 3's edit rather than assuming its line numbers are
unchanged.

---

## 1. Commit the ops-hardening work

### 1.0 What's actually in the working tree (verified, not re-derived)

```
Modified (10):
  .agents/skills/execute-operations-config/SKILL.md
  .agents/skills/validate-operations-config/SKILL.md
  .claude/agents/implementer.md
  .claude/commands/implement.md
  .claude/operations/scripts/execute-json-ops.py
  .claude/operations/scripts/validate-config-json.py
  .claude/skills/execute-operations-config/SKILL.md
  .claude/skills/validate-operations-config/SKILL.md
  .codex/agents/implementer.toml
  docs/ARCHITECTURE.md
Untracked (5):
  .claude/plans/archive/ops-hardening-implementer-contract.json   (spent — do not execute)
  .claude/plans/archive/ops-review-approval-binding.json          (stale — see Item 2)
  .claude/plans/plan-ops-hardening-implementer-contract.md        (design doc, revision 6)
  .claude/plans/plan-review-approval-binding.md                   (design doc, revision 3)
  tests/test_ops_hardening.py                                     (15 new tests)
```

This is the code half of `plan-ops-hardening-implementer-contract.md` (revision 6, scored
97/100 APPROVED by review #6 per `plan-review-approval-binding.md` §1). The archived
`ops-hardening-implementer-contract.json` records 72 approved edits across 12 operations; it
is marked "spent" in `.claude/plans/archive/README.md` because it was already applied to this
working tree by a prior session.

**Verified finding — do NOT duplicate the CHANGELOG entry.** `CHANGELOG.md` lines 153–173
(`### Changed` block) already describe this exact change ("Ops engine no longer loses the
original file...", "fails closed on anchor drift...", "Validator simulates edits
cumulatively...", "Implementer contract: reactive reads...") — committed prematurely in
`55933cb` ("fix(commands): /refine stops leaking the full plan into reviewer prompts", which
bundled an unrelated CHANGELOG paragraph). The wording was checked against the current diff
and is accurate. **Do not add a second entry for this in Item 1's commits** — it would
duplicate content already on `main`. If a reviewer wants this cleaned up (right content, wrong
commit), that is a `git log --follow`-visible cosmetic issue only, not a blocker — note it in
the commit message of 1.3 below and move on; rewriting already-unpushed-but-11-commits-deep
history for a cosmetic attribution mismatch is not worth the risk.

### 1.1 The 3-hunk review gap — decision required before committing

The task framing for this item names three hunks as "never reviewed": `implement.md`'s
STEP 0 item 2 wording change and its Error Handling paragraph, and one comment in
`docs/ARCHITECTURE.md`. Direct comparison against the plan doc's own op descriptions shows:

- `implement.md`'s current diff (STEP 0 item 2, Phase 1/Phase 2 rewrite, Error Handling
  paragraph) matches **Op 10** in `plan-ops-hardening-implementer-contract.md` §4 verbatim —
  Op 10 was added specifically because "review #5 caught this," so it WAS reviewed as part of
  revision ≥5/6.
- `docs/ARCHITECTURE.md`'s current diff matches **Op 11** (§5), added because "review #4 caught
  this as an unacknowledged DoD gap" — also reviewed.

So on direct evidence, these three hunks are NOT unreviewed — they trace to the plan's own
op numbers and reviewer findings. **However**, `plan-review-approval-binding.md` §1 states
review #6 approved the plan at **72 edits**, then "four cheap MINOR fixes were applied,
reaching 74 edits" — a 2-edit gap between what review #6 saw and what is now on disk, and one
of those 4 fixes ("resetting `_result_emitted` in `finally`") was explicitly **tried and
rejected** per §3 Op 1's changelog in the same doc. This is the actual gap: not "3 unreviewed
hunks" by name, but an unquantified 2-edit delta between the last scored revision (72) and the
current tree, with no record of what those 2 edits are.

**Required action before running 1.3's commits:**
```bash
# Count actual edits currently in the archived (spent) ops.json vs the 72 review #6 scored:
python3 -c "
import json
d = json.load(open('.claude/plans/archive/ops-hardening-implementer-contract.json'))
print(sum(len(op.get('edits', [])) + (1 if op['type']=='file_create' else 0) for op in d['operations']))
"
```
- If this prints `72`: the archived config IS what review #6 scored, and the "74 edits"
  claim in `plan-review-approval-binding.md` §1 is itself stale/wrong (that doc is about a
  *different* feature and may be describing a session detail that never made it into the
  archived config). Proceed to commit as-is (1.3) — **no owner sign-off needed beyond the
  plan's own existing "Owner approval required: yes" line**, since the shipped code matches
  the last-reviewed artifact.
- If it prints anything else (e.g. `74`), diff the archived config's op1 edit count against
  the current `execute-json-ops.py`'s actual `_result_emitted`-handling code (`grep -n
  "_result_emitted" .claude/operations/scripts/execute-json-ops.py`) to find the 2 extra
  edits. Per §3 Op 1 of `plan-review-approval-binding.md`, the rejected `finally`-reset
  suggestion should NOT be present — confirm it isn't (`grep -n "_result_emitted = False"
  .claude/operations/scripts/execute-json-ops.py` should show it set only once, at module
  scope or at the start of a run, never inside a `finally`). If the extra edits are benign
  (e.g. a docstring tweak), note them in the commit message and proceed. If they change
  behavior beyond what's documented, **STOP and get explicit owner sign-off** on those 2
  edits specifically before committing (Golden Rule) — do not fold them into 1.3 silently.

This check is cheap (one Python one-liner + two greps) and turns a vague "was this reviewed"
question into a concrete, evidence-based go/no-go. Do it first; it gates 1.3.

### 1.2 Split into conventional commits (one concern each)

Bundling the test file with the two engine scripts avoids an intermediate commit with known
failing/missing tests (bad bisectability); bundling the full contract-rewrite corpus (agent +
both skill mirrors + Codex mirror + implement.md) in one commit reflects that it is one
concern — "implementer contract, Claude and Codex corpora in sync" — per this repo's own
"update every reference when renaming/changing a contract" rule.

**Commit A — engine hardening + tests** (the CRITICAL fix; keep separable from the contract
rewrite so `git bisect` can isolate an engine regression from a prompt-wording regression):
```
git add .claude/operations/scripts/execute-json-ops.py \
        .claude/operations/scripts/validate-config-json.py \
        tests/test_ops_hardening.py
git commit -m "$(cat <<'EOF'
fix(ops): first-write-wins backups, fail-closed anchors, RESULT-JSON evidence

execute_code_edit/execute_file_delete re-copied the target over its backup on
every operation touching one file, so a second op's backup captured the first
op's mutation and rollback restored the intermediate state instead of the
original (data-loss bug, reproduced in plan-ops-hardening-implementer-
contract.md §10). Backups are now first-write-wins per run, refusing a
project-root manifest.json name collision in both dry-run and real execution.

The anchor-matching loop was fail-soft (skip missing anchors, first-occurrence
replace on ambiguous ones); it now aborts before any write on a missing or
ambiguous (count>1, checked against currently-mutated content) anchor, and
the batch rolls back on any operation failure. Dry-run threads simulated file
state across operations on one file so its preview matches real sequential
execution. The engine now emits a unified diff plus a machine-readable
RESULT-JSON: summary line on every reported exit path (config error, lock
contention, manifest failure, operation failure, crash, signal) so a caller
with no Read access to target files still gets verifiable evidence of what
changed.

validate-config-json.py's GUARDs 10/11 now simulate each edit cumulatively
(within an operation and across operations on the same file, both modern and
legacy config formats) instead of validating every edit against pristine
disk content — closing the gap where an earlier edit could make a later
edit's anchor ambiguous or newly create it, undetected until apply time.

15 new tests in tests/test_ops_hardening.py pin: same-file rollback restores
pristine content, backup-file pristine-content invariant, file_delete after
code_edit keeps the pristine backup, manifest.json collision refusal in both
modes, dry-run/execute divergence removed, diff+RESULT-JSON on success and on
every failure mode, a post-loop crash leaving applied changes intact, the
transaction being retired before the summary prints (SIGINT-safety), and
three validator cumulative-simulation cases.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

**Commit B — implementer contract rewrite (Claude + Codex corpora)**:
```
git add .claude/agents/implementer.md .claude/commands/implement.md \
        .claude/skills/execute-operations-config/SKILL.md \
        .agents/skills/execute-operations-config/SKILL.md \
        .claude/skills/validate-operations-config/SKILL.md \
        .agents/skills/validate-operations-config/SKILL.md \
        .codex/agents/implementer.toml
git commit -m "$(cat <<'EOF'
docs(agents): rewrite implementer contract for reactive reads + evidence

The implementer's Safety Rules told it to "ALWAYS read a file before editing
it" and "create backup of files that will be modified" — busywork the ops
engine already guarantees (fix(ops) in the prior commit), duplicated at real
token cost. The contract now: validates ops.json first (a mandatory step the
old spec omitted entirely — the pipeline's only uniqueness guard was
optional), never reads target files or ops.json upfront, and relays the
engine's diff + RESULT-JSON output as its evidence of what changed, reading a
target file only to diagnose a reported failure. implement.md's Phase
1/Phase 2 wording is corrected to match the engine's single-batch-invocation
contract (no per-operation loop exists to "announce" or drive). Both
execute-operations-config SKILL.md mirrors (.claude/ and .agents/) and the
.codex/agents/implementer.toml mirror get the same rewrite so the Claude and
Codex corpora do not drift; validate-operations-config's two mirrors drop the
stale claim that a multi-match anchor is a warning (GUARD 11 is a hard,
cumulative FAIL).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

**Commit C — architecture docs**:
```
git add docs/ARCHITECTURE.md
git commit -m "$(cat <<'EOF'
docs(architecture): document first-write-wins backups + RESULT-JSON contract

Execution Safety guarantee list and the pipeline diagram were stale relative
to the engine hardening and implementer contract rewrite in the prior two
commits (the diagram said "Implementer reads ops.json + plan.md", which the
new contract explicitly does not do).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

**Commit D — plan docs housekeeping**:
```
git add .claude/plans/archive/ops-hardening-implementer-contract.json \
        .claude/plans/plan-ops-hardening-implementer-contract.md
git commit -m "$(cat <<'EOF'
docs(plans): archive the executed ops-hardening config

Records the design history (6 review rounds) and the spent ops.json for the
engine-hardening + implementer-contract change landed in the prior 3 commits.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

Leave `.claude/plans/archive/ops-review-approval-binding.json` and
`.claude/plans/plan-review-approval-binding.md` uncommitted here — they belong to Item 2 and
the archived json must be regenerated (stale) before it is committed as anything other than a
historical record. If Item 2 is deferred, commit them in a 5th `docs(plans):` commit with a
commit message stating explicitly that the ops.json is stale and NOT to be executed —
prefer landing Item 2 first so the doc and a validated config land together.

### 1.3 Acceptance criteria
- `git status` shows a clean tree (mod­ulo Item 2's untouched files if deferred).
- `python3 -m pytest tests/ -q` → 595 passed (no count change; test file already counted at
  plan time since it's untracked-but-present).
- `python3 -m pytest tests/test_ops_hardening.py -v` → 15 passed, individually visible.
- `ruff check src/ tests/ scripts/` clean (`tests/test_ops_hardening.py` is in ruff's scope;
  the two `.claude/operations/scripts/*.py` files are excluded per `pyproject.toml`
  `extend-exclude`).
- `mypy` clean (ops scripts outside `files=["src/claudekit"]`, unaffected).
- `python3 scripts/gen-docs.py --check` and `python3 scripts/gen-registry.py --check` — both
  must stay green; this item adds no agents/commands/skills/hooks, so no count changes.
- `shellcheck install.sh .claude/hooks/*.sh` — unaffected by this item (no `.sh` files
  touched); confirmed clean anyway (§Baseline).
- Reproduce the gap-0 fix by hand once: create a 2-op-same-file ops.json, run it forcing op 2
  to fail, confirm the rollback restores the ORIGINAL content and the backup file matches it
  (mirrors `plan-ops-hardening-implementer-contract.md` §10's rehearsal).

### 1.4 Risks & fallback
- **Risk:** the 1.1 edit-count check reveals real unreviewed behavior changes.
  **Fallback:** split those specific lines into their own commit, tagged in the message as
  "unreviewed — pending owner sign-off," and do not fold them into Commit A/B. Everything else
  in this plan can still proceed; Items 2–5 do not depend on those specific lines.
- **Risk:** `git commit` ordering above still leaves `tests/test_ops_hardening.py` passing
  only once both engine files are staged together (they are, in Commit A — verified by design,
  not by assumption, since the test file imports/subprocesses both scripts).
- **Rollback:** none of these commits are pushed; `git reset --soft HEAD~4` (adjust count if
  Item 2's docs commit is folded in) fully undoes this item with zero remote impact.

---

## 2. Rebase and land approval-binding

**Depends on:** Item 1 committed (review.md/implement.md's current content, which the
approval-binding config's `code_edit` anchors must target, only becomes a stable base once
Item 1's Commit B lands — Commit B does not touch `review.md`, but DOES touch `implement.md`,
which this item also edits).

### 2.1 What's reusable verbatim vs. what must be regenerated

The archived `ops-review-approval-binding.json` has 9 operations:

| Op | Type | Target | Reusable as-is? |
|---|---|---|---|
| 1 | `file_create` | `.claude/operations/scripts/review-record.py` | **Yes** — new file, no anchor to drift |
| 2 | `code_edit` (4 edits) | `.claude/commands/review.md` | **No** — regenerate (see 2.2) |
| 3 | `code_edit` (2 edits) | `.claude/agents/reviewer.md` | **No** — regenerate (see 2.3) |
| 4 | `code_edit` (1 edit) | `.claude/commands/implement.md` | **No** — regenerate (see 2.4); file changed under Item 1 |
| 5 | `code_edit` (1 edit) | `.claude/commands/refine.md` | Verify anchor still matches (§2.5) — likely reusable |
| 6 | `code_edit` (1 edit) | `.gitignore` | **Yes** — append-only, anchor-free (see 2.6) |
| 7 | `file_create` | `tests/test_review_record.py` | **Yes** — new file |
| 8 | `code_edit` (1 edit) | `src/claudekit/cli/main.py` | Verify anchor (§2.7) — line numbers may have shifted |
| 9 | `code_edit` (1 edit) | `CHANGELOG.md` | **No** — regenerate; the `### Added` block's top bullet (the "Queued ops configs..." entry, `CHANGELOG.md:16-24`) is the current anchor point, not whatever the archived config anchored on |

Reuse the two `file_create` payloads (ops 1 and 7) byte-for-byte from
`.claude/plans/archive/ops-review-approval-binding.json` — read them with `python3 -c
"import json; print(json.load(open('...'))['operations'][0]['content'])"` rather than
re-deriving the script from the design doc prose; the design doc (`plan-review-approval-
binding.md` revision 3) documents *why* each piece of the script exists, but the archived
JSON's `content` field IS the reviewed, tested (**20/20** — extracted and counted directly
from the archived JSON's `content` field via `grep -c "def test_"`; the design doc's own
prose claims "17" in several places, which is stale/wrong and must not be trusted over the
artifact itself), `py_compile`-clean artifact — treat it
as the source of truth for those two files.

### 2.2 `review.md` — exact target state (current file read at plan time, 83 lines)

Current bash block (lines 24–41) manually derives `OPS_FILE` from `PLAN_FILE` with a
two-form fallback. Replace with a call to the new script's `resolve` subcommand, which
implements the same two-form logic (plus a third/fourth slug fallback) inside
`review-record.py` — do not keep both the shell fallback AND the script; the shell version
is now dead logic once the script exists.

**Edit 1** (replaces lines 32–41, the `OPS_FILE` derivation block):
```bash
OPS_FILE=$(python3 .claude/operations/scripts/review-record.py resolve "$PLAN_FILE")
RESOLVE_EXIT=$?
if [ $RESOLVE_EXIT -eq 3 ]; then
  echo "ERROR: could not resolve a unique ops.json for $PLAN_FILE (ambiguous or missing)."
  exit 1
fi
```

**Edit 2** (after line 69's `review_output=$(...)` capture, before line 77's `echo
"$review_output"`): pipe the raw reviewer output into the record script so the verdict is
bound to the ops.json's hash before anything else happens:
```bash
echo "$review_output" | python3 .claude/operations/scripts/review-record.py write "$PLAN_FILE" "$OPS_FILE" --from-review -
```
Keep `echo "$review_output"` immediately after — the human-readable verdict must still print;
`write` is a side effect, not a replacement for showing the verdict.

**Edit 3** (`DELTA REVIEW MODE` injection): before constructing `REVIEWER_MSG` (before line
43), add:
```bash
DELTA_BLOCK=""
DIFF_OUT=$(python3 .claude/operations/scripts/review-record.py diff "$PLAN_FILE" "$OPS_FILE" 2>/dev/null)
DIFF_EXIT=$?
# diff prints "(no changes since approval)" and "# FULL REVIEW REQUIRED" with exit 0 too —
# both mean NO delta block (full/normal review runs unmodified). Only a real diff qualifies.
if [ $DIFF_EXIT -eq 0 ] && [ -n "$DIFF_OUT" ]; then
  case "$DIFF_OUT" in
    "(no changes since approval)"*|"# FULL REVIEW REQUIRED"*) : ;;
    *)
      DELTA_BLOCK="

DELTA REVIEW MODE — a prior approved review exists for a different version of this ops.json.
Changed content (approved -> current), prior findings shown WITHOUT the prior score so you
re-judge rather than reaffirm:
$DIFF_OUT"
      ;;
  esac
fi
```
then append `$DELTA_BLOCK` to the end of `REVIEWER_MSG` (after line 67's closing quote,
before the variable is used). The `case` exclusion above is load-bearing, not defensive
styling: without it, the reviewer receives a "delta" block in exactly the two situations
where there must be none (nothing changed / change too sweeping for delta mode). The
archived revision-2 config solved this the same way — reuse its pattern, and add an
acceptance check to §2.9: with a FULL-REVIEW-sized change staged, the constructed
REVIEWER_MSG must NOT contain "DELTA REVIEW MODE".

**Edit 4** (interactive/Task-tool path — `review.md` currently documents ONLY the scripted
bash path, lines 18–78; there is no separate interactive section to edit today, unlike
`implement.md`/`plan.md`). Add a new numbered step after the existing step 2 (lines 80–84):
```markdown
3. **If invoked via the Task tool instead of this bash block** (the bash block never runs),
   you must record the verdict manually — a review whose verdict was never recorded is not
   an approval:
   ```bash
   echo "<the subagent's raw review output>" | python3 .claude/operations/scripts/review-record.py write "$PLAN_FILE" "$OPS_FILE" --from-review -
   ```
   Skipping this step means `/implement`'s STEP 0 gate (Item 2.4) will refuse with exit 3
   (no record) — it fails closed, not silently.
```

### 2.3 `reviewer.md` — Delta Review Mode section (353 lines)

Read the file first to find the section immediately after the existing output-format/decision
rules content (do not guess a line number here — it depends on the exact heading structure at
implementation time, which may itself have shifted since this plan's research pass). Add a new
`## Delta Review Mode` section with this content, verbatim intent from
`plan-review-approval-binding.md` §3 Ops 2–3:
```markdown
## Delta Review Mode

When the caller's message includes a "DELTA REVIEW MODE" block, a prior review already
approved a different version of this ops.json. The block shows a normalized diff
(approved → current) and the prior review's findings — deliberately WITHOUT its score, so
you re-judge the current version rather than reaffirming the old one.

- Verify every changed anchor against the filesystem yourself (Read/Grep) — the diff shows
  WHAT changed, not whether it is still correct.
- Check whether the delta reopens any listed prior finding (e.g. a fix that was reverted).
- Never assume "small diff" means "safe" — a one-line change to a security-relevant anchor
  is not lower risk than a large refactor.
- Score and decide using the same `=== REVIEW ===` format as a full review. This caller-
  specified format overrides your own default REVIEW REPORT template when the two would
  otherwise conflict.
```
Also add a short note near the top of the agent's output-format instructions stating that a
caller-specified format (the `=== REVIEW ===` block) takes precedence over the agent's own
default template — `plan-review-approval-binding.md` review round 1 found these two format
descriptions contradicted each other in the original draft.

### 2.4 `implement.md` STEP 0 — depends on Item 1's final committed text

After Item 1 lands, STEP 0 item 1 reads (current, pre-Item-1, line 32; Item 1 does not touch
this line so it will read identically after):
```
1. An approved plan exists (review score >= 90 or explicit user override)
```
Change to:
```
1. An approved plan exists (review score >= 90 or explicit user override). Verify mechanically:
   ```bash
   OPS_FILE=$(python3 .claude/operations/scripts/review-record.py resolve "$PLAN_FILE")
   ```
   ```bash
   python3 .claude/operations/scripts/review-record.py check "$PLAN_FILE" "$OPS_FILE"
   ```
   Exit 0 → proceed. Exit 1/2/3/4 → STOP (drift, no record, or sub-90/non-APPROVED
   verdict); never treat a non-zero exit as approval, and never re-run `check` in a retry
   loop hoping for a different result — a failing check means re-review is required, full
   stop.
```
**Both calls must be separate `Bash` invocations** (not `OPS=$(python3 ... ; python3 ...
"$OPS")`) — the implementer's tool grant in `INVOCATION.md:100` is a literal prefix match on
`Bash(python3 .claude/operations/scripts/*)`; a shell assignment or compound command is a
different string and may not match depending on the grant matcher's exact semantics. Keeping
each call as its own bare `python3 .claude/operations/scripts/<script>.py ...` invocation is
the only form proven to match.

### 2.5 `refine.md` — verify, don't blindly reuse

`refine.md` builds its own `REVIEWER_MSG` per cycle and only writes `plan.md`/`ops.json` once,
at Step 3, after convergence (confirmed by reading the file's Cycle A/B structure). The
archived config's op 5 edit for this file should be a **Notes-section bullet**, not a
functional change: state that `review-record.py resolve`/`write` run once against the FINAL
iteration's verdict, same as a one-shot `/review`, and that automatic delta review *across*
refine iterations is an explicit, unclaimed follow-up (would need ops.json persisted per
iteration, which `/refine` does not do). Read the archived op 5 text before writing this edit
— if it matches this description, reuse it; if it claims `/review` is called from inside the
loop or lands inside a user-facing banner (both flaws review round 1 found in the FIRST
draft, per `plan-review-approval-binding.md` §3 Op 5), it was not fixed and must be rewritten
to this corrected form.

### 2.6 `.gitignore`

Append (no anchor needed, `code_edit` op 6 is safe to reuse or trivially recreate):
```
.claude/reports/reviews/
```
Add near the existing `# ClaudeKit` section (currently ends around the
`.claude/hooks/compact-counter.txt` line per `.gitignore`'s current tail) for topical grouping.

### 2.7 `src/claudekit/cli/main.py` — doctor script list

Current anchor (verified at plan time, `main.py:198-199`):
```python
for script in ["validate-config-json.py", "execute-json-ops.py",
               "extract-json-from-plan.py", "restore-backup.py", "shared.py"]:
```
Change to:
```python
for script in ["validate-config-json.py", "execute-json-ops.py",
               "extract-json-from-plan.py", "restore-backup.py", "shared.py",
               "review-record.py"]:
```

### 2.8 `CHANGELOG.md`

Insert as a new bullet inside the existing `### Added` block under `[Unreleased]`, immediately
after the "Zero-LLM-cost regression test..." bullet — anchor on its literal closing text,
"...silently reintroduce either leak." (currently `CHANGELOG.md:34`; use the text, not the
line number, since line numbers shift as earlier items in this plan land):
```markdown
- **Review verdicts are now bound to the artifact they approved.** `/review` recorded
  nothing beyond stdout, so an approved ops.json could be edited post-approval with no way
  for `/implement` to detect it — this happened for real during this session (see
  `plan-review-approval-binding.md`). `review-record.py` hashes ops.json at review time,
  gates `/implement` on a matching APPROVED/`>=90` record, and offers delta review (diff +
  prior findings, score withheld) for small post-approval edits so re-approval doesn't cost
  a full review every time.
```

### 2.9 Acceptance criteria
- `python3 .claude/operations/scripts/validate-config-json.py <regenerated-ops.json>` →
  APPROVED, exit 0.
- `python3 .claude/operations/scripts/execute-json-ops.py <regenerated-ops.json> --dry-run` →
  all operations/edits bound, exit 0.
- `python3 -m pytest tests/test_review_record.py -q` → **20 passed** (reused verbatim from
  the archived `file_create` payload — counted directly from the JSON's `content` field
  via `grep -c "def test_"`, not from the design doc's prose, which says "17" in several
  places and is stale; if any anchor-dependent test needed the regenerated `resolve`
  behavior to change, update the test file too, re-collect with `pytest --collect-only`,
  and correct this number again rather than re-trusting either source blindly).
- `python3 -m pytest tests/ -q` → 595 + 20 = **615 passed**. Confirm this by actually running
  `pytest --collect-only tests/test_review_record.py | tail -1` once the file is written —
  do not carry the 20 forward as fact without that check, since a regeneration-driven edit
  to the file (per the note above) could change it again.
- End-to-end rehearsal on a toy plan: `/plan` → `/review` (APPROVED) → make one SMALL
  SEMANTIC edit to ops.json (e.g. append one edit entry — NOT whitespace: the normalized
  diff deliberately reports formatting-only changes as "(no changes since approval)", so a
  whitespace edit cannot trigger delta mode) → `/review` again → confirm `DELTA REVIEW MODE`
  triggers and the diff is far smaller than the file (mirrors the "707 B vs 69,378 B"
  measurement in `plan-review-approval-binding.md` §8). Separately: a whitespace-only edit →
  `diff` reports formatting-only, but `/implement` → `check` must STILL exit 2 (hash uses raw
  bytes). Then, with the semantic edit un-reviewed → `/implement` → `check` must exit 2
  (DRIFT) and the implementer must STOP; after re-review records APPROVED → `check` exit 0.
- Delta-exclusion guard (pins the §2.2 Edit 3 `case` statement): with a sweeping change
  staged (past the size ceiling), the constructed `REVIEWER_MSG` must NOT contain
  "DELTA REVIEW MODE"; same with zero changes staged.
- `ruff check src/ tests/ scripts/`, `mypy`, `gen-docs.py --check`, `gen-registry.py --check`
  all green. `review-record.py` lives under `.claude/operations/scripts/`, outside both ruff's
  and mypy's scoped paths per `pyproject.toml` (same as the other ops scripts) — confirm this
  is still true rather than assuming (`extend-exclude`/`files` could have changed since this
  plan was written).

### 2.10 Risks & fallback
- **Risk:** `resolve`'s stem-form-first logic doesn't match a real `/plan`/`/refine` output
  filename in practice (this was the round-1 CRITICAL bug per `plan-review-approval-binding.md`
  §3). **Mitigation:** the 20 reused tests explicitly pin the un-stripped-stem form; do not
  skip running them before treating this item as done.
- **Risk:** the interactive/Task-tool manual-record step (2.2 Edit 4) is prose-enforced and
  can be skipped by a careless caller. **Mitigation:** this is accepted and documented as
  fail-closed — a skipped record means `/implement` refuses with exit 3, never silently
  approves. Do not try to "fix" this by making `/implement` infer approval some other way.
- **Rollback:** `git checkout -- .claude/commands/review.md .claude/commands/implement.md
  .claude/commands/refine.md .claude/agents/reviewer.md CHANGELOG.md .gitignore
  src/claudekit/cli/main.py; rm -f .claude/operations/scripts/review-record.py
  tests/test_review_record.py; rm -rf .claude/reports/reviews/` (only the last rm if created
  by rehearsal, never real approval records) — or the engine's own auto-backup /
  `restore-backup.py` for a failed in-progress execution.

---

## 3. Shellcheck gate — surfaced, not silent

### 3.1 Finding (corrects the task's framing — verify before acting on either version)

CI **already runs shellcheck twice**, redundantly: `.github/workflows/ci.yml`'s `shellcheck`
job (lines 99–112) and `.github/workflows/security.yml`'s "Validate shell scripts" step
(lines 39–45) both `apt-get install -y shellcheck` and run it over `install.sh` +
`.claude/hooks/*.sh`. So the CI-level DoD gate is not silently skipped — it runs, and would
fail the build on a real finding.

The actual gap: **locally**, `shellcheck` was not installed on this machine (confirmed at plan
time), so any session following CLAUDE.md's own documented DoD command
(`shellcheck install.sh .claude/hooks/*.sh`) got a shell "command not found" and — per
`.ai/SESSION_STATE.md`'s own past entries — that gap has been *noted* repeatedly
("shellcheck not installed locally, unchanged pre-existing gap") but never closed, and nothing
in `ck doctor` or the test suite surfaces this as anything other than a command failing in a
way a session might work around by just not running it. That is the "silent" part: the local
tooling gives no structured signal (warn or otherwise) that this DoD command is unusable —
a session has to already know to check.

**Now installed and run** (this plan's own verification pass): `shellcheck install.sh
.claude/hooks/*.sh` → **zero findings across all 20 hook scripts + install.sh**. No shell-lint
fixes are needed as part of this item — only the surfacing mechanism.

### 3.2 Change 1 — `ck doctor` gains a shellcheck-availability check

**File:** `src/claudekit/cli/main.py`, inside `cmd_doctor` (function starts line 110). Insert
the new check after the Bash-version check block and before the Operations-scripts block —
anchor on literal text, not line numbers: the Bash block's true-branch statement is
`check(f"Bash available: {bash_ver[:60]}", True)`, and the Operations-scripts block starts
with the comment `# Operations scripts`. Both will shift once Item 2.7's script-list edit
lands above this point, so search for these two strings fresh with `grep -n` rather than
trusting any line number cited anywhere in this plan.
```python
    # Shell-lint tooling (used by the repo's own DoD gate, not installed by default)
    shellcheck_path = shutil.which("shellcheck")
    check("shellcheck available", "warn" if shellcheck_path is None else True,
          "not on PATH — install with `brew install shellcheck` (macOS) or "
          "`apt-get install shellcheck` (Linux) to run the repo's shell-lint DoD gate "
          "locally; CI runs it regardless")
```
Requires `import shutil` at the top of `main.py` if not already imported — check first
(`grep -n "^import shutil" src/claudekit/cli/main.py`); if absent, add it alongside the
existing `import subprocess`/`import sys` block.

### 3.3 Change 2 — a local pytest that reports rather than silently not-running

**File:** new `tests/test_shell_lint.py`:
```python
"""Runs shellcheck over install.sh and .claude/hooks/*.sh when available; reports a
visible SKIP (not silence) when the tool is absent, so `pytest -v` output always states
whether this DoD gate ran."""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHELLCHECK = shutil.which("shellcheck")

pytestmark = pytest.mark.skipif(
    SHELLCHECK is None,
    reason="shellcheck not installed — CI (.github/workflows/ci.yml, security.yml) still "
           "gates this; install locally with `brew install shellcheck` / "
           "`apt-get install shellcheck` to run it here too",
)


def _shell_scripts():
    yield REPO_ROOT / "install.sh"
    yield from sorted((REPO_ROOT / ".claude" / "hooks").glob("*.sh"))


@pytest.mark.parametrize("script", list(_shell_scripts()), ids=lambda p: p.name)
def test_shellcheck_clean(script):
    result = subprocess.run([SHELLCHECK, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, f"shellcheck findings in {script.name}:\n{result.stdout}"
```
This makes `pytest -v` output a per-file `SKIPPED (shellcheck not installed — ...)` line
when the tool is absent — visible, not silent — and a real per-file PASS/FAIL when present,
which is strictly more granular than the repo-wide DoD command.

### 3.4 Explicitly NOT doing (judgment call, state don't decide silently)

- **Not** consolidating the two duplicate CI jobs (`ci.yml`'s `shellcheck` job vs.
  `security.yml`'s step) — they are currently byte-identical in intent and low-risk to leave
  duplicated; flag as a minor follow-up in `.ai/BACKLOG.md` P3 rather than doing a
  CI-workflow edit inside this item (CI workflow changes are higher blast-radius than a
  doctor check or a new test file, and are out of this item's stated scope).
- **Not** adding shellcheck to `pre-commit.sh` (or any other hook) as a blocking local gate —
  CLAUDE.md's own admission that the 6 DoD commands are "currently prompt-enforced" (task 010
  makes them mechanical) means this item should not unilaterally promote ONE of the six to
  hook-enforced while the other five stay prompt-enforced; that inconsistency is task 010's
  job, not this item's.

### 3.5 Acceptance criteria
- `ck doctor` (fresh checkout, shellcheck NOT on PATH) shows a `warn`-level line naming the
  install command, does not fail the overall doctor run.
- `ck doctor` (shellcheck on PATH) shows a passing check.
- `pytest tests/test_shell_lint.py -v` shows either 21 individual PASS lines (20 hooks +
  install.sh) or 21 SKIPPED lines with the install-command reason — never silent absence.
- `shellcheck install.sh .claude/hooks/*.sh` — zero findings (already true; regression-guard
  only, no new fixes expected).
- `python3 -m pytest tests/ -q` → 615 + 21 = **636 passed** (21 new parametrized cases; if
  shellcheck is present in the CI runner, they run for real and must stay green there too —
  confirm by reading the CI job's log after this lands, since it changes what the existing
  duplicate CI shellcheck jobs already exercise).

### 3.6 Risks & fallback
- **Risk:** `shutil.which` behaves differently on Windows CI runners (none exist for this
  repo today per `docs/` — Windows is Icebox in `BACKLOG.md`) — no mitigation needed now.
- **Rollback:** `git checkout -- src/claudekit/cli/main.py; rm -f tests/test_shell_lint.py`.

---

## 4. Fleet rollout

**Scope note:** this session must not touch any repo other than `claudekit` (explicit
constraint from the task). This item plans the commands for whichever session/owner runs the
rollout; do not execute them here.

### 4.1 Targets (verified to exist on disk, per `~/IdeaProjects/` listing)
`qa-agents`, `qaforge-ai`, `MobileUIAutomator`, `AppiumLens`, plus per
`fleet-sync-state` memory (22 days old at plan time — re-verify, don't trust blindly):
`LeanApis`, `ai-agent-system`. **`AppiumLens` is explicitly held back** — do not run `ck
update` against it; it carries ~26 kit files with real IntelliJ/Gradle customization, 15
project-only skills, and local June-30 fixes flipping `/plan`/`/review`/`/refine` to
Task-tool invocation. Flag it in the rollout report; do not force it.

### 4.2 Order and verification, per project (repeat for each of the 5 non-`AppiumLens`
targets)
```bash
cd ~/IdeaProjects/<project>
ck diff                    # 1. see what's locally modified vs. the installed manifest FIRST
git status                 # 2. confirm no uncommitted work would be clobbered
ck update                  # 3. only after 1-2 are clean/understood; backs up automatically
ck doctor --strict         # 4. verify health post-update
git diff --stat            # 5. sanity-check the blast radius matches expectations
```
- If step 1 (`ck diff`) shows local customizations (per `fleet-sync-state`: qa-agents' 3
  manual-QA agents + 4 commands; MobileUIAutomator's 9 project skills), confirm `ck update`'s
  three-way merge preserves them (documented behavior: unchanged→replace, modified→keep+`.new`,
  removed→prompt — per `.ai/roadmap.md` §2.2, this is "warn-and-overwrite-with-backup," NOT a
  true merge yet). **Read the diff/backup output carefully before deleting any `.new` files.**
- If step 3 fails or step 4 reports new failures, STOP for that project — do not force through
  remaining projects on the assumption the failure is project-specific; check whether it
  reproduces the ops-hardening/approval-binding changes' new behavior (e.g. a project with its
  own stale queued ops.json would now fail the "validate against HEAD" gate from a prior
  session's `1cf3771` commit, if that project already updated to a version including it).
- MobileUIAutomator's 9 project skills reference `AppiumLens` incorrectly (known, per
  `fleet-sync-state` memory) — this is pre-existing and out of scope for this rollout; note it
  in the report but do not fix it here (a `/adapt` rewrite, separate task).

### 4.3 Acceptance criteria
- Each of the 5 targets: `ck doctor --strict` exits 0 post-update, `git status` in that
  project shows only the expected manifest-tracked files changed (no untouched local
  customization silently dropped).
- A short rollout report (paste `ck diff` before/after and `ck doctor --strict` output per
  project) — this is evidence, not a formality, per CLAUDE.md's "Communicate: evidence-first."
- `AppiumLens` explicitly untouched; its entry in the report states why (owner-decision-
  pending, cross-referenced to `.ai/SESSION_STATE.md`'s "Blocked / waiting" section).

### 4.4 Risks & fallback
- **Risk:** a target project has its own uncommitted work that `ck update`'s backup-then-
  overwrite could bury under a `.new` file a developer doesn't notice. **Mitigation:** step 2
  (`git status`) before step 3, every time, no exceptions; if dirty, stop and ask the project's
  owner before updating.
- **Risk:** version skew — a target might be several ClaudeKit versions behind, and `ck
  update`'s legacy-install path (added per `fleet-sync-state`) might not have been exercised
  against a base that old. **Mitigation:** `ck doctor --strict` after update is the acceptance
  gate specifically to catch this; don't skip it to save time.
- **Rollback:** `ck update` backs up automatically (same engine as the local ops backups);
  each project's own git history is the second net — never force-push or discard local state
  to "fix" a bad update, restore from the `ck`-created backup or `git checkout` the specific
  files instead.

---

## 5. Smaller items

### 5a. `.ai/AGENTS.md` split (100 KB → files under ~10 KB)

**Measured section sizes** (verified via `awk` byte-counting at plan time, not estimated):

| Section | Lines | Bytes |
|---|---|---|
| Header + TOC | 1–22 | 2,581 |
| Architecture Diagrams | 23–97 | 2,685 |
| Agent Interaction Model | 98–162 | 5,612 |
| 10 Core Pipeline agents (coordinator..explore) | 163–535 | ~29,000 |
| 20 Specialist agents (tester..model-router) | 536–1109 | ~48,000 |
| 9 Meta-doc pointer stubs | 1110–1153 | ~9,100 |
| Known Issues | 1154–1188 | 8,110 |

**Target split** (7 files, each measured under 10 KB after the split — verify with `wc -c`
per file as a hard gate, not an assumption):

1. `.ai/AGENTS.md` — Header + TOC + Architecture Diagrams (~5.3 KB), rewritten as the index:
   links to the 6 files below instead of inlining their content.
2. `.ai/AGENTS_INTERACTION_MODEL.md` — Agent Interaction Model (~5.6 KB).
3. `.ai/AGENTS_PIPELINE_1.md` — coordinator, planner, reviewer (~9.3 KB).
4. `.ai/AGENTS_PIPELINE_2.md` — implementer, verifier, debugger, documenter, doc-updater,
   gitOps, explore (~19.6 KB — **still over budget**; split again into `_PIPELINE_2.md`
   (implementer, verifier, debugger, ~8.8 KB) and `_PIPELINE_3.md` (documenter, doc-updater,
   gitOps, explore, ~10.7 KB, split once more if `wc -c` confirms it's over — do the
   measurement, don't eyeball it).
5. `.ai/AGENTS_SPECIALISTS_1.md` through `_N.md` — the 20 specialist agents in groups of ~4
   (each ~9.5–10 KB per the per-agent byte counts above: tester+security-scanner+devops+
   database-architect ≈ 10.0 KB is the tightest group; use groups of 3 wherever a group of 4
   would exceed 10 KB after actually writing the file, not from the pre-split estimate).
6. `.ai/AGENTS_PROTOCOLS.md` — the 9 Meta-doc pointer stubs (~9.1 KB).
7. `.ai/AGENTS_KNOWN_ISSUES.md` — Known Issues (~8.1 KB).

**Process:** do not hand-copy sections — script the split (`csplit` or a short Python script
keyed on `^## ` headings and the measured byte offsets above) so content is preserved
byte-for-byte modulo the new file headers/cross-links, then diff-reconstruct
(`cat .ai/AGENTS.md .ai/AGENTS_*.md | <strip added headers> | diff - <original backup>`) to
prove nothing was dropped before deleting the monolithic version.

**Acceptance criteria:**
- Every resulting file: `wc -c <file>` < 10,240 (10 KB), measured, not assumed.
- `.ai/README.md`'s pointers to `.ai/AGENTS.md` updated to reference the new file set (grep
  `.ai/README.md` and every other `.ai/*.md` for `AGENTS.md` references first —
  `grep -rln "AGENTS.md" .ai/` — and update every hit, not just the obvious ones).
- Reconstruction diff (above) is empty except for added headers/cross-links.
- No `gen-docs.py`/`gen-registry.py` impact (they don't read `.ai/AGENTS.md`) — confirm by
  running both `--check` commands after the split, expect no change in output.

**Risk:** this is a big mechanical diff (100 KB touched) with no test coverage of `.ai/*`
content — the reconstruction diff IS the test. **Fallback:** if reconstruction fails to
reproduce content exactly, do not force it through; the monolithic file is not broken today,
only oversized, so there's no urgency that overrides getting the split right.

### 5b. `suggest-compact.sh` trigger — conclusion, not a task

**Verified:** `suggest-compact.sh` (read in full at plan time) already counts tool calls via a
lockfile-protected daily counter and fires a foreground `PostToolUse` message every 40 calls
— this is the FIX from `plan-token-waste-workflow-fixes.md` Issue 5, already landed (commit
`51db588`, confirmed in `git log`). The task's framing ("better trigger available to hooks, or
explicitly conclude count is the best proxy") is answered here:

**Conclusion: tool-call count is the best proxy available to a hook, and no change is
recommended.** Reasoning: a `PostToolUse` hook has no access to the actual context-window
token count (that's session/runtime-internal state, not exposed to hooks); the two
alternatives worth naming and rejecting:
- **Wall-clock time since session start** — worse proxy than call count; a session doing
  heavy `Read`-only exploration for 10 minutes burns far more context than 10 minutes of
  `Bash(ls)` calls, and time-based nudging would fire at the wrong moments in both directions.
- **Bytes of tool output/input observed** — technically closer to real context growth, but
  would require the hook to inspect every tool's payload size (available via the
  `PostToolUse` hook's JSON input), which is a bigger, riskier change to a hook that must stay
  fast (<100ms) and `exit 0`-always; the marginal accuracy gain over call-count is not
  established to be worth that risk without measurement this plan doesn't have.

**No ops.json for this sub-item** — it is a documented conclusion, not a code change. Record
it in `.ai/BACKLOG.md`'s Icebox or a new "Decided, no action" note near the top of
`suggest-compact.sh`'s own header comment (one line: "Tool-call count chosen over
byte-size/wall-clock as the context-growth proxy — see plan-remaining-fixes-2026-07-31.md
§5b for the rejected alternatives and why.") if the reviewer wants the decision durably
recorded in the file a future session will actually read.

### 5c. Backlog hygiene — verified, no changes needed

Checked `.ai/BACKLOG.md` and `.ai/SESSION_STATE.md` against the current repo state:
- Task 008 (corpus consolidation) is correctly listed in `BACKLOG.md`'s P0 ("Decision:
  consolidation merge list sign-off (task 008)") and P1 ("Task 008 prep... draft the migration
  table for owner review") — accurately blocked-on-owner, matching `CLAUDE.md`'s own framing.
- SKILL.md body-splitting (the other half of the "not implement them here" instruction) is
  correctly recorded in `SESSION_STATE.md`'s "Pending work" §5 as a task-009 follow-up
  ("splitting large SKILL.md bodies into core + references/") and separately NOT listed as an
  open backlog task (it's a documented "not in scope" note in
  `plan-context-budget-lazy-skills.md`, which is the right place for it).
- **No edits needed** to either file for this sub-item. (If a future session wants to actually
  scope the SKILL.md split, that's new planning work, not a backlog-hygiene fix.)

### 5d. Additional finding, not in the original list: stale test-count docs

Found while gathering evidence for this plan (not requested, noted for completeness per
CLAUDE.md's "surface open decisions instead of deciding them"): `grep -rl "516 tests"
.ai/ CLAUDE.md` hits 7 files (`CLAUDE.md`, `.ai/CONTEXT.md`, `.ai/AI_PROJECT_HANDOVER.md`,
`.ai/SYSTEM_OVERVIEW.md`, `.ai/MEMORY.md`, `.ai/SESSION_STATE.md`, `.ai/MODEL_ONBOARDING.md`);
actual count is 595 today (636 after Items 2–3 land). This is the same drift
`plan-ops-hardening-implementer-contract.md` §5 already found and explicitly deferred
("multi-file docs sweep, not a one-line fix... deferred to its own follow-up"). **This plan
makes the same call** — do not fix it here; file it as a new P3 `BACKLOG.md` line
("Stale test-count references across 7 `.ai/*`+`CLAUDE.md` files — sweep after this plan's
Items 1–3 land, since they change the count again") so it doesn't get silently lost twice.

---

## Implementation order (restated, with commit boundaries)

| Step | Item | Commits | Depends on |
|---|---|---|---|
| 1 | 1.1 evidence check (no commit) | — | baseline |
| 2 | 1.2 Commits A–D | 4 commits | Step 1 clean |
| 3 | 2.2–2.8 regenerate + validate + implement | 1 commit (new script + edits + tests) | Step 2 |
| 4 | 3.2–3.3 doctor check + test file | 1 commit | none (could run before 1–2, sequenced here for single-session ordering only) |
| 5 | 5a AGENTS.md split | 1 commit | none |
| 5 | 5b decision note (optional 1-line) | folded into 5a's commit or skipped | none |
| 5 | 5d backlog line | folded into whichever commit touches BACKLOG.md, or its own tiny commit | none |
| 6 | 4 fleet rollout | N/A (not a claudekit commit; separate report) | Steps 2–5 landed on `main` |

Each numbered commit is independently revertable; no step here depends on an unmerged LATER
step.

## Full DoD verification (run after every step above, and once more at the end)

```bash
python3 -m pytest tests/ -q               # 595 -> 615 (Item 2) -> 636 (Item 3)
ruff check src/ tests/ scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
shellcheck install.sh .claude/hooks/*.sh  # now runnable locally (Item 3 installs+verifies it)
```

Plus per-item acceptance criteria above, plus: CHANGELOG `[Unreleased]` entries per Item 2
(Item 1's is already present, see §1.0), and `.ai/SESSION_STATE.md` + `.ai/CHANGELOG_AI.md`
updated manually at the end of the work period per CLAUDE.md's "Docs" rule.

## Cross-cutting risks

| Risk | Mitigation |
|---|---|
| Item 2's regenerated ops.json anchors drift again before execution (the exact failure mode Item 2 exists to close) | Run `resolve`/`check` on Item 2's OWN ops.json against itself once written, as a dogfooding smoke test, before calling Item 2 done |
| Line numbers cited throughout this plan (e.g. `implement.md:32`, `main.py:198`) shift once earlier items commit | Every cited anchor is paired with either exact current content to `grep` for, or an explicit "re-verify before use" note — never rely on line numbers alone once Items 1–2 have landed |
| Fleet rollout (Item 4) run by a different session/person without this plan's context | §4 is written to be self-contained: exact commands, exact order, exact stop conditions |
| Golden Rule: any of the above lands without owner sign-off | Every item above states its dependency on Item 1's evidence check (§1.1) or is independently low-risk (doc splits, a new doctor check, a new skip-visible test) — nothing here is scoped to bypass "no code changes without explicit user approval" |

## Out of scope (explicit, carried from the source plans)

- TOCTOU freshness pinning between validate and execute (`plan-ops-hardening-implementer-
  contract.md` §7).
- Signing/authenticating review records — local-actor threat model only, same framing as
  "denylist speed bump, not a sandbox" (`plan-review-approval-binding.md` §5).
- CI parity gate for `.codex`/`.agents` mirror drift.
- Consolidating the two duplicate CI shellcheck jobs (§3.4 — filed as a BACKLOG follow-up).
- `usedBy` field semantics cleanup, command-file mandatory-skill trimming (task 009 follow-ups,
  unrelated to this plan).
- Task 008 corpus consolidation itself (owner-gated, tracked separately per §5c).
