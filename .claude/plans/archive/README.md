# Archived ops configs

Ops configs whose anchors no longer match HEAD live here. `tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head` gates the parent directory: a queued (non-archived) ops config that fails `validate-config-json.py` fails the suite, so stale plans get caught mechanically instead of at execution time.

Move a config here when it is **spent** (already executed — anchors consumed by its own edits) or **stale** (the target files changed underneath it — regenerate via `/plan` before executing).

| File | Why archived |
|---|---|
| `ops-hardening-implementer-contract.json` | Spent — executed before archiving; its output is the ops-hardening working-tree changes (see `plan-ops-hardening-implementer-contract.md`). |
| `ops-review-approval-binding.json` | Superseded — never executed as-is; its command-file edits targeted pre-2026-07-31 `review.md`. Its two `file_create` payloads (`review-record.py`, `tests/test_review_record.py`) were reused byte-for-byte by `ops-approval-binding-rebased.json`. Kept as the reviewed design record (3 review rounds). |
| `ops-approval-binding-rebased.json` | Spent — executed 2026-07-31 (RESULT-JSON: 9/9 ops success). The rebase of the above against HEAD, per `plan-remaining-fixes-2026-07-31.md` §2. |
| `ops-task-014-supply-chain-hardening.json` | Spent — executed 2026-08-01 (RESULT-JSON: 11/11 ops success). All supply chain hardening operations applied: action SHA pins, MCP version pins, hash-pinned test deps, CI guards. |
| `ops-workflow-file-templates-ops-schema.json` | Spent — executed 2026-08-10 in worktree `agent/workflow-file-templates-ops-schema` (7/7 ops success), merged as `dfaf6e5`. Fixed AGENTS_KNOWN_ISSUES.md #9 (legacy ops schema in `_shared/WORKFLOW_FILE_TEMPLATES.md`); plan: `plan-workflow-file-templates-ops-schema.md`. |
| `ops-floor-json-flag.json` | Spent — executed 2026-08-17 (RESULT-JSON: 4/4 ops success). Added `--json` to `scripts/check-context-floor.py` + tests + CHANGELOG. Also the first measured pipeline under the token-efficiency prompts: planner never Read the 47KB CHANGELOG (grep-anchored), 31,959 planner tokens total; plan: `plan-floor-json-flag.md`. |

### 2026-08-19 — reflection/review-discipline batch (7 workstreams, 21 ops)

One parallel decomposition with a disjoint file-ownership map (19 files, zero collisions), 13 review
rounds, every verdict hash-bound via `review-record.py`. Every plan failed its first review; scores
on approval ran 91–95. Executed in dependency order, `plan-ops-approval-gate` last because its own
gate closes on every sibling config the moment it lands.

| File | Why archived |
|---|---|
| `plan-context-economy-rules.ops.json` | Spent — executed 2026-08-19 (4/4). Bounded reads, output spill, and script-first folded into `token-optimization` + `context-budget`; net −10 chars on the skill-description floor. Review 95/100, 1 round. |
| `plan-review-floor-and-iron-law-scope.ops.json` | Spent — executed 2026-08-19 (2/2). Per-PR adversarial review floor into CLAUDE.md (301 raw chars, 133 raw headroom left under the ×4 delivery weighting) + OPEN decision 21 on Iron Law scope. Review 88→93, 2 rounds. **Execution defect:** its `add_after` lacked a leading newline and concatenated onto the Tier 3 bullet (442-char line); fixed immediately after. |
| `plan-e2e-pipeline-test-task.ops.json` | Spent — executed 2026-08-19 (1/1). Wrote `review/tasks/015-e2e-pipeline-flow-tests.md`: 41 cases, 36 deterministic / 4 live-spawn / 1 hybrid, mutation proof for all 9 groups. Review 86→92, 2 rounds. |
| `plan-review-discipline.ops.json` | Spent — executed 2026-08-19 (5/5, 15 edits). code-reviewer Phase 0 revision confirmation, new `verification-gap-lens` skill, finding-`Class` ratchet in `.ai/REVIEW_GUIDE.md`. Review 81→88→92, 3 rounds (ceiling). Round-1 fix closed a refuse-everything hole and opened a blind-to-untracked-files one; round 3 closed both. |
| `plan-reflection-lifecycle-gates.ops.json` | Spent — executed 2026-08-19 (6/6). External append-only reflection ledger, sanitized fingerprints, HMAC receipts, PreToolUse checkpoint gate, interrupt-once Stop/SubagentStop, first `PreCompact` hook. 79/79 tests. Review 88→87→92, 3 rounds. Round-2 fix introduced a symlink-laundering bypass that let an arbitrary source write pass BOTH this gate and `ops-enforcement.sh`; the reviewer constructed the exploit, round 3 closed it (islink refusal + parent-only realpath + `ln` blocked). |
| `plan-agent-tool-grants.ops.json` | Spent — executed 2026-08-19 (5/5). Honest framing for the frontmatter/INVOCATION grant contradictions + `tests/test_agent_tool_grant_drift.py`. Review 89→89→92, 3 rounds. Established by live measurement that a frontmatter-declared `Bash(...)` specifier is **not applied** on the interactive path, so the implementer holds unscoped Bash and the interactive Iron Law is prompt-enforced, not harness-enforced. |
| `plan-ops-approval-gate.ops.json` | Spent — executed 2026-08-19 (3/3). Moved the approval check INTO `execute-json-ops.py` so it cannot be skipped; 13 behavioral tests. Review 88→91, 2 rounds. Verified live after landing: a drifted ops.json is refused with `exit 1`, `RESULT-JSON.reason="approval-gate: ..."`, `operations: []`, `backup_dir: null`, and no backup directory created — refusal precedes every side effect. |
| `plan-iron-law-scope-and-hook-count.ops.json` | Spent — executed 2026-08-19 (4/4), and the **first config gated by the approval check landed earlier the same day** ("Approval: reviewed verdict verified for this exact ops.json"). Implements Decision 21 Option A: tracked `.ops-source-globs` marker makes `.claude/{agents,commands,skills,hooks,operations}/*` count as SOURCE in this checkout only, with a never-source denylist checked first so the bootstrap cannot deadlock. Dormant under `ECC_HOOK_PROFILE=minimal` by design, pinned by a test. Also made `gen-docs.py` count `.sh`+`.py` hooks minus sourced/imported libraries and OWN the prose count sites — the published number was 19 while the repo shipped 20 (`reflection.py` is a library imported by `reflection-gate.py`, like `lib.sh`, so it is not a hook). 50 behavioral tests; the denylist arm is bound (deleting it → 11 failures). Review 92/100, 1 round; three refutation attempts — user-project regression, self-deadlock, marker DoS — all failed. |
