# Implementation Plan A: Day-One Blockers (shipped config only)

> **Revision 3 — narrowed by owner decision.** Rounds 1 and 2 bundled "fix the day-one
> blockers" with "rewrite command segmentation in the security module". The parsing rewrite
> twice moved a hole rather than closing it, so it is now a separate project:
> [`plan-validator-segmentation.md`](plan-validator-segmentation.md) (**Plan B**, not to be
> executed in this session). **This plan changes no code in
> `src/claudekit/security/command_validator.py`.**
>
> This document contains no bare secret literal — rounds 1 and 2 did, so committing the plan
> tripped the very bug it fixes. Key headers are written `PRIVATE[ ]KEY`.

## Overview

A user who runs `./install.sh <project> --full` on a fresh Python project cannot make their
first commit. Two independent causes, both in **shipped configuration and content**, neither
requiring a validator change:

1. `templates/python/config.env` ships `BUILD_CMD="pip install -e ."`. `pip` is not in
   `DEFAULT_ALLOWLIST`, and `pre-commit.sh` *executes* `build_cmd`, so the blocking hook
   returns 1 on any staged `src/*.py`.
2. The secrets scanner matches its own pattern definitions, so committing `.claude/` — which
   the installer places in the user's repo — is unconditionally blocked, and the failure
   message forbids `--no-verify`.

Tier 3 (the secrets scanner is a security control).

## Scope

- **In scope:** `templates/python/config.env`; the secrets-pattern fix across all six shipped
  files that self-match; `tests/test_doctor_gate.py`; a new behavioral test module; CHANGELOG.
- **Out of scope:**
  - **`command_validator.py` — untouched.** Everything that needed it moved to Plan B.
  - `install.sh` (parallel workstream). This plan fixes the *inputs* the installer copies.
    Consequence: tests assert the *shape* of the installed `build_cmd`, not byte equality with
    the template, because exact rendering/escaping is install.sh's business.
  - `.claude/agents/gitOps.md` — its regex form (`(RSA |EC |DSA )?PRIVATE KEY`) genuinely
    cannot match the five literals. Confirmed twice.
  - The pre-existing `config.json` / `.example` / `*.lock` skip in `check_secrets`.

## Audit: all ten templates vs. the validator (unchanged by this plan)

**40 non-empty commands, 19 rejected.** (Rounds 1–2 of this plan said "36 / 18"; that was my
arithmetic error, corrected here by recount.)

| Language | BUILD | TEST | LINT | COVERAGE |
|---|---|---|---|---|
| csharp | PASS | PASS | PASS | PASS |
| generic | (empty) | (empty) | (empty) | (empty) |
| go | PASS | PASS | **FAIL** `golangci-lint` | PASS |
| java | **FAIL** `gradlew` | **FAIL** | **FAIL** | **FAIL** |
| kotlin | **FAIL** `gradlew` | **FAIL** | **FAIL** | **FAIL** |
| php | PASS | PASS | **FAIL** `php-cs-fixer` | **FAIL** base parsed as `XDEBUG_MODE=coverage` |
| python | **FAIL** `pip` → **fixed here** | PASS | PASS | PASS |
| ruby | PASS | **FAIL** pattern (`exec`) | **FAIL** (`exec`) | **FAIL** (`exec`) |
| rust | PASS | PASS | PASS | PASS |
| swift | **FAIL** `swift` | **FAIL** | **FAIL** `swiftlint` | **FAIL** |
| typescript | PASS | PASS | PASS | PASS |

### Which languages remain blocked after Plan A

**Plan A fixes exactly one of the 19: `python` BUILD_CMD.** The other **18 stay blocked**, and
a blocked command means `pre-commit`, `pre-push` and `post-implement` refuse to run that
language's configured gate:

| Language | Still-blocked commands | Needs |
|---|---|---|
| go | LINT | allowlist `golangci-lint` |
| java | BUILD, TEST, LINT, COVERAGE | allowlist `gradlew`/`gradle` |
| kotlin | BUILD, TEST, LINT, COVERAGE | allowlist `gradlew`/`gradle` |
| php | LINT, COVERAGE | allowlist `php-cs-fixer`; env-prefix parsing |
| ruby | TEST, LINT, COVERAGE | `bundle exec` vs the shell-builtin `exec` regex |
| swift | BUILD, TEST, LINT, COVERAGE | allowlist `swift`, `swiftlint` |

