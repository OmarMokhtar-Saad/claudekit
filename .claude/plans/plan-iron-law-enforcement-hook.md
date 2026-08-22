# Implementation Plan: Iron Law Enforcement Hook (Workstream 12)

Ops config: `.claude/plans/plan-iron-law-enforcement-hook.ops.json` (3 operations, validator APPROVED)

> **Round-4 note — the three-round review ceiling was waived by the owner** for one
> specific reason: rounds 2 and 3 each found a new arbitrary-write flag in the *same* class
> (`pytest --log-file`, `-o`, `-c`; then `ruff --add-noqa`, `pytest --debug`), with round 3
> finding two of them inside the verbs round 2 had just claimed to sweep. That is not a
> patchable defect, it is a structural one, so round 4 is an **architectural change**
> (D5e) rather than another patch. Recorded here per the owner's instruction.

## Overview

Hard rule 1 (the Iron Law) says implementation flows through `ops.json` and the operations
engine, and the implementer never gets Edit/Write. `implementer.md:8` grants
`tools: ["Read", "Bash", "Grep", "Glob"]` — no Edit, no Write — but it grants **unrestricted
`Bash`**, and a frontmatter-declared `Bash(<specifier>)` is **not applied** on the interactive
path (measured 2026-08-19 against Claude Code 2.1.235; recorded in
`.claude/agents/_shared/INVOCATION.md:167-190`). The interactive implementer can therefore
`sed -i`, `cat > file`, `python3 -c "open(p,'w')"`, `tee`, `git apply`, `patch`, `perl -pi`,
`sh -c '...'`, a heredoc or `$(...)` and bypass the Iron Law completely.

This plan adds `.claude/hooks/iron-law-gate.py`: a `PreToolUse` / `matcher: "Bash"` hook that
acts **only** when the payload's `agent_type` is `implementer`, permits a **named allowlist**
(the ops engine, the reflection escape hatch, a read-only inspection set, and a verification
set), and rejects everything else with `exit 2` + stderr. It makes the interactive Iron Law
harness-enforced instead of prompt-enforced.

## Scope

- **In Scope**
  - New `.claude/hooks/iron-law-gate.py` (Python 3.9, stdlib only).
  - Registration of that hook in `.claude/settings.json` (one appended `PreToolUse` entry).
  - New behavioral tests at `tests/test_iron_law_hook.py`.
- **Out of Scope (not owned by this workstream — raised in Risks)**
  - `.claude/hooks/reflection*.py`, `ops-enforcement.sh`, `execute-json-ops.py`.
  - Any agent `.md` (including `implementer.md` and `_shared/INVOCATION.md`, whose "the hook
    is not in place yet — do not describe the interactive Iron Law as enforced until it is"
    sentence becomes stale once this lands), any skill, `CLAUDE.md`, `CHANGELOG.md`, `.ai/**`,
    `install.sh`, `scripts/**`, `docs/**`.
  - Narrowing the other over-wide frontmatter grants (`explore`, `security-scanner`,
    `silent-failure-hunter`).

## Prerequisites

None. Additive, single new file plus one registration edit. No dependency changes (stdlib
only), no schema changes, no migration.

---

## Context Summary — what was verified, not assumed

### 1. `agent_type` really is in the `PreToolUse` payload (re-verified on 2.1.237)

The spec's note was measured on 2.1.235; the installed harness has since moved to
**2.1.237** (`~/.local/share/claude/versions/2.1.237`). Verified directly against that
binary rather than trusting the note. The base hook-input builder is:

```js
function $y(e,t,r,n){let o=n?.agentType??Z$(); /* ... */
  return{session_id:e.id, transcript_path:J4(e.id), cwd:t, prompt_id:act()??void 0,
         permission_mode:r, agent_id:n?.agentId, agent_type:o, effort:a}}
```

and `executePreToolHooks` spreads exactly that object:

```js
let c={...$y(n.session,Yt(),o,n), hook_event_name:"PreToolUse",
       tool_name:e, tool_input:r, tool_use_id:t};
```

So `agent_type` is present on every `PreToolUse` payload, on both spawn paths.

**Consequence that matters for the pass-through rule:** on the main thread `n?.agentType` is
undefined and the fallback is `Z$()`, which returns `mainThreadAgentType` — set only when the
session was started with `--agent`. For an ordinary main session the value is `undefined`, so
`JSON.stringify` drops the key and **`agent_type` is simply absent**. Absent ⇒ pass through.
(A session literally launched as `claude --agent implementer` *will* be attributed as the
implementer. That is correct, not a bug.)

### 2. The sanctioned loop, enumerated from the current files

From `.claude/agents/implementer.md` (Steps 1-4, Safety Rules, Edge Cases) and
`.claude/commands/implement.md` (Phases 1-3), the implementer's Bash surface is:

| Source | Command | Allowlist rule |
|---|---|---|
| implementer.md Step 1 / implement.md §3 | `python3 .claude/operations/scripts/validate-config-json.py <ops.json> --stamp-baseline` | ops engine (A) |
| implementer.md Step 2 / implement.md §4 | `python3 .claude/operations/scripts/execute-json-ops.py <ops.json> --dry-run` | ops engine (A) |
| implementer.md Step 3 | `python3 .claude/operations/scripts/execute-json-ops.py <ops.json>` | ops engine (A) |
| implementer.md Step 4 | build / lint / test from plan.md, else `.claude/hooks/config.json` `project.*` | verification (D) |
| implementer.md IRON LAW §, verbatim: "Bash is otherwise for read-only inspection (`cat`, `grep`, `ls`, `git status`, build/test/lint verification)" | those verbs | read-only (C) |
| implementer.md Edge Cases: "Tests fail but they were already failing before → Verify by checking git status." | `git status` | read-only (C) |
| implementer.md "Build tool not found → Check common locations" | `ls`, `find`, `which` | read-only (C) |

