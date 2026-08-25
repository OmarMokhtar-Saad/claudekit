# Plan — Phase 1b: free the dispatcher's stdin, and close the merge/LOW findings

**Base:** `726d3b9` (local `main` moved mid-session; the
review record binds to this commit, not to the earlier `54f82c8`)
**Tier:** 3 (security-relevant: `dispatch.sh` is the blocking-hook path)
**Slug:** `dispatcher-payload` — plan and ops filenames share it.
**Ops config:** `.claude/plans/ops-dispatcher-payload.json` (authored after sign-off
on this document; Phase 1a must be green first)

## Scope

The `## Post-execution findings — dispatcher wiring + approval machinery` rows in
`.ai/BACKLOG.md`, in the ranked order they are filed, minus the approval-machinery
section (Phase 1a).

## D1 — the >1 MB payload regression `[HIGH]`

`.claude/hooks/dispatch.sh:254` passes the payload through the ENVIRONMENT
(`CK_PAYLOAD="$PAYLOAD"`) because the heredoc already occupies stdin. Past `ARG_MAX`
(1048576) `execve` returns `E2BIG`, the resolver fails, and the blocking branch exits
2. Measured in the backlog: 1000.1 KB -> rc 0; 1020.1 KB -> rc 2, with a message
naming neither the size nor the cause.

**The obvious fix is WRONG and must not be repeated.** Spilling the payload to a
`ck_mktemp` file and passing `CK_PAYLOAD_FILE` was planned, reviewed twice (82, then
61 with six MAJORs) and abandoned unexecuted at `b7d1cc8`. Measured: unpatched under
`ulimit -f` gives a correct fail-closed `rc 2`; patched gives `rc -25` (SIGXFSZ). It
introduces the first payload-sized write in `dispatch.sh`, hence a new `RLIMIT_FSIZE`
kill surface, and a signal-killed hook emits neither 0 nor 2 — breaking hard rule 2
and plausibly reading as NON-blocking to the host. That trades a fail-CLOSED
usability bug for a possible fail-OPEN safety bug.

**The fix taken: move the resolver body into a file beside `dispatch.sh` so stdin is
free, and pipe the payload in.** The backlog names this as the second option and it
dodges every objection to the first, because **nothing is written to disk at all** —
no new `RLIMIT_FSIZE` surface, no cleanup branch, no `ulimit -f` test that skips on
both macOS and Linux. A pipe has neither an `ARG_MAX` nor a file-size limit.

    HANDLERS=$(printf '%s' "$PAYLOAD" | EVENT="$EVENT" TOOL_NAME="${TOOL_NAME:-}" \
        python3 "$SCRIPT_DIR/dispatch_resolve.py" "$REGISTRY" 2>>"$LOG_FILE")

The resolver reads stdin instead of `os.environ["CK_PAYLOAD"]`. Its logic moves
verbatim — the registry invariant, the readable/unreadable distinction, the
matcher/precondition asymmetry and the whitespace-in-args rejection are all
behaviour-preserving.

**"Only the transport changes" is NOT true of the naive move, and review proved it.**
`os.environ` decodes with `surrogateescape` and cannot raise, so an undecodable
payload merely became `readable = False` and every guard ran. Text-mode stdin decodes
with `errors='strict'` under a normal user locale (`LANG=en_US.UTF-8`), so one invalid
UTF-8 byte raised `UnicodeDecodeError`, the resolver exited 1, and handler resolution
produced nothing — measured 10 handlers to 0 on a non-blocking event. The suite could
not see it because no test sets a locale. The resolver therefore reads
`sys.stdin.buffer` and decodes with `surrogateescape` explicitly, which restores the
old semantics exactly, and a locale-setting regression test covers both a blocking and
a non-blocking event.

**Two details that are not incidental:**

1. **Read stdin FIRST, before anything that can exit** — necessary, but NOT
   sufficient, and an earlier revision overclaimed here. Draining first covers the
   resolver's own `exit 3` paths (unreadable registry, illegal registry row). It does
   nothing for the paths where the resolver never starts — missing file, syntax error,
   resolver-is-a-directory — and review measured all three leaking
   `printf: write error: Broken pipe` onto user-visible stderr, directly above the
   BLOCKED line, at 2 MB. So the writer's stderr is redirected to the log as well.
   Both are needed; neither alone closes the LOW.