All 18 are unblocked by **Plan B**, and every one is bound here by an `xfail(strict=True)`
case in `STILL_BLOCKED`, so when Plan B lands they flip to XPASS and fail the suite — the
signal to delete them. `test_the_blocked_set_is_not_silently_growing` makes the set a ratchet:
entries may leave, never join.

### The Python build command

`python3 -m compileall -q -x '(^|/)(\.venv|venv|env|\.tox|\.direnv|\.git|\.claude|build|dist|node_modules|site-packages)/' .`

- Passes the **unmodified** validator (`python3` is already allowlisted) — verified.
- **Not "non-mutating".** `compileall` writes `__pycache__` by design, so a commit produces
  untracked files in a repo that does not ignore them, and it errors on a read-only checkout.
  The property that matters is that it **installs nothing** — hence the renamed test,
  `test_build_cmd_does_not_install_packages`.
- Scoped to `.`, not `src`: verified that `compileall -q src` on a project with no `src/`
  prints "Can't list 'src'" and **exits 0** — a green no-op. `compileall -q .` exits 1 on the
  same syntax error and 0 on a clean tree.
- `-x` now also excludes `\.git` and `\.claude` (added this round). Verified: with a Python-2
  style file under `.claude/hooks/` the exclusion holds and the tree exits 0.

#### The remaining false-positive class, and why `.` is still the right default

**Measured:** in a tree containing one pre-existing unparseable `.py` outside the excluded
directories, this command **exits 1** and the first commit is blocked. Python-2 leftovers,
deliberate syntax-error test fixtures, and templated `.py` files all trigger it.
`test_source_commit_is_not_blocked` cannot surface it, because that fixture tree holds only
`src/app.py`. (The separate concern that ClaudeKit's own shipped `.py` files might not parse on
an older user interpreter did **not** reproduce on the reviewer's interpreter — exit was 0 —
so it is recorded as a risk for users on interpreters older than our files target, not as a
measured failure. The new `\.claude` exclusion removes it either way.)

**I considered the alternatives and none is better:**

| Option | Why not |
|---|---|
| `compileall -q src` | The original silent-pass bug: **exits 0** when `src/` is absent, which is the common flat layout. Trades a loud false positive for a silent false negative — strictly worse for a gate. |
| Compile only staged files (`git diff --cached … \| xargs python3 -m compileall`) | Correct in principle and the behaviour we actually want, but `xargs` is deliberately **not** allowlisted (it smuggles arbitrary payloads), so the screen rejects it. `build_cmd` is one static string with no access to the staged list. |
| `python3 -m compileall -q $(git diff --cached --name-only)` | With no staged `.py`, `compileall` receives **no arguments and compiles `sys.path`** — far worse. |
| Empty `BUILD_CMD` | Restores the `generic` template's honest "no gate configured", but ships Python users no build check at all. |

**Decision, and it is an owner-visible trade-off rather than an oversight:** keep `.`. A gate
that fails loudly on a genuinely unparseable file in the user's own tree is defensible and
actionable; one that reports success while checking nothing is not. The escape hatch is
first-class and documented in the CHANGELOG entry — override `project.build_cmd` in
`.claude/hooks/config.json`, which is the same knob the hook already reads. If the owner
prefers the quieter default, the one-line change is to ship `BUILD_CMD=""` for python and let
users opt in; say so and I will flip it.

## Threat model for the secrets-scanner fix

**Control:** `check_secrets()` greps each staged blob against 13 patterns; any hit fails the
commit, and `block-no-verify` removes the `--no-verify` escape.

**Bug:** five patterns are stored as bare literals, so the hook matches itself. Same self-match
in `.claude/agents/opensource-sanitizer.md` and both copies of the `insecure-defaults` SKILL.md
(which document a literal password and API-key assignment as examples of what *not* to do).