**Measured:** `.claude/hooks/config.json` `project.build_cmd/test_cmd/lint_cmd` are all
**empty strings** in this repo, so Step 4 falls through to the plan's own validation commands.
This repo's DoD set is `python3 -m pytest tests/ -q`, `ruff check`, `mypy`,
`python3 scripts/gen-docs.py --check`, `python3 scripts/gen-registry.py --check`,
`shellcheck`, `ck doctor --strict`.

**`git` is legitimately needed** (`git status` is named in implementer.md's own edge-case
handling, and reporting what changed is part of its output format), but only as a *reporter* —
implementer.md says "Do NOT commit anything (that's GitOps's job)".

### 3. Loop-termination proof (the failure mode that matters most)

If this hook blocks `execute-json-ops.py`, the implementer's only sanctioned action is gone
and it can do nothing at all. The full walk, with every step's verdict measured against the
prototype:

1. Receives the plan and ops path — `Read` tool, unaffected by this hook.
2. `validate-config-json.py … --stamp-baseline` → **ALLOW**.
3. `execute-json-ops.py … --dry-run` → **ALLOW**.
4. `execute-json-ops.py …` → **ALLOW**.
5. Reads `RESULT-JSON:` / diff from stdout — no Bash call.
6. Verification: `python3 -m pytest`, `pytest`, `ruff check`, `ruff format --check`, `mypy`,
   `shellcheck`, `ck doctor --strict`, `git status`, `git diff --stat` → **ALLOW**.
7. Reflection interlock: if `reflection-gate.py` raises a checkpoint, only
   `python3 .claude/hooks/reflection.py {receipt,trigger,non-attempt,status}` clears it →
   **ALLOW** (see Risk R2).
8. A verification command *outside* the allowlist (e.g. `python3 scripts/gen-docs.py --check`,
   `npm test`) → **BLOCK**, and the denial text routes the agent onto the terminating path
   `implementer.md` already documents: *"If a verification command is outside your granted
   tool scope … report the implementation as 'executed via ops.json — verification pending'
   and hand off to the Verifier, whose tool grant covers build/test/lint."*

Every branch terminates. Step 8 is why the allowlist can stay tight without deadlocking: the
prompt already contains a sanctioned exit for exactly this case. `tests/test_iron_law_hook.py`
pins steps 2-7 as `SANCTIONED`, **32** commands, and treats any block of them as "the
implementer is left with no possible action". CLAUDE.md's six mandatory DoD gates are pinned
separately as `DOD_COMMANDS` (`test_dod_command_is_permitted`), because tightening flags is
only safe if the commands the project actually *requires* still pass.

### 4. Delivery is already handled (confirmed, not assumed)

`install.sh:251-263` `_copy_hook_assets` copies hook assets **structurally** (deny-list of
`*.log|*.pyc|*.orig|*.rej|*.swp|*~`, `compact-counter.txt`, `settings.local.json`), so a new
`.py` hook ships. `install.sh:265-275` chmods `+x` by **shebang**, not extension, so the
installed copy is executable even though the ops engine creates the source file 0644.
`install.sh:286-340` and `tests/test_hook_delivery.py::test_every_wired_hook_resolves_after_install`
fail closed on a wired-but-missing hook — which is precisely the guard that would catch a
delivery regression here. `tests/test_hook_delivery.py::test_all_source_hook_assets_installed`
is structural and covers the new file automatically.

---

## Design Decisions

### D1 — Allowlist, never denylist (hard rule 6)

An enumeration of forbidden write vectors was already attempted and rejected: the first
attempt missed `git apply`, `patch`, `ed`, `perl -pi`, `xargs`, `sh -c`, heredocs and
backticks. A denylist is the "speed bump, not a sandbox" shape hard rule 6 warns about, and it
must be re-audited every time a new write tool appears on the host. The hook therefore permits
a named set and rejects everything else, **including anything it cannot confidently parse**.

### D2 — Reject metacharacters and wrappers *before* tokenising

