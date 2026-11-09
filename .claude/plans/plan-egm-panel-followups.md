# Plan: /review panel follow-ups (tag-first Output Format, safe $ARGUMENTS, real-CLI smoke)
Round: 2

Tier: 3 (touches `tests/test_review_panel.py`)
Branch: `fix/egm-panel-audit` (worktree `claudekit-egm-fix`), on top of 4fefe89b / e91f8ef7.
Source: `.claude/plans/tracker-egm-audit.md` "Follow-ups" 1-3.

Files:
  - `.claude/agents/plan-design-critic.md`
  - `.claude/agents/plan-readiness-critic.md`
  - `.claude/commands/review.md`
  - `tests/test_review_panel.py`
  - `CHANGELOG.md`
  - `.claude/plans/tracker-egm-audit.md`

## Why

1. **Output Format contradicts the run contract.** Both critics' run contract (line 36 in both)
   says "Start each finding with its severity in bold, **Blocker**, **Major** or **Nit**", but their
   `# Output Format` (`plan-design-critic.md:80-83`, `plan-readiness-critic.md:79-82`) says
   `1. **Severity**: [Blocker | Major | Nit]`. A critic following the second writes `**Severity**: Major`,
   which the scripted count (`tag` regex, review.md:85) does not count, so the count floor (K6) misses it.
2. **`$ARGUMENTS` is pasted as text** into `case " $ARGUMENTS " in` (review.md:82). Args containing `"` break
   the shell; args containing `$(...)` or backticks run as a command inside the double quotes.
3. **No real-CLI run** of `claude -p --agent <critic> --allowedTools "Read,Grep"`: every test uses a stub.

## Alternatives

- Count `**Severity**: X` in the regex too — rejected: keeps two formats; the persona should match its own
  contract.
- Escape `$ARGUMENTS` by instruction to the model — rejected: the substitution is done by the harness, not the
  model. A quoted heredoc takes the text literally (no expansion, no quote parsing).
- Pass args via an env var — not available: the harness only substitutes text into the command prompt
  (verified by the argecho probe in section 4, not assumed).
- Pass args through a file the model writes — rejected: the model would need a Write step with the same
  quoting problem, and /review's allowed tools stay minimal.

Threat model: `/review` args are typed by the session's own user, who can already run any shell command.
This is a robustness fix (a `"` or `$(` in args must not break or alter the panel), not a security boundary.
The heredoc is therefore a full fix for quotes/`$`/backticks and a documented partial fix for one input:
an argument line that is exactly the delimiter. The delimiter is made unguessable-by-accident
(`CK_REVIEW_ARGS_EOF_7f3a9c`); a per-run random delimiter is impossible because the text is substituted
before any shell runs.

## Change

### 1. Output Format (both critics)

`plan-design-critic.md`: replace the 4 lines under `#### IF Mode: REVIEW`, from the anchor
`For each finding, include:` through the anchor line starting `3. **Finding & Recommendation**:` (verified
today at :80-83; design and readiness differ by one line, so edit by anchor, not number) with:

```
For each finding, write one block whose first line starts with the severity tag in bold, exactly
`**Blocker**`, `**Major**` or `**Nit**` (a list number or bullet before it is fine), then:
- **Affected Scope**: File path, line numbers, or architecture subsystem affected.
- **Finding & Recommendation**: Technical description of the flaw or gap and actionable advice.
Do not add a separate Severity field; the leading tag itself is what is counted.
```

`plan-readiness-critic.md`: the same, with its own labels kept:
`- **Affected Scope**: Implementation task item, affected files, or line numbers.` and
`- **Finding & Guidance**: Concrete technical explanation of the implementation hurdle.`

In the NOTICE header comment (two lines, :18-19), edit by the substring
`added the claudekit run contract below.` (followed on the same line by ` See ...`); change that substring to `added the claudekit run contract below, Output Format writes the severity as the
leading tag.` (both critics, same anchor).

### 2. `$ARGUMENTS` read through a quoted heredoc (review.md)

Directly after the line that is exactly
`# Advisory panel (_shared/REVIEW_PANEL.md): never recorded, never blocks; --no-panel skips it.` (today :81), insert:

```bash
# Args arrive as raw text; a quoted heredoc keeps quotes, $ and backticks literal.
# Limit: an argument line that is exactly the delimiter ends it early.
CK_ARGS=
IFS= read -r -d '' CK_ARGS <<'CK_REVIEW_ARGS_EOF_7f3a9c' || :
$ARGUMENTS
CK_REVIEW_ARGS_EOF_7f3a9c
CK_ARGS=$(printf '%s' "$CK_ARGS" | tr '\n' ' ')
```

