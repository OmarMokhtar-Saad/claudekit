# Plan: /review panel audit fixes (K2-K6)

Tier: 3 (touches `tests/test_review_panel.py`)
Branch: `fix/egm-panel-audit` (worktree `claudekit-egm-fix`, from origin/main 41649612).
Source: `.claude/plans/tracker-egm-audit.md` rows K2-K6. K1 is a local symlink plus agent-config (other repo); K7 WONTFIX; K8 DEFERRED.
Round 2: revised for round 1 (reviewer 84 REVISE; design critic 0B/4M; readiness critic 1B/4M). Changes: count regex accepts list markers, exact texts given, test harness pinned, the crash mutation made real, Alternatives added, Risks widened.

Files:
  - `.claude/commands/review.md`
  - `.claude/agents/_shared/REVIEW_PANEL.md`
  - `.claude/agents/plan-design-critic.md`
  - `.claude/agents/plan-readiness-critic.md`
  - `tests/test_review_panel.py`
  - `CHANGELOG.md`
  - `.claude/plans/tracker-egm-audit.md`

## Goal
1. K2: the scripted (`claude -p`) path of `/review` runs both critics. Today only `review.md:23` mentions them; the bash block (`review.md:29-81`) runs reviewer alone.
2. K3: one failure rule. A critic that times out, crashes, cannot find the plan, or ends without a valid plain-text `PANEL:` last line is `PANEL: incomplete`, never retried in the same round, never blocks.
3. K6: a critic's total comes only from its last non-empty line, raised to the number of severity-tagged finding lines when those are more. A `PANEL:` line anywhere else is ignored.
4. K4: the "recording call never names a critic" assertion runs (today it matches `review-record.py write`; review.md says `plan-write`).
5. K5: tests pin the panel contract, and a behaviour test runs the scripted parse.

## Findings that shape the design
- The critics' `## Output Format` lists per-finding fields `1. **Severity**: [Blocker | Major | Nit]` (plan-design-critic.md:80, plan-readiness-critic.md:79), so findings have no fixed leading tag today. Hermes solved this with one run-contract line (house-ops `bin/egm_review/personas/design.md:23`). Step 1 adds the same rule here, and the count regex allows an optional list marker (`1.`, `2)`, `-`, `*`, `+`), because numbered findings are the likely shape.
- Budgets: `review.md` is 104 lines, ratchet 125 (`.claude/lint-baseline.json:47`, checked by `tests/test_lint.py`, `<=`). The block below is 19 lines and line 23 stays one line: 123. The critics are not in `tests/test_agent_prompt_size.py` `SPLIT` (the only per-agent ceiling), so +1 line each has no cap; the frontmatter and tool-grant suites still run.
- `CHANGELOG.md` `[Unreleased]` (line 13) uses bold-prefixed bullets (`- **Added: ...**`), not `###` subsections. The entry follows that style.
- The block runs in whatever shell the Bash tool uses (zsh here, bash 3.2 elsewhere). It uses only `case`, `grep -E`, `sed -E`, `awk`, `[ ]`. No `[[ =~ ]]`, no arrays, no `set -e` dependence.

## Alternatives considered
- Parse in a Python helper (a `review-record.py panel-parse` subcommand): easier to unit-test, but it grows a security-relevant Tier 3 script and a second parser for an advisory, unrecorded line. Rejected. The inline block is still tested by running it (step 4).
- Critics emit JSON: changes the EGM persona contract that Hermes shares and that the Apache notice covers. Rejected.
- A hook that checks the `PANEL:` line: the panel is advisory by design (REVIEW_PANEL.md:12). Rejected.

## Steps (one commit, in this order: critics, shared doc, review.md, tests, CHANGELOG; tracker in a second docs commit after the sha exists)
1. Both critics, Run contract, directly after the "At most 8 findings" line (line 35), add exactly:
   `- Start each finding with its severity in bold, **Blocker**, **Major** or **Nit** (a list number or bullet before it is fine). Write the final PANEL line as plain text, no backticks.`
