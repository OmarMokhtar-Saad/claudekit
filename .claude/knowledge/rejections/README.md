# Rejection briefs

Durable, project-local record of **why a plan was rejected**, so a later session can learn
from a review round instead of repeating it.

- `<ops-slug>.md` — one appended section per non-approving review round.
- `INDEX.jsonl` — one appended line per brief section (append-only sidecar index).

**These files are TRACKED on purpose.** They are the feedback loop's only durable carrier;
an untracked brief dies with the machine that wrote it.

## Who writes this

Exactly one writer: `review-record.py cmd_write`, after the review record and its ops
snapshot are already on disk. Emission is fail-soft by construction — any failure warns to
stderr and the verdict is still recorded. Nothing in this directory can withhold an
execution approval.

Trigger: the **2nd** non-approving round (REJECTED, REVISE, or score < 90) for one ops
slug. Key: `slug` + `round`, so re-running `write` never duplicates a line or a section.

## What is in a brief

Plan slug, session id, per-round scores/decisions, the verdict trail, ODC `defect_type` and
`trigger` (recorded EMPTY — a guessed classification is worse than an absent one; the
analyst or a human fills them), `prompt_version`, and the reviewer's findings.

## What is NEVER in a brief

- The **absolute transcript path**. It trips `_safe_text` and the secret self-scan.
- The **SessionStart reflection token**. It is never read on this path.
- Any raw free text: findings pass through `reflection.py` `_safe_text` (which *rejects*)
  and fall back to `bounded_token` (which *digests*), so unsafe text lands as a digest
  rather than leaking or silently vanishing.

## Why the session id is a raw UUID and not a hash

The whole value of a brief is that a later agent can open the session that produced the
rejection: `transcript-miner.py <session-id> --around <ops-slug>`. Transcripts live at
`~/.claude*/projects/<project-slug>/<session-uuid>.jsonl`, so a hashed reference is
unresolvable and root-cause analysis dies. A session UUID is a local filename, not a
credential. It is recorded only when it matches `^[0-9a-fA-F-]{8,64}$`; anything else is
recorded as `unknown`.

## Reading them back

```bash
python3 .claude/operations/scripts/review-record.py rejections search "<keywords>"
```

Exit 0 = match, exit 3 = nothing recorded. **Silence is not evidence:** no match means
unknown, not "this never happened". A brief is a prior, not a proof — verify it against the
current tree before acting on it.

## Why the prompts say what they say

Kept here, not in `planner.md`/`reviewer.md`: those two files are loaded into **every**
pipeline spawn and are gated by `scripts/check-context-floor.py`, so rationale belongs
where it is pulled on demand and the rule stays in the prompt.

**Why every round must emit the verdict block.** Measured on the live corpus before this
change: **80 review records, 80 APPROVED, 79 of 80 single-round.** Not because review always
passes — because only the round that passed was ever written. `rounds[]` is the only durable
trace a verdict leaves, so a rejection that is never written leaves none at all.

**Why `/code-review` records only BLOCK and REQUEST CHANGES.** `review-record.py` writes
score/decision at the TOP level of the record, and `cmd_check` authorises execution on
`decision == "APPROVED"` plus a threshold. Recording an APPROVE from a **diff** review would
therefore let a review that never scored the plan authorise execution of its ops.json — a
privilege escalation. A non-approving verdict cannot do that: `check` still exits 4.
`--only-non-approving` enforces it **inside the parser**, because an earlier shell filter and
`parse_verdict` could read different verdict blocks when the anchors differed in whitespace.

**Why a hit is a PRIOR and not a proof.** A brief records what one reviewer decided about one
plan at one commit. Re-read the files before acting on it, and separate the three causes that
need opposite fixes: a weak plan (yours to fix), a miscalibrated rubric, an underspecified
task. Silence is not evidence: no match means unknown, not "this has never gone wrong".

## Backfilled rows are reconstructions, and are marked as such

`review-record.py rejections backfill` mines session transcripts for review verdicts that
predate the capture path. **Its default is a dry run**: it prints what it would write —
transcripts scanned, verdict blocks found, unparseable, approving, unattributable, rows —
and writes nothing without `--write`.

A backfilled row is lower confidence than a live one, because a transcript-derived verdict
is *reconstructed*, not recorded. Every such row is identifiable:

| field | value |
|---|---|
| `source` | `backfill` |
| `verdict_origin` | `reconstructed` — excluded from every score trend, like `gate-token` |
| `confidence` | `reconstructed-from-transcript` |
| `round` | **negative** (`-1`, `-2`, … oldest first per slug) |

The round is negative because the transcript does not carry one. A negative ordinal keeps
the single `(slug, round)` idempotency key every other reader already uses and can never
collide with a live round, so a re-run is a no-op and a backfilled row can never be
mistaken for a recorded one.