2. **The refusal message must name the size and the cause.** Today it says only
   `BLOCKED: could not resolve hook handlers for PreToolUse`. It gains the resolver's
   exit code and the payload length, because a refusal an operator cannot diagnose is
   most of why this row sat unfixed. The length is labelled **chars**, not bytes:
   `${#PAYLOAD}` counts characters, and calling that "bytes" while diagnosing a byte
   limit would be its own small lie.

### D1's packaging trap — the reason this is not a two-line change

- `install.sh:273-284` `_copy_hook_assets` ships **every** file in `hooks/` (its own
  comment records why: `python3 <missing>` exits 2, and one fresh install blocked
  every Edit, Write and Bash). So a `.py` sibling ships correctly. Verified by
  reading; to be re-verified by installing.
- But `scripts/gen-docs.py:75` `HOOK_GLOBS = ("*.sh", "*.py")` counts it, and
  `_is_helper_module` only recognises a `.py` helper when a sibling **imports** it
  (`^\s*(?:import|from) <stem>`). A resolver invoked as `python3 dispatch_resolve.py`
  is imported by nothing, so it would inflate the published hook count 22 -> 23 and
  turn `gen-docs --check` red.
- Moving it to a subdirectory is NOT an option: `_copy_hook_assets` copies only
  regular files (`[[ -f ]]`), so a subdir would not ship, and every hook would then
  fail closed in installed trees — the exact catastrophe that comment is about.

**Fix:** extend `_is_helper_module`'s non-`.sh` branch to also treat a `.py` as a
helper when a **shell** sibling invokes it by path, on a line that is not a comment.
Two narrower-looking versions were measured wrong first, each silently taking the
count 22 -> 21 with every test green:

1. matching the bare filename anywhere — `iron-law-gate.py` discusses
   `reflection-gate.py` in five comments, so a real hook became a helper;
2. requiring an interpreter on the same line — still matched PROSE, in a comment or a
   docstring, that happened to write `python3 <name>.py`.

