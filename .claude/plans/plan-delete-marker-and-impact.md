# Plan: `(delete)` marker for Tier 3 deletions, drop `impact --ops`, rewrite rule 4

Tier: 3
Parent: plan-remove-ops-phase2.md ("Owner decision still open", option (c)). Owner approved the direction (c) plus a cap of 3 deletions per plan; protected files stay protected.
Branch: `feat/remove-ops` (continues; nothing pushed).

## Phase 0: design precheck
Ownership model: the plan's `Files:` header is the single declaration of what a Tier 3 change may write; `review-record.py` parses it (`parse_plan_files`), binds it to the plan sha256 at `plan-write`, and answers `plan-check <plan> --path P`; `plan-gate.sh` (Edit/Write) and `checkpoint-gate.sh` ask it through `plan-lib.sh`; `shell-write-gate.py` is the only Bash hook that already parses `rm`. The value of this change sits in exactly those five files plus the prose that names the old cap. One finding changes the shape of the work: **no deletion detection exists today.** `plan-gate.sh` matches only Edit/Write and treats any write as "covered or not"; `rm`, `git rm` and `unlink` of a Tier 3 file reach no plan check at all (`shell-write-gate.py` only guards the owner-only paths), and a Write that empties a file is just a write. So "reuse" means: reuse the `Files:` parser, `plan-check`, `pg_is_t3`, `_path_matches` and the `shell-write-gate.py` segment loop, and add one detection step in each of the two existing hook entry points. No new hook, no new registry entry, no new counts.

Prior searches (Phase 0): `ck rejections search` does not exist in this CLI (not run); `knowledge-ledger.py search` ran: 1 unrelated match (reflection-a1779aadd07b, a fixture-seeding note). `project-graph hubs` lists neither `review-record.py` nor `plan-lib.sh` as a hub; both are reached through their CLI/source only. Neither result changes the design.

## Goal
1. A Tier 3 path may be deleted only when the approved plan lists it in `Files:` with a trailing `(delete)` marker. Max 3 marked deletions per plan, checked when the plan is recorded.
2. `project-graph.py impact --ops` (reads an ops.json that no longer exists) is removed with its docs and tests.
3. Rule 4 and its echoes say what the code now does.

## Findings that fix the design
- `.claude/hooks/plan-gate.sh:23-26` only continues for Edit/Write tools; step 4 (`pg_authorised "$REL"`, line 104) is the single authorisation point. `.claude/plan-gate.globs` does not exist in this repo, so Tier 3 = the default rule in `plan-lib.sh:41-45` (everything except `.claude/*`, `*.md|*.txt|*.rst|*.adoc|*.log|*.tmp`). Deleting a `.claude/` or `.md` file is NOT Tier 3 and stays ungated (the owner scoped this to Tier 3; stated in the docs below, not widened).
- `review-record.py:1159 parse_plan_files` returns only the backticked tokens (`` `path` (delete) `` already parses to `path`, the marker is dropped), and comma-form tokens would keep the marker text. `_FILES_RE` at 1136, `_BARE_GLOBS` at 1137, `cmd_plan_write` at 1230 (refusal `EXIT_PLAN_BAD_FILES = 8` at 1241), `cmd_plan_check` at 1307, parser registration at 1381.
- `plan-remove-ops-phase2.md` already uses the style `` `path` (delete) `` on continuation lines, so the marker needs no format change. That plan has far more than 3 marked paths and is already recorded; the cap runs at `plan-write` only, so its record is untouched, but re-recording it would now be refused (named in Risks).
- `impact` is a whole subcommand whose only input is `--ops`; nothing in agents, commands, skills, hooks, docs or other tests calls it (grep: only `codebase-mapping/SKILL.md:224`, the module docstring lines 17 and 35-37, `project_graph_render.py:6`, the three comments at project-graph.py 544/718/973, and `tests/test_project_graph_impact.py`, which nothing else imports). The reviewer routing it provided was never wired to a hook. Minimal replacement: none in code. The planner's existing Discovery step 7 (`.claude/agents/planner.md:99-101`: `project-graph.py hubs` and `query <file> --direction in`, "a GOD-NODE ... MUST appear in the Risk Assessment") already is the live route; the skill doc gets one sentence pointing to it. `is_god_node` stays (used by `hubs` and `render`).
- No test asserts rule-4 text: grep of `tests/` for `Protected files stay`, `MAX_DELETIONS`, `Protected-file guards` finds only `tests/test_repo_hygiene.py:68` (the unrelated `repo-hygiene.py clean --max-deletions`). Nothing asserts CONSTITUTION Article V text either. Generated counts ("29 ops guards" at `.ai/MEMORY.md:11`, `.ai/SYSTEM_OVERVIEW.md:46`) are gen-docs-owned and are not hand-edited here.

