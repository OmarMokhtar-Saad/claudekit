# Implementation Plan: Honest Agent Tool Grants (Workstream 7)

## Overview

Agent frontmatter `tools:` and `.claude/agents/_shared/INVOCATION.md` contradict each other,
and the contradiction is not cosmetic: the Task-tool spawn path reads the frontmatter, so the
implementer holds **unscoped Bash** and the Iron Law is bypassable in every interactive
session. This plan settles — by measurement, not assumption — whether frontmatter can express
a scoped Bash grant (it cannot), then makes INVOCATION.md tell the truth, closes the
code-reviewer row that a just-landed Phase 0 invalidated, hardens the implementer's Iron Law
against Bash mutation, and adds a behavioral drift gate.

## Evidence (measured 2026-08-19, Claude Code 2.1.235, no WebSearch/WebFetch)

All probes ran in throwaway fixture projects. **Observed `permission_mode`: `default`** —
captured directly from the `PreToolUse` payload for the very command in question, not
inferred. Fixture settings were `{"permissions": {"allow": [], "deny": []}}`: **no allow rule
and no deny rule**, so nothing in the environment pre-approves anything. No permission bypass
flag was used anywhere.

### Primary evidence: a differential test with the spawn path held constant

The same rule, `Bash(python3 *)`, was given the same write command
(`python3 -c "open(...,'w')..."`), same model, same `default` mode, same empty allow list,
**both arms loaded through `--agent`** so the spawn path is not a variable:

| Arm | How the agent was configured | Result |
|---|---|---|
| frontmatter | `--agent probe2`, frontmatter `tools: ["Read", "Bash(python3 *)"]` | **approval demanded**, no file — rule NOT applied |
| CLI | `--agent probe3` (bare `tools: ["Read", "Bash"]`) + `--allowedTools "Read,Bash(python3 *)"` | ran **unapproved**, file written — rule APPLIED |

The only variable is *where the rule was declared*. An allow-rule IS honoured by an
agent-loaded session; the identical rule placed in frontmatter is not. The probe is
write-based, so no safe read-only auto-approval explains it, and it relies on no self-report.