and change `case " $ARGUMENTS " in` to `case " $CK_ARGS " in`. `read -d ''` hits EOF and returns 1 by design,
hence `|| :`. `:` always returns 0, so the list succeeds even under `set -e` (the block does not set it;
the model's Bash tool may). Trailing newline: the heredoc's final newline becomes a trailing space in `CK_ARGS`;
harmless, since the `case` pads with spaces anyway. The `tr` folds a multi-line arg so `*" --no-panel "*` still matches at a line end.
Why not `CK_ARGS=$(cat <<'EOF' ...)`: macOS `/bin/bash` 3.2 mis-parses a heredoc body inside `$(...)` that
holds an unbalanced `"` (verified 2026-11-09: "unexpected EOF while looking for matching"). The `read` form
was run on the case-i payload plus `)`, `(`, `'`, `\` and a second line under `/bin/bash` 3.2.57, Homebrew
bash, `zsh -f` and `/bin/sh`: all four kept the text literal, matched `--no-panel`, created no file.

`grep -n ARGUMENTS .claude/commands/review.md` today shows exactly one hit (:82, the `case` line), so the
test's `.replace` touches only the heredoc body. The implementation re-runs that grep; after the change the
only hit must be the heredoc body line.

### 3. Tests (`tests/test_review_panel.py`)

- Harness: the run call becomes exactly
  `subprocess.run(argv + [script], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)`
  (`cwd=tmp_path` is new, so `pwned` lands where the test looks). The test now mimics the harness's text substitution instead of setting a shell variable:
  `script = "PATH='%s':$PATH\nPLAN_FILE=p.md\n" % bindir + _panel_block().replace("$ARGUMENTS", args)`
  (the `ARGUMENTS='%s'` assignment is removed).
- SHELLS becomes a list of `(id, argv)` tuples, `ids=lambda s: s[0]`, the test unpacks `_, argv = shell`:
  `("bash", ["bash", "-c"])` always; `("zsh", ["zsh", "-f", "-c"])` only if `shutil.which("zsh")`;
  `("sysbash", ["/bin/bash", "-c"])` only if `/bin/bash` exists and `os.path.realpath("/bin/bash") !=
  os.path.realpath(shutil.which("bash"))`. Rows not added are absent (not skipped). On Linux CI `/bin/bash`
  is usually the PATH bash, so sysbash is a no-op there; on macOS it is bash 3.2 (hard rule 8).
- New CASES rows:
  - `("i", 'x" $(touch pwned) `touch pwned2`', "PANEL: 0 blocker, 0 major", 0, "PANEL: 0 blocker, 0 major")`.
    `subprocess.run(..., cwd=tmp_path)`; for case i also assert `not (tmp_path / "pwned").exists()` and
    `pwned2` likewise. `touch` is not shadowed (bindir holds only the `claude` stub). Two assertions bind two
    regressions: restoring `case " $ARGUMENTS "` gives a shell syntax error, so the PANEL-line assertion fails
    (the file check alone would not catch it); an unquoted delimiter runs `$(touch pwned)`, so the file check
    fails.
  - Empty `$ARGUMENTS`: cases a-e, g, h already substitute `""` (an empty heredoc body line); they are the
    empty-args rows. No new row.
  - `("m", "CK_REVIEW_ARGS_EOF_7f3a9c", "PANEL: 0 blocker, 0 major", 0, "PANEL: 0 blocker, 0 major")`: pins the
    documented limit. The arg line closes the heredoc early; the real delimiter line then runs as an unknown
    command (stderr only); the panel still runs and parses. If the limit ever breaks the panel, m fails.
  - Former case j dropped: it duplicated case f (`--no-panel`) and could not fail.
  - `("l", "plan.md\n--no-panel", "PANEL: 9 blocker, 9 major", 0, None)` (real newline): defensive guard that
    the `tr` fold keeps a line-end `--no-panel` matching. Whether the harness ever substitutes a real newline is
    unverified.
  - Former case k dropped: the tag regex already counts `1. **Major**` (case b); it bound nothing.
- `test_critic_contract` (per critic) is the real regression test for section 1: slice
  `sec = body.split("\n# Output Format\n", 1)[1].split("\n## Target Standard", 1)[0]` (assert both anchors
  exist). Assert `"**Severity**" not in sec` (any spacing or form), and `sec` contains `` `**Blocker**` ``,
  `` `**Major**` `` and `` `**Nit**` `` (the run contract sits above the slice, so it cannot satisfy this).
  Fails today.
- `test_review_command_reads_args_through_quoted_heredoc`: structural guard only; review.md contains
  `<<'CK_REVIEW_ARGS_EOF_7f3a9c'` and no `case " $ARGUMENTS "`. Case i is the behavioural test.

Run: `uvx --with pyyaml pytest -q -p no:cacheprovider tests/test_review_panel.py` (every SHELLS row present).
Then the full suite as ck-bg job: `uvx --with pyyaml --with jsonschema --with-editable . pytest -q -p no:cacheprovider`,
plus the CLAUDE.md DoD gates: `ruff check src/ tests/ scripts/ .claude/operations/scripts/`,
`python3 scripts/gen-registry.py --check`, `python3 scripts/gen-docs.py --check`. If a registry/hash gate
drifts because agent bodies changed, regenerate with the same script without `--check` and commit it.

Mutations (each must fail the named IDs, in every shell row): restore `case " $ARGUMENTS "` ->
`test_scripted_panel_parse[i-bash]`, `[i-zsh]`, and `[i-sysbash]` where that row exists, fail; unquote the delimiter
(`<<CK_REVIEW_ARGS_EOF_7f3a9c`) -> the same IDs fail (pwned created); drop the `tr` fold -> `[l-*]` fail;
restore `1. **Severity**: [Blocker | Major | Nit]` in one critic -> `test_critic_contract[<critic>]` fails.
Revert each with `git checkout -- <file>` after recording the failure.

### 4. Real-CLI smoke (validation, not a test)

`--agent` resolves against the cwd's `.claude/agents/`, so every run is from the scratch dir.
`S=$SCRATCH/smoke; mkdir -p $S/.claude/plans $S/.claude/commands && cp -R .claude/agents $S/.claude/ && git -C $S init -q`.
Plan `$S/.claude/plans/plan-smoke.md`: 10 lines, one planted defect (step 3 "update the auth service", no
file, no test).

a. Per critic, exactly the scripted loop's call:
   `(cd $S && echo "Plan: .claude/plans/plan-smoke.md. Review it." | claude -p --agent <critic> --allowedTools "Read,Grep") > $S/<critic>.out`.
   Checks (commands, results recorded):
   `awk 'NF{l=$0} END{print l}' $S/<critic>.out | grep -Ex 'PANEL: [0-9]+ blocker, [0-9]+ major'`;
   `grep -cE '^[[:space:]]*([-*+]|[0-9]+[.)])?[[:space:]]*\*\*(Blocker|Major|Nit)\*\*' $S/<critic>.out` >= 1;
   `grep -c '\*\*Severity\*\*:' $S/<critic>.out` = 0;
   `grep -ci 'auth' $S/<critic>.out` >= 1 (planted defect flagged; reported, not a gate).
b. argecho probe, by bytes on disk, not by model reply. `$S/.claude/commands/argecho.md` holds one bash
   block: review.md's heredoc lines verbatim, then `printf '%s' "$CK_ARGS" > argecho.out`, and the instruction
   "Run the bash block exactly as written with the Bash tool; reply done." Run
   `(cd $S && claude -p --model haiku --allowedTools Bash '/argecho x" $(touch pwned) `z`')`.
   Pass = `argecho.out` bytes equal `x" $(touch pwned) `z` ` (trailing space from the fold) and `$S/pwned` is
   absent. This is the real path (harness substitutes, model runs the block). If the model alters the block,
   re-run once; two failures count as a (b) failure.

Cost: about $0.50. Failure policy: the (a) checks are non-gating, reported only. A failed (a) check does not block the commit (the tests prove the code);
the tracker marks follow-up 3 "smoke FAILED: <check>" with the output path and the final report says so.
A failed (b) blocks the commit: case i would be testing the wrong substitution; re-plan case i first.

### 5. CHANGELOG + tracker

CHANGELOG `Unreleased` / Fixed: "/review: critic Output Format writes the severity as the leading tag;
`$ARGUMENTS` read through a quoted heredoc (no shell break or command run on quotes/`$(...)` in args)."
Tracker: follow-ups 1-3 marked done with the commit sha and the smoke result.

## Risks

- `read -d ''` + quoted heredoc verified under bash 3.2, bash 5, zsh, sh (section 2); all test shells run it.
- A model may still write `**Severity**:`; the count floor then simply does not raise the count (today's
  behaviour) — never lowers it.
- Smoke costs about $0.50 (two sonnet critic calls).

## Rollback

Revert the commit; no state.
