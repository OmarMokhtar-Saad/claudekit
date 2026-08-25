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