**Rejected — skip the file or a region.** That creates a named hiding place: a real key pasted
into that file ships silently.

**Chosen — make the literal not appear.** Write each pattern with a bracketed space
(`PRIVATE[ ]KEY`). Under `grep -iE`, `[ ]` matches exactly one space, so detection is
byte-for-byte identical, while the file's own text no longer matches. Every file, including the
hook itself, is still scanned in full. Verified; upheld under three rounds of attack.

**Honest limits.** `pre-commit.sh:167-172` **already** skips `*.lock`, images/fonts/pdf and any
path ending `config.json`, `config.template` or `.example`. A real key in `config.json` ships
silently today. This plan adds **no new exclusion** and does not close that one; it is
disclosed in the CHANGELOG and bound by `xfail(strict=True)`.

### FINDING 1 (found by this plan's own tests, during execution): the scanner could not
detect any credential VALUE

Plan A executed cleanly, then `test_real_api_key_in_a_shipped_markdown_file_is_caught`
failed with returncode 0. The test was right and the control was wrong. Measured on a fresh
`--full` install: a real `api_key` assignment appended to a shipped SKILL.md, staged, and
`pre-commit.sh` **exits 0** and logs "No secrets detected in staged files".

Three compounding causes, all verified by execution:

1. `pre-commit.sh` **never sources `lib.sh`** (verified: the file has no `source`/`.` line),
   so `ERE_QUOTE_CLASS` / `ERE_NOT_QUOTE_CLASS` are always unset there and the inline `${:-}`
   defaults always apply.
2. Those defaults are syntactically broken: a `'` inside a double-quoted `${:-}` default opens
   a single-quote context. Running the two lines standalone, bash prints
   `bad substitution: no closing '}'`; the statements merge and the negated-quote class ends
   up **empty**.
3. The pattern the hook actually ran, from `bash -x` on the live hook, was
   `api_key\s*[:=]\s*["']{8}` — **eight consecutive quote characters**, which no real
   credential matches.

**Blast radius, measured rather than reasoned:** I planted one real credential for each of the
seven value-bearing patterns in a fixture install and ran the shipped hook — **0 of 7 were
detected.** The only detections were the hook's own five `PRIVATE KEY` self-matches (the bug
Plan A already fixes). Those five and `private_key` use no `${nq}`, which is exactly why the
self-matching bug was visible and this one was not. `private_key` was also degraded but in the
other direction — it collapsed to `private_key\s*[:=]\s*` with no quote requirement, so it
is **over-broad**, firing on any `private_key =` line. Both mirrors are affected.

**Fix.** Build the defaults with no quote inside an expansion:

```bash
local q="${ERE_QUOTE_CLASS:-}"
if [ -z "$q" ]; then q='["'"'"']'; fi
```

`if` rather than `[ -z … ] && …` deliberately: this file runs under `set -e`, and while the
`&&` form happens to be exempt in current bash, the `if` form is unambiguously safe on bash 3.2
and needs no reasoning about `set -e` exemptions to review.

**`lib.sh` decision, stated because it was asked:** leave `lib.sh` unchanged and do **not**
export these. The hook does not source it, so exporting would change nothing here; and the
repaired defaults are correct standalone, which is the property that matters for a blocking
hook. Widening the coupling — making a blocking hook depend on sourcing a shared library for
its security ruleset to be correct — is the failure mode that produced this defect. Other
hooks that *do* source `lib.sh` continue to get the shared values. Verified after the fix:
the emitted pattern is `api_key\s*[:=]\s*["'][^"']{8}` and planted `api_key`, `password` and
`access_token` credentials are all detected.

### FINDING 2: the repo-scan test walked the filesystem, not the index

`test_no_committed_file_matches_a_live_pattern` failed on `.claude/hooks/hooks.log` — untracked
and gitignored — which had recorded an earlier run's own scanner test. A test whose name asserts
it checks *committed* files was walking the working tree. Any log that records command text
matches a secret pattern the moment someone tests the scanner, so this self-poisons
indefinitely. Enumeration now goes through `git ls-files` (the index), with `SCAN_ROOTS` and the
hook's own skip set applied as filters on top, plus a regression test that a gitignored file
holding a pattern is invisible to the enumeration.

