# Implementation Plan: close the three known gaps in agent memory

Tier 3 (the clustering change alters what text reaches a file that is auto-injected into
an agent's system prompt). Branch: `feat/memory-scaffold-fleet`.
Ops config: `.claude/plans/plan-memory-maturity.ops.json`.
Artifacts written: `.claude/operations/scripts/knowledge-ledger.py`,
`src/claudekit/cli/main.py`, `tests/test_agent_memory_scaffold.py`,
`tests/test_doctor_gate.py`, `tests/test_memory_injection_contract.py`, `install.sh`.

**`install.sh` was not in the original scope.** The Phase 2 contract test found a defect
in the shipped stub while being written: its example line `- [Title](file.md)` is a
literal markdown link to a file that never exists, so **every fresh install carried a
dangling memory link** — a memory the agent is told about and cannot follow. The template
now describes the format instead of demonstrating it with an unresolvable link. Recorded
here because a test that finds a real defect the first time it runs is the point of
writing it, and the artifact it touches has to be named to be reviewed.

## Overview

Three gaps were disclosed rather than fixed when the scaffold shipped. Each is now
measured, not asserted:

1. **`distill` cannot cluster.** Grouping is exact-match on the signature after
   whitespace normalisation. Run against real corpora: AppiumLens 15 receipts → 15
   groups; qa-agents 82 receipts → **82 groups**. Zero merges at either scale. A human
   clustered both by hand, and 73 of qa-agents' 82 collapsed into 6 lessons — so the
   signal is there and the tool cannot see it.
2. **Nothing proves an agent reads its memory.** 17 tests assert the file is written.
   None asserts it is written where Claude Code actually loads from, in a shape it can
   load. The feature's core claim is unverified.
3. **No aging, and the size warning fires too late.** `doctor` warns only once a file is
   already past 200 lines — i.e. once Claude Code is already silently truncating it. No
   signal at 150, and nothing ages out a stale entry.

## Phase 1: opt-in fuzzy clustering

**Why this is safe to add now, having refused it before.** The earlier refusal was
correct in context: an unreviewed similarity heuristic must not decide what reaches a
system prompt. Three properties change that:

- Clustering affects the **draft only**. `distill` still never writes `MEMORY.md`.
- It is **opt-in** (`--similarity N`), default off. The literal path is untouched, so
  every existing behaviour and test stands.
- The draft **shows its work**: each group lists the receipts it merged, so a human
  verifies the grouping rather than trusting it.

**Algorithm — deterministic, stdlib-only, explainable.** Token-set Jaccard over the
normalised signature:

- lowercase, split on non-alphanumerics, drop tokens of 2 characters or fewer
- drop a small stop-list of words that appear in nearly every receipt and therefore
  carry no signal (`assumed`, `would`, `could`, `this`, `that`, `were`, `which`)
- similarity = `|A ∩ B| / |A ∪ B|`
- greedy single-pass agglomeration over a **pre-sorted** corpus

**What "deterministic" does and does not mean here.** Pre-sorting guarantees the result
is independent of **filesystem enumeration order** — that is the property Phase 4 tests.
It does **not** by itself make greedy agglomeration insensitive to comparison order;
that is what the complete-linkage rule below is for. The earlier wording conflated the
two.

**Comparison rule: complete linkage, stated explicitly.** A receipt joins a group only
if it meets the threshold against **every existing member**, not against the
last-inserted one or a centroid. This is what bounds chaining: without it, A~B and B~C
above threshold would drag A and C together even when A~C is below it, which is exactly
the over-merging this feature must not do silently. Phase 4 tests that case directly.

**`--similarity` takes an integer percentage, 1-99.** 100 is rejected with a message
pointing at the default, because **Jaccard = 1.0 is NOT equivalent to today's exact
match** — an earlier draft of this plan claimed it was "by construction" and that was
false. Jaccard compares token *sets*; the literal path compares normalised *strings*.
Measured counterexample:

| A | B | literal-equal | Jaccard |
|---|---|---|---|
| `tests mock the database` | `the database tests mock` | **False** | **1.00** |
| `a heredoc is refused by the guard` | `...by that guard` | False | 0.75 |

Reordered words, and words separated only by dropped stop-tokens, give 1.0 while the
literal path keeps them apart. Dropping short tokens and stop-words makes this *more*
likely, not less, since it discards information before the comparison. So omitting
`--similarity` is the only way to get literal grouping, and it remains the default — one
path, reached by not opting in, rather than a second path claiming to imitate the first.

**No LLM.** A model call here would make the draft non-reproducible and add a network
dependency to a stdlib-only script. The clustering only has to be good enough for a
human to accept or split; it does not have to be right.

**Refusal preserved.** Every sanitiser check runs per group, unchanged. A group whose
text still carries a secret after redaction is refused, exactly as before.

## Phase 2: the injection contract

A true end-to-end proof — spawn an agent, confirm it behaves differently — needs a live
model call, which is neither deterministic nor available in CI. State that limit rather
than fake it.

What *can* be pinned, in a new `tests/test_memory_injection_contract.py`:

- The path Claude Code loads is `.claude/agent-memory/<agent>/MEMORY.md`, exactly as
  written by the installer, for **every** agent declaring `memory: project` — derived
  from the tree, so a renamed agent fails the test.
- `declaring_agents()` (what `distill` routes by) and the agent set `doctor` enumerates
  stay in sync — a drift there is silent in exactly the way this plan worries about.
- Every shipped `MEMORY.md` in this repo is within **200 lines and 25 KB**, the documented
  truncation limits.
- A `MEMORY.md` carries **no YAML frontmatter**: it is the index Claude Code injects
  verbatim, and a `---` block would be injected as literal text.
- Every `[[wikilink]]` and every markdown link in an index resolves to a file that
  exists beside it — a dangling pointer is a memory the agent cannot follow.
- `distill`'s draft path is that same path plus `.draft`, so a human moving the draft
  lands it exactly where injection reads.

Named honestly: a contract test, not proof of behaviour. The docstring says so.

## Phase 3: aging and an earlier warning

- **`doctor` warns at 80% of the cap (160 lines)**, before truncation begins, with the
  count and the cap. The existing over-200 warning stays and takes priority.
- **`distill --stale DAYS`** lists entries whose `date:` is older than DAYS and are still
  unfixed, so a human can close them deliberately. It **lists only** — never closes.
  Closing on a clock is the silent-retirement failure this ledger already learned from
  (`entry_status`'s malformed→UNFIXED rule exists for exactly that reason).

## Phase 4: tests

Behavioural, running the real script:

- Omitting `--similarity` reproduces the literal grouping exactly.
- The measured divergence is pinned with **these exact strings**: `tests mock the
  database` and `the database tests mock` are two groups literally, and score Jaccard
  1.0. Pinning the literal strings (not a paraphrase) is deliberate: the divergence
  depends on the tokenizer regex and stop-list, so drift there must re-break this test
  rather than silently resurrect the retracted equivalence.
- `--similarity 60` merges two paraphrases of one lesson, and does **not** merge an
  unrelated signature.
- Clustering is independent of **filesystem enumeration order**: the same receipts
  discovered in a different order produce the same groups.
- **Chaining is bounded.** Fixture where A~B and B~C are above threshold but A~C is
  below: assert C does **not** join A's group. This is the deliberate assertion the
  complete-linkage rule exists to make true. It asserts **non-membership only, never a
  specific group shape** — which of `{A,B}+{C}` or `{B,C}+{A}` results is comparison-order
  dependent, which the plan does not claim to control. Do not tighten this assertion.
- `--similarity 100` is **rejected** with a message naming the default, and the message
  says why (token-set equality is not string equality).
- A merged group lists every receipt it consumed.
- Sanitiser refusal still fires **inside** a fuzzy group (the refusal is not bypassed by
  clustering).
- `doctor` warns at 160 lines and still warns past 200, with the over-200 message
  taking priority.
- `--stale 1` lists an old unfixed entry and does not modify it.
- The whole injection-contract suite above.

## Rollback

Every phase is additive and opt-in.

| Phase | Undo | Residue |
|---|---|---|
| 1 | Revert. `--similarity` is opt-in and defaults off, so the literal path is what ships either way. | None. Drafts are not `MEMORY.md`. |
| 2 | Revert. Tests only. | None. |
| 3 | Revert. The 160 warning disappears; the 200 warning is untouched. `--stale` only ever printed. | None. |

No migration, no deletion, no format change. `distill` still never writes `MEMORY.md`
and still never closes a receipt.

## Risks

- **Over-merging.** Two distinct lessons merged into one entry would lose one. Bounded
  in four ways, in order of strength: complete linkage (a receipt must clear the
  threshold against every member, so chaining cannot quietly widen a group); opt-in with
  literal grouping as the default; the draft listing every receipt per group; and the
  human accept step. The first is the real bound — the others are backstops. The failure
  is visible in the draft, never silent in the prompt.
- **A retracted safety claim.** This plan previously asserted `--similarity 100` was
  identical to literal grouping and used that as the anchor for reversing an earlier
  refusal. It was false, and a maintainer could have relied on it. It is now retracted
  in the text above with the counterexample that falsifies it, and 100 is rejected
  outright rather than quietly admitting extra merges.
- **Under-merging** is the status quo and costs nothing new.
- **A false sense of coverage from Phase 2.** Mitigated by naming it a contract test in
  the docstring and in this plan.

## Definition of Done

`pytest` · `ruff` · `mypy` · `gen-docs --check` · `gen-registry --check` ·
`check-plan-artifacts --check` · `check-context-floor --check` · `shellcheck` ·
CHANGELOG · conventional commit.