**It reads ONE project: this one.** Claude Code stores transcripts per project under
`~/.claude*/projects/<mangled-path>/`, and the unscoped glob matched **99 project roots,
2019 transcripts, only 172 of them this repository's** — a real dry run proposed 17 rows of
which **9 came from two unrelated repositories**. Every kitted project writes
`ops-<slug>.json`, so the slug filter scopes nothing; only the project root does. The scan
resolves this repo's directory (`--project-root` overrides it), **fails closed** when it
cannot — scanning nothing rather than everything — and the dry-run report names the scope
and the per-project transcript count before you approve `--write`.

Slugs are normalised through `ops_slug()` / `plan_slug()`, the same functions the live
records use, so a backfilled row keys under the slug its own live history uses.

Two refusals are load-bearing. **Attribution never guesses**: the ops slug must be the one
and only candidate in the verdict's window, or the verdict is skipped and counted.
**Credential scrubbing fails closed**: without `reflection.py`'s `redact_secrets`, backfill
refuses to read transcript text at all rather than emitting it unscrubbed. And backfill
writes **only** this store — never `.claude/reports/reviews/`, which is the file
`cmd_check` authorises execution from.


## `defect_type` / `trigger`: written only by `rejections classify`

`cmd_write` records both fields EMPTY and always will. It cannot classify a defect, and a
guessed label is worse than an absent one: the distribution **shift** over these two axes
is the process signal, so a distribution polluted by inference measures the inference.

```
review-record.py rejections classify <slug> <round> --type T --trigger X [--by NAME]
```

- **Append-only.** A classification is a new `{"row_type": "classification", ...}` line in
  `INDEX.jsonl`. Re-classifying appends again; readers fold and take the last, and every
  earlier call stays on disk. A correction that destroys what it corrects is not a record.
- **Refuses what it cannot verify.** Exit 3 when no brief row exists for `(slug, round)`;
  exit non-zero for a type outside `DEFECT_TYPES` or a trigger that is not a kebab token.
- **The type vocabulary is closed and is `flow-analyst.md`'s**, so the prompt that
  proposes a label and the script that records it cannot drift apart.
  `--trigger` is deliberately open (shape-validated only): it names a reviewer rubric
  line, and those are not a stable enumeration.
- `rejections stats --by-type` prints both distributions over **classified rows only**,
  with `unclassified=N` beside them. Nothing is imputed into `other`.


## How `session_id` is resolved, and why it refuses to guess

Order: `--session-id` → `CLAUDE_SESSION_ID` → `CLAUDEKIT_SESSION_ID` → a **proven**
process-tree match against the pointer the SessionStart hook records → `"unknown"`.

**Recency is not in that list on purpose.** Measured on the host this was written on:
21 transcripts modified within two hours, the newest of them `agent-*.jsonl` (a subagent,
never a session), and several belonging to sessions running concurrently in this same
repo. "The most recently modified transcript" therefore resolves to the wrong file, and a
wrong session id is worse than none: `transcript-miner.py` would slice an unrelated
session and the analyst would attribute someone else's work as the cause of a rejection,
with nothing downstream able to notice.

The proof is common ancestry. `reflection-gate.py` sees the only authoritative session id
this repo ever gets — the hook payload's — and records it beside its own ancestor pids in
reflection.py's external ledger root (outside the repository, 0700, 24h TTL, so no session
token ever reaches a tracked file). `review-record.py` intersects its own ancestor chain
with those and accepts the match only when it is **unique at the nearest depth**: nesting
resolves (an inner `claude -p` shares the outer session's ancestors) and two concurrent
sessions resolve to `"unknown"` rather than to a coin flip.

**`session: unknown` means brief-only, not "no transcript existed".** It is announced by a
`WARNING` when the brief is written, counted by `rejections stats` as
`unresolved_sessions=N`, and reported by `rejections search` on every hit it affects. The
commands pass `--session-id "${CLAUDE_SESSION_ID:-}"` explicitly so the dependency is
visible at the call site and works the moment anything exports the variable — but a slash
command has no channel to the id either, so that is plumbing, not the fix.


## Rationale relocated from `code-reviewer.md`

Both agents' prompts are budgeted; this file is not, and it is read on demand. So the rules
stay in the prompts and the arguments live here.

**Why the verdict block is mandatory on EVERY round, not just on a rejection.** Measured on
the live corpus before the loop shipped: **80 review records, 80 APPROVED, 79 of 80
single-round.** Not because review always passed -- because only the round that passed was
ever written. `rounds[]` is the only durable trace a verdict leaves, so a rejection that is
never written leaves none at all, and the entire rejection corpus this store exists to hold
was produced and discarded for months.

**Why `code-reviewer` emits a number at all, having been told never to score.** Its Exit
Rule is a blocking-finding COUNT, deliberately: a number invites another round over
findings that do not block, which is how an 85/100 with zero blockers gets read as a
rejection. But `review-record.py` refuses to parse a block without `SCORE:`, so a
score-less code review records nothing. The fixed VERDICT->SCORE table (95/92/75/60) is the
narrow resolution: the integer is a **gate token**, a fixed function of the verdict, never
a judgement, and the Exit Rule -- not the number -- still decides whether there is another
round. The alternative considered and rejected was teaching the parser to accept a
score-less block, which changes behaviour on the execution-approval path.

