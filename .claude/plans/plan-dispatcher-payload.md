# Plan — Phase 1b: free the dispatcher's stdin, and close the merge/LOW findings

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

The resolver reads `sys.stdin` instead of `os.environ["CK_PAYLOAD"]`. Its logic moves
verbatim — the registry invariant, the readable/unreadable distinction, the
matcher/precondition asymmetry and the whitespace-in-args rejection are all
behaviour-preserving; only the payload's transport changes.

**Two details that are not incidental:**

1. **Read stdin FIRST, before anything that can exit.** The resolver exits 3 on a
   registry parse failure and on an illegal registry row. If it exits before draining
   stdin, the writing `printf` takes SIGPIPE and leaks
   `printf: write error: Broken pipe` to hook stderr. Draining first closes the
   separate `[LOW]` filed for `dispatch.sh:346` at the same time, without a
   `2>/dev/null` that would also hide real errors.
2. **The refusal message must name the size and the cause.** Today it says only
   `BLOCKED: could not resolve hook handlers for PreToolUse`. It gains the payload
   size and the resolver's exit code, because a refusal an operator cannot diagnose
   is most of why this row sat unfixed.

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
helper when a sibling *invokes it by path* (`python3 ... dispatch_resolve.py`). That
keeps the generator structural — its docstring's stated intent is "a future helper
needs no edit here" — and keeps the count honest at 22, because the resolver is a
helper, not a hook. Hard rule 8 is satisfied by fixing the generator, never the
published number.

## D2 — `decisions.merge()` is dead code claiming parity `[MEDIUM]`

Mutating `worst = ALLOW` -> `worst = DENY` leaves the suite green, and
`dispatch.sh:48-49` claims the module is parity-tested. Only `from_exit_code`,
`to_exit_code` and `clamp_advisory` actually are. The live merge is the bash one and
IS mutation-proven, so there is no live risk — the problem is that the file most
likely to be read as canonical is the one nothing checks.

**Decision: delete `merge`, and narrow the `dispatch.sh` sentence to the three
functions genuinely covered.** The backlog offers "parity test over the 4^n tuples OR
delete". Deleting is preferred because a parity test would enshrine a second
implementation of a rule that has exactly one live implementation; the cheaper
artifact is the one that cannot drift. If the Python merge is wanted later it should
arrive with its caller.

## D3 — the two remaining `[LOW]`s

- **Broken-pipe leak** (`dispatch.sh:346`): closed as a side effect of D1's
  "drain stdin first", not by `2>/dev/null`.
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

## Must be proven by mutation, not asserted

1. **A 2 MB `Write` payload returns 0** (currently rc 2). This is D1's headline
   proof and the one the backlog demands.
2. A malformed payload still fails closed (`rc 2` on a blocking event), and a
   command_matcher handler is still NOT APPLICABLE on an unreadable payload — the C1
   fix from a previous round must survive the move. Its existing tests must stay
   green, and the real-registry termination test must still terminate.
3. No `printf: write error: Broken pipe` on the stderr of a >=100 KB payload, proven
   by asserting on captured stderr rather than by eye.
4. `gen-docs --check` stays green at `hooks=22`, and the generator's new
   helper-detection branch is proven by MUTATING it — remove the branch and watch the
   count go to 23. A count gate that passes against its own mutant is the failure
   mode this repo has shipped twice.
5. An installed tree (`install.sh` into a temp `DEST`) contains `dispatch_resolve.py`
   and its hooks resolve. Proven by running the installer, not by reading it.
6. Deleting `merge` leaves the suite green, and the three genuinely-covered functions
   keep their parity tests.

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