## Design

### Marker semantics (review-record.py)
- New helper `_files_entries(text) -> list[(path, is_delete)]` holds the loop body of `parse_plan_files` and also reads a trailing `(delete)` (case-insensitive, optional whitespace) after a backticked token, or at the end of a comma-form token. `parse_plan_files(text)` keeps its signature and returns the paths with the marker stripped (so `files` in existing records and all current callers are unchanged). New `parse_plan_deletions(text)` returns the marked paths.
- `cmd_plan_write`: after the bare-glob refusal, refuse with `EXIT_PLAN_BAD_FILES` when (a) a `(delete)` entry contains glob characters (`*?[`), or (b) more than `MAX_PLAN_DELETIONS = 3` entries are marked. The message names the count and says large removals need several reviewed plans (keeps DECISIONS 7's intent).
- `cmd_plan_check` gains `--delete` (requires `--path`): after the existing sha256/score/coverage checks it also requires `--path` to be in `parse_plan_deletions(<plan text>)` (plan text is hash-bound by the check above, so no new record field is needed and old records keep working). Failure prints `NOT MARKED (delete): ...` and returns `EXIT_PLAN_NOT_AUTHORISING` (4).

### plan-lib.sh
New `pg_authorised_delete "$rel"`, a copy of `pg_authorised` that calls `plan-check "$plan" --path "$rel" --delete`. Same fail-closed behaviour when the recorder is missing.

### plan-gate.sh (Write-to-empty)
Between the carve-out (step 3) and the binding (step 4): when the tool is `Write`, `content` is the empty string and the target exists with size > 0, use `pg_authorised_delete`; otherwise `pg_authorised` as today. The deny text names the `(delete)` marker. The deny list, FROZEN-header check and Tier 1 carve-out (Edit only) are untouched, so protected files stay protected first. Header comment updated. An Edit that shrinks a file to nothing is not detected (honest limit, stated in the header).

### shell-write-gate.py (rm / git rm / unlink)
Add `_tier3_delete_violation(command, cwd)` called from `main()` after the existing `_violates` check; the existing protected-path check and its fail-closed parse stay first.
- Per segment of `re.split(r"[;&|\n]+", command)`: `shlex.split`; skip a leading `sudo`/`command`/`VAR=x`; verbs `rm`, `unlink`, and `git rm`. Segments that do not parse, or whose operands contain `$` or a backtick, are skipped (documented speed-bump limit).
- Operands: non-option tokens (honour `--`), `glob.glob` expanded relative to the payload `cwd`; a directory operand expands to its files (cap 200, over the cap blocks with "narrow the command").
- Active only where `<root>/.claude/plans` exists (same switch as plan-gate). Root is resolved like plan-gate's `resolve_root` (payload `cwd`, then `git rev-parse --show-toplevel`). Only **git-tracked** existing files are checked (`git ls-files --error-unmatch`); untracked and ignored files (`rm -rf build dist __pycache__`, `rm src/x.pyc`) are never blocked. All tracked targets go to ONE `bash` call (batched, not one spawn per file) that sources `plan-lib.sh` and loops, printing every path where `pg_is_t3 "$rel" && ! pg_authorised_delete "$rel"`. `SCRIPT_DIR`, `ABS_ROOT` and the target list are passed through the subprocess **environment / stdin (NUL-separated)**, never interpolated into the script string, so a hostile filename cannot inject shell. A helper that cannot run blocks (fail closed). Tier classification stays single-sourced in `plan-lib.sh`.
- Block message (exit 2, stderr): names the path and says "list it in the approved plan's `Files:` with `(delete)` (max 3 per plan)". Docstring updated. Not detected: `find -delete`, `git clean`, `mv`, scripted `os.remove`, a delete inside `$(...)` (speed bump, not a sandbox, hard rule 6).
- Protected files stay protected: `settings*.json`, `plan-gate.globs` and the review records are matched by the existing `PROTECTED` check before this runs, and `pg_is_denied_path` runs before any plan check in plan-gate; a `(delete)` marker never lifts them.

### impact removal
Delete `read_ops`, `ops_paths`, `top_package`, `cmd_impact` and the `impact` argparse block from `project-graph.py`; drop the docstring lines 17 and 35-37 and fix the section banner at 538-540 (keep `is_god_node` under a "god-node rule" banner); reword the comments at 544, 718 ("as read_ops does" becomes "as resolve_against does") and 973-974; remove now-unused imports/types only if ruff/mypy say so. Delete `tests/test_project_graph_impact.py`.

### Prose
- Rule 4 (CLAUDE.md:47, AGENTS.md:43), same text in both: `4. Protected files stay protected (hooks); deleting a Tier 3 file needs \`(delete)\` on its path in the plan's \`Files:\` (plan-gate), max 3 per plan.`
- `.ai/KNOWLEDGE_BASE.md:98`: `4. Protected-file guards and the \`(delete)\` marker (max 3 deletions per plan, plan-gate).`
- `.ai/MEMORY.md:14`: replace `protected files + MAX_DELETIONS=3` with `protected files + \`(delete)\`-marked deletions (max 3/plan)`.
- `.ai/SECURITY_GUIDE.md:15`: replace the whole "Ops guards" bullet (keep numbering 5) with `5. **Deletion marker** — a Tier 3 deletion (rm, git rm, unlink, Write-to-empty) needs \`(delete)\` on the path in the approved plan's \`Files:\`, max 3 per plan; protected paths (review records, settings, plan-gate.globs) stay owner-only and a marker never lifts them; \`checkpoint-gate\` takes a git checkpoint before Tier 3 edits.` The other bullets (secret hygiene etc.) are untouched; layer 2's hook list already names plan-gate.
- `.claude/local/CONSTITUTION.template.md` Article V: Section 2 "Protected Files": protected files stay protected by hooks (plan-gate deny list for review records, settings and plan-gate.globs; shell-write-gate for the shell forms; config-protection for lint/type configs) and a plan cannot unlock them; replace the stale "cannot be deleted via operations config" list with what `config-protection.sh` actually protects (the implementer greps its pattern list first and copies only that). Section 3 "Safety Limits": backup = a git checkpoint (`checkpoint-gate` tags `ck-checkpoint/<epoch>` before the first Tier 3 edit; restore with `git stash apply <tag>`; a deleted tracked file is also recoverable from git); deletions of Tier 3 files must carry `(delete)` in `Files:`, max 3 per plan; remove "Deletion reason minimum" and "Automatic backup before all operations" (ops-engine behaviours).
- `.claude/agents/_shared/planner-reference.md:69-71`: add one bullet: a path the plan deletes is written `` `path` (delete) ``, concrete (no globs), at most 3 per plan; plan-gate blocks a Tier 3 deletion that is not marked.
- `.claude/skills/codebase-mapping/SKILL.md:224-227`: delete the `impact` bullet; add one sentence: "To score a plan's blast radius, run `hubs` and `query <file> --direction in` for each file it touches (planner Discovery step 7); a GOD-NODE goes in the Risk Assessment."
- `CHANGELOG.md` `[Unreleased]`: Added (`(delete)` marker, cap 3, shell and Write-to-empty detection), Removed (`project-graph.py impact`), Changed (rule 4). `.ai/CHANGELOG_AI.md`: one entry (the decision, the "no deletion detection existed" finding, honest limits). `.ai/DECISIONS.md` (history) is not edited.

## Implementation steps
Order: parser first, then hooks, then removal, then prose, then tests-at-the-end (owner rule: no full suite; touched files only).

1. `.claude/operations/scripts/review-record.py` (File/Action/Details): add `MAX_PLAN_DELETIONS = 3`, `_DELETE_MARK_RE`, `_files_entries`, `parse_plan_deletions`; make `parse_plan_files` a thin wrapper; add the two refusals to `cmd_plan_write` (after line 1241); add `--delete` to the `plan-check` parser (line ~1383) and the check to `cmd_plan_check` (before the final `OK` print); update the module docstring usage (line 13) and exit-8 text (line 23). Done when: `plan-check <plan> --path p --delete` exits 0 for a marked path, 4 for an unmarked covered path, and `plan-write` refuses a plan with 4 marked paths (exit 8).
2. `.claude/hooks/plan-lib.sh`: add `pg_authorised_delete` next to `pg_authorised` (line 72). Done when: `bash -n` and shellcheck pass.
3. `.claude/hooks/plan-gate.sh`: add the Write-to-empty branch before step 4 (line ~103), update the header comment and deny text. Done when: shellcheck passes; an empty Write over an existing covered-but-unmarked T3 file exits 2, over a marked one exits 0, a non-empty Write is unchanged.
4. `.claude/hooks/shell-write-gate.py`: add `_tier3_delete_violation` and the call in `main()`; docstring update. Done when: with `app.py` git-added in the fixture, `rm app.py` exits 2 without a marked plan and 0 with one; `rm -rf build` (untracked) exits 0; `rm README.md` and `rm -rf /tmp/x` exit 0; the existing protected-path tests still pass; ruff clean (100 cols).
5. `.claude/operations/scripts/project-graph.py` and `project_graph_render.py` (line 6-7 comment: drop the `impact` sentence): remove `impact` as described; then `git rm tests/test_project_graph_impact.py` (this is the plan's one `(delete)`; with step 4 live it needs the marker, which is the dogfood check).
6. Prose files in the order of the Prose section; CHANGELOG last.
7. `tests/test_plan_gate_hooks.py` and `tests/test_review_record_plan.py`: add the tests below.

## Testing strategy
Behavioral, hooks run for real in the existing `proj` fixture (copies `plan-lib.sh`, gates and recorder; `_approve(proj, files=...)` takes the Files text), each with `profile` None and `minimal`:
- `test_review_record_plan.py`: `parse_plan_files` ignores the marker for ticked and comma forms; `parse_plan_deletions` returns only marked paths; `plan-write` refuses 4 marked deletions (rc 8) and accepts 3; refuses a globbed marker; `plan-check --delete` rc 0 marked / 4 unmarked / 4 for a path not in `Files:` / still 2 on drift; old records without any marker keep authorising `--path` (regression).
- `test_plan_gate_hooks.py` (plan-gate): Write-to-empty on an existing T3 file blocked without a marker, allowed with one, non-empty Write unchanged, empty Write to a new file unaffected, deny-list path still blocked even if marked.
- `test_plan_gate_hooks.py` (Write-to-empty asserts `extract_json_field` reads `content`; shell-write-gate extras: `rm -rf build dist`, `rm src/x.pyc` and an ignored file allowed; a tracked file named with a quote, `;` or `$(...)` is blocked without injection; fixtures `git add` the file):
- `test_plan_gate_hooks.py` (shell-write-gate): `rm app.py`, `git rm app.py`, `unlink app.py`, `rm -f -- app.py`, a glob `rm *.py` blocked without the marker; allowed with it; `rm` of a non-T3 file (`notes.md`) and with no `.claude/plans` dir allowed; `rm .claude/settings.local.json` still blocked by the old check even with a marker; a marked 4th deletion cannot be recorded so is blocked; unparseable payload still fails closed.
- Removal: `python3 .claude/operations/scripts/project-graph.py impact` exits 2 (argparse) and `--help` lists no `impact`; the other `project-graph` tests (the files matching `tests/test_project_graph*.py`) pass.
- Text: none asserts rule 4; add no text-pinning test.

## Validation commands
```bash
python3 -m pytest tests/test_plan_gate_hooks.py tests/test_review_record_plan.py tests/test_project_graph*.py tests/test_hook_paths.py tests/test_structure.py -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
shellcheck .claude/hooks/plan-gate.sh .claude/hooks/plan-lib.sh
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
python3 scripts/check-context-floor.py --check
ck doctor --strict
```
`check-context-floor` guards CLAUDE.md size: the new rule 4 is about 20 characters longer than the old one; if the floor trips, shorten the wording, never raise the floor. `.agents/skills/codebase-mapping/SKILL.md` carries no `impact --ops` text (verified), so no mirror change is needed; still run `gen-registry.py --check` (and `gen-agents-mirror.py --check` if the script exists).

## Rollback plan
One commit per concern (parser+hooks+tests, impact removal, prose); revert the commit. `checkpoint-gate` snapshots Tier 3 edits (`git stash apply ck-checkpoint/<epoch>`). Records are unchanged by this plan (no new field), so a revert needs no migration.

## Risks
- Gate regression is the main risk: the new Bash check runs on every `rm`. Mitigation: it is inert without `.claude/plans`, skips unparseable/variable operands, and tests cover both a blocked and an allowed form per verb. A false block is recoverable by listing the path with `(delete)` in a new plan; there is no env escape hatch (by design).
- `plan-remove-ops-phase2.md` (many `(delete)` paths, recorded) can no longer be re-recorded; if it must be, split it. Its current record keeps working because `plan-check` without `--delete` ignores the marker.
- Untracked Tier 3 files removed by `rm` have no checkpoint (checkpoint-gate only sees Edit/Write) and nothing in git; stated in the CONSTITUTION text as "tracked files are recoverable from git".
- Scope is Tier 3 only; `.claude/**` and docs deletions (for example `.claude/agents/implementer.md`) are not gated, as before. If the owner wants them gated, that is a `plan-gate.globs` change (owner-only file), not this plan.
- Blast radius: `review-record.py` is imported by `src/claudekit/cli/flow.py:222` only through its CLI (`plan-check`, no `--delete`), so existing callers are unaffected. `project-graph hubs` was run: neither touched file is a hub.
- `tests/test_hook_paths.py` reads hook text (cwd-relative `.claude/` assignments; sourced libs must not define `SCRIPT_DIR`): keep new code in `plan-lib.sh`/`plan-gate.sh` clear of both; run it and `test_structure.py` in step 7.

## Code quality
Stdlib only, py3.9 (no `|` unions, use `typing`), bash 3.2-safe (`[ ]`, no associative arrays), ruff 100 cols, exit 2 + stderr for blocks, no new file, no new hook, no new registry entry.

Files:
  `CLAUDE.md`
  `AGENTS.md`
  `CHANGELOG.md`
  `.ai/SESSION_STATE.md`
  `.ai/KNOWLEDGE_BASE.md`
  `.ai/MEMORY.md`
  `.ai/SECURITY_GUIDE.md`
  `.ai/CHANGELOG_AI.md`
  `.claude/local/CONSTITUTION.template.md`
  `.claude/agents/_shared/planner-reference.md`
  `.claude/skills/codebase-mapping/SKILL.md`
  `.claude/hooks/plan-lib.sh`
  `.claude/hooks/plan-gate.sh`
  `.claude/hooks/shell-write-gate.py`
  `.claude/operations/scripts/review-record.py`
  `.claude/operations/scripts/project-graph.py`
  `.claude/operations/scripts/project_graph_render.py`
  `tests/test_plan_gate_hooks.py`
  `tests/test_review_record_plan.py`
  `tests/test_project_graph_impact.py` (delete)
