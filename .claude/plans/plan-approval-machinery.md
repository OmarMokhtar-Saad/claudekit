# Plan — repair the approval machinery so it can service a multi-config plan

**Tier:** 3 (security-relevant: this is the Iron Law's own enforcement path)
**Slug:** `approval-machinery` — plan file and ops file share it deliberately; see
"Bootstrapping" below.
**Ops config:** `.claude/plans/ops-approval-machinery.json`

## Why this is Phase 1a, ahead of the dispatcher work

`.ai/BACKLOG.md` `## Approval-machinery defects, found by using it (2026-08-22)`
files five defects that made the sanctioned execution path unable to service a plan
with more than one ops config. Every subsequent plan in this repo has to be executed
through that path, so repairing it first means the dispatcher work (Phase 1b) can be
serviced normally instead of hand-dodging the slug defect with carefully chosen
filenames. The handoff ranked the ARG_MAX regression first; that ordering is kept
within Phase 1b, but the machinery repair is a prerequisite to executing anything
cleanly and is therefore lifted ahead of it.

## Root cause: three filed defects are one bug

The two `[HIGH]`s and the `[MEDIUM]` overwrite are the same defect seen from three
angles: **review records are keyed by the PLAN slug, while the executor's gate
resolves candidates from the OPS filename.**

- `review-record.py:56` `plan_slug()` strips `plan-` from the *plan* stem.
- `review-record.py:94` `record_paths(slug)` names the record from that slug.
- `execute-json-ops.py:777` `_approval_slugs()` derives candidates from the *ops*
  filename first, then the config's `plan` field.

Verified on the live artifact the backlog says is stuck: `.claude/plans/ops-mcp-probe.json`
carries `"plan": "mcp-probe-addendum"`, so the executor looks for records under
`mcp-probe` / `mcp-probe-addendum`, while the record written for it sits under
`generators-that-cannot-drift`. Hence `no review record for 'mcp-probe'` on a config
that was reviewed APPROVED 93.

The same keying explains the overwrite: two configs under one plan collapse onto one
record path, and the second `write` destroys the first (measured live: 105925 -> 10524
bytes).

**One change fixes all three:** key the record by the ops config's identity. The
executor already resolves from the ops filename, so the two sides then agree by
construction rather than by coincidence.

The remaining `[HIGH]` (`--stamp-baseline` vs the approval hash) turns out not to be
a code defect at all — see C2.

## Changes

### C1 — key review records by ops identity (`review-record.py`)

`record_paths()` takes the ops path instead of the plan slug and derives the key by
inverting exactly the filename forms `resolve_ops()` emits — `plan-x.ops.json`,
`ops-x.json`, `x.ops.json`, `x.json` all key as `x`. This is the same inversion
`_approval_slugs()` already performs, so the two implementations agree on the key.

The record body keeps `plan` for provenance, and gains `slug` naming the key
explicitly, so a future consumer never has to re-derive it.

**Backward compatibility.** Records already on disk are keyed by plan slug.
`check` and `diff` therefore look up the ops key first and fall back to the legacy
plan-slug path, reporting which one satisfied the lookup. `write` only ever writes
the new key — the legacy path is read-only, so it drains as plans are archived rather
than needing a migration step. Nothing under `.claude/reports/` is a source artifact,
so no migration is warranted.

The path-sanitisation in `record_paths()` (collapse non-`[A-Za-z0-9._-]`, strip
leading dots) is preserved verbatim: the key is now derived from a filename rather
than a plan stem, which is no less attacker-influenced, so the guard still earns
its place.

### C2 — the stamp/approval collision is a SEQUENCING defect (no code fix)

The backlog files this as a `[HIGH]`: `--stamp-baseline` writes a `baseline` key into
the config, the review record binds `sha256(ops.json)` over raw bytes, so stamping
invalidates the verdict and `check` refuses with DRIFT — "any plan whose steps say
'stamp, then execute an approved config' is unrunnable by construction."

That is true only of that ORDER. Measured on unmodified `HEAD`, with no code change:

    1. validate-config-json.py ops-order.json --stamp-baseline   -> APPROVED
    2. review-record.py write plan-order.md ops-order.json ...    -> Recorded APPROVED (95)
    3. execute-json-ops.py ops-order.json
         Approval: reviewed verdict verified for this exact ops.json
         Baseline: verified (1 file(s) unchanged since stamping)
         Successful: 1

Stamp, then record, then execute. The two mechanisms do not actually cancel; they
were merely being invoked in the wrong order. Re-stamping after approval SHOULD
force re-review — the artifact changed.

**A sidecar redesign was drafted here and CUT.** It moved the baseline to
`<config>.baseline.json` with a `baseline_sidecar` declaration in the hashed bytes.
Two review rounds rejected it (82, then 62 with five MAJORs), and the reasons are
worth recording so it is not attempted again:

- Requiring the declaration made `--stamp-baseline` reject **every config the repo's
  own generator emits**. `implementer.md:83` runs that command unconditionally and
  treats non-zero as STOP, so step 1 of the sanctioned workflow would have broken for
  every future plan. The consumers (5 test call sites) were migrated; the producers
  were not, and a green suite hid it.
- Tamper-evidence was only partly restored. Deletion refused, but re-stamping after
  drift, or swapping in a baseline computed over an unrelated file, both still yielded
  `Baseline: verified` with the approval record intact — while the plan prose claimed
  the trade was "closed". Hard rule 6.
- `echo '{}' > <config>.baseline.json` disabled the drift gate at rc 0, printing
  `Baseline: none` — the exact outcome the new code's own docstring called "strictly
  worse than having no gate".

So the whole of C2 reduces to two cheap, safe things: **make the DRIFT refusal name
stamping as the likely cause** (the message "ops.json changed after it was reviewed"
is what sent a previous session redesigning the mechanism instead of reordering two
steps), and **pin both orders with tests** so the working one cannot regress and the
broken one keeps being caught. `validate-config-json.py`, `execute-json-ops.py`,
`operations-schema.json` and `test_work_loss_protection.py` are untouched.

### C3 — put the `=== REVIEW ===` block in the reviewer's contract

`review-record.py --from-review` parses an anchored `=== REVIEW ===` block
(`_BLOCK_RE`, `_SCORE_RE`, `_DECISION_RE`). `reviewer.md:242` does mention that block
— but only to say that *if the caller specifies such a format, it wins*. So the
backlog row is slightly imprecise: the prompt is not silent, it is **conditional**,
and a caller who does not spell out the format still gets prose. The fix is therefore
to make the block mandatory and specify it inline, not to add it from nothing.

Either way the consequence is the same: a reviewer can return a flawless verdict the
approval gate cannot consume — measured this session as five review rounds of prose
with execution stalled behind them.

Fix: state the required output block in `reviewer.md`, with the exact anchors and
field forms. The template in the prompt is deliberately written so that the *example*
does not itself parse as a real score — `_SCORE_RE` is anchored to digits, so
`SCORE: <integer 0-100>` cannot be mistaken for a verdict. This is asserted by test
T4 rather than assumed.

### C4 — stop `reviewer.md` demanding proofs it cannot run

`subagent_type: reviewer` has no Bash, so the mutation proofs its own prompt demands
are impossible for it; every finding that mattered this session came from
`code-reviewer`. The backlog offers "grant `reviewer` Bash, or retire it in favour of
`code-reviewer`".

Taking the second option, in its narrow form: `reviewer.md` is amended to scope its
own remit to artifact review, and to route any review that must *prove a gate binds*
to `code-reviewer`. Granting Bash to a plan-review agent would widen a tool surface
to fix a prompt inconsistency, which is the more expensive of the two fixes and needs
an owner decision; scoping the prompt needs none and removes the false demand today.
Recorded in the backlog row as the narrower fix taken, with the tool grant left filed.

## Bootstrapping (chicken-and-egg)

This plan repairs the very gate it must pass through, so it has to be executable
under the *current*, broken rules. With `plan-approval-machinery.md` and
`ops-approval-machinery.json`, today's `plan_slug()` yields `approval-machinery` and
today's `_approval_slugs()` yields `approval-machinery`. The two agree, so this
config approves and executes on the old code path. No `--no-approval`, no
self-issued record.

`--stamp-baseline` is **not** used on this config — not because it is broken, but
because the config has no need of it and stamping would only add a step whose
ordering constraint (C2) must then be honoured. The baseline behaviour is exercised
on throwaway configs in T3 instead.

## Tests — behavioural, each proven by mutation

Ten cases in `tests/test_approval_machinery.py`, driving the real scripts against a
real temp tree. **Eight fail against unmodified `HEAD`** (measured: `8 failed,
2 passed`). The other two are PIN tests, not regressions, and are labelled as such
rather than counted as proof:

- `test_stamp_then_record_then_execute_succeeds` passes on `HEAD` by design — it
  pins the working order C2 identifies, which is the whole point of that finding.
- `test_diff_renders_a_legacy_snapshot_for_its_own_config` passes on `HEAD` because
  `HEAD` keys by plan slug natively. It binds to the NEW code, proven by mutation
  below rather than by a red-at-HEAD run.

Coverage:

- **T1** an addendum config named differently from its plan executes, asserting
  `Approval: reviewed verdict verified` on a REAL execution. A `--dry-run` cannot
  test this: the executor prints `Approval: not required for --dry-run` and skips the
  gate — a first draft passed against `HEAD` for exactly that reason.
- **T2** two configs under one plan both keep their records and both still verify.
- **T3a/T3b** the working and broken stamp orders (C2), including that the DRIFT
  refusal names `--stamp-baseline`.
- **T4a/T4b** the block `reviewer.md` specifies parses when filled, and the unfilled
  placeholder records no verdict.
- **Legacy fallback** on `check`: a re-keyed record still authorises its own config
  and says which key satisfied the lookup; and a legacy record cannot authorise a
  DIFFERENT config (the sha256 binding refuses it, exit 2 — resolution can only ever
  be over-permissive down to byte identity, so this fails closed).
- **Legacy fallback on `diff`**, and `_record_covers`. Round-2 review deleted both and
  the full 1939-test suite stayed green — no test invoked `diff` at all. Both are now
  bound.

**Mutation results** (each on a fresh copy with the config applied):

| Mutant | Result |
|---|---|
| M6b — delete the `cmd_diff` legacy fallback | RED (`test_diff_renders_a_legacy_snapshot_for_its_own_config`) |
| M7 — `_record_covers` returns `True` | RED (`test_diff_refuses_to_borrow_another_configs_snapshot`) |

M6b and M7 both left the suite fully green before this revision; they are the two
`vacuous-check` instances round 2 identified, and closing them is what takes that
class off its standing debt for this seam.

## Risk

- **C1 changes where approvals are looked up.** Mitigated by the legacy read-path
  fallback and by T1/T2. Worst case is a lookup miss, which fails CLOSED (exit 3,
  `NO RECORD`) — it cannot turn an unapproved config into an approved one.
- **C2 changes nothing about where the baseline lives.** The sidecar redesign was
  cut, so `validate-config-json.py`, `execute-json-ops.py` and
  `operations-schema.json` are untouched and the baseline stays in the config. The
  residual is stated plainly rather than mitigated: an in-config baseline is only as
  trustworthy as the config's own approval binding, and that binding is intact —
  editing or removing the baseline changes the bytes the review record hashes, which
  is exactly why the sidecar was a downgrade. C2's only code change is five lines of
  refusal TEXT in `review-record.py`, which cannot affect a verdict.
- **C3/C4 are prompt-only** and cannot affect the enforcement path at runtime.
- No change to `MAX_DELETIONS`, **no deletions of protected files** (`reviewer.md`
  does match `PROTECTED_PATTERNS` `*.md`, but protection is consulted only on
  `file_delete` — `execute-json-ops.py:569` — and nothing here deletes), no new
  dependency, no component-count edits, no new assets.

## Asset-count delta

Net **0** new assets. C1 and C2 modify one existing script (`review-record.py`);
C3/C4 modify one existing agent prompt. One new test module. Three operations, nine
edits, two files touched plus the new test.

## Definition of Done

Archive the spent config FIRST: `test_delivery_contract_smoke.py` asserts that every
queued config under `.claude/plans/` validates against `HEAD`, and this config edits
the very files it validates against, so in the other order the suite is red for a
reason that has nothing to do with the change.

    # 1. archive ops-approval-machinery.json + README row, THEN:
    python3 -m pytest tests/ -q
    ruff check src/ tests/ scripts/
    mypy
    python3 scripts/gen-docs.py --check
    python3 scripts/gen-registry.py --check
    python3 scripts/gen-model-policy.py --check
    python3 scripts/check-context-floor.py
    shellcheck install.sh .claude/hooks/*.sh

Then: archive `ops-approval-machinery.json` to `.claude/plans/archive/` with a README
row; update `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md`, `.ai/BACKLOG.md` (tick the
four rows, record C4's narrower fix and the deferred tool grant), and `CHANGELOG.md`
`[Unreleased]`. Verifier does not auto-run — ask first.

## Out of scope

Phase 1b (ARG_MAX resolver-to-stdin, `decisions.merge` parity, the two remaining
LOWs) and Phase 2 (`ck adapt`). Baseline tamper-evidence: the sidecar attempt is cut,
and the residual (an in-config baseline is only as trustworthy as the config's own
approval binding, which is intact) is left as-is rather than redesigned. Granting `reviewer` the Bash tool — owner-gated,
left filed.