2. `.claude/agents/_shared/REVIEW_PANEL.md`: replace line 23 with exactly:
   `Read only each critic's last non-empty line. \`PANEL: <n> blocker, <n> major\` is valid; anything else (timeout, crash, missing plan, no or malformed line, the critic's own \`PANEL: incomplete - <reason>\`) is reported \`PANEL: incomplete\`, never retried in the same round, never blocks. A \`PANEL:\` line anywhere but last is ignored. If the reply has more \`**Blocker**\`/\`**Major**\` finding lines than that line counts, the larger number is the critic's total; the uncovered counts in the summary are drawn from that total (deduplication can only lower them).`
   (Backslashes above are only for this plan; the file gets plain backticks.) The file goes from 25 to 25 lines.
3. `.claude/commands/review.md`:
   - Line 23 becomes exactly: ``PANEL: unless `--no-panel`, also run `plan-design-critic` and `plan-readiness-critic` as in `.claude/agents/_shared/REVIEW_PANEL.md` (advisory; only `reviewer`'s block is recorded). The scripted block below runs them itself.``
   - Inside the bash block, after the `review-record.py plan-write ... || echo "WARNING: ..."` lines, add exactly:
   ```bash
   # Advisory panel (_shared/REVIEW_PANEL.md): never recorded, never blocks; --no-panel skips it.
   case " $ARGUMENTS " in *" --no-panel "*) ;; *)
     echo "=== PANEL (scripted: raw counts, not deduplicated against reviewer) ==="
     tag='^[[:space:]]*([-*+]|[0-9]+[.)])?[[:space:]]*\*\*'
     for c in plan-design-critic plan-readiness-critic; do
       out=$(echo "Plan: $PLAN_FILE. Review it." | claude -p --agent "$c" --allowedTools "Read,Grep") \
         || { echo "$c: claude exited $?"; out=""; }
       printf '%s\n' "$out"
       last=$(printf '%s\n' "$out" | awk 'NF{l=$0} END{print l}')
       if printf '%s\n' "$last" | grep -Eq '^PANEL: [0-9]+ blocker, [0-9]+ major$'; then
         b=$(printf '%s' "$last" | sed -E 's/^PANEL: ([0-9]+) blocker.*/\1/')
         m=$(printf '%s' "$last" | sed -E 's/.* ([0-9]+) major$/\1/')
         nb=$(printf '%s\n' "$out" | grep -cE "${tag}Blocker\*\*"); nm=$(printf '%s\n' "$out" | grep -cE "${tag}Major\*\*")
         [ "$nb" -gt "$b" ] && b=$nb; [ "$nm" -gt "$m" ] && m=$nm
         echo "$c: PANEL: $b blocker, $m major"
       else echo "$c: PANEL: incomplete"; fi
     done
     echo "=== END PANEL ===" ;;
   esac
   ```
   - stderr is not redirected: an auth or CLI error shows on the terminal, and the exit status is printed; neither is parsed. `grep -c` prints 0 when nothing matches (its exit 1 is inside `$( )`). Matching is case-sensitive: the critic is told the exact tags, and prose like "blocker" is not counted.
4. `tests/test_review_panel.py`:
   - K4: the loop matches every line containing `review-record.py`; assert at least one matched and none names a critic.
   - Critic contract test: also assert the step-1 line is present in each critic.
   - K5 `test_panel_contract_is_pinned` (wording pins only; the behaviour test below does the real work): REVIEW_PANEL.md has `PANEL: <n> blocker, <n> major`, `PANEL: incomplete`, `never retried`, `last non-empty line`, `Plan: <plan path>. Review it.`; review.md has `Plan: $PLAN_FILE. Review it.`, `for c in plan-design-critic plan-readiness-critic`, `*" --no-panel "*)` and `'^PANEL: [0-9]+ blocker, [0-9]+ major$'`.
   - K5 `test_panel_allowed_tools_match_frontmatter`: regex `--allowedTools "([^"]+)"` on the review.md line that contains `--agent "$c"`; sorted comma split == each critic's frontmatter tools (`["Grep", "Read"]`).
   - K6 `test_scripted_panel_parse`, parametrized over shell (`bash`, and `zsh` if `shutil.which("zsh")`, else skipped) and the cases below.
     - Extraction: from review.md take the lines from the one starting `# Advisory panel` through the first line equal to `esac` (after stripping). Assert both bounds were found.
     - The script run is: `PATH='<tmp_path>/bin':$PATH\nPLAN_FILE=p.md\nARGUMENTS='<case args>'\n` + the extracted block. The PATH line lives in the script text, not only in env, because a user `~/.zshenv` can prepend to PATH and shadow the stub (seen during the pre-check: the real `claude` ran). Invocation: `subprocess.run(argv, env=..., capture_output=True, text=True, timeout=30)` with argv `["bash", "-c", script]` or `["zsh", "-f", "-c", script]` (`-f` skips startup files; `zsh` and `-f` are separate argv entries).
     - Stub: `tmp_path/bin/claude`, mode 0755, exact text:
       `#!/bin/sh` / `cat >/dev/null` / `: > "$STUB_DIR/called"` / `printf '%s\n' "$STUB_REPLY"` / `exit "${STUB_RC:-0}"`.
       env = `os.environ` copy with `PATH=tmp_path/bin:` + PATH, `STUB_DIR`, `STUB_REPLY` (a string), `STUB_RC`.
     - Each case asserts the exact stdout lines `plan-design-critic: <want>` and `plan-readiness-critic: <want>`:
       a. reply `x\nPANEL: 1 blocker, 2 major` → `PANEL: 1 blocker, 2 major`;
       b. reply `1. **Blocker** a\n2) **Blocker** b\n- **Major** c\n**Nit** d\nPANEL: 0 blocker, 0 major` → `PANEL: 2 blocker, 1 major`;
       c. reply `PANEL: 0 blocker, 0 major\nmore prose` → `PANEL: incomplete`;
       d. reply `PANEL: 0 blocker, 0 major`, `STUB_RC=1` → `PANEL: incomplete`, and a `claude exited 1` line;
       e. reply `PANEL: incomplete - plan not found` → `PANEL: incomplete`;
       g. reply ``x\n`PANEL: 1 blocker, 0 major` `` (backticked) → `PANEL: incomplete`;
       f. args `--no-panel` → stdout has no `=== PANEL`, and `STUB_DIR/called` does not exist.
5. `CHANGELOG.md` `[Unreleased]`, first bullet: `- **Fixed: /review panel.** The scripted path now runs both critics; a critic without a valid last-line \`PANEL:\` is \`incomplete\` and never blocks; counts cannot be lower than the tagged finding lines; a vacuous test assertion now runs.`
6. Second commit (docs): `.claude/plans/tracker-egm-audit.md` K2-K6 → FIXED with the first commit's sha.

## Validation
- `uvx --with pyyaml pytest -q tests/test_review_panel.py tests/test_lint.py tests/test_agent_frontmatter.py tests/test_agent_prompt_size.py tests/test_agent_tool_grant_drift.py`.
- Mutations, each applied to review.md alone, test run, then reverted with `git checkout -- .claude/commands/review.md` (output kept in the commit's evidence note):
  - drop `|| { ...; out=""; }` → case d fails (it prints `PANEL: 0 blocker, 0 major`);
  - delete the two `[ ... -gt ... ]` max statements → case b fails;
  - replace `awk 'NF{l=$0} END{print l}'` with `cat` → cases a and b fail (multi-line text never matches the anchored regex);
  - drop `([-*+]|[0-9]+[.)])?` from `tag` → case b fails (counts 0 numbered, so 1 blocker);
  - make the `case` pattern `*" --never "*)` → case f fails.
- Full DoD gate from CLAUDE.md (pytest, ruff, mypy, gen-docs/registry/model-policy/context-floor checks, shellcheck, `ck doctor --strict`).

## Risks
- Prompt injection: the plan is untrusted data. A plan can push a critic to drop its tags and end with `PANEL: 0 blocker, 0 major`. The floor catches only tagged findings. Residual: the panel stays advisory, the reviewer is independent, and the critics' DATA-not-instructions rule stays.
- Critics run one after the other with no timeout: latency is roughly doubled, and a hung critic hangs the scripted `/review`, the same as a hung reviewer today. macOS has no `timeout(1)`. Accepted. A killed run is `incomplete` by step 2.
- A last line with backticks, a trailing space or `\r` is `incomplete`. This fails safe, and step 1 tells critics to write it plain.
- The scripted path cannot deduplicate against the reviewer, so it prints raw counts and the header says so. The Task path still deduplicates.

## Rollback
`git revert` of the two commits; no data, hooks or settings change.