### The plan's own artifacts

`.claude/plans/` is **not** gitignored and 18 ops configs are committed under
`archive/` — the coordinator's `git add -A` already swept a previous revision of this ops.json
into a commit. So "the operator does not stage the ops.json" (revision 2's answer) was not a
control at all. Fixed properly: **every `find` anchor in the ops config is chosen so it cannot
match a live pattern** — `RSA PRIVATE KEY'` carries no `BEGIN`, so no pattern matches it, and
the SKILL.md anchors survive because JSON escapes the quote (`\"admin123\"`), breaking the
`= "` adjacency the pattern needs. `.claude/plans` is therefore **in** `SCAN_ROOTS`, and the
staging convention is deleted. Verified: scanning both artifacts with all 13 live patterns
yields zero hits.

## Implementation Steps

1. `templates/python/config.env` — BUILD_CMD.
2. `.claude/hooks/pre-commit.sh` — 5 pattern literals (one edit each, `BEGIN`-free anchors),
   an explanatory comment, and a failure message that names a sanctioned way forward.
   The comment is inserted with `add_after` whose payload **begins with a leading `\n`**, so
   it lands as a blank line then the comment block, inside the `patterns=( … )` array. That
   separation is **deliberate**, for two reasons: the leading newline is required by the ops
   engine's `add_after` contract (without it the payload concatenates onto the anchor line,
   corrupting the `private_key` pattern), and a blank line before a comment block is ordinary
   shell formatting. It is inert — bash ignores it, and `_scanner_patterns()` filters blank
   and `#` lines before using the array.
3. `.codex/hooks/pre-commit.sh` — same literal fix.
4. `.claude/agents/opensource-sanitizer.md` + `.codex/agents/opensource-sanitizer.toml`.
5. `.claude/skills/insecure-defaults/SKILL.md` + `.agents/skills/insecure-defaults/SKILL.md`.
6. `tests/test_doctor_gate.py` — bind `templates/*/config.env`, rename to
   `test_build_cmd_does_not_install_packages`.
7. `tests/test_day_one_blockers.py` — new.
8. `CHANGELOG.md` — two edits, because `[Unreleased]` already contains **both** a
   `### Security` and a `### Fixed` H3, in that order. The new bullets are **prepended to the
   existing `### Fixed` block** (anchored on its first bullet), and `### Known limitation` is
   inserted as a single new H3 **after** that block, immediately before `### Changed`. An
   earlier revision anchored on `## [Unreleased]\n\n### Security` and emitted its own
   `### Fixed`, which would have produced a duplicate H3 and inverted the section order —
   nothing gates that (`tests/test_structure.py:171` only checks a heading exists), so it
   would have shipped silently.

## Testing Strategy

Fixtures use `tempfile.mkdtemp(dir=REPO.parent)` — **never `$TMPDIR`**: `ops-enforcement.sh:43`
exempts `/private/tmp/claude-*`, `/tmp/claude-*` and `/var/folders/*` (what macOS `$TMPDIR`
resolves to), so a fixture there makes hooks exit 0 and assertions pass silently.

- **`TestTemplateCommandsSurviveTheScreen`** — all 40 commands through the `check-command` CLI;
  the 18 in `STILL_BLOCKED` are `xfail(strict=True)`. `test_every_template_command_is_discovered`
  asserts **exactly 40**, not `>= 30`: a parser regression that silently dropped nine commands
  would otherwise pass while those commands stopped being screened. The ratchet is a
  **membership** check (`STILL_BLOCKED <= _BASELINE_BLOCKED`), not a headcount — a cardinality
  cap would let a newly blocked command take the place of one Plan B unblocks, which is exactly
  what the guard exists to prevent.
  *Mutant:* restore `pip install -e .` → `python-BUILD_CMD` flips.
  *Mutant:* land Plan B → 18 XPASS, suite fails until the set is emptied.