**What this establishes, and what it does not.** It establishes that the
**frontmatter-declared specifier is not applied**. It does **not** separate *why*: whether
the specifier is stripped at parse time (H1) or retained but ignored by the permission layer
(H2) was not distinguished, and the interactive **Task-tool** subagent path was not isolated
— both arms used `--agent` — so a narrow H2 variant ("the Task path applies no allow-rule to
subagents at all") remains untested there. The agent self-report of `Read`+`Bash` from a
declared `Bash(git status:*)` weakly favours H1, but it is corroborating only and is not
relied on. **Missing arm, named so this stays falsifiable:** trust a fixture workspace, put
`Bash(python3 *)` in `.claude/settings.json` `permissions.allow`, and spawn via the Task
tool; if the write still demands approval, the H2 variant holds. (Attempted 2026-08-19 and
blocked by the workspace trust dialog, which would have required editing the user's
`.claude.json` trust config — deliberately not done.)

**The ship-relevant conclusion is unaffected and keeps high confidence:** frontmatter cannot
scope Bash, so the interactive implementer effectively holds unscoped Bash. H1 and H2 both
predict that, and the disposition in this plan is correct under either.

### Control: `--allowedTools` scoping genuinely refuses out-of-scope commands

Under `--allowedTools "Read,Bash(python3 *)"`, a `perl -e "open(F,'>',...)"` write **required
approval** and did not run, while the `python3` write ran freely. Scoping on that path is real
enforcement, not decoration — which is what makes the differential above meaningful.

### Corroborating (weaker instruments, not load-bearing)

- A fixture agent declaring `tools: ["Read", "Bash(git status:*)"]`, asked to list its
  registered tools, answered exactly `Read` and `Bash`. This is an LLM narrating its own
  registration — treated as **corroborating only**.
- `uname -s && whoami` ran unapproved under that same agent. Also corroborating only: these
  are safe read-only commands that `default` mode may auto-approve regardless of scoping.
- Binary inspection: internal agent configs carry bare-name `tools:["*"]`-style lists
  alongside `agentType/model/permissionMode`, while `Tool(specifier)` parsing lives on the
  separate `--allowedTools` path (`Ignoring --allowedTools rule "..."` diagnostics).

### Specifier syntax: BOTH forms verified on the `--allowedTools` path

The space form is the one this plan writes six times for code-reviewer, so it was measured
rather than assumed:

- `Bash(python3 *)` — **space form: HONOURED** (write ran unapproved).
- `Bash(python3:*)` — **colon form: HONOURED** (write ran unapproved).
- No `Ignoring --allowedTools rule` diagnostic was emitted for either.

Both parse. The space form is retained, matching the existing debugger row precedent, and the
six new code-reviewer rules are **not** silently ignored.

### `agent_type` is available to hooks

`agent_type` is present in the `PreToolUse` payload on BOTH the `--agent` and the Task-tool
(`subagent_type`) paths, alongside `tool_name`, `tool_input.command`, `permission_mode`,
`cwd`, `session_id`, and `tool_use_id`. The feared blocker on option (b) does not exist on
this version: a hook CAN attribute a Bash call to the calling subagent.

**Answer to the design question:** frontmatter `tools:` accepts bare tool names only.
Scoping exists solely on the headless `claude -p --allowedTools` path. The interactive
implementer therefore cannot be scoped by frontmatter.

**Confidence, stated separately.** "Frontmatter cannot scope Bash" — **high**, from the
differential test. "The six new code-reviewer rows grant Phase 0's verbs headlessly" —
**measured for rule syntax** (both forms parse and enforce); the individual `git`/`gh` verbs
are not separately exercised, and the row is a permission grant, not a guarantee that any
particular repo state makes those commands succeed.

**Option chosen: (c) now, (b) next — explicitly, not silently.** Option (a) is rejected
because removing `Bash` also removes the ops engine itself (`python3 execute-json-ops.py` is
invoked *through* Bash), which would break `/implement`. Option (b) is the correct mechanical
fix and is now proven implementable, but every hook and `.claude/settings.json` is owned by
another workstream — so this plan documents the gap honestly (hard rule 6), tightens the
prompt-level Iron Law, and hands an **allowlist-shaped** spec to the hooks workstream.

## Scope

- **In Scope:** `INVOCATION.md` truth-telling + the code-reviewer row; the implementer's Iron
  Law wording; a behavioral drift gate under `tests/`.
- **Out of Scope:** any hook, `.claude/settings.json`, `execute-json-ops.py`, CLAUDE.md,
  CHANGELOG.md, docs/, `.ai/BACKLOG.md`. Also out of scope: the `explore`,
  `security-scanner`, and `silent-failure-hunter` frontmatter files, which are **also**
  drifted (see Risks) but are not owned by this workstream.

## Prerequisites

None. No new dependencies; stdlib only.

## Implementation Steps

### Step 1: Correct the code-reviewer `--allowedTools` row
- **File:** `.claude/agents/_shared/INVOCATION.md`
- **Action:** Modify
- **Description:** The row grants `Read,Grep,Glob` with no Bash, but the just-landed Phase 0
  ("Confirm the Revision") requires `gh pr diff/view`, `git diff`, `git show`,
  `git rev-parse`, `git ls-files --others`, and `git worktree add/remove`. A code-reviewer
  spawned headlessly under the current row cannot complete Phase 0 and must emit
  `CANNOT REVIEW`.
- **Details:** Replace the grant with
  `Read,Grep,Glob,Bash(git show *),Bash(git diff *),Bash(git rev-parse *),Bash(git ls-files *),Bash(git worktree *),Bash(gh pr *)`,
  matching the debugger precedent, and update the rationale to cite Phase 0.

### Step 2: Add the frontmatter-vs-`--allowedTools` truth section
- **File:** `.claude/agents/_shared/INVOCATION.md`
- **Action:** Modify (insert after the "Never grant unrestricted `Bash`" paragraph)
- **Description:** State plainly that the existing table is the **headless** contract, that
  the interactive Task path reads frontmatter, and that frontmatter grants are bare names
  only — with the probe results and version pinned so the claim is falsifiable.
- **Details:** Adds (a) the measured findings, (b) a rule never to write `Tool(specifier)` in
  frontmatter because it reads as enforcement and is not, (c) an honest statement that the
  implementer's Iron Law is prompt-enforced on the interactive path pending the hook, and
  (d) a machine-parseable table of the actual frontmatter grants per agent, which becomes the
  drift gate's fixture.

### Step 3: Extend the implementer's Iron Law to cover Bash mutation
- **File:** `.claude/agents/implementer.md`
- **Action:** Modify
- **Description:** The Iron Law currently forbids only `Edit`/`Write`. That is exactly the
  hole: the agent holds unscoped Bash, so `sed -i`, `cat > file`, `tee`, and
  `python3 -c "open(...,'w')"` all bypass it while obeying the letter of the rule.
- **Details:** Forbid **any** file-mutating Bash, name the specific vectors, and permit only
  `execute-json-ops.py` (plus read-only inspection), so the prompt-level rule at least
  matches the actual threat model until the hook lands. Frontmatter `tools:` is deliberately
  left unchanged — see Evidence.

### Step 4: Add the grant-drift gate (textual/structural)
- **File:** `tests/test_agent_tool_grant_drift.py`
- **Action:** Create
- **Description:** Regression test for this exact bug class: frontmatter and INVOCATION.md
  silently disagreeing. The file is named `..._drift` so a green suite can never be
  misread as proving enforcement — nothing here is behavioral; all four tests are
  textual/structural checks over file contents.
- **Details:** Four tests — (1) every agent's frontmatter `tools:` set equals the
  INVOCATION.md frontmatter table row (the drift gate); (2) no frontmatter `tools:` entry
  contains a `(` specifier anywhere in `.claude/agents/`, since specifiers are silently
  stripped and are therefore a false sense of enforcement; (3) the code-reviewer row grants
  the git/gh verbs Phase 0 needs; (4) the implementer's Iron Law names Bash mutation.

## Testing Strategy

- `python3 -m pytest tests/test_agent_tool_grant_drift.py -q` — new gate.
- `python3 -m pytest tests/ -q` — full suite, zero failures.
- `ruff check tests/test_agent_tool_grant_drift.py` — line-length 100.

**Which tests are actually bound (asked for explicitly).** `test_documented_grants_match_frontmatter` is genuinely bound: it checks all ten documented rows against real frontmatter and fails on injected drift (verified). `test_no_specifier_in_any_frontmatter_tools` passes **vacuously today** — no agent frontmatter contains a `(` at all — so it is a preventive ratchet, not a control. The remaining two gate **deletion only**: they fail if the corrected text is removed, not if it is wrong.

**Honesty note on what the test proves.** The brief asked whether the test can assert the
*actual registered tool grant* rather than grepping YAML. It cannot, in CI: obtaining the
real grant requires booting an authenticated `claude` session (network + credentials +
~13-14s cold boot), which is not admissible in this suite. These are textual checks, not behavioral ones. What they *do* prove is the
invariant whose violation caused this bug — that the documented grant and the grant the
harness will actually read never diverge again — plus the `Tool(specifier)` footgun, which is
a genuine behavioral fact established by the manual probe and recorded with its version pin
in INVOCATION.md. The manual probe is the evidence; the test is the ratchet.

`tests/test_behavior_spec.py::TestAgentRegistration` was evaluated as the home and rejected:
its stated contract is *YAML structural validity* (does the agent register at all), it
deliberately avoids parsing values, and its `KNOWN_KEYS` check is orthogonal to grant
semantics. A separate file keeps both contracts legible.

## Rollback Plan

`git checkout -- .claude/agents/_shared/INVOCATION.md .claude/agents/implementer.md` and
`rm tests/test_agent_tool_grant_drift.py`. All three changes are text-only, with no runtime or
schema surface; reverting restores the prior (incorrect but non-crashing) state.

## Risk Assessment

- **Low Risk:** Steps 1-3 are prompt/doc text. No executable path changes.
- **Low Risk:** Step 4 is additive; it cannot fail an unrelated change unless that change
  itself introduces grant drift, which is the point.
- **Medium Risk — cross-workstream handoff (hooks owner). Specify it as an ALLOWLIST.**
  The Iron Law remains prompt-enforced on the interactive path. The mechanical fix is
  unblocked (`agent_type` is measured-present on both spawn paths). **Do not build it as a
  denylist.** Any enumeration of mutating commands is incomplete — `git apply`,
  `git checkout -- <path>`, `patch`, `ed`, `perl -pi`, `perl -i`, `xargs`, plus anything
  wrapped in `sh -c`, `bash -c`, a heredoc, backticks, or `$(...)` all evade a pattern list,
  and a denylist is exactly the "speed bump, not a sandbox" shape hard rule 6 warns about.
  Spec: a `PreToolUse` hook, `matcher: "Bash"`, that reads `agent_type` from stdin and when
  it equals `implementer` **permits only** (a) argv matching
  `python3 .claude/operations/scripts/execute-json-ops.py *`, and (b) a named read-only verb
  set — and **rejects everything else, including anything it cannot confidently parse**.
  Per hard rule 2 it must `exit 2` with stderr and fail closed. The parsing layer must be
  specified, because a bare verb list is not decidable:
  1. **Reject before matching** any command containing a shell metacharacter or wrapper:
     `;`, `|`, `&&`, `||`, newline, backticks, `$(`, `<<` heredoc, `sh -c`, `bash -c`,
     `env`, `xargs`, `nohup`, `eval`.
  2. **Match on the full tokenised argv**, never a string prefix (`git diff` must not be
     satisfied by `git diff --output=x`) and never a substring of the raw command.
  3. **Conditionally-mutating verbs need argv rules, not names.** Permit `sed` only if NO
     token starts with `-i` and none equals `--in-place`. Never permit `git checkout`,
     `git apply`, `git restore`, `git reset`. `pytest` executes arbitrary repo and
     `conftest.py` code, so treat it as mutating-capable, not read-only — include it only
     if the hooks owner accepts that explicitly.
  4. **Non-implementer case is explicit pass-through:** if `agent_type` is absent or is any
     value other than `implementer`, the hook exits 0 without opinion. It must not fail
     closed on unrelated agents or on the main session.
  A starting read-only set: `cat`, `head`, `tail`, `sed` (per rule 3), `grep`, `rg`, `ls`,
  `find`, `wc`, `git status`, `git diff`, `git log`, `git show`, `ruff`, `mypy`,
  `shellcheck`.

- **Medium Risk — wider drift left unfixed.** `explore`, `security-scanner`, and
  `silent-failure-hunter` all declare `Bash` in frontmatter while INVOCATION.md documents
  them as read-only `Read,Grep,Glob`. This is the same bug in three more files that this
  workstream does not own. Step 2's table records their **actual** grants so the
  documentation stops lying today; narrowing them is a follow-up for their owner. Note the
  drift gate will therefore pass on the honest-but-wide grants — it gates divergence, not
  policy.
- **High Risk:** none identified.
