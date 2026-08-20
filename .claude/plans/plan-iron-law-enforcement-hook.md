# Implementation Plan: Iron Law Enforcement Hook (Workstream 12)

Ops config: `.claude/plans/plan-iron-law-enforcement-hook.ops.json` (3 operations, validator APPROVED)

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
pins steps 2-7 as `SANCTIONED`, 24 commands, and treats any block of them as "the implementer
is left with no possible action".

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

Mitigation: pytest's plugin-injection and file-emitting flags are refused (`-p*`, `--pdb`,
`--pdbcls`, `--junitxml`, `--junit-xml`, `--result-log`, `--basetemp`), pinned by
`pytest-plugin-injection`. **Named residual #1.**

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

`.claude/settings.json` already wires, in order: `reflection-gate.py` (`matcher ""`),
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
- **Details:** 24 `SANCTIONED` commands × must-not-block; 55 `BLOCKED` write vectors ×
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

`test_every_blocked_command_is_bound_to_the_guard` copies the hook into `tmp_path`, injects
`return True, ''` as the first statement of `decide()`, and re-runs **all 55** blocked payloads
against the mutant. Every one must flip to exit 0. Any case that still blocks is reported by
label as "does not test the guard". The real tree is never modified — same discipline as
commit `f783c6e` ("install test simulates broken source in a copy, never the real tree").

### Measured results (prototype, run in a mirror repo before writing this plan)

| Measurement | Result |
|---|---|
| Repo suite baseline, `ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q` | **1017 passed in 100.14s** |
| `tests/test_iron_law_hook.py` against the prototype | **102 passed in 7.05s** |
| Sanctioned loop commands allowed | 24 / 24 |
| Write vectors blocked (incl. every bypass named in the brief) | 55 / 55 |
| Blocked cases that flip to exit 0 with `decide()` neutered (boundness) | 55 / 55 |
| Pass-through cases (absent + 6 other `agent_type`s) | 7 / 7, exit 0, empty stderr |
| `minimal` profile | exit 0, `WOULD-BLOCK head=sed` in `hooks.log` |
| Unparsable payload | exit 0, `ERROR … unparsable` logged |
| `python3 scripts/gen-docs.py --check` (pre-change) | `agents=29 commands=42 skills=76 hooks=20` → OK |
| `execute-json-ops.py <ops.json> --dry-run` | 3 operations, `RESULT-JSON status: success` |
| Post-edit `.claude/settings.json` | parses as JSON; exactly 1 `iron-law-gate.py` entry wired |
| `validate-config-json.py <ops.json>` | **APPROVED**, rc 0 |

Expected post-implementation suite total: **1017 + 102 = 1119**, minus any collisions (none —
the test module name is new).

### Verification commands for the implementer

```bash
python3 -m pytest tests/test_iron_law_hook.py -q     # the new matrix
python3 -m pytest tests/ -q                          # full suite, zero failures tolerated
ruff check src/ tests/ scripts/                      # tests/ IS linted (line-length 100)
python3 -c "import json;json.load(open('.claude/settings.json'));print('settings OK')"
```

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

- **L1 — Non-implementer callers.** Explicit `agent_type` pass-through with empty stderr,
  covered by 7 parametrized cases. Structurally the hook returns 0 before reading `tool_input`
  for anyone but the implementer.
- **L2 — Composition with the other 9 `PreToolUse` entries.** The hook is monotone (blocks
  only, never allows), so it cannot weaken or contradict any existing gate (D8).
- **L3 — Delivery.** `install.sh` copies hooks structurally and chmods by shebang; the wired-
  hook resolver and `test_hook_delivery.py` fail closed on a missing wired hook (verified, §4).

### Medium Risk

- **R1 — Over-blocking a legitimate verification command in a downstream project.** In a Node
  or Go project, `npm test` / `go test` are not on the list. Mitigations, in order: (a)
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

### High Risk

- None identified. The one candidate — "this hook stops implementation entirely" — is
  eliminated by construction: the 24-command `SANCTIONED` corpus is drawn verbatim from
  `implementer.md` and `implement.md` and asserted non-blocking, the loop-termination walk in
  §3 covers every branch including the reflection interlock, and the residual branch (an
  unlisted verification command) exits via a handoff the implementer's prompt already
  documents.