- **`TestFreshInstallFirstCommit`** — the fixture writes `pyproject.toml` **before** install and
  passes `--language python`. Revision 2's fixture installed into an empty dir, so
  `detect_language()` returned `generic`, whose commands are empty, so `run_build()` returned 0
  before screening and the headline test passed *with the bug present*. It was vacuous.
  - `test_installed_build_cmd_is_the_python_template_command` — non-empty, contains
    `compileall`, no `pip install`. *Mutant:* drop `--language` → flips.
  - `test_source_commit_is_not_blocked` — **exit 0**. *Mutant:* restore `pip install -e .` →
    exit 1.
  - `test_build_cmd_screen_actually_ran_against_the_source_under_test` — three-part: the hooks
    **log** contains `running build:`, does not contain `unscreened` (the rc=127 fallback that
    executes `build_cmd` *without* screening), and a `claudekit` shim marker exists. The shim
    is required because `pre-commit.sh:45` prefers a console script on `PATH`, so on a machine
    with claudekit pip-installed the hook would screen an installed wheel rather than this
    working tree. *Mutant:* remove the shim → marker missing, flips.
  - `test_shipped_build_cmd_catches_a_syntax_error_in_a_flat_layout` — runs the **installed**
    command against `pkg/bad.py` with no `src/`; asserts nonzero. *Mutant:* revert to
    `compileall -q src` → exits 0, flips. This is what distinguishes a gate from a green no-op.
- **`TestSecretPatternConstruction`** (new) — extracts the hook's own pattern-construction
  block, runs it, and asserts on the **built pattern strings** for both mirrors: no shell
  error on stderr, each of the seven value-bearing patterns contains the negated quote class
  followed by a repetition count, and `private_key` still requires a quote. Asserting on
  construction rather than only on behaviour is the point — construction is what broke, and a
  re-implemented copy of the logic in the test would have been just as broken and just as
  green. **Verified: 0/9 of these assertions pass against the shipped hook, 9/9 against the
  fix.**
- **`TestSelfScanIsClean`** — stage the three shipped files, assert **exit 0**; plus a repo scan
  with **all 13 live patterns** (read out of the hook, comment lines filtered) over
  `SCAN_ROOTS` including `tests` and `.claude/plans`. The post-filter mirrors the hook's own
  skip set (`pre-commit.sh:167-172`) exactly, guarded by `test_skip_mirror_matches_the_hook`:
  an independently written list would be *stricter than the control it mirrors* and could red
  on a binary extension the hook would never flag. `SCAN_ROOTS` is scoped to what this plan is
  responsible for, not the whole repo — `review/` and `docs/` are committed but out of scope,
  and `review/tasks/003-fix-hook-bugs-and-fail-closed.md:49` already contains a line matching a
  live pattern, so adding `review` would red the suite for a pre-existing, unrelated reason.
  Recorded as a follow-up rather than silently omitted. Revision 2 scanned only the five
  private-key patterns and excluded `tests/`, which is why its own test module — containing
  `api_key` `=` `"` followed by eight non-quote characters — self-matched undetected. BSD
  `grep -E` on macOS honours `\s`, so that fired locally, not only in CI.
  *Mutant:* revert any one literal, or any one SKILL.md row in either copy → flips.
- **`TestRealSecretIsStillCaught`** — *the test that matters.* Plant a real RSA header **into
  the hook itself**, and an `api_key` literal into the shipped SKILL.md: **exit 1** both times.
  The credential case is parametrized over **three** of the seven value-bearing patterns —
  `api_key` and `access_token` (the `{8}` run) and `password` (the `{4}` run) — so the class is
  covered rather than one instance. Each case restores the file in `finally` (the fixture is module-scoped, so revision 2 passed
  only by class ordering). Third case: a key in `.claude/hooks/config.json`, `xfail(strict=True)`.
  *Mutant:* fix BUG 2 by excluding the hook or markdown → `TestSelfScanIsClean` stays green and
  these flip to exit 0. *Mutant:* close the `config.json` hole → XPASS, suite fails, marker must go.

**Vacuity statement.** Revision 1 claimed "no test passes against unfixed code" and that was
false for two tests. Corrected claim, per test rather than blanket: **every case above has a
named mutant that flips it**, and the two previously vacuous tests are fixed by the `--language`
fixture and the log-file/shim assertions.