A command containing any of `;` `|` `&` `>` `<` `` ` `` `$(` newline or carriage return
cannot be reduced to a single argv, so no allowlist decision about it can be trusted. `&`
covers `&&`/`||`; `>` covers `>` and `>>`; `<` covers `<<` heredocs and `<(...)`. Wrapper
heads (`sh`, `bash`, `zsh`, `env`, `xargs`, `nohup`, `eval`, `exec`, `command`, `time`,
`timeout`, `sudo`, `watch`, `script`, `expect`, `parallel`, `setsid`, `stdbuf`, `nice`, …)
are refused because they can execute anything behind an allowlisted-looking head.

**Addition beyond the spec:** a leading `VAR=value` environment assignment is refused too.
`reflection-gate.is_receipt_cli` *skips* them; here that would allow
`PYTHONPATH=/tmp python3 …execute-json-ops.py` or `LD_PRELOAD=…`, changing what an allowlisted
binary does. The implementer has no documented need for one.

### D3 — Full tokenised argv, never a prefix or substring

`shlex.split(..., posix=True)`; a `ValueError` is a block. Matching is on `tokens[0]`'s
basename plus per-verb argv rules. `git diff` is not satisfied by `git diff --output=x`
(pinned by `test_prefix_match_does_not_satisfy_the_allowlist`). Script arguments are matched
by `(realpath(parent), basename)` — the **parent only** is resolved, exactly the anti-symlink
control documented in `reflection-gate.is_receipt_inbox_write`; resolving the full path would
let a symlink named `execute-json-ops.py` launder an arbitrary script into the allowlist
(pinned by `test_symlinked_ops_script_is_not_laundered`).

### D4 — `sed` is excluded outright (a correction to the reviewed spec)

The spec says "permit `sed` only if no token starts with `-i` and none equals `--in-place`".
**That rule is incomplete.** `sed` writes files without `-i` through its own `w` / `W`
commands and the `s///w` flag:

```
sed -n '1,5w /tmp/out' src/x.py      # writes /tmp/out, no -i anywhere
```

Making `sed` safe would require parsing the sed script language, which is not a decidable
allowlist. `cat`, `head`, `tail` and `grep` cover every read need `implementer.md` actually
states, so `sed` is simply not on the list. Pinned by the
`sed-w-command-writes-without-i` case. For the same reason `sort` (`-o FILE`) and `uniq`
(`uniq IN OUT`) are excluded from the read-only set.

### D5 — `pytest` IS permitted, and the residual is recorded rather than hidden

`pytest` executes `conftest.py` and arbitrary repo code, so it is mutation-capable. It is
permitted anyway, for three reasons, and the trade is stated in the hook header:

1. `implementer.md` Step 4 makes running the test suite **mandatory** and this repo's test
   command is `python3 -m pytest`. Blocking it breaks the implementer's own sanctioned loop
   at the verification step — the exact failure mode this plan is required to avoid.
2. The code pytest runs is repo code that **already exists**. The implementer cannot
   introduce or alter a `conftest.py` without first passing through the ops engine, which is
   the transaction / backup / approval gate the Iron Law exists to protect. Permitting pytest
   does not create a *new* path to mutate the tree; it inherits whatever the repo already
   trusts itself to execute.
3. Hard rule 6 honesty: this hook is a real harness control and strictly stronger than the
   prompt it replaces, but it is **not a sandbox**. Pretending pytest were inert would be the
   dishonest framing the rule forbids.

Mitigation: pytest's plugin-injection, config-injection and file-writing flags are refused —
`-p*`, `-o*`, `-c*`, `--pdb`, `--pdbcls`, `--junitxml`, `--junit-xml`, `--result-log`,
`--basetemp`, `--log-file`, `--log-file-level`, `--override-ini`. **Named residual #1.**

**Review correction (MAJOR 1).** The first revision omitted `--log-file`, `-o` and `-c`, so
`pytest --log-file=src/claudekit/__init__.py tests/` was ALLOWED — it creates and truncates an
arbitrary path, destroying a source file with no ops.json, no backup and no approval. That is
a *different and worse* thing than the residual above: not "runs repo code we already trust"
but "points pytest's own writer at a path of our choosing". `-o` (ini override) and `-c`
(arbitrary ini) likewise carry `addopts = -p evil`. `-p`/`-o`/`-c` are matched by PREFIX as
well as by set membership, because `_decide_flag_guard` only splits on `=` and pytest accepts
attached forms. The same bypass class was then swept in the sibling verbs: `ruff -o`,
`--output-file` and `--config`, and `mypy --config-file` (a mypy config may declare `plugins`,
which is arbitrary code). Pinned by `pytest-log-file`, `pytest-log-file-detached`,
`pytest-ini-override`, `pytest-alt-ini`, `pytest-override-ini-long`, `ruff-output-file`,
`ruff-config-injection`, `mypy-config-plugin-injection`.

### D5e — flags are DEFAULT-DENY (round-4 architectural inversion)

**The defect was structural, not a missing entry.** v1 allowlisted VERBS but DENYLISTED
their FLAGS (one write-flag table per verb). That is exactly the shape hard rule 6 calls a
speed bump, reappearing one level down *inside* an allowlist. `ruff`, `mypy` and `pytest`
have large versioned flag surfaces; any release can add a writer, so no enumeration of the
dangerous set is stable and none can be proven complete. Three rounds found new writers in
that class and it was not converging — round 2 claimed to have "swept the sibling verbs"
and round 3 falsified that claim *in the swept verbs*.

**The change.** For every flag-gated verb, a token beginning with `-` is REFUSED unless it
is in that verb's small explicit SAFE list. The write-flag denylists are **deleted**, not
merely bypassed — keeping them would falsely signal that the dangerous set is known, which
is the precise claim three rounds falsified.
`test_no_flag_denylist_survives_in_the_hook` asserts structurally that none of the six v1
symbols survives.

**The burden inverts, which is the whole point.** A future `ruff` release that adds a writer
is denied without anyone noticing it exists. The failure mode of an unknown flag becomes an
**over-block** — annoying, visible in `hooks.log`, fixable by adding one entry — instead of
a **bypass**, which is silent, invisible and exploitable.
`test_invented_flag_is_refused_without_being_enumerated` pins the property with
`ruff check --totally-new-writer=x src/`, and first asserts that string does not appear in
the hook so the test cannot be circular. That property is the one thing a denylist could
never have had.

**Every SAFE list is derived from a command the implementer is actually instructed to run**
(CLAUDE.md's six DoD gates, implementer.md Steps 1-4, implement.md Phases 1-3), and nothing
is added for hypothetical convenience:

| Verb | SAFE flags | Derived from |
|---|---|---|
| `pytest` | `-q`, `--quiet` | `python3 -m pytest tests/ -q` |
| `ruff` | `--check`, `--diff` | `ruff check src/ tests/ scripts/`; both exist only so `ruff format` has a non-writing form |
| `mypy` | *(none)* | `mypy` |
| `shellcheck` | *(none)* | `shellcheck install.sh .claude/hooks/*.sh` |
| `ck`/`claudekit` | `--strict`, `--dry-run` | `ck doctor --strict`; `ck execute --dry-run` |
| `find` | `-name`, `-type`, `-maxdepth`, `-mindepth`, `-path` | implementer.md "Build tool not found → Check common locations" |
| `git` (reporters) | `--porcelain`, `--short`, `--stat`, `--numstat`, `--name-only`, `--name-status`, `--oneline`, `--cached`, `--staged`, `--show-toplevel`, `-n`, `-<digits>` | `git status`, `git diff --stat`, `git log --oneline -5` |
| `git branch`/`remote` | `-v`, `-vv`, `--verbose`, `--list`, `--show-current`, `-a`, `--all` | listing only (D5b) |
| ops scripts | `--dry-run`, `--stamp-baseline` | implementer.md Steps 1-3. `--no-approval` is deliberately absent: implement.md requires explicit user authorization for it. |
| `scripts/gen-*.py` | `--check` | DoD gates 4-5 (D5d) |
| `reflection.py` | its argparse flag set | the escape hatch (R2) |

**Cross-cutting rules.**

- **`@argfile` and every response-file syntax is REFUSED for every verb.** It is a flag
  source the gate cannot inspect, which defeats the entire design — mypy's `@file` would
  otherwise smuggle `--html-report` straight back in. Pinned by `mypy-response-file`,
  `ruff-response-file`, `pytest-response-file`.
- **`--` is REFUSED for every verb.** *Decision, documented rather than defaulted:* not one
  sanctioned command needs it, and honouring it would add a second parsing mode (post-`--`
  tokens as positionals) for no gain. Pinned by `double-dash-separator`.
- **Attached and detached forms are both covered.** Membership is tested on
  `token.split("=", 1)[0]`, so `--output=x` is judged as `--output`. **A flag therefore
  only belongs in a SAFE list if it is safe with ANY value** — that is the standing entry
  criterion, and it replaces the old "audited enumeration" concession in residual 3.
- **Positionals are path-constrained**: no `..` segment, no `~`, and no absolute path
  outside the project root. **Globs are not expanded by the gate** — the shell expands them
  *after* the hook runs, so `.claude/hooks/*.sh` arrives literally and is judged as an
  ordinary relative path (pinned by the DoD gate-6 case). Exempted: `reflection.py`
  argument values, because a receipt payload is data rather than a path and over-blocking
  the one escape hatch is the fatal failure mode.
- **Two verb classes.** *Flag-inert* (`cat`, `head`, `tail`, `wc`, `ls`, `grep`, `egrep`,
  `fgrep`) accept any `-` token, because the verb's entire flag surface is write-free on
  both GNU and BSD. This is **not** a flag denylist: it is a per-verb assertion that must be
  argued before a verb joins the class. Everything speculative was removed to shrink the
  surface — `file` (because `file -C -m <name>` writes a `.mgc` and nothing instructs the
  implementer to run it), plus `stat`, `du`, `nl`, `cut`, `tr`, `column`, `diff`, `rg`,
  `which`, `basename`, `dirname`, `pwd`.
- **Extension verbs get NO safe flags**, so `CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS` cannot grant
  more than a built-in verb (`test_extra_verbs_get_no_safe_flags`).

### D5f — every verb must name a PROGRAM, not a word (round 4, corrected in round 5)

Verb matching was basename-only, so `/tmp/evil/cat`, `/tmp/evil/ruff` and `./shellcheck`
resolved to allowlisted verbs and ran whatever binary sat at that path. Verbs now require
`"/" not in tokens[0]` (PATH lookup only). The pre-existing
`test_extra_verbs_rejects_path_bearing_entries` did **not** cover this — it exercises a
*non*-allowlisted basename — so `test_allowlisted_verb_given_as_a_path_is_blocked` was added.

**Round-5 correction — the round-4 justification was wrong and the code matched the wrong
justification.** It read "`_decide_python` already resolved script paths for exactly this
reason", which **conflates resolving the SCRIPT with resolving the INTERPRETER**. They are
different controls and both are required. The path check sat BELOW the `_PYTHON_HEADS`
dispatch, so the interpreter branch returned first and interpreters were exempt from the
very control this section added:

```
/tmp/evil/python3 .claude/operations/scripts/execute-json-ops.py p.ops.json   -> ALLOWED
```

The SCRIPT argument resolved into the ops directory and satisfied `_OPS_SAFE`, and the gate
then ran an arbitrary binary that merely happened to be named `python3`, with an argv of the
caller's choosing. The check now runs **above** the dispatch, for every verb including
interpreters. No `SANCTIONED` or `DOD_COMMANDS` entry uses a path-bearing interpreter, so
there is no over-block cost. Pinned by `path-bearing-interpreter-ops` and
`relative-path-bearing-interpreter`, and — critically — both appear in the *declared
collateral* of the `path-bearing-inert-verb` mutant, which is how the fix is proven bound to
that specific check rather than to something else.

**Known and accepted (round-5 note, no code change).** The `reflection.py` `path_check=False`
exemption lets `--file <any readable path>` through. Traced in review to
`reflection.py:930-946`: `--file` is READ-only and every write stays inside the ledger
directory, so it is not a write vector. At worst it is an error-message read-leak of a file
the implementer already holds the `Read` tool for. Recorded rather than closed, because
narrowing it risks the one fatal failure mode (R2).

### D5b — `git branch` and `git remote` are not read-only (review MAJOR 2)

The first revision listed both in `_GIT_READ_ONLY` under a comment claiming git was
"permitted only as a reporter". That was inaccurate: `git branch -D feature` and
`git remote add|remove|set-url|prune` all mutate repository state, destructively in the
`-D`/`prune` case, by an agent whose entire contract is "no mutation outside the ops engine".
They are kept — `git branch --show-current` is genuinely useful — but only when **every**
remaining token is a pure listing flag (`-v`, `-vv`, `--verbose`, `--list`, `--show-current`,
`-a`, `--all`). **Round-4 correction:** the flag list alone did not stop them, because
`git remote add origin <url>` mutates through *positionals*, not flags — it was still
ALLOWED. Positionals are now refused for these two subcommands unless `--list` is present,
which is the one form that legitimately takes one. That also fixes the round-3 over-block:
`git branch --list 'feat*'` now passes. Pinned by `git-branch-delete`, `git-branch-move`,
`git-branch-create-positional`, `git-branch-delete-flagonly`, `git-remote-add`,
`git-remote-set-url`, `git-remote-prune`, with `git branch --show-current`,
`git branch --list`, `git branch --list 'feat*'` and `git remote -v` in `SANCTIONED`.

### D5c — the gate must not record the secrets it blocks (review MAJOR 3)

`emit()` writes to `hooks.log` under **both** profiles, and everything it writes has already
been rejected — so it is precisely the text most likely to carry a credential or a host path.
The first revision logged the raw head and reason, and the env-assignment reason embedded the
whole offending token, so a blocked `AWS_SECRET_ACCESS_KEY=<value> python3 …` was recorded
verbatim, value included. A gate that records the secrets it blocks is worse than the bypass
it prevents. Three changes: the env-assignment reason now names only
`tokens[0].split("=", 1)[0]` (the VARIABLE, never the value); every other interpolated token
goes through `safe()`, which delegates to `reflection.bounded_token` — the sanitizer this repo
already standardised on (`reflection-gate.py:339`) — with a basename-only fallback if the
import is unavailable; and `redact()` blanks the value of every `NAME=value` token before the
command is shown on stderr or logged. **Round-4 extension:** v1 handled only that one
shape, so `--password=x`, `--token x` (space-separated), `https://user:tok@host` and bare
high-entropy strings survived into `denial_message()` → stderr, which is persisted in the
transcript. `hooks.log` was never the exposure (that line is `head=` + `reason=`, both
`safe()`-digested). `redact()` now covers all three shapes and delegates the bare/embedded
case to `reflection.looks_like_credential()` — an existing, already-tuned detector in this
repo that was simply unused — rather than to another regex invented here. Pinned by
`test_secret_shapes_are_redacted_from_stderr`. The reason sentence itself is **not** digested wholesale:
its components are already sanitized, and hashing it would destroy the variable name that
makes the block actionable. Pinned by `test_blocked_secret_value_never_reaches_the_log`
(both profiles, asserting the VALUE is absent from log *and* stderr while the NAME survives)
and `test_absolute_host_paths_are_digested_in_the_log`.

### D5d — the two remaining mandatory DoD gates (review MAJOR 4)

CLAUDE.md requires six gates; the first revision blocked two of them, since `_decide_python`
allowed only the ops-engine scripts and `reflection.py`. `python3 scripts/gen-docs.py --check`
and `python3 scripts/gen-registry.py --check` are now permitted, matched by resolved parent
directory (`<root>/scripts`) plus exact basename, and **only when `--check` is present** —
without it `gen-docs.py` REWRITES the docs, which is exactly the un-transacted mutation this
gate exists to stop. No deadlock resulted before the fix (the Verifier handoff terminates),
but every implementer in this repo was permanently unable to complete two mandatory gates,
a far larger practical cost than R1 admitted. All six gates are now pinned as
`DOD_COMMANDS` and verified through `decide()` (6/6 permitted). Pinned by two
`SANCTIONED` entries plus
`gen-docs-without-check`, `gen-registry-without-check` and
`other-repo-script-even-with-check` (an unrelated `scripts/*.py` stays blocked even with
`--check`, so the rule is the basename pair, not the flag).

### D6 — `ECC_HOOK_PROFILE`: record under `minimal`, block under `standard`/`strict`

**Decision: deliberate divergence from `ops-enforcement.sh`, following `reflection-gate.py`.**

`ops-enforcement.sh:15` short-circuits wholesale (`[ … = minimal ] && exit 0`). This hook does
not. Under `minimal` it computes the full decision, logs
`[iron-law-gate] [WOULD-BLOCK] head=<verb> reason=<...>` to `hooks.log`, and exits 0. Under
`standard`/`strict` it blocks.

Justification:

- **This repo develops with `ECC_HOOK_PROFILE=minimal`** (the gitignored
  `.claude/settings.local.json`, per CLAUDE.md's "Session setup gotcha"). A wholesale
  short-circuit would therefore produce **zero dogfood signal** — we would ship an allowlist
  whose real-world tightness we had never observed. That is exactly the problem Decision 21
  addressed, and exactly the reasoning `reflection-gate.py`'s PROFILE CONVENTION block records
  ("`minimal` suppresses BLOCKING only; recording keeps running").
- Recording costs nothing and cannot strand anyone: `minimal` remains a genuine escape hatch
  because `exit 0` is still returned.
- It gives a cheap, honest answer to the one open question the allowlist cannot answer a
  priori — *does it block anything the implementer legitimately needs?* — via
  `grep WOULD-BLOCK .claude/hooks/hooks.log`.

Both halves are pinned: `test_minimal_profile_suppresses_blocking` and
`test_minimal_profile_still_records_the_decision`.

### D7 — Fail directions: the two unknowns fail *opposite* ways, on purpose

| Situation | Direction | Why |
|---|---|---|
| stdin is not JSON / not an object | **OPEN** (exit 0, logged `ERROR`) | We cannot tell *whose* command it is. Blocking would deny **every Bash call the main agent makes** — catastrophic and outside this hook's remit. **No coverage is lost:** `reflection-gate.py` is wired on the same event with `matcher: ""` and already fails **CLOSED** on an unparsable `PreToolUse` payload (`reflection-gate.py` `main()`), so the chain still denies. |
| `agent_type` absent / empty | **OPEN** (exit 0, silent) | Main agent. Explicit pass-through; the hook must be invisible. |
| `agent_type` ≠ `implementer` | **OPEN** (exit 0, silent) | Every other subagent. Out of remit. |
| `tool_name` present and ≠ `Bash` | **OPEN** (exit 0) | Belt-and-braces behind the `matcher`. |
| `agent_type` = `implementer`, command missing/non-string | **CLOSED** (exit 2) | We know who is asking and cannot prove what they asked for. Mirrors `ops-enforcement.sh`'s fail-closed posture. |
| `agent_type` = `implementer`, command does not tokenise | **CLOSED** (exit 2) | Same. |
| `agent_type` = `implementer`, head not on the allowlist | **CLOSED** (exit 2) | The point of the hook. |

### D8 — Composition with the existing 9-entry `PreToolUse` chain

`.claude/settings.json` already wires **ten** `PreToolUse` entries, in order: `reflection-gate.py` (`matcher ""`),
`ops-enforcement.sh` / `config-protection.sh` / `security-reminder.sh` / `file-guard-gate.sh`
(Edit/Write matchers), then on `matcher "Bash"`: the `git commit` → `pre-commit.sh` shim,
`commit-quality.sh`, the `git push` → `pre-push.sh` shim, `block-no-verify.sh`, and
`command-guard.sh`. This hook is appended **last**.

- **It cannot contradict any of them, structurally.** `PreToolUse` semantics are conjunctive:
  any hook exiting 2 blocks. This hook only ever *removes* permission — it never returns an
  "allow" decision that could override another gate. A monotone blocker composes with any
  chain by construction. The only reachable failure mode is over-blocking.
- **Double-block is harmless where it occurs.** `git commit` by the implementer trips both
  `pre-commit.sh`/`commit-quality.sh` and this hook. The implementer is instructed not to
  commit anyway ("Do NOT commit anything (that's GitOps's job)"), and two exit-2s produce one
  block.
- **The reflection escape hatch is explicitly protected** — see Risk R2. This is the single
  over-block that would be fatal, and it is allowlisted and regression-tested.
- **`command-guard.sh` is unaffected**: it is a denylist over the same field. Where they
  disagree, the stricter wins, which is this hook.

### D9 — Extension point for downstream projects

`CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS` (colon-separated **bare basenames**, entries containing
`/` are ignored). Mirrors the existing `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW` precedent in the
ops validator, so it is a pattern this repo already carries rather than a new config surface.
It deliberately accepts **no argv patterns**: a pattern in an env var would read as scoping
while providing none — the same lie as a frontmatter `Bash(...)` specifier. Off by default.

---

## Implementation Steps

### Step 1: Create the hook
- **File:** `.claude/hooks/iron-law-gate.py`
- **Action:** Create
- **Description:** `PreToolUse` allowlist gate scoped to `agent_type == "implementer"`.
- **Details:** Python 3.9 / stdlib only, `from __future__ import annotations`, ≤100 columns.
  Structure: module docstring carrying the WHY / SCOPE / FAIL DIRECTIONS / PROFILE CONVENTION /
  HONEST FRAMING / PYTEST rationale → constant tables (`_METACHARACTERS`, `_WRAPPERS`,
  `_READ_ONLY`, `_FIND_WRITE_FLAGS`, `_GIT_READ_ONLY`, `_RUFF_WRITE_FLAGS`,
  `_MYPY_WRITE_FLAGS`, `_PYTEST_WRITE_FLAGS`, `_CK_SUBCOMMANDS`, `_REFLECTION_VERBS`) →
  `decide()` returning `(allowed, reason)` and never raising → `main()` implementing the D7
  matrix → `emit()` implementing the D6 profile rule. Blocks with `exit 2` + stderr only
  (hard rule 2). `CLAUDEKIT_HOOK_LOG` overrides the log path for tests.

### Step 2: Create the behavioral tests
- **File:** `tests/test_iron_law_hook.py`
- **Action:** Create
- **Description:** The full matrix, fed as real JSON on stdin to the real hook as a subprocess.
- **Details:** 32 `SANCTIONED` + 6 `DOD_COMMANDS` × must-not-block; 93 `BLOCKED` vectors ×
  must-block-with-`IRON LAW`-stderr-and-empty-stdout; agent scoping (absent / planner /
  reviewer / verifier / explore / gitOps / general-purpose all pass through, case-insensitive
  `Implementer` matches); fail-open and fail-closed cases; both profile halves;
  `standard`/`strict` both block; extension-point on and off; anti-laundering (symlinked ops
  script, decoy basename outside the engine directory, prefix-match). `ECC_HOOK_PROFILE` is
  forced explicitly in every run, and `CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS` is stripped from the
  inherited environment so no result depends on the developer's session.

### Step 3: Register the hook
- **File:** `.claude/settings.json`
- **Action:** Modify
- **Description:** Append one `PreToolUse` / `matcher: "Bash"` entry after `command-guard.sh`.
- **Details:** `bash -c 'ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel
  2>/dev/null || pwd)}"; python3 "$ROOT/.claude/hooks/iron-law-gate.py"'` — byte-identical in
  shape to the existing `reflection-gate.py` wiring, so `install.sh`'s wired-hook resolver and
  `tests/test_hook_delivery.py`'s `HOOK_REF` regex both recognise it.

---

## Testing Strategy

### Boundness proof (required by the brief)

Two layers, because the first alone is not sufficient (review MINOR (b)).

**Wholesale.** `test_every_blocked_command_is_bound_to_the_guard` copies the hook into
`tmp_path`, injects `return True, ''` as the first statement of `decide()`, and re-runs **all
93** blocked payloads. Every one must flip to exit 0. This proves each case depends on
`decide()` *at all*.

**Surgical.** That is too weak on its own: it cannot tell whether `git -C /tmp status` is
caught by a `-C` rule or merely by the generic global-option branch. So
`test_blocked_case_is_bound_to_its_own_guard` runs **eight** targeted mutants, each
disabling ONE guard. **Round-5 correction:** the earlier version asserted only that the
TARGET case flipped, which does not establish "each mutant disables exactly one thing" — a
claim that was made and was demonstrably false for the path-bearing mutant, which also
unblocks four sibling cases. Each mutant now declares its `collateral` set and the test
asserts the flipped set is **exactly** `{target} | collateral` across all 93 blocked cases —
nothing more, nothing less. That is the honest form: it still pins each case to its own
guard, and it makes every guard's blast radius measured instead of asserted. The widest is
the inversion mutant itself (15 collateral cases), and that width IS the value of the
architecture. The guards are: `cat-redirect` and
`pipe-to-tee` ← `_METACHARACTERS`; `pytest-log-file` ← `_PYTEST_SAFE`;
`git-branch-delete-flagonly` ← `_GIT_LIST_SAFE`; `git-remote-add` ← the git positional rule;
`find-delete` ← `_FIND_SAFE`; `path-bearing-inert-verb` ← the PATH-only verb rule; and
`invented-flag-refused-by-default` ← **the default-deny branch itself**, the one mutant that
pins the architecture rather than a table. A ninth mutant,
`test_absolute_path_digest_is_bound_to_safe`, neuters `safe()` and requires the host path to
reach the log — without it the digest assertion would be near-vacuous (see below).

Writing these caught four real defects: a mutant written as `X = () or (...)` disabled
nothing (it evaluates to the non-empty tuple); the git output-flag table could not be
disabled at all because the attached `--output=` form was hardcoded at the call site;
`git branch -D x` turned out to be bound to *two* guards, making it a poor surgical target
(split into a flag-only case and a positional case); and the git positional hole fixed in
D5b was found by writing the `git-remote-add` mutant.

A fifth defect was found in round 5: `test_absolute_host_paths_are_digested_in_the_log` was
near-vacuous. Its case (`/Users/.../evilbin --go`) interpolated only `safe(head)`, and `head`
is already the basename, so the absolute path could never have reached the log even with
`safe()` deleted. It now uses a **positional-outside-root refusal**, where the full path IS
the interpolated value, and `test_absolute_path_digest_is_bound_to_safe` mutates `safe()`
away and requires the path to appear — proving the assertion tests `safe()`.

The real tree is never modified — same discipline as commit `f783c6e` ("install test
simulates broken source in a copy, never the real tree").

### Measured results (prototype, run in a mirror repo before writing this plan)

| Measurement | Result |
|---|---|
| Repo suite baseline, `ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q` | **1017 passed in 100.14s** |
| `tests/test_iron_law_hook.py` against the prototype | **174 passed in 46.43s** (the exact-blast-radius mutants run 8 x 93 payloads) |
| Sanctioned loop commands allowed | 32 / 32 |
| CLAUDE.md DoD gates permitted | 6 / 6 |
| Write vectors blocked (every bypass from rounds 1-5) | 93 / 93 |
| Blocked cases that flip to exit 0 with `decide()` neutered (wholesale boundness) | 93 / 93 |
| Surgical mutants whose flipped set is EXACTLY `{target} \| declared collateral` | 8 / 8 |
| SAFE-list entries across all verbs (residual surface, R7) | 40 |
| Invented flag `--totally-new-writer=x` (never enumerated anywhere) | refused, exit 2 |
| Pass-through cases (absent + 6 other `agent_type`s) | 7 / 7, exit 0, empty stderr |
| `minimal` profile | exit 0, `WOULD-BLOCK head=sed` in `hooks.log` |
| Unparsable payload | exit 0, `ERROR … unparsable` logged |
| `python3 scripts/gen-docs.py --check` (pre-change) | `agents=29 commands=42 skills=76 hooks=20` → OK |
| `execute-json-ops.py <ops.json> --dry-run` | 3 operations, `RESULT-JSON status: success` |
| Post-edit `.claude/settings.json` | parses as JSON; exactly 1 `iron-law-gate.py` entry wired |
| `validate-config-json.py <ops.json>` | **APPROVED**, rc 0 |

Expected post-implementation suite total: **1017 + 174 = 1191**, minus any collisions (none —
the test module name is new).

### Verification commands for the implementer

```bash
python3 -m pytest tests/test_iron_law_hook.py -q     # the new matrix
python3 -m pytest tests/ -q                          # full suite, zero failures tolerated
ruff check src/ tests/ scripts/                      # tests/ IS linted (line-length 100)
python3 scripts/gen-registry.py --check              # also proves the DoD gates are allowed
```

Every command above is one the gate PERMITS. The first revision of this plan listed
`python3 -c "import json;json.load(open('.claude/settings.json'))"`, which this artifact
forbids — a plan prescribing a command its own hook blocks. `test_hook_is_wired_on_pretooluse_bash`
parses `settings.json` inside the suite, so the ad-hoc `python3 -c` check was redundant as
well as forbidden.

**Honest coverage note:** `pyproject.toml:48` sets `extend-exclude = [".claude", …]` for ruff
and `files = ["src/claudekit"]` for mypy, so **the hook itself is neither linted nor
type-checked by the repo gates** — same as `reflection-gate.py`. It is written to the same
standards (py3.9, ≤100 cols, `from __future__ import annotations`, typed), but the binding
gate for it is `tests/test_iron_law_hook.py`, not `ruff`/`mypy`. `tests/test_iron_law_hook.py`
*is* covered by ruff.

---

## Rollback Plan

- `execute-json-ops.py` backs up every target and rolls the **entire** batch back on any
  failure; no partial state is possible from the engine itself.
- Manual rollback after a successful run: delete `.claude/hooks/iron-law-gate.py` and
  `tests/test_iron_law_hook.py`, and remove the appended `PreToolUse` entry from
  `.claude/settings.json` (or `git checkout -- .claude/settings.json`).
- **Zero-downtime disable without any edit:** set `ECC_HOOK_PROFILE=minimal` — the hook
  degrades to record-only (D6). This is the intended emergency valve if the allowlist turns
  out to be too tight in the field.
- Removing the hook restores the previous state exactly: nothing else references it, and the
  file is additive.

---

## Risk Assessment

### Low Risk

- **L0 — `find` write actions.** `-delete`, `-exec`, `-execdir`, `-ok`, `-okdir` by exact
  match plus the entire `-f…` family by PREFIX, so a future `-f<something>` writer cannot
  escape by not being enumerated (the plan/code drift raised as review MINOR (a); the code
  now implements the prefix rule the plan described). Pinned by `find-delete`, `find-exec`
  and `test_find_write_prefix_rule_is_not_a_bare_enumeration`.
- **L1 — Non-implementer callers.** Explicit `agent_type` pass-through with empty stderr,
  covered by 7 parametrized cases. Structurally the hook returns 0 before reading `tool_input`
  for anyone but the implementer.
- **L2 — Composition with the other 9 `PreToolUse` entries.** The hook is monotone (blocks
  only, never allows), so it cannot weaken or contradict any existing gate (D8).
- **L2b — Per-call cost.** `project_root()` runs on every implementer Bash call and forks
  `git rev-parse` when `CLAUDE_PROJECT_DIR` is unset. It is memoized for the process and its
  timeout is 2s, not 10s (review MINOR (d)).
- **L3 — Delivery.** `install.sh` copies hooks structurally and chmods by shebang; the wired-
  hook resolver and `test_hook_delivery.py` fail closed on a missing wired hook (verified, §4).

### Medium Risk

- **R1 — Over-blocking a legitimate verification command in a downstream project.** In a Node
  or Go project, `npm test` / `go test` are not on the list. (In THIS repo the gap was real
  and worse than first stated — two mandatory DoD gates were blocked; fixed under D5d.) Mitigations, in order: (a)
  `implementer.md`'s documented Verifier handoff terminates the loop rather than deadlocking
  it, and the denial text names it; (b) `CLAUDEKIT_IMPLEMENTER_EXTRA_VERBS` widens it opt-in;
  (c) `minimal` degrades to record-only. **Follow-up:** after one dogfood cycle, mine
  `grep WOULD-BLOCK .claude/hooks/hooks.log` and widen the built-in verification set from
  measured data rather than speculation.
- **R2 — Fighting the reflection gate over its escape hatch.** `reflection-gate.py` can block
  the implementer on a pending checkpoint, and the **only** way out is
  `python3 .claude/hooks/reflection.py {receipt,trigger,non-attempt,status}` — the receipt
  inbox alternative is a `Write`, which the implementer does not hold. If this hook rejected
  that CLI the implementer would be **permanently deadlocked**. This has already happened once
  in this repo and had to be fixed. It is explicitly allowlisted (Category B, matched by
  resolved path + verb) and pinned by two `SANCTIONED` cases. Note the shared constraint: both
  gates refuse metacharacters, so a receipt payload must reach the CLI via `--file` or a
  metacharacter-free `--json` argument.
- **R3 — pytest is mutation-capable.** Named residual #1 (D5). Accepted deliberately with the
  reasoning recorded in the hook header, plugin-injection flags refused. Re-open if the
  implementer's role ever changes such that Step 4 is no longer mandatory.
- **R4 — Hook-count drift, cross-workstream.** `scripts/gen-docs.py` counts hook files;
  measured **20 today, 21 after this lands**, so `python3 scripts/gen-docs.py --check` will
  FAIL until docs are regenerated. `scripts/**`, `docs/**` and `CLAUDE.md` are **not owned by
  this workstream**. **Handoff required:** the docs owner runs `python3 scripts/gen-docs.py`
  (regenerate — never hand-edit counts, hard rule 8) and updates CLAUDE.md's "19 hooks" prose,
  which is *already* stale against the measured 20.
  **THE COMMIT IS GATED ON THIS HANDOFF.** `python3 scripts/gen-docs.py --check` is one of
  the six DoD commands and it WILL fail between this plan landing and the regeneration.
  Nobody may report DoD-green in that window; the Definition of Done is not met until the
  count is regenerated. The coordinator owns R4 and R5.
- **R5 — Stale honesty statement, cross-workstream.** `_shared/INVOCATION.md:181-189` and
  `.ai/BACKLOG.md:59` both say "**The hook is not in place yet** — do not describe the
  interactive Iron Law as enforced until it is." Once this lands that sentence is false in the
  other direction, which is its own hard-rule-6 violation. **Handoff required** to the agents-
  doc owner (and `.ai/` owner) to flip it, with the honest qualifier that enforcement now
  covers the Bash tool for `agent_type == implementer` only, is disabled by
  `ECC_HOOK_PROFILE=minimal`, and carries the pytest residual.
- **R6 — `agent_type` is harness-supplied and could change shape.** Verified against 2.1.237
  (§1); the field is built unconditionally by `$y`. If a future release renames or drops it,
  the hook silently degrades to full pass-through (fail open) — a regression that no test can
  catch from inside the repo. **Mitigation:** re-run the `$y` verification on Claude Code
  upgrades, as `.ai/AGENTS_PROTOCOLS.md` already prescribes for the spawn-path spike.

- **R7 — What default-deny does and does not buy.** Stated plainly rather than implied away
  (hard rule 6). It **closes** the "unknown writing flag" class outright: an unenumerated
  flag is refused, so no future `ruff`/`pytest`/`mypy` release can open a bypass. What
  remains is narrower and different in kind: a flag *on* a SAFE list must be safe with **any
  value**, and that is a property argued per entry, not proven. **Measured: 40 SAFE entries
  today** — git 11, reflection 8, git-list 7, find 5, pytest 2, ruff 2, ck 2, ops 2,
  check-only 1, mypy 0, shellcheck 0 — plus one numeric-shorthand rule (`-<digits>`) for the
  git reporters. An earlier revision of this paragraph said "21", which undercounted by
  roughly 2x; in the one paragraph whose job is to state the residual attack surface, that
  is the wrong kind of error, so the number is now generated from the shipped tables rather
  than recalled. Each entry is traceable to a command the implementer is instructed to run. Mitigation: every
  SAFE-list addition is a security change requiring a BLOCKED case beside it, the flag-inert
  verb class requires a per-verb write-free argument before admission, and eight surgical
  mutants keep each guard load-bearing.
- **R8 — Over-blocking is now the expected failure mode, by design.** SAFE lists are as small
  as the DoD gates require, so ordinary variations (`pytest -x`, `pytest -k name`,
  `git log --graph`) are refused. This is the accepted trade: an over-block is visible in
  `hooks.log`, terminates via the Verifier handoff, and is fixed by one reviewed entry.
  Mine `grep WOULD-BLOCK .claude/hooks/hooks.log` after one dogfood cycle and widen from
  measured data, never speculatively.

### High Risk

- None identified. The one candidate — "this hook stops implementation entirely" — is
  eliminated by construction: the 32-command `SANCTIONED` corpus is drawn verbatim from
  `implementer.md` and `implement.md` and asserted non-blocking, the loop-termination walk in
  §3 covers every branch including the reflection interlock, and the residual branch (an
  unlisted verification command) exits via a handoff the implementer's prompt already
  documents.