Restricting invokers to `*.sh` siblings is what makes it hold: Python prose lives in
`.py` files. The generator stays structural (its docstring's intent is "a future
helper needs no edit here"), the count stays honest at 22, and hard rule 8 is
satisfied by fixing the generator rather than the published number. A **converse**
test is required too — every handler registered in `dispatch-registry.json` must
still classify AS a hook — because asserting only that the resolver is a helper is
one-directional and would have passed for both broken versions. The converse test
must assert an exact count, not `> 0`, or a registry rename leaves it green on almost
nothing; `dispatch.sh` and `post-implement.sh` are counted hooks that no registry row
names, so they are asserted explicitly.

**Known constraint, documented rather than fixed:** the pattern requires a literal
`python3`/`python`. Invoking the resolver through a variable (`"$CK_PY" foo.py`) is
not recognised, so the count goes to 23 and `gen-docs --check` goes RED. That is the
loud direction, and a future maintainer who "tidies" the invocation into a variable
will find out immediately rather than silently publishing a wrong count.

## D2 — `decisions.merge()` is public API with no coverage `[MEDIUM]`

Mutating `worst = ALLOW` -> `worst = DENY` leaves the suite green, and
`dispatch.sh:48-49` claims the module is parity-tested when only `from_exit_code`,
`to_exit_code` and `clamp_advisory` are.

**The backlog offers "parity test OR delete", and an earlier revision of this plan
chose DELETE. That was wrong and is reversed.** `merge` is re-exported at
`src/claudekit/enforcement/__init__.py:60` and listed in its `__all__`, so it is
**public API**, not dead code — the grep that declared it uncalled searched for call
sites and missed the package export. Deleting an exported symbol to avoid writing a
test is the wrong trade, and it also broke three test modules on import.

**Decision: keep `merge`, cover it directly, and make the `dispatch.sh` claim
accurate.** A shell<->Python parity test is not available for it: the merge that
actually runs is inline bash arithmetic in `dispatch.sh`, not a callable `lib.sh`
function, and it is already mutation-proven there (flipping the comparison must make
a block vanish). So the Python side is covered over the decision tuples directly, and
the comment now names which three functions are under parity test and says plainly
that the live merge is the bash one.

## D3 — the two remaining `[LOW]`s

- **Broken-pipe leak**: closed in BOTH pipes, and it took two changes rather than the
  one an earlier revision claimed. The handler pipe gets `2>>"$LOG_FILE"`; the
  resolver pipe needs the same, because draining stdin first cannot help when the
  resolver never starts. The log, not `/dev/null`, so a real write failure stays
  recoverable. **Conditional, and measured:** this holds whenever `hooks.log` is
  writable. With the log read-only, a 2 MB payload re-exposes the noise — but
  fail-closed (`rc 2`) and with `Permission denied` printed beside it, so the cause is
  visible rather than mysterious.
- **`stderr_preview` persists up to 512 bytes of handler stderr** to
  `.claude/runtime/events/*.jsonl`: a one-line note in `docs/HOOKS.md` that the event
  log may contain guard stderr. The directory is gitignored and advisory stdout is not
  captured, so this is a disclosure, not a code change.

## D4 — four PreToolUse hooks are structurally unable to block `[LOW]`

`file-guard-gate`, `security-reminder`, `pre-commit`, `pre-push` are
`tier: "advisory"` in `dispatch-registry.json`. None has an `exit 2` path today, so
there is no live regression, but a future `exit 2` in a file named `*-gate.sh` would
be silently clamped. **Fix:** a test asserting those four remain `exit 2`-free, so
the clamp and the artifact cannot drift apart. Cheap, and it binds a real invariant.

## D5 — the same defect in two shipped blocking hooks (scope expansion, declared)

D1's locale regression test surfaced `sys.stdin.read()` in two **blocking** hooks. They
are pre-existing, and this plan does not make them worse, so scope discipline would
allow filing them — but leaving them meant shipping a red test or weakening the
assertion, so they are fixed here and declared.

- **`reflection-gate.py:108`** — nothing caught the decode error, so the hook died with
  a traceback and emitted `rc 1`. That is neither 0 nor 2: a **hard rule 2 violation**,
  read by the host as non-blocking. Now `rc 2` with a reason. Unambiguously a repair.
- **`iron-law-gate.py:649`** — and here the first draft's rationale was WRONG, which
  round-2 review caught. `UnicodeDecodeError` is a subclass of `ValueError`, so the
  existing `except ValueError` already caught it; nothing ever raised and no traceback
  was printed. The real defect is which branch that `None` reached: `main()` treats an
  unreadable payload as **FAIL OPEN by design** (`iron-law-gate.py:668`), so a single
  invalid byte was a passthrough key past the implementer allowlist. Decoding with
  surrogateescape makes the payload readable, so the gate judges it.
  **This flips a verdict** — an implementer `rm -rf` carrying an invalid byte goes
  `rc 0` -> `rc 2`. A block/allow change in a hard-rule-1 hook does not ship on a
  comment's word, so both directions are tested: the undecodable disallowed command
  blocks, and an undecodable *allowed* command still passes.

`.claude/operations/scripts/review-record.py:213` has the same shape and is
deliberately LEFT ALONE: it reads reviewer prose, not a hook payload, and a decode
failure there records no verdict, so `/implement` reports `NO RECORD` — fail-closed.
Filed as a follow-up for diagnostics only.

## D6 — round-3 corrections (this section is the delta round 4 reviews)

Round 3 scored 85/100 with **zero blockers** and, unlike rounds 1 and 2, found no
fail-open introduced by the fix. Two MAJORs and four minors are folded into THIS
config rather than deferred, because they correct this change:

- **`src/claudekit/cli/main.py` — the doctor blind spot (round-3 M1).** This change
  creates the first file on which every `PreToolUse` call depends and which
  `settings.json` never mentions. `_required_hook_scripts` is derived from
  `settings.json`, so deleting only `dispatch_resolve.py` left `ck doctor --strict`
  reporting **25/26 green while every tool call was blocked** — the same "healthy
  install on a completely blocked project" the wired-hook check exists to end, re-
  entered through a file it cannot see. A second check derives the INVOKED set from the
  installed hooks themselves (`_invoked_sibling_scripts`), mirroring
  `gen-docs.py:_is_helper_module`, so a future helper needs no edit and the check cannot
  rot into a stale name list. `$SCRIPT_DIR/` is the discriminator and is load-bearing:
  five non-comment lines in `ops-enforcement.sh` print
  `python3 .claude/operations/scripts/execute-json-ops.py` inside a remediation message,
  and a bare-filename match would demand those live under `.claude/hooks/`.
- **`scripts/check-plan-artifacts.py` — the plan/config ratchet (round-3 M2), folded
  into the gate that already existed.** Plan/config divergence was found in three
  consecutive rounds (4 of 10, 4 of 10, 3 of 11) and remedied three times with prose, so
  the floor had to become mechanical. It was first written here as a test in
  `tests/test_delivery_contract_smoke.py` — then `726d3b9` landed
  `scripts/check-plan-artifacts.py` from another session: the same floor, from the same
  recurrence, in the better shape. Shipping both would have put two independent
  implementations of one gate in the repo, which is the near-duplicate class task 008
  exists to stop, so the test was DROPPED and its two genuine additions folded into the
  script:
    1. **Resolution by the config's declared `plan` field**, not the filename alone.
       `execute-json-ops.py:_approval_slugs` already resolves both ways. Filename-only
       resolution reported OK on every config whose declared plan differs from its
       filename, with all of its operations unchecked; `ops-mcp-probe.json` was the live
       instance, invisible with both paths unexamined. **A config with no plan document
       at all still PASSES** — that is deliberate, a Tier 1 routing fact rather than
       drift, and the fold preserves it.
    2. **An explicit failure when a config declares a plan but no operations**, and
       when a writing operation carries no `path`. `validate-config-json.py` already
       REJECTS the empty and renamed-key shapes upstream (measured: `[] should be
       non-empty at path: operations`; `unknown field(s): 'ops'`), so this is
       defence-in-depth rather than a hole being closed — it matters because the gate now
       runs standalone in CI, where the validator is not there to catch them for it.
  While in that file, its substring match is fixed too (`names_path`), on BOTH branches.
  Tightening only the basename was the first attempt and review measured it worse than no
  fix: `scripts/gen-docs.py` stayed satisfied by a plan naming
  `templates/scripts/gen-docs.py` — a DIFFERENT file — while the accompanying test
  certified the class as closed, making the suite evidence against a defect it did not
  cover. Both the full path and the basename are whole-token now, a trailing `.` is
  excluded — but CONDITIONALLY: excluding every following `.` rejected ordinary
  sentence-final prose ("edits scripts/gen-docs.py."), a shape 12 of the 67 existing plan
  documents already use, so the gate would have reddened CI on correct plans. A gate that
  cries wolf is a gate the next author routes around, which costs more than the hole it
  closes. The converse test now pins that shape explicitly, because the first version of
  it covered backticks, prose and full paths but not a name at the end of a sentence. Two more holes the fold had opened are
  closed with it: the declared `plan` value is constrained to a slug (as a path fragment,
  `../x` escaped `.claude/plans` and an absolute value discarded the parent, pointing the
  gate at any file that mentions the paths), and it is normalised by stripping BOTH
  prefixes as `execute-json-ops.py:_approval_slugs` does (`"plan": "ops-foo"` resolved to
  nothing and passed with every operation unchecked). The gate
  is wired into **`.github/workflows/ci.yml`** and the Definition of Done in
  **`.ai/CHECKLISTS.md`**; it was referenced by neither, so nothing ran it. It is
  deliberately NOT added to `CLAUDE.md`'s command block: that file has 44 characters of
  headroom against the always-on context floor (30956/31000 at `726d3b9`), and
  `check-context-floor.py` is a hard gate, so a DoD line there costs more than it buys.
  Measured: adding it took CLAUDE.md to 31308 and turned the floor OVER.
- **`.claude/plans/plan-mcp-probe-addendum.md`** — created so the resolution above has a
  document to find, which is what actually makes that config's two operations visible.
  It records what the addendum carries and why `--probe` was cut from the core of
  `ops-generators-that-cannot-drift.json` at that plan's round-1 finding C2, applied in
  its revision 2. Naming the paths inside another plan's document was the alternative and
  is worse: the config declares its own slug, so its own plan is where the description
  belongs.
- **`.claude/hooks/dispatch.sh` (minor).** The `RESOLVER RATIONALE` block still said it
  was "kept OUT of the heredoc on purpose" and cited a `check-silent-failure.py`
  line-cap that the extraction made moot; a reader was told the logic sat in a heredoc
  below, and there is no heredoc in the file. Retitled to say where the code actually
  lives and why the prose stays at the call site. One further stale reference — "the
  heredoc's stderr is appended there" — now reads "the resolver's stderr".
- **`CHANGELOG.md` (minor).** Two bullets credited bugs that never shipped: the
  undecodable-payload regression and the resolver-side broken pipe were both introduced
  and fixed *inside this change*, and the old `os.environ` transport decoded with
  `surrogateescape` and could not raise. The surrogateescape behaviour is now stated as
  an invariant the new transport preserves, and the broken-pipe bullet is scoped to the
  handler pipe. **The reflection-gate `rc 1` -> `rc 2` bullet stays**: that defect did
  ship, and it is a real hard-rule-2 violation.
- **`tests/test_dispatch_payload.py` (minors).** The reflection-gate contract is now
  asserted on its **exit code** (`rc == 2` plus the gate's own reason). The only test
  that reddened under the text-mode mutant asserted the absence of a traceback, which a
  later refactor to `return {}` would satisfy while restoring the fail-open. Proof 1's
  fail-closed half — a 2 MB write to a guarded path is still blocked, for the guard's
  own reason — is now bound rather than verified by hand.
- **`scripts/gen-docs.py` (minor).** The surviving pattern's constraint is documented at
  the code site, not only in this plan: the interpreter must be a literal `python3` on
  the same line as the filename.

## Other operations this config carries

Named here because a Tier 3 plan must describe everything its config does. Enforced by
the ratchet in D6, not by this list being diligent:

- **`CHANGELOG.md`** `[Unreleased] / Fixed` — the >1 MB refusal, the undecodable-payload
  regression, the broken-pipe noise, and both hook behaviour changes from D5.
- **`tests/test_event_log.py`** — the second sandbox that copies the dispatcher and so
  must copy `dispatch_resolve.py` too. Same consequence as `test_dispatch_merge.py`:
  whatever ships beside the dispatcher has to be sandboxed beside it. Without it,
  `test_dispatcher_actually_emits_a_conforming_record` fails with "model-visible but
  not logged", which is the fail-closed path working, not a logging bug.
- **`docs/HOOKS.md`** — the `stderr_preview` disclosure (D3).
- **`tests/test_dispatch_payload.py`** — the new behavioural suite for this change: the
  2 MB proofs and their fail-closed converse, the undecodable-payload proofs under an
  explicit locale, the resolver-is-a-helper-not-a-hook pair with its converse, the
  `decisions.merge` coverage from D2, and the reflection-gate exit-code contract.
- **`tests/test_iron_law_hook.py`** — both directions of the D5 verdict flip: an
  undecodable *implementer* command must now be blocked, and an undecodable *allowed*
  command must still pass. The second is what bounds the tightening.
- **`tests/test_dispatch_merge.py`** — the first dispatcher sandbox; it must copy
  `dispatch_resolve.py` for the same reason as `test_event_log.py`, and its anchored
  mutant test is re-pointed at the resolver rather than left silently proving nothing.
- **`src/claudekit/cli/main.py`** and **`tests/test_doctor_gate.py`** — the doctor
  blind spot, round-3 M1; see D6.
- **`scripts/check-plan-artifacts.py`**, **`tests/test_check_plan_artifacts.py`**,
  **`.claude/plans/plan-mcp-probe-addendum.md`**, **`.github/workflows/ci.yml`** and
  **`CLAUDE.md`** — round-3 M2, folded into the gate that landed at `726d3b9`; see D6.

## Must be proven by mutation, not asserted

1. **A 2 MB `Write` payload returns 0** (currently rc 2). This is D1's headline
   proof and the one the backlog demands. It must NOT become a fail-open: a 2 MB write
   to a guarded path must still be BLOCKED for the guard's own reason.
2. **An invalid-UTF-8 payload does not disarm resolution**, under an explicitly set
   `LC_ALL=en_US.UTF-8`, on a blocking and a non-blocking event.
3. A malformed payload still fails closed (`rc 2` on a blocking event), and a
   command_matcher handler is still NOT APPLICABLE on an unreadable payload — the C1
   fix from a previous round must survive the move. Its existing tests must stay
   green, and the real-registry termination test must still terminate.
4. No `printf: write error: Broken pipe` on captured stderr, on a payload of **>= 256
   KB** — comfortably past the ~64 KB pipe buffer. An earlier revision's test used
   4096 bytes, which fits entirely in the buffer, so the writer never blocked and the
   test was structurally unable to see the leak it claimed to guard. Exercised on the
   missing-resolver path specifically, since that is where draining does not help.
5. `gen-docs --check` stays green at `hooks=22`, and the generator's new
   helper-detection branch is proven by MUTATING it — remove the branch and watch the
   count go to 23. A count gate that passes against its own mutant is the failure
   mode this repo has shipped twice.
6. An installed tree (`install.sh` into a temp `DEST`) contains `dispatch_resolve.py`
   and its hooks resolve. Proven by running the installer, not by reading it.
7. **The iron-law flip binds in both directions:** reverting that hook to text-mode
   stdin must turn the "undecodable implementer command is blocked" test RED, and an
   undecodable *allowed* command must still pass.
8. `decisions.merge` binds: mutating `worst = ALLOW` -> `worst = DENY` must turn the
   new tests RED. Measured before this plan: the pre-existing suite stayed green under
   that mutation (86 passed), which is the coverage gap being closed. The export
   itself is asserted too, since being public API is the reason it is kept.
9. **The doctor helper check binds.** Delete `dispatch_resolve.py` from a real
   installed tree and `ck doctor` must FAIL and name the file — measured 25/26 green
   before the check existed. Asserted in all three directions, because a negative alone
   would be satisfied by a doctor that fails for any reason: the healthy install reports
   the check as a pass, the damaged install fails and names the file, and the damaged
   install's dispatcher really does return `rc 2` on a real payload.
10. **The folded ratchet binds, in both directions.** Remove one operation target's
    mention from this plan document and `check-plan-artifacts.py` must exit 1 naming
    that path; restore it and the gate returns 0. Its three new behaviours are each
    proven by their own mutation: a config whose declared plan resolves is CHECKED (it
    was silently skipped before), a config with no plan document still PASSES, and a
    basename appearing only inside a longer filename no longer counts. The converse is
    asserted too — a plan naming its artifacts in prose, by backticked basename and by
    full path, must stay green.
11. **The reflection-gate exit code binds.** Revert that hook to text-mode stdin and the
    new test must go RED on `rc != 2`, not merely on the presence of a traceback.

## Hard constraints

Python stdlib only; bash 3.2 / macOS-safe; hooks stay shell-form `type: command`;
blocking = `exit 2` + stderr, fail closed; no `--dangerously-skip-permissions`; no
component-count hand-edits; protected files stay protected; MAX_DELETIONS=3.

`decisions.py` losing `merge` is a deletion inside a file, not a file deletion, so
`is_protected_file` (consulted only on `file_delete`) does not apply.

## Definition of Done

Archive the spent config FIRST (`test_delivery_contract_smoke.py` validates every
queued config against `HEAD`), then:

    python3 -m pytest tests/ -q
    ruff check src/ tests/ scripts/
    mypy
    python3 scripts/gen-docs.py --check
    python3 scripts/gen-registry.py --check
    python3 scripts/gen-model-policy.py --check
    python3 scripts/check-context-floor.py
    shellcheck install.sh .claude/hooks/*.sh

Plus: `ck doctor --strict` on an installed tree. Re-run the gates AFTER committing —
committing makes plan files tracked and the secret self-scan enumerates
`git ls-files`, which has reddened this branch four times.

## Out of scope

`ck adapt` (Phase 2). The secret self-scan's missing exemption model — filed, and
independently worth doing, but not this plan. Granting `reviewer` the Bash tool
(owner-gated).

## Artifacts named retrospectively (2026-08-25)

`scripts/check-plan-artifacts.py` gained a hyphen-boundary prefix walk, so a config named
after its STEP now resolves to its parent plan. This plan's step configs had never been
checked against it -- the resolver returned nothing and the gate skipped them silently --
and the first checked run found paths this document does not name. Listed here rather than
left unnamed, because a plan that hides what its configs wrote cannot be reviewed for it.

| Path | Config |
| --- | --- |
| `.claude/plans/archive/README.md` | `ops-dispatcher-payload-docs.json` |
| `.ai/SESSION_STATE.md` | `ops-dispatcher-payload-docs.json` |
| `.ai/CHANGELOG_AI.md` | `ops-dispatcher-payload-docs.json` |