**Follow-ups recorded, not silently dropped:**
1. `test_skip_mirror_matches_the_hook` detects *changes* to the two existing skip clauses in
   `check_secrets`, but not the *addition* of a third — a new clause would leave
   `_SKIP_SUFFIX_RE` stricter than the control and surface as a spurious red in
   `test_no_committed_file_matches_a_live_pattern` rather than a clear failure here.
   Asserting that the skip block contains exactly two `continue`-guarded clauses would close
   it.
2. `review/` and `docs/` are committed but outside `SCAN_ROOTS`;
   `review/tasks/003-fix-hook-bugs-and-fail-closed.md:49` matches the live `api_key` pattern
   today, so adding `review` needs that line fixed first.
3. The `config.json` / `.example` skip in `check_secrets` remains a real hole, bound by
   `xfail(strict=True)`.

**`tests/test_security.py` must pass UNCHANGED.** Round 2 read every assertion in it and none
is affected by this plan (which touches no validator code); any failure there is a defect in
this change, not an obsolete test. (Revision 2 carried an instruction to "update" it — deleted,
because handing an implementer written authority to edit a security test is how a real
assertion gets removed during execution.)

### Still needs execution to settle
`pytest tests/ -q` · `pytest --cov=src/claudekit/security` (≥85%) ·
`shellcheck .claude/hooks/pre-commit.sh .codex/hooks/pre-commit.sh` (the `[ ]` inside the
single-quoted array entries, the reworded `echo` block) · `mypy` · `gen-docs.py --check` ·
`gen-registry.py --check` · `ck doctor --strict` · that `install.sh --language python` renders
`\.` and `'…'` intact through `config.env` → JSON → `bash -c` (the reviewer reports
install.sh:407-419 strips only outer quotes and :501-513 uses `json.dump`, so this should hold).

Only `ruff` is encoded as a `run_command` op: the ops engine's allowlist is
`black, gofmt, goimports, isort, pip-compile, prettier, ruff, rustfmt`. Do not widen it.

## Rollback Plan

Single-branch file edits: `git revert`, or `git checkout HEAD~1 -- <path>`. No migration, no
state. Every operation is independently revertible; nothing here has an ordering dependency.

## Risk Assessment

- **High:** none.
- **Medium:** `.claude/hooks/pre-commit.sh` is a blocking hook on every contributor's and every
  user's commit path — a syntax slip breaks all commits (`shellcheck` + behavioral tests cover
  it). Also: `compileall` now walks the whole project on every commit with a source file
  staged; `-x` filters per *file*, so a large excluded virtualenv is still traversed. Cost is
  bounded but non-zero on big trees.
- **Medium (new, disclosed this round):** the shipped `build_cmd` fails the commit on any
  **pre-existing unparseable `.py`** outside the excluded directories — measured, exit 1. A
  user with a Python-2 leftover or a deliberate syntax-error fixture in their tree hits a
  blocked first commit from a file unrelated to their change. Alternatives are tabulated above
  and each is worse; the escape hatch is overriding `project.build_cmd` in
  `.claude/hooks/config.json`. Flagged for an owner decision, not buried.
- **Medium (new):** the secrets scanner's seven value-bearing patterns are being repaired
  from a state where they matched nothing. Anyone who relied on a green pre-commit run as
  evidence that no credential was staged had no such evidence. Repairing them may surface
  pre-existing matches in repos that have been committing against the dead scanner — a loud,
  correct failure, but a new one for those users.
- **Low:** template/docs/CHANGELOG edits; the three mirrors; the test-scope widening. Residual:
  users on an interpreter older than our shipped `.py` files target — not reproduced, and the
  new `\.claude` exclusion removes the exposure regardless.
- **Accepted and disclosed:** 18 template commands remain blocked until Plan B; the
  `config.json` scanner exclusion remains open, bound by `xfail(strict=True)`.

### Blast radius
`pre-commit.sh` sits on every commit. `templates/python/config.env` reaches every new Python
install. Neither the validator nor `install.sh` is modified, which is what keeps this plan's
radius smaller than the previous two revisions'.
