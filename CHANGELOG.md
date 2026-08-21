# Changelog

All notable changes to ClaudeKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Versioning correction (2026-07):** the entry previously published as `1.3.0`
> (2026-04-11) actually shipped *after* `2.0.0` (2026-03-17). It has been renumbered to
> `2.1.0` to restore monotonic order. Two agents listed under it — `dead-code-hunter` and
> `open-source-forker` — never shipped and have been removed.

## [Unreleased]

### Added
- **Layered profiles and `ck profile`.** `.claude/profiles/` replaces the flat
  `ECC_HOOK_PROFILE` switch with four declared profiles — `minimal`, `standard`, `strict` and a
  `python` stack profile — composed through `base -> profile -> project-local -> override`, each
  layer replacing rows by id. `ck profile list` names what is installed and which is active;
  `ck profile show <name> --resolved` prints the composed result with **each row attributed to the
  layer that won it**, which is the half that was missing: resolution nobody can inspect is
  resolution nobody can trust. A malformed or unknown profile fails closed with a named cause —
  there is no permissive fallback — and `ck doctor` re-derives every hook's real per-profile mode
  from the shipped hook file, so a profile that has drifted from the hooks is a health failure.
  **`ECC_HOOK_PROFILE` is unchanged and keeps working**: it selects the profile, and no hook reads
  the new format. Profiles *declare*, and are gate-bound to what the hooks actually do; they do not
  yet control them, and `.claude/profiles/README.md` says so rather than implying otherwise.

### Removed
- **The `.codex/` mirror (53 files).** A Codex-CLI corpus copy that nothing installed, packaged or
  referenced; its own `config.toml` set `ECC_HOOK_PROFILE=minimal` so every enforcement hook it wired
  stood down, and its `hooks.json` hardcoded 20 absolute paths to one developer's home directory. It
  had been a stale copy of `.claude/hooks/` since 2026-07-30, never adapted for Codex — the hooks
  still wrote into `.claude/`. **If you were running Codex CLI against a clone of this repo, that
  corpus is gone**; the `.agents/` skills mirror is unaffected. Removed rather than gated, because
  gating it would have bought permanent two-tree maintenance for something with no consumer.

### Fixed
- **`format-typecheck.sh` ran for any unrecognised `ECC_HOOK_PROFILE` value.** Its guard was a
  positive list (`= minimal`, `= standard`) sitting directly under a comment reading "runs in strict
  only", so a typo — or any new profile name — fell through and started an expensive Stop-time
  format + typecheck. Now a negative guard (`!= strict`), matching its two sibling strict-only
  gates. Identical behaviour on all three real values; found by the new profile gate on its first run.
- **`ck uninstall` deleted files it did not own.** The install manifest records a sha256 per
  file, but uninstall removed every path it *listed* without comparing a single digest — so a
  prompt a user had spent a week tuning was removed as readily as an untouched one. Uninstall
  now acts only on files whose digest still matches, and **fails closed** when any managed
  file has local modifications, naming them and offering two explicit ways forward:
  `--keep-modified` (remove only what the receipt still owns) and `--force` (remove them too,
  backed up first). Neither hides behind `--yes`, which only skips a prompt. When files are
  kept the manifest is rewritten to describe exactly what is still kit-owned.
- **The manifest recorded files that are the user's by definition.** `settings.local.json`
  became kit-owned on any re-install, so `ck update` would overwrite a project's own
  permission allowlist and `ck uninstall` would delete it. It, `hooks.log` and `.pyc` files
  are now never recorded.

### Fixed
- **15 skill-load instructions could never execute.** 33 of 76 skills carried
  `disable-model-invocation: true`, which removes a skill from the Skill tool's listing
  entirely — yet 15 of them were named in agents' "Skill Loading" sections: 8 as mandatory
  (including `execute-operations-config`, the implementer's Iron Law mechanism, and
  `validate-operations-config`, the reviewer's) and 7 as on-demand (five being the
  coordinator's adaptive aids). All 15 are now un-flagged, decided per skill, so the declared
  contracts can actually run. `tests/test_skill_loading_contract.py` makes the rule mechanical:
  no agent may declare a load — mandatory or on-demand — of a skill it cannot invoke.
- **The context floor charged for skills no model can see.** `check-context-floor.py` counted
  all 76 skill descriptions including the 33 model-invisible ones, inflating that category by
  ~3,900 chars. It now counts only what enters context, and the budget was **lowered**
  14000 → 9000 to match the corrected basis.

### Changed
- **Eval definitions name a capability tier, not a vendor model**, and a definition carrying
  a `model` key is now rejected outright. This closed a surface the model-policy audit did not
  cover — and **two of the four evals were not testing the shipped agent**:
  `implementer-no-fabrication` ran on sonnet while `implementer` ships on haiku, and
  `reviewer-refutes-and-formats` ran on opus while `reviewer` ships on sonnet.
- **Model routing is expressed in capability tiers, not vendor model names.**
  `.claude/model-policy.json` is now the single source of truth: it maps each of the 29
  agent roles to what it is *accountable for* and to a capability tier (`most-capable` /
  `balanced` / `fast`), and maps each tier to a concrete model in one place. Changing which
  model a tier means is a one-line edit instead of a sweep through 30 files.
  `scripts/gen-model-policy.py` projects the table onto the agent frontmatter and
  `--check` is a new drift gate with its own CI step beside `gen-docs`/`gen-registry`.
  **No agent's model changed:**
  the seeded tiers resolve to exactly the models every agent already shipped, which is what
  the gate proves. A malformed policy fails closed and writes nothing.
- **Role and capability are now chosen separately.** Each role declares only its
  accountability; the tier it earns is a separate field, with optional `escalate_to` /
  `escalate_when` replacing the prose "escalate to opus for architecture plans" rule.

- **Every hand-written `--model` literal is now accounted for.** Commands ship to user
  projects, which have no tier resolver, so they keep concrete model names. Each one must
  either resolve to its own role's tier or appear in `model-policy.json`'s
  `callsite_overrides` with a reason; the registry holds exactly one entry per literal, so
  it cannot decay into a file-level allowlist. **Known contradiction, recorded not changed:**
  `/review` spawns the reviewer on `opus` for every plan, while the reviewer role defaults to
  `balanced` and escalates conditionally. Repointing it is a user-visible behaviour change to
  a quality gate and awaits owner approval (`.ai/BACKLOG.md`).
- **`TOKEN-MODEL-POLICY` fleet-sync marker bumped v2 → v3**, so the 16 kitted projects
  receive the tier-based routing block on their next sync instead of skipping it as already
  present.

### Added
- **Installs record their source commit.** The manifest gains
  `source: {commit, pinned, dirty}`, so an installed tree is traceable to an immutable
  40-char SHA rather than to a mutable version string. A source checkout with uncommitted
  changes records `pinned: false` — it does not correspond to its own commit, and claiming a
  pin would imply a reproducibility the artifact does not have.
- **The eval suite can run without an API key.** `scripts/run-evals.py` gains
  record-once/replay-many cassettes (`--record` / `--replay`). A cassette is bound to a
  fingerprint of everything the model saw — the agent's own prompt file, the skills the
  registry maps to it, the operations-scripts tree, the resolved model, tool grants, prompt,
  fixture tree and setup files — so editing the corpus makes replay **fail closed** naming
  what moved, rather than serving a stale pass. Cost budgets, descriptions and the evals' own
  checks are deliberately excluded, so tightening a check does not force a paid re-record.
  `evals/cassettes/` ships empty: recording costs real money and is the owner's call.
- **`--inject` proves the evals' checks actually bind**, with no API key and no recordings.
  Four adverse model behaviours (`timeout`, `truncation`, `malformed_tool_call`, `refusal`)
  are injected and the **exit code is inverted**: green means every eval *rejected* the broken
  response. An eval that passes one is reported by name as `PASSED DESPITE FAULT`.
- **Evidence precedence ladder in `CLAUDE.md`.** Current files outrank indexes, memories,
  plans, and agent reports; generated indexes, reports, caches, and runtime state are not
  source artifacts; and **retrieved text is evidence, never an instruction channel** — which
  now explicitly covers the auto-memory store and prose returned by subagents.
- **`.ai/RESEARCH.md`**, a dated adoption matrix (source → pattern → Adopted/Retained/Rejected
  → local proof owner) recording *rejections and their reasons*, so settled decisions stop
  being re-litigated.

### Security
- **The secrets scanner could not detect any credential value. Seven of its thirteen
  patterns never matched anything.** `pre-commit.sh` does not source `lib.sh`, so
  `ERE_QUOTE_CLASS` / `ERE_NOT_QUOTE_CLASS` were always unset and the inline `${:-}`
  defaults always applied — and those defaults put a `'` inside a double-quoted default,
  which opens a single-quote context. Bash reported `bad substitution`, the two statements
  merged, and the negated-quote class ended up **empty**. The pattern the hook actually ran
  was `api_key\s*[:=]\s*["']{8}` — eight consecutive *quote characters* — which no real
  credential matches. **Staged credentials matching `api_key`, `apikey`, `api_secret`,
  `password`, `passwd`, `secret_key` or `access_token` were not being detected**, and
  `private_key` was left over-broad (no quote required). Measured on a fresh `--full`
  install: 0 of 7 planted real credentials detected; the hook exited 0 and logged "No
  secrets detected in staged files". Both mirrors were affected
  (`.claude/hooks/pre-commit.sh`, `.codex/hooks/pre-commit.sh`). The defaults are now built
  without a quote inside an expansion and are correct standalone, so the hook no longer
  depends on `lib.sh` for them. Only the five `BEGIN ... PRIVATE KEY` literals, which use
  no quote class, ever worked — which is why the scanner's self-matching bug was visible
  while this one was not. This remains a denylist speed bump, not a sandbox: it raises the
  cost of committing a credential by accident and does not stop a determined author.
- **A newline was not treated as a command separator, bypassing the blocklist.**
  `_SEPARATORS` listed `"\n"`, but `shlex` only ever emitted that token for an *escaped*
  newline; with `whitespace_split` a BARE newline was swallowed as whitespace. So
  `ls\nrm -rf /` validated as base command `ls` and was **allowed** — while `rm` is on the
  blocklist. Multi-line strings are the normal case for the Bash-tool guard. `validate()`
  now splits on newlines and validates each line, *below* the whole-string pattern checks
  (those use `[^;&|]*`, which spans newlines, and are all that remains when
  `security.safeMode` is false).
  The split is **quote-aware**: a newline inside quotes belongs to an argument, so
  `git commit -m "subject<newline><newline>Co-Authored-By: …"` keeps working, and a
  backslash line-continuation is untouched. Quoted text was already treated as an argument
  rather than a command, so honouring quotes here hides nothing that was previously caught.
  Scope of "bypass closed", stated precisely: newline-separated commands are refused in both
  `safeMode` states — bare newlines, newlines behind a trailing comment, and comment-hidden
  separators. Argument-position `eval`/`exec`, and wrapper arguments with `safeMode` off, are
  *not* covered and are disclosed below.
- **Two token shapes put a blocklisted command out of the blocklist's reach**, both of them
  falsifying that list's own documented promise ("never allowed, even in unsafe mode"). A
  leading file-descriptor number landed in command position, because the segmenter dropped a
  redirect and its target but not the digit before it — `2>/dev/null rm -rf /` was **allowed
  with `safeMode` off**, and bash really does delete the file. And an *empty* expansion glued
  to a command name (`` ``rm ``, `rm$()`, `$''rm`, `$""rm`) is removed by bash before the
  command is resolved but was matched literally here, so it too was allowed. Both are closed.
  The digit is removed only when it is **adjacent** to the redirect, **outside quotes**, at
  **its own position** — `2 files` and `2 > log` are commands *named* `2` in bash, `echo
  "a 2>b"` redirects nothing, and a `2>` inside one argument must not erase a `2 > …` command
  elsewhere in the line. The command name is additionally matched with expansion punctuation
  stripped, and that stripped spelling feeds the **deny** checks only, never the allowlist:
  using it for both measured 5,118 new ALLOWs, because `$ls` normalises to the allowlisted
  `ls` while actually meaning "run whatever this prints". **Disclosed widening:** in the
  default mode `2> log echo hi` and similar now validate `echo` instead of being rejected as
  "Command not in allowlist: 2", which was an accident of the same defect.
- **`scripts/check-validator-differential.py`** — a CI gate that fails a change to
  `CommandValidator` which turns a REJECT into an ALLOW **for its generated corpus**. It fuzzes
  shell metacharacters through the baseline and the working-tree validator in both `safeMode`
  states, seeded with every blocklisted command and one trigger per dangerous-pattern rule,
  because combinatorics alone reached 3 of 27 blocklisted commands and 1 of 17 patterns — so an
  earlier draft reported "no protection removed" while a mutant deleted 46 of them. It is a
  regression gate, not a soundness proof, and not a validator-versus-bash oracle: a payload both
  versions wrongly allow is invisible to it. Intended widenings are **declared** in
  `DISCLOSED_WIDENINGS`, narrowed by the exact verdict the old validator gave.
- **`scripts/check-validator-vs-bash.py`** — the second gate, and the one that covers the class
  the first cannot. The differential gate compares `CommandValidator` against *itself* at
  another commit, so a payload **both** versions wrongly allow is invisible to it — and that is
  precisely the shape of every fail-open found in this release. This one asks bash: each payload
  the validator ALLOWS is executed with `rm`, `sudo`, `chmod`, `curl`, `dd` and friends replaced
  by shell functions that print a marker and do nothing, and a marker is a divergence. It is
  contained deliberately — empty `PATH`, throwaway cwd and `HOME`, per-child CPU/memory/file
  limits, `noclobber`, and fork-bomb, loop and **absolute-path redirect** shapes refused before
  execution and *counted* rather than passed. That last one was a real escape found in review:
  `echo x > /etc/hosts` is in the corpus as a dangerous-pattern probe, and redirection is bash's
  own parser rather than anything `PATH` controls, so the first validator that allowed it would
  have written to the real path — as root, on a CI runner. The containment is also the blind
  spot: with no `PATH` there is no `xargs`, and refused shapes are not observed. Stated in the
  script, not just here.
- **A quote inside a trailing comment could hide a whole command, in both modes.** `shlex`
  strips `#`-comments by default and discards the rest of the line, so in
  `make test # don't rebuild<newline>rm -rf /` the apostrophe never reached the tokenizer, no
  separator was produced, and the command validated as a single segment with base `make` —
  **allowing the blocklisted `rm`**. Comment stripping is now disabled in the tokenizer, so
  the tokenizer and the newline splitter no longer disagree about where quotes are, and
  that input is refused as malformed. A backslash before the newline was a second,
  separate route into the same fail-open - bash gives a backslash no special meaning
  inside a comment, but the splitter applied line-continuation semantics
  unconditionally, so a commented line ending in `\` swallowed the newline and the
  command on the next line was **allowed in both modes**. A comment body is now inert to
  quotes and escapes alike, as it is in bash — an intermediate fix that suppressed only the
  escape re-opened the hole through quote parity (`echo # don\'t` + newline + `rm -rf /`),
  and a balanced quote in a comment had always hidden the following line. All three are
  closed in this release. **Cost, disclosed:** a comment containing an
  *unbalanced* quote is no longer discarded, so a benign `echo hi # don't` is now refused —
  it fails closed, where the old behaviour failed open. Comments without an unbalanced quote,
  and any `#` inside quotes, are unaffected; no `#` appears in any shipped template command.
- `CommandValidator`: `eval`/`exec` are now matched in **command position** per segment
  rather than as bare words anywhere in the string, so `bundle exec rspec` is no longer
  rejected as shell `exec`. **Measured costs of that precision, all previously rejected and
  now accepted:** `python3 -c "import x; eval(payload)"` and
  `git commit -m "then exec the thing"` in the default mode; and with `safeMode` **false**,
  `ls | xargs eval $PAYLOAD` — nothing inspects a wrapper's argument once the allowlist is
  off, since `xargs` is not blocklisted. Command-position `eval`/`exec` is still refused in
  both modes. Closing the wrapper case needs argument inspection for
  `xargs`/`env`/`nohup`/`timeout`, which is tracked separately rather than folded in here.
- **Heredoc bodies are now validated as commands.** This catches a blocklisted command
  inside a heredoc, and it also **rejects a benign one**: `cat <<EOF` / `hello world` / `EOF`
  was accepted before and is refused now, because a body line's first word is read as a base
  command. Quote-aware splitting does not help — a heredoc body is not quoted. Skipping
  bodies would require modelling delimiters, `<<-` and quoted delimiters, and any error in
  that model becomes a bypass, so this fails closed deliberately.
- The malformed-command message now reports the error shlex actually raised instead of
  always claiming "unmatched quotes" — a security control should not assert a cause it did
  not check.
- `VAR=value cmd` prefixes are now parsed as the shell does, with the assignment name
  checked against a small **allowlist** (`CI`, `COVERAGE`, `XDEBUG_MODE`, `NODE_ENV`, …).
  This is a **widening** relative to the previous behaviour, which rejected every such
  prefix. The allowlist polarity is deliberate: a denylist of dangerous names cannot be
  complete, and its misses (`RUBYOPT`, `JAVA_TOOL_OPTIONS`, `GRADLE_OPTS`, `MAVEN_OPTS`,
  `CLASSPATH`, `GIT_CONFIG_COUNT`, `GEM_HOME`, `PYTHONHOME`, …) grant execution to
  commands this same change allowlists. The check is **not** gated on `safeMode`, so it is
  also a tightening in the other direction: `FOO=bar mycmd` was accepted with safe mode off
  and is now refused by name.
- `DEFAULT_ALLOWLIST` gains eight build/test/lint entry points — `gradle`, `gradlew`,
  `mvn`, `mvnw`, `golangci-lint`, `swift`, `swiftlint`, `php-cs-fixer` — the same class as
  the existing `cargo`/`dotnet`/`composer`/`npm` entries, and the only way the go, java,
  kotlin, php and swift templates can run their configured gate. Measured after this change:
  all 40 non-empty template commands pass the screen, 0 rejected. `pip` was deliberately
  **not** added: needing it was a config defect, not a policy gap. This remains a denylist
  speed bump, not a sandbox.
- **The Iron Law is now enforced on the interactive path, not just stated**
  (`.claude/hooks/iron-law-gate.py`; plan: `.claude/plans/plan-iron-law-enforcement-hook.md`).
  `implementer.md` grants no Edit/Write but does grant unrestricted `Bash`, and a frontmatter
  `Bash(...)` specifier was measured NOT to apply on the interactive path — so `sed -i`,
  `cat >` and `python3 -c "open(...,'w')"` all bypassed hard rule 1. A `PreToolUse` hook keyed
  on `agent_type == "implementer"` now allowlists the ops engine plus a small verification set
  and refuses everything else (`exit 2` + stderr), routing the agent to the Verifier handoff.
  It passes through untouched when `agent_type` is absent or is not the implementer, so the
  main agent and every other subagent are unaffected.
  **Flags are default-deny, not denylisted:** three review rounds enumerating forbidden flags
  never converged (`pytest --log-file/-o/-c/--override-ini`, then `ruff --add-noqa` and
  `pytest --debug` *in the verbs the previous round claimed to have swept*, then
  `mypy --install-types` and `@argfile`). An unknown flag is now refused, so a future release
  cannot add a writer that slips through. **Positionals are checked too** —
  `git remote add origin <url>` mutates through arguments, not flags. The verb must name a
  PATH-resolved program, and that check sits above the interpreter dispatch.
  174 behavioral tests; eight surgical mutants asserting the exact set of cases each one flips.
  Honest residual: the SAFE tables are audited enumerations of *permitted* arguments — smaller
  and more stable than enumerating forbidden ones, but not a proof; `pytest` is permitted and
  executes `conftest.py`.
- **Reflection ledger scoped per uid and project, untrusted roots refused**
  (plan: `.claude/plans/plan-reflection-ledger-isolation.md`). The fallback was one
  `$TMPDIR/claudekit-reflection` shared by every session, project and user of that temp dir.
  Two checkouts on one machine collided — the universal defect. It is now
  `<tmp>/claudekit-reflection-u<uid>/<sha256(realpath(project_root))[:16]>`, created `0o700`
  and re-verified on each use with `os.lstat`.
  A local integrity issue was reproduced rather than theorised: `Path.mkdir(parents=True,
  exist_ok=True)` FOLLOWS a symlink planted at the root, so a planted `<key>.jsonl` symlink
  turned `open("a")` into an append-only write primitive into any file the uid owns; and
  `O_EXCL` stops the session token being overwritten but not PRE-created, so the loser adopts
  an attacker-chosen HMAC key. Sized honestly: unreachable on single-user macOS (`TMPDIR` is
  already a private `/var/folders/.../T`), real only on shared Linux hosts where `TMPDIR` is
  unset and the parent is world-writable `/tmp`. An untrusted root DEGRADES — bookkeeping
  failure never blocks work.

### Fixed
- **A new user's first commit was blocked twice over on a fresh `--full` install**
  (plan: `.claude/plans/plan-day-one-blockers.md`).
  1. `templates/python/config.env` shipped `BUILD_CMD="pip install -e ."`. `pip` is not in
     `DEFAULT_ALLOWLIST`, and `pre-commit.sh` *executes* `build_cmd`, so the blocking hook
     returned 1 on any staged `src/*.py`. It is now `python3 -m compileall -q -x ... .` —
     it installs nothing and is PEP 668-safe. (It is not side-effect free: `compileall`
     writes `__pycache__` by design.) It is scoped to `.` rather than `src` because
     `compileall -q src` **exits 0** on a project with no `src/` directory, compiling
     nothing and reporting success. Trade-off, stated because it is a real one: a
     pre-existing unparseable `.py` anywhere outside the excluded directories now fails
     the commit. Override `project.build_cmd` in `.claude/hooks/config.json` if that is
     wrong for your tree.
  2. The secrets scanner matched its own pattern definitions, flagging
     `.claude/hooks/pre-commit.sh`, `.claude/agents/opensource-sanitizer.md` and
     `.claude/skills/insecure-defaults/SKILL.md` — files the installer places in the user's
     repo — while the failure message forbids `--no-verify`. Pattern literals are now
     written `PRIVATE[ ]KEY` (identical ERE semantics), so **no new exclusion is added**
     and a real key planted in the hook itself is still caught. The failure message now
     names a sanctioned way forward. The pre-existing skip of `*.lock`, binaries and any
     path ending `config.json` / `config.template` / `.example` (`pre-commit.sh:167-172`)
     is **unchanged** and remains a real gap: a key committed to `config.json` still ships
     silently. It is bound by an `xfail(strict=True)` test and tracked as a follow-up.
- `tests/test_doctor_gate.py::test_build_cmd_does_not_mutate_the_environment` bound only
  `.claude/hooks/config.json`, which `install.sh` overwrites from the templates — so it
  read green while the shipped path was broken. It now binds the templates too, and is
  renamed `test_build_cmd_does_not_install_packages` to describe what it actually checks.
- **`config.schema.json` constrained only its root object, so typos in nested keys
  validated clean.** `additionalProperties: false` was set on the root but on none of the
  nested objects, so `hooks."pre-commit".enabeld = false` passed validation and then read
  as `enabled: true` at runtime. Every nested object is now closed. Five hook `description`
  keys and `post-tool-use.tools` were present in the shipped config but undeclared in the
  schema; they are now declared, so the tightening does not reject a valid config.
- **The approval gate reported "no review record exists" and "a verdict exists but does
  not authorise this ops.json" identically.** `execute-json-ops.py` collapsed
  `review-record.py`'s three distinct exit codes (2 drift / 3 no record / 4 unauthorised
  verdict) into a single `review-record check exit N` reason in `RESULT-JSON`. The three
  causes now carry distinct, named reasons; the exit code is retained alongside them.
- **A configured-looking command that ran nothing, and a health gate that could not pass**
  (plan: `.claude/plans/plan-doctor-gate.md`). `install.sh` defaulted every unconfigured
  project command to a no-op print command, and `templates/generic/config.env` shipped the
  same placeholder. It exits 0, so `pre-push` "ran the full test suite" and printed
  `Tests: PASSED` for a project with no tests configured - strictly worse than an empty
  value, which the hook skips and says so. Unconfigured commands now stay empty; only the
  rendered `CLAUDE.md`/`CONSTITUTION.md` get a human-readable placeholder.
  **Deliberate regression, disclosed at install time:** a project whose commands cannot be
  detected now goes from `ck doctor --strict` exit 0 to exit 1 until you configure them.
  Empty is the honest state, and a project whose gates run nothing should be told so; the
  installer now prints exactly that. Relatedly, if the installer cannot rewrite
  `.claude/hooks/config.json` for your project it blanks the command section, and if that
  write fails too it aborts and cleans up its staging directory - it will no longer leave
  ClaudeKit's own `pytest`/`ruff` invocations in your repo to be executed by your next
  commit.
- **`ck doctor --strict` failed on a `--minimal` install that was exactly as installed**
  (same plan). Skills, the skills registry, hooks and `settings.json` are absent there **by
  design**, and doctor now reads `.claude/.claudekit-manifest.json` to say so through a new
  `Skipped` result - separate from `Passed`, so a minimal install no longer reports the same
  verdict as a full one, and separate from `Warnings`, so it does not fail `--strict`. The
  manifest is unsigned, hand-editable JSON, so `mode` is never trusted alone: the manifest's
  own file record must also list no skills, hooks or `settings.json`. Flipping `mode` on a
  half-delivered full install therefore still fails, as does a tree with no manifest - while
  your own skills and hooks added to a minimal install, never being kit-managed, keep it
  green. This repo's own `project` commands are populated too (overwritten per project at
  install time, so nothing leaks to users), which makes `ck doctor --strict` exit 0 here for
  the first time. `coverage_cmd` requires `pytest-cov`: install `tests/requirements.txt` or
  `post-implement` will report coverage FAILED (loudly, never as a pass).
- **Installer shipped `settings.json` but not the Python hooks it references**, so a fresh
  full-mode install blocked every Edit, Write and Bash: `python3 <missing-file>` exits 2, and
  exit 2 on `PreToolUse` means BLOCK. The extension allowlist is replaced with a structural
  denylist, `chmod +x` is driven by shebang rather than extension, and both `install.sh` and
  `ck doctor` now derive the expected hook set from the installed `settings.json` and verify
  every wired hook resolves — `ck doctor` previously reported a healthy install on a fully
  blocked project. The check is deliberately conservative: anything it cannot classify as a
  script is ignored, never required, after an earlier revision would have blocked installation
  for everyone the moment a hook logged to `hooks.log`.
  **User-visible:** existing pre-fix installs will now correctly FAIL `ck doctor --strict`.
- **The ops engine silently stripped file modes.** `atomic_write` created its temp file with
  `mkstemp` (0600) and `os.replace` handed that mode to the target, so every edited file came
  out 0600 — which took `install.sh` to 0600 and shipped `ops-enforcement.sh` and
  `gen-docs.py` as `100755 => 100644`. Invisible to git for non-executables, since 0600 and
  0644 both store as `100644`. Fixed with one shared helper across both write paths; backup,
  rollback and post-state restore were verified unaffected (they use `shutil.copy2`).
  This was pre-diagnosed at `review/code-review.md:286` **with the fix written out** and left
  unfixed until it caused damage.
- **Reflection tests leaked process-global environment.** Both `ref` fixtures ended with
  `os.environ.pop(...)` — a delete, not a restore — so any later test relying on an ambient
  value silently retargeted to the shared temp dir. New `tests/conftest.py` provides
  `scoped_env()` (restores prior values including absence, in a `finally`) and a
  function-scoped `reflection_env`. Nothing is autouse.
- **Executable bits restored** on `ops-enforcement.sh` and `gen-docs.py`, stripped by the ops
  engine before the fix above landed.

### Known limitation
- An audit of all ten language templates against `CommandValidator` found **19 of 40**
  non-empty commands rejected by the screen — meaning `pre-commit`/`pre-push`/
  `post-implement` refuse to run them. This release fixes the Python one. The other 18
  (go LINT; all four java; all four kotlin; php LINT and COVERAGE; ruby TEST, LINT and
  COVERAGE; all four swift) need `CommandValidator` changes and are tracked in
  `.claude/plans/plan-validator-segmentation.md`. Each is bound by an `xfail(strict=True)`
  case in `tests/test_day_one_blockers.py`, so closing them cannot go unnoticed.

### Changed
- **The Iron Law now covers this repo's own product** (Decision 21, Option A). A tracked
  `.ops-source-globs` marker makes `.claude/{agents,commands,skills,hooks,operations}/*` count
  as SOURCE in this checkout, after a hard-coded never-source denylist (plans/reports/knowledge/
  backups) checked FIRST so the bootstrap cannot deadlock. **User projects are provably
  unaffected** — with no marker the exemption logic is identical to before, and absent, empty,
  unreadable, whitespace and CRLF markers all resolve to dormant. Deliberately DORMANT under
  `ECC_HOOK_PROFILE=minimal`, which this repo still defaults to; that switch is the owner's.
- **The hook count was wrong, not stale.** `gen-docs.py` globbed `*.sh`, so the Python hooks
  were invisible. It now counts `*.sh` + `*.py` minus files another hook sources or imports
  (structural, not a name list), and OWNS the prose count sites instead of telling a human to
  hand-edit them. `--check` still returns before the fixer runs, so the CI gate stays
  non-vacuous.

### Added
- **`review/code-review-triage.md`** — all 108 findings in `review/code-review.md` triaged:
  53 LIVE, 49 FIXED, 5 OBSOLETE, 1 UNVERIFIABLE, zero P0 and, on the evidence, zero P1. Of the
  53 live, only 21 are mechanically catchable and **13 need nothing built** — just an existing
  gate pointed at code it should already cover (`gen-docs --check` scopes to five docs files;
  `pyproject.toml:57` limits `mypy` to `src/claudekit` so the operations engine is untyped; no
  executable references `config.schema.json`, which is why the shipped `config.json` has failed
  the shipped schema for 46 days). Includes a sampling disclosure naming which verdicts rest on
  execution versus reading, and retracts two of its own errors in place.
- **Approval gate enforced inside the ops engine** (plan:
  `.claude/plans/plan-ops-approval-gate.md`): `execute-json-ops.py` now verifies the
  reviewer verdict itself before any mutation, instead of relying on a prose step in
  `/implement` that a direct executor call skipped entirely. Refusal is fail-closed and
  precedes lock, backup, manifest and every write: `exit 1` with
  `RESULT-JSON.reason="approval-gate: …"`, `operations: []`, `backup_dir: null`. Gating
  binds on slug identity (existing record, or a sibling/`.claude/plans` plan document, or
  a `plans/` parent, or `ECC_OPS_GATE_ALL=1`), so renaming or copying a config no longer
  sheds it. `--dry-run` is exempt; `--no-approval` is a loudly-bannered escape hatch.
  13 behavioral tests. Residual: an ad-hoc config with no plan document and no record is
  still ungated — recorded as an explicit SECURITY limitation with a default-flip path.
- **Reflection checkpoints — a mechanical circuit breaker for failure loops** (plan:
  `.claude/plans/plan-reflection-lifecycle-gates.md`): `.claude/hooks/reflection.py` keeps an
  append-only JSONL ledger OUTSIDE the repo and outside the transcript, so it survives
  compaction and cannot be committed. Failures are recorded as a digest over six
  low-cardinality fields (phase, target, failure class, platform, invariant, head); raw error
  text, absolute paths, and credential-shaped tokens are digested before they can reach disk.
  Two active failures raise a checkpoint; identical fingerprints raise a deep one. While a
  checkpoint is pending the `PreToolUse` gate blocks implementation mutation and unchanged
  test reruns while leaving diagnosis, planning, and receipt creation available. Receipts are
  HMAC'd with a per-session `0o600`/`O_EXCL` token and bound to a digest of the exact active
  set, so a checkpoint can only be cleared by the one actually owed — an integrity speed bump
  against accidental or lazy discharge, **not** an adversarial control (the agent can read the
  token). Adds the repo's first `PreCompact` hook and makes `Stop`/`SubagentStop` blocking with
  interrupt-once semantics. 79 behavioral tests.
- **`verification-gap-lens` skill** (plan: `.claude/plans/plan-review-discipline.md`): asks one
  question — if the behavior this change produces broke where it is used, would a test fail?
  Four gap shapes including *unbound check* (a guard that still passes with the thing it
  protects removed), the Demonstration technique, and the rule that a check in your own diff is
  proved by mutating the shipped artifact and reading the failure, not by imagining it.
  Adapted MIT from the chaos-engine subtree of ShaftHQ/SHAFT_ENGINE, itself from bmad-method.
- **Finding-class ratchet** (`.ai/REVIEW_GUIDE.md`): every finding carries a recurrence
  `Class`; when a class reaches three entries it earns a mechanical check or a written
  "cannot be mechanised, and why". Seeded with eight classes evidenced in this repo, each row
  naming the check that catches it now or an honest "nothing yet".
- **`tests/test_agent_tool_grant_drift.py`** (plan: `.claude/plans/plan-agent-tool-grants.md`):
  gates divergence between each agent's frontmatter `tools:` and its documented
  `--allowedTools` row. Textual, not behavioral — green does not prove enforcement.
- **`review/tasks/015-e2e-pipeline-flow-tests.md`**: 41-case end-to-end spec for
  plan→review→implement→verify, split 36 deterministic / 4 live-spawn / 1 hybrid, with an
  enumerated mutation proof for all nine groups.
- **`--json` output for the context-floor gate** (plan:
  `.claude/plans/plan-floor-json-flag.md`): `python3 scripts/check-context-floor.py --json`
  prints the measurement as a single JSON object
  (`{"sizes": {...}, "budgets": {...}, "total": N, "ok": bool}`) instead of the human
  table, so CI jobs and agents can consume the floor mechanically. Combined with
  `--check` it still exits 1 when over budget; the default table output is unchanged.
- **`run_command` operation type** (plan: `.claude/plans/plan-run-command-op.md`): plans
  can now regenerate machine-generatable content (lockfiles, formatter output, codegen)
  instead of hand-transcribing it — 58% of the largest archived ops.json was a
  hand-typed pip lockfile. Fail-closed security contract, enforced by validator GUARDs
  30–34 and re-checked in the executor: argv array with `shell=False` (no shell ever
  spawns), allowlisted executable basenames only (pip-compile, black, isort, ruff,
  prettier, gofmt, goimports, rustfmt; per-project extension via
  `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW`), `reason` required, max 5 per plan, no
  absolute/`..` arguments, bounded timeout (default 120s, cap 600s), and mandatory
  ordering after all file operations because commands are not rolled back by the
  transaction. Dry-run prints without executing. 16 behavioral tests in
  `tests/test_run_command_ops.py`.
- **Context-floor CI gate** (`scripts/check-context-floor.py --check`): measures the
  always-on context injected into every session (agent/skill/command frontmatter
  descriptions + CLAUDE.md) and fails above per-category char budgets — same drift-gate
  pattern as `gen-docs.py --check`. Behavioral tests in `tests/test_context_floor.py`,
  including a regression guard that keeps `<example>` blocks out of agent descriptions
  (one allowed for the confusable pairs reviewer/code-reviewer, doc-updater/documenter).

### Changed
- **`code-reviewer` must confirm the revision before writing any finding** (Phase 0): it is
  handed an exact revision and reads it without touching the shared working tree
  (`gh pr diff`, `git show <ref>:<path>`, a detached `git worktree`, or — for the common local
  case — `git rev-parse HEAD` plus `git diff HEAD` **and `git ls-files --others` so newly added
  files are not invisible**). If it cannot confirm, it reports the new `CANNOT REVIEW` verdict
  and stops. Previously it inherited whatever the shared tree happened to hold, and a search
  that missed because the tree was wrong returned a clean no-match — indistinguishable from a
  real absence.
- **Per-PR adversarial review floor** (CLAUDE.md, `TOKEN-MODEL-POLICY` block bumped to **v2** so
  fleet-synced projects receive it — sync is skip-if-marker-present): every PR gets at least one
  diff review before it merges, by a fresh `code-reviewer` instance, never the author, prompted
  to refute. Stop at the first round with zero blocking findings; ceiling three rounds; rounds
  2+ read only the diff since the last verdict. Honest limitation recorded: the floor is inert
  for direct-commit work, which is much of this repo's own history.
- **Bounded reads, output spill, and script-first** folded into `token-optimization`, with the
  static-vs-variable accounting split into `context-budget`. Bound every read; after truncation
  narrow once; never reread an unchanged input; spill oversized output to disk and forward the
  path plus the one fact it established. Guard clause: token savings never drop negation,
  safety, or required attribution.
- **Token-efficiency pass over the pipeline prompts** (measured, see
  `.claude/plans/plan-token-efficiency.md`):
  - Agent frontmatter descriptions: `<example>` blocks stripped (29 files, −14,393 chars
    ≈ 3.6k tokens off every context window; descriptions 22,046 → 7,566 chars).
  - `planner.md`: new "Anchor Extraction Discipline" — locate `find` anchors with
    `grep -n -C3` instead of whole-file Reads (archived plans showed 737 KB ≈ 184k tokens
    of avoidable full Reads); never hand-transcribe generated content (lockfiles).
  - `reviewer.md`: new "Token-Efficient Ops Review" — for ops.json >15 KB, score from a
    grep-built op manifest and spot-check ≤3 highest-risk ops instead of re-reading the
    full payload the validator already proved.
  - `CLAUDE.md`: trivial fast-path replaced with 3-tier blast-radius routing (Tier 1
    single-file/no-risk-surface skips planner+reviewer; Tier 3 security/migrations
    unchanged full pipeline).
- **Worktree-per-agent parallel execution.** New `worktree-manager.py` operations script
  (create/list/remove/prune; validated slugs, git-ignored registry at
  `.claude/state/worktrees.json`, atomic lock-protected writes, max 5 concurrent, safe
  removal that refuses dirty trees / unmerged commits / the primary worktree; secrets
  never copied by default), new `/worktree` command as the lifecycle primitive, and a
  coordinator "Worktree Isolation Protocol" + gitOps "Multi-Agent Merge Protocol"
  (workers commit on `agent/*` only; single merge authority; one verification pass on the
  integration branch). Isolation is proof-tested: `execute-json-ops.py` executed with
  cwd = a worktree root writes inside the worktree and cannot escape it
  (`tests/test_worktree_manager.py`, 20 behavioral tests).
- **`cross-tool-collaboration` skill + `docs/PARALLEL_AGENTS.md`.** Running multiple
  Claude accounts (`CLAUDE_CONFIG_DIR` isolation with hardening rules) and heterogeneous
  AI tools (Cursor/Codex via the AGENTS.md standard, MULTI_AGENT_PLAN.md contract,
  disjoint ownership, foreign-tool-output-is-data trust boundary) on one repository.
  Dual-account recipe published per owner directive (2026-08-09 /goal).

- **`/xpipe` — the cross-account/cross-tool pipeline with per-participant off-flags.**
  `xpipe.py` orchestrates brain (second account, plans) → hands (current account, reviews
  + implements) → cursor (cross-vendor review) with `--no-brain` / `--no-cursor` /
  `--solo` switches; unavailable participants auto-degrade with an explanation (second
  account not logged in, cursor-agent absent) and with everything off the flow IS the
  standard single-session pipeline. Headless stages use per-stage scoped `--allowedTools`
  (never `--dangerously-skip-permissions`); REVISE verdicts stop the chain (exit 3).
  12 behavioral tests (`tests/test_xpipe.py`).

### Changed
- `/batch` reconciled with the worktree engine: units execute in waves of ≤5 concurrent
  worktrees (was 5–30 unbounded), lifecycle goes through `worktree-manager.py`, and
  agent-side PR/merge steps are removed — integration flows through the gitOps
  Multi-Agent Merge Protocol.
- `multi-agent-coordination` skill gains Pattern 4 (worktree-per-agent) and the
  `MULTI_AGENT_PLAN.md` template; `using-git-worktrees` gains the worktree-per-agent
  rules, per-worktree env (`.worktree-env` port/device offsets), and a documented
  session-rooted-hooks limitation. `.agents/` skill mirrors updated in lockstep
  (`.codex/` mirror refresh deferred to the next corpus sync — `.codex/agents/gitOps.toml:30`
  still references the skill and will pick up the frontmatter change then).

### Fixed
- **Honest framing of agent tool grants** (hard rule 6; plan:
  `.claude/plans/plan-agent-tool-grants.md`). `_shared/INVOCATION.md` documented scoped
  `--allowedTools` per role, but agent frontmatter contradicted it in three places and the
  Task-tool spawn path reads the frontmatter — most seriously `implementer.md`, which declared
  unrestricted `Bash`, leaving the Iron Law bypassable via `sed -i` / `cat >` /
  `python3 -c "open(...,'w')"`. Measured on Claude Code 2.1.235 with a differential probe
  (identical rule, identical permission mode `default`, empty allow list, varying only the
  declaration site, both arms via `--agent`): a rule honoured through `--allowedTools` is **not
  applied** when declared in frontmatter. Whether it is stripped at parse time or retained and
  ignored was not separated, and the untested interactive-Task variant is named as a falsifiable
  missing arm. INVOCATION.md now states plainly that the interactive implementer holds unscoped
  Bash and that the Iron Law is **prompt-enforced, not harness-enforced**, there; the
  implementer's own rule is restated as a general prohibition on any command that writes any
  path, with examples marked non-exhaustive. `code-reviewer`'s row now grants the git/gh verbs
  its Phase 0 requires. An allowlist `PreToolUse` hook keyed on `agent_type` (confirmed present
  in the payload on both spawn paths) is specified and backlogged — that, not this, closes the
  hole. This release does not claim the hole is closed.
- **Validator no longer misattributes `oneOf` schema failures** (found by independent
  review 2026-08-17): a run_command with a too-short `reason` used to report
  `unknown field(s): 'command', 'reason'` while listing those fields as allowed. The
  validator now maps the failing operation's declared `type` to its schema variant and
  reports that variant's actual error (e.g. `'short12' is too short` at
  `operations.0.reason`).
- **Context-floor gate now budgets the per-spawn pipeline floor** (review finding: the
  planner/reviewer/implementer body total grew 4% with nothing failing while only
  always-on categories were gated). New `pipeline agent bodies` category, budget 43,000
  chars, with a regression test.
- **Install test no longer mutates the real working tree** (found by independent
  review): `test_mid_failure_preserves_existing_claude` moved the repo's actual
  `CONSTITUTION.template.md` aside and restored it in a `finally` — an interrupted run
  (Ctrl-C, CI timeout) left the tree broken and cascaded failures into every later
  install/structure test until a complete run happened to restore it. The broken source
  is now simulated in a throwaway copy of the repo; the working tree is never touched.
- **`tests/test_structure.py` is cwd-independent**: `ROOT` was a relative path that
  resolved against the invoker's working directory, so running pytest from outside the
  repo root broke every path-existence assertion. Now `os.path.abspath`.
- **Shared agent template no longer teaches an ops.json schema the validator rejects.**
  `_shared/WORKFLOW_FILE_TEMPLATES.md` documented `version`/`plan_ref`/`file`/`changes`/
  `type: create|modify|delete|move|rename` — every one of which `validate-config-json.py`
  rejects, so any agent that followed the shared template produced a config the Reviewer had
  to auto-reject (AGENTS_KNOWN_ISSUES.md #9). It now carries the canonical modern schema
  (`plan` + `operations`; `file_create`/`file_delete`/`code_edit`; `path`/`edits`;
  `additionalProperties: false`), names `generate-operations-config` +
  `operations-schema.json` as the schema owners, and documents the enforced rules (deletion
  cap, unique `find` anchors, array-order execution). New
  `tests/test_agent_doc_ops_examples.py` runs the real validator against every
  ops-config-shaped JSON fence in `.claude/agents/**` and `.claude/skills/**`, so a legacy
  example cannot silently return.
- **`using-git-worktrees` was model-invocation-disabled while four loaders instruct
  agents to load it** (`commands/git.md`, `agents/gitOps.md`, `commands/batch.md`,
  `.codex/agents/gitOps.toml`) — agents could never actually load the skill. Frontmatter
  flag removed for this skill only; the corpus-wide flag-vs-loader contradiction is
  backlogged (interacts with task 009's context-budget policy).
- **Versioned Python interpreters no longer rejected by the command guard.** `python3.12`,
  Homebrew's `python3.14`, `pip3.x` (bare or by absolute path) normalize to their
  allowlisted base (`python3`/`pip3`) for allow/block decisions; multi-Python machines
  previously got per-interpreter "not in allowlist" rejections that stalled sessions.
  Normalization applies to the blocklist too, so it cannot be used to bypass screening
  (`python3.12.evil` does not match). Regression cases in `tests/test_security.py`.

### Added
- **Work-loss protection — a concurrent session can no longer silently wipe accumulated
  work.** Four layers, prompted by a real incident (an external `git checkout` reset a file
  mid-multi-round-plan, destroying five rounds of edits, discovered only via test failures):
  (1) the command guard now blocks destructive git (`reset --hard`, `clean -f`,
  `checkout -- <path>`/`checkout .`, worktree `restore`, `stash drop/clear`) while benign
  forms (branch checkout, `-b`, `restore --staged`, soft/mixed reset) stay allowed;
  (2) `validate-config-json.py --stamp-baseline` records sha256 of every target file into
  ops.json and the executor refuses to run — before any write, dry-run included — when a
  stamped file changed since (`BASELINE DRIFT` report names each file); the /implement flow
  now stamps by default; (3) every successful execution snapshots the post-state of touched
  files under `<backup>/post/` and `restore-backup.py --post` restores that checkpoint —
  forward recovery from an external wipe becomes one command instead of replaying every
  archived ops config; (4) session-start warns when another live Claude session holds a lock
  in `.claude/locks/` (per-pid files, dead pids pruned, warning-only). Behavioral coverage in
  `tests/test_work_loss_protection.py` (15 tests) and `tests/test_security.py` (destructive
  vs benign git corpus).
- **Project graph sidecar — agents query cached structure instead of re-grepping the repo
  each session.** New `.claude/operations/scripts/project-graph.py` (stdlib-only;
  `build`/`query`/`hubs`/`path`/`stale`) stores an agent-built dependency graph at
  `.claude/project-graph.json`. Graphify-inspired patterns, no new dependency: every edge
  carries a confidence tier (`extracted`/`inferred`/`ambiguous`), `hubs` ranks fan-in/fan-out
  and flags GOD-NODE candidates, `path` reports a route's weakest-tier confidence, and
  `stale` re-hashes file-backed nodes (sha256) so an outdated graph is detected, not trusted.
  The LLM (codebase-mapping skill, new Step 7) extracts nodes/edges from any language; the
  script owns validation (anti-traversal ids, no dangling edges, size guards) and integrity
  (hashes, line counts). Explore, planner and refactor-cleaner go graph-first when the sidecar
  exists — script exit 3 means no graph/no match and they fall back to grep, so ungraphed
  projects behave exactly as before. Refactor risk rules: a GOD-NODE is always RISKY; an
  `ambiguous` inbound edge promotes SAFE to CAREFUL. Fully automatic in the workflow: the
  existing session-start hook reports graph status (none / fresh / STALE with the merge
  remediation) each session — no new hook spawn — and explore records back manually-traced
  dependencies via `build --merge`, so the graph accretes as agents work. Behavioral coverage in
  `tests/test_project_graph.py`, including a byte-identity guard on the
  `.claude/skills` ↔ `templates/skills` twins.
- **Per-issue knowledge ledger — the project stops re-diagnosing bugs it already fixed.**
  New `.claude/knowledge/issues/<slug>.md` store (markdown + frontmatter: `signature`,
  `root_cause`, `fix`, `files`, `date`, `verified`) plus
  `.claude/operations/scripts/knowledge-ledger.py` (stdlib-only; `search`/`record`/`list`/
  `prune`). Writes fire **only at the Verifier PASS checkpoint** and only when the existing
  `continuous-learning` reusability+novelty rubric scores >= 10 — no second scoring scheme, no
  write on RETRY/FAIL, duplicate signatures refused, slugs constrained so an entry cannot
  escape the ledger directory. The debugger gains a **Phase 0** that greps the ledger before
  any fresh diagnosis and reports the known root cause (after re-validating it) instead of
  re-deriving it; retrieval is pull-only — never auto-injected into context or CLAUDE.md — and
  keyword-based, so there is no index and no new dependency. Ledger hygiene rides the existing
  periodic backlog/docs-drift sweep: `prune` archives entries whose referenced files are all
  gone. Scope is project-local; cross-project promotion to `~/.claude/skills/learned/` is an
  explicit future phase. Behavioral coverage in `tests/test_knowledge_ledger.py`.
- **Supply chain hardened: every external ref is now pinned, and CI keeps it that way.**
  `security.yml` was still on mutable action tags (`@v4`, `@v5`) and ran with the default token
  scope; it is now SHA-pinned with `permissions: contents: read`, and all three workflows carry
  precise `# vX.Y.Z` comments. The MCP template no longer fetches `@latest`: all five servers are
  pinned to exact versions and the filesystem server ships **read-only** (`--allow-write` is now
  a documented opt-in), with a "what this grants" disclosure in `templates/mcp/README.md`.
  `tests/requirements.txt` became a fully hash-pinned lock generated from the new
  `tests/requirements.in`, installed in CI and release with `--require-hashes`. A new
  `supply-chain-pins` CI job fails on any unpinned `uses:` ref or any `@latest` under
  `templates/mcp/`, and three new `tests/test_mcp.py` assertions enforce the MCP pins. Dependabot
  now also watches the test lock. Release signing, SHA256SUMS and the repo-slug claim remain open
  (task 014 steps 5-7) -- they need a real release and an owner account action.
- **Queued ops configs are now validated against HEAD by the test suite.**
  `test_queued_ops_configs_validate_against_head` runs `validate-config-json.py` over
  every non-archived `.claude/plans/*.json`; a config whose anchors no longer match the
  tree fails the suite instead of failing (or mis-applying) at execution time. Spent or
  stale configs move to the new `.claude/plans/archive/` (see its README). Found live:
  the archived `ops-review-approval-binding.json` was never executed, its anchors target
  the pre-fix `review.md`, and its replacement text would have reintroduced the
  `PLAN TO REVIEW: $PLAN_CONTENT` payload leak — it must be regenerated under the
  path-not-payload contract before being pursued.
- **Zero-LLM-cost regression test for the delivery-transport contract**
  (`tests/test_delivery_contract_smoke.py`). Extracts `/plan`'s actual scripted-path
  bash block and runs it against a stub `claude` binary that emits a ~40KB fake
  plan+ops payload (matching the scale of the originally observed leak); asserts
  the payload lands on disk and validates but never reaches stdout, and stdout
  stays within the documented ≤15-line summary limit. A companion test assembles
  `/refine`'s documented 2-iteration single-script design the same way and asserts
  both iterations write the same fixed `PLAN_FILE`/`OPS_FILE` in place with only
  scoreboard-sized stdout. Pins the transport behavior mechanically so a future
  change can't silently reintroduce either leak.
- **The shell-lint DoD gate is now surfaced, never silent.** CI always ran shellcheck,
  but locally an uninstalled shellcheck meant the documented DoD command simply errored
  and sessions worked around it. `ck doctor` now warns (with the install command) when
  shellcheck is off PATH, and `tests/test_shell_lint.py` runs it per-script when present
  — 21 visible PASS lines, or 21 visible SKIPs naming the install command when absent.
- **Review verdicts are now bound to the artifact they approved.** `/review` recorded
  nothing beyond stdout, so an approved ops.json could be edited post-approval with no way
  for `/implement` to detect it — this happened for real during this session (see
  `plan-review-approval-binding.md`). `review-record.py` hashes ops.json at review time,
  gates `/implement` on a matching APPROVED/`>=90` record, and offers delta review (diff +
  prior findings, score withheld) for small post-approval edits so re-approval doesn't cost
  a full review every time.

### Fixed
- **`/refine` iterations 2+ now delta-review instead of full re-reviewing.** Every
  refine iteration spawned a fresh reviewer that re-read the whole plan + ops.json +
  code (~100k tokens per round; a live 5-iteration run burned ~600k). Cycle B now
  records each verdict via `review-record.py` and hands the next reviewer only the
  diff + the prior findings (sonnet for deltas; full review only when the diff tool
  demands it). Paired convergence rules: defects in sections the delta didn't touch
  that no prior review flagged go to `FOLLOW_UPS` — reported, but excluded from
  `CRITICAL_MAJOR_COUNT` and the score — and two consecutive sub-threshold rounds
  with disjoint findings STOP the loop for a user decision. Fixes both failure
  modes observed live: per-round full-read cost and moving-target scoring that
  never terminates (83 → 88 → new scope each round).
- **`/refine`'s headless iteration-1 planner message was self-contradictory.** It told
  the planner to "report only a short summary" while the wrapper's only delivery channel
  is stdout-to-file — a compliant planner would produce a plan file with no ops.json,
  and the loop would die with "IRON LAW violated" on the very first iteration. Now tells
  the planner its stdout IS the payload, matching iteration 2+'s (already-correct)
  framing.
- **`suggest-compact.sh`'s `PostToolUse` matcher lost Read/Grep/Glob/Task coverage.**
  Narrowed to `Edit|Write|Bash` when the hook was fixed from a no-op `PreToolUse` entry
  earlier — but exploration-heavy tool calls are exactly what ballooned the originally
  observed sessions to 300k+ tokens. Restored to `""` (all tools); also added
  `cd "$ROOT"` to the wrapper so the hook's relative counter-file path can't drift if a
  session's cwd wanders (harmless while the hook was a no-op, now load-bearing).
- **`/review` had the same `PLAN TO REVIEW: $var` leak `/refine` had.** It `cat`'d the
  whole plan file into `$PLAN_CONTENT` and interpolated it into the reviewer prompt every
  run. Now derives the paired `ops-*.json` path from the plan filename and hands the
  reviewer both paths to Read itself — the plan body never enters the main context.
- **The path-not-payload contract is now written down.** `.claude/agents/_shared/
  INVOCATION.md` gained an explicit "Delivery contract" section (interactive spawns write
  their own artifacts and return paths; headless spawns' stdout is redirected straight to
  disk, never teed/echoed); `HANDOFF_PROTOCOL.md`'s handoff rules and `planner.md`'s
  Phase 4 (Save Outputs) now state the same rule explicitly, so future commands/agents
  don't regress `/plan` and `/refine`'s fix.
- **`/plan` leaked its full payload into the main session context twice per cycle.**
  The scripted path piped the entire planner output through `tee`, printing the full
  plan+ops.json as Bash stdout; the interactive path told the planner to return the
  complete plan in its response and then had the main agent re-type it through Write
  (the source of a measured 42,665-char Write). Scripted path now writes silently
  (`printf > file`, no `tee`) and reports only paths + a ≤15-line summary (op count,
  validation verdict, first 3 plan lines). Interactive path now has the planner write
  `.claude/plans/plan-*.md` and `ops-*.json` itself (nothing in this repo's hooks blocks
  an interactive Task-subagent writing to `.claude/plans/` — verified) and return only
  paths + a short summary; the main agent re-validates once but never Reads the plan
  body back into context.
- **`/refine` pasted the full plan into the reviewer's prompt every iteration.** The loop
  stored the plan in a `current_plan=$(...)` shell variable in one Bash call and consumed
  it in a later call (`PLAN TO REVIEW: $current_plan`) — shell state doesn't persist across
  Bash tool calls, so the main agent hand-pasted the entire plan into the reviewer message
  each time (the observed ~26k-token heredoc leak), and each revision iteration re-emitted
  the complete plan + a new ops.json from scratch. `/refine` now fixes `PLAN_FILE`/`OPS_FILE`
  paths once before iteration 1; the planner writes/edits those files in place (interactive:
  via Task-tool Write; scripted: the wrapper script saves stdout to disk, never `echo`s it),
  and the reviewer is handed only the two paths to Read itself. Only the per-iteration
  scoreboard (`=== REFINE REVIEW ITERATION N ===`, a dozen lines) ever enters context.
- **`suggest-compact.sh` context-budget nudge was a complete no-op.** It was registered
  as `PreToolUse` (whose stdout is never shown to the model) and additionally ran its
  tip from a backgrounded subshell with a trailing `&` on the settings entry too, so the
  "run /compact" tip was double-detached from stdout regardless of hook event. Moved to
  `PostToolUse` (matcher `Edit|Write|Bash`, no trailing `&`), counter/tip logic now runs
  in the foreground (still <100ms, file-touch only), and the nudge cadence tightened from
  every 50 tool calls to every 40 with a stronger message. Still `exit 0` always
  (non-blocking).
- **`command-guard.sh` was fail-open by default.** The default `standard` profile
  only *warned* about a validator-flagged Bash command; nothing was actually
  denied unless a project opted into `strict`. `standard` now blocks a flagged
  command and an unparseable payload, matching the documented "denylist" framing.
  One narrower permissive path remains, kept deliberately and documented: if the
  `claude-kit` package isn't installed, the validator can't run at all, and
  blocking every Bash command in that state would brick installs that ship
  `.claude/` without the Python package — `standard` still warns there, `strict`
  blocks it too. `docs/HOOKS.md`, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, and
  several `.ai/*` files described the old warn-only behavior; updated to match.
- **`pre-commit.sh` ran `config.json`'s `project.build_cmd` unscreened.** It was
  handed straight to `bash -c` on every commit touching source files — a
  malicious or corrupted `config.json` (e.g. from a checked-out branch) was
  arbitrary code execution on `git commit`. It's now screened through the same
  CommandValidator that gates the Bash tool before running, and `config.json`
  is refused outright if it's a symlink.
- **Audit-log forging in `command-log-audit.sh`.** The hook wrote the raw Bash command
  straight into `bash-commands.log`, so a command containing embedded newlines could forge
  additional, fake audit entries (attributing arbitrary commands to arbitrary directories).
  `\n`/`\r` are now escaped before the line is written; regression test asserts a forged
  entry stays on a single log line. Low severity — a local audit trail, and anyone running
  the command already has local execution — but the log is now trustworthy as evidence.
- **Agent registration was silently broken for all 28 agents.** Bare `<example>` blocks
  between YAML frontmatter fields made every agent file unparseable, so Claude Code
  registered none of them — both the Task tool and `claude -p --agent <name>` failed with
  "agent not found", disabling the kit's entire dispatch layer (`/plan`, `/review`,
  `/refine`, `/audit`, ...). Examples now live inside the `description:` block scalar
  (routing signal preserved); verified post-fix: `claude -p --agent explore` resolves and
  completes (measured ~13s cold boot). This also resolves the Task-tool-vs-`claude -p`
  contradiction: local agents register fine once frontmatter parses — `INVOCATION.md` now
  documents both mechanisms (Task tool default in-session; scoped `claude -p` for
  scripted/CI paths with the cold-boot cost stated). Structural regression test added.
- **Headless pipeline was broken at the save step (found by end-to-end test).** `claude -p`
  spawns cannot write into `.claude/**` — the platform's sensitive-path gate requires
  interactive approval and no `--allowedTools` grant or settings allow rule bypasses it
  (all three tested). The planner burned turns retrying blocked Writes and ended asking a
  human who isn't there. Now: stdout is the explicit headless delivery contract — the
  planner emits plan + ops.json in its response, `/plan` and `/refine` save via tee and the
  restored `extract-json-from-plan.py` ops script (recreated; it existed only in pre-2.0
  installs), then validate. The implementer likewise no longer stalls when verification
  commands exceed its scoped tool grant — it reports "executed, verification pending" and
  hands off to the verifier. E2E pipeline validated on a fixture: plan(opus $0.68) →
  review(opus $0.18, refutation ran) → implement(sonnet $0.36) → verify(sonnet $0.64,
  scores matched ground truth) ≈ $1.86. `ck doctor` now checks the extract script ships.

### Added
- **`web-researcher` agent (haiku) — the only agent that calls WebSearch/WebFetch.** The
  main agent and planner must delegate external lookups to it; it reads pages inside its own
  context and returns a distilled answer instead of raw page content, with results cached to
  `.claude/reports/research/`. For library/framework/API docs, context7 MCP is tried first.
- **Coordinator Orchestration Protocol v2.** Triage table (trivial fast-path / single task /
  decompose), file-ownership map so no two sub-plans ever write the same file, parallel
  read-only plan+review fan-out, a composition gate that dry-runs all approved ops.json
  files together before anything touches the tree, and disjoint-set parallel execution.
- **Codex CLI mirror.** `.codex/` (28 agents, 26 hooks, `config.toml`) + `.agents/skills/`
  (75 skills) + a Codex-flavored `AGENTS.md`, so the same prompt corpus runs under Codex CLI.
- **Behavioral eval framework (task 010).** `claudekit eval` + `scripts/run-evals.py` +
  `evals/`: each eval spawns a real agent in an isolated fixture workspace and asserts on
  behavior, not prompt text — planner artifacts extractable + validator-APPROVED, reviewer
  verdict-block format + refutation catches a planted phantom-file defect, implementer
  never fabricates verification it couldn't run, verifier numbers match executed ground
  truth. Four evals derived from the 2026-07-08 E2E pipeline run; per-eval cost budgets;
  `--dry-run`/`--list` are free and covered by offline tests. This makes the quality gates
  mechanically checkable instead of prompt-enforced-only.

### Changed
- **Ops engine no longer loses the original file on a multi-operation rollback.**
  `execute-json-ops.py` backed up a file on *every* operation touching it, so a second
  operation overwrote the pristine backup with already-mutated content — a later failure
  then "rolled back" to that intermediate state, and `restore-backup.py` / `/rollback`
  restored the wrong content. Backups are now first-write-wins per run.
- **Ops engine fails closed on anchor drift at apply time.** An edit whose `find` pattern
  is missing or ambiguous in the current (already-mutated) content now aborts and rolls
  back, instead of skip-and-continue with first-occurrence replacement. Dry-run threads
  simulated file state across operations so previews match real sequential execution, and
  the engine prints a unified diff plus a machine-readable `RESULT-JSON:` summary line on
  config load/normalize error, lock contention, manifest failure, operation failure,
  crash, and signal; absence of the line means the process never reached a reported
  exit path (killed outright, or failed before execution began).
- **Validator simulates edits cumulatively.** `validate-config-json.py` GUARDs 10/11 now
  validate each anchor against the content as it will exist when the executor reaches
  that edit — within an operation and across operations on the same file.
- **Implementer contract: reactive reads.** The implementer now validates (a mandatory step
  its own spec previously omitted), dry-runs, and executes by passing paths to the ops
  scripts, and relays the engine's diff and `RESULT-JSON` output as evidence; it reads
  target files only to diagnose reported failures. Mirrored into the Codex corpus.
- **Per-agent model routing tuned for token economy.** `reviewer` opus → sonnet (escalates
  to opus per-call for multi-phase, architecture-touching, or security-relevant plans),
  `implementer` and `explore` sonnet → haiku. `planner` stays opus. The surviving invariant
  is "a quality gate never runs on haiku", not "the reviewer is always opus" — the routing
  spec test now encodes that, and requires the escalation path to stay documented.
- **Hooks no longer break in non-git projects.** All 21 hook wrappers resolved the
  project root with bare `git rev-parse --show-toplevel` — in a project without `.git`
  (e.g. qa-agents) every hook tried to run `/.claude/hooks/...` at the filesystem root and
  failed on every session. Root resolution is now `CLAUDE_PROJECT_DIR` → git → `pwd`;
  verified by executing the real session-start wrapper in a non-git sandbox.
- **Pipeline commands are dual-mechanism.** `/plan`, `/review`, `/refine` name the Task
  tool as the interactive default (local agents register post-frontmatter-fix; no cold
  boot, shared MCP/permissions) and keep scoped `claude -p` as the scripted/CI path — one
  delivery contract for both. The verifier now scopes lint/types/coverage to the changed
  files (full test suite always); `--all` forces the repo-wide audit pass. The
  PostToolUseFailure hook's embedded Python was a guaranteed SyntaxError, logging every
  failed tool as "unknown" — fixed, failures now log the real tool name.
- **Context budget: lazy skill loading (task 009 core).** Agents no longer preload their
  whole skill list: each declares ≤3 mandatory skills (`using-superpowers` + role-core) and
  moves the rest to an explicit on-demand tier with per-skill load triggers ("load when the
  work touches auth/input/secrets", ...). Mandatory preload drops 16,120 → 6,649 lines
  across the 18 skill-loading agents (−59%); coordinator alone 2,397 → ~350 lines. Effort
  is unchanged — the operating rules live in the always-present `_shared` docs; skill
  bodies are depth that loads exactly when the trigger fires.
- **skills-registry.json is now generated, not hand-maintained.** New
  `scripts/gen-registry.py` derives `agentMapping` from the agent files' Skill Loading
  sections (single source of truth) with a `--check` drift gate wired into the test suite
  — the audit had found 10 mapped agents with no skill section and 2 commands mapped as
  agents; the mapping is now 18 honest entries. Budget gate tests: max 3 mandatory skills
  per agent, every on-demand entry must declare its trigger.
- **Frontier-behavior corpus upgrade.** Audited all shared agent docs, 10 core agents, 14
  core commands, and the load-bearing skills against a 10-pattern operating spec (parallel
  batching, persistence, verification, adversarial self-check, evidence integrity, calibrated
  autonomy, read-before-conclude, context economy, root-cause discipline, resumable
  decomposition) so Opus/Sonnet agents operate at frontier level. Highlights:
  - "Batch independent tool calls in ONE message" is now mandated corpus-wide
    (AGENT_TEMPLATE, using-superpowers, TASK_TOOL_SPECIFICATION, coordinator, and the
    verify/debug/explore/audit/santa/plan workflows). The "3+ problems before parallelizing"
    gate is gone (2+ suffices).
  - New mandatory **Refutation Pass** before any PASS/clean/complete claim
    (VERIFICATION_PROTOCOL + verification-before-completion): what breaks it, what wasn't
    run, which claim rests on prose.
  - Evidence integrity: numbers must come from executed output; evidence is exempt from
    silent-mode token caps; templates no longer pre-print fake evidence (refine success
    banner now actually runs the validator + dry-run; loop-start gate lines quote real
    results); token-optimization can never compress verification evidence.
  - Persistence: retries must change approach (never verbatim — including coordinator error
    recovery); executing-plans' mid-plan "Continue?" permission loop removed — an approved
    plan is the permission; checkpoint to files instead.
  - Fixed unexecutable contracts: 8 commands' broken `@agents/` references (the delegated
    agent specs never loaded); reviewer `--dual` no longer tells a spawn-less agent to spawn
    (orchestrated by the command layer); planner frontmatter reconciled with INVOCATION.md
    (Write granted, Agent removed, Bash scoped to the ops validator); INVOCATION.md tool
    table extended from 2 to 10 roles.
  - Model routing: planner sonnet→**opus** (feeds the ≥90 plan gate), verifier
    haiku→**sonnet** (scores a hard ≥80 gate); coordinator stays sonnet (routing is
    table-driven). 24 anchor tests (`tests/test_behavior_spec.py`) pin all of the above.

### Added
- **Legacy-install lifecycle support.** Installs that predate the v2.1 manifest are no
  longer locked out of the lifecycle commands:
  - `claudekit diff` falls back to comparing managed assets (`agents/ commands/ skills/
    hooks/ operations/scripts/ settings.json`) against the kit source when no manifest
    exists, classifying files as `identical` / `differs` / `custom` / `not installed`.
  - With a manifest **and** kit source available, `diff` refines `modified` into
    `locally modified` / `kit-updated` / `both changed`, and lists project-added
    `custom` files.
  - `claudekit update` now works on pre-manifest installs (confirmation-gated full-mode
    reinstall that writes a manifest for next time).
  - The installer preserves project-custom assets across reinstalls: backup files not
    tracked by the old manifest (or, for pre-manifest backups, anything under
    `agents/ commands/ skills/`) are restored into the new tree instead of being
    stranded in `.claude.bak-*`. Old kit-managed files are never resurrected when a
    manifest exists.

### Security
- **Wired the security layer (was dead code).** `CommandValidator`/`PathGuard` are now
  reachable in production via a `PreToolUse` Bash guard (`.claude/hooks/command-guard.sh`)
  and the `claudekit check-command` / `check-path` CLI. Framed honestly as a **denylist
  speed bump, not a sandbox**.
  - `CommandValidator.from_config` now reads the `security` section (was `hooks` — user
    `safeMode`/`allowedCommands` were silently ignored).
  - Inspects every segment of a chained command (`; && || |`) plus `$(...)`/backtick
    substitution payloads, not just `argv[0]`. `bash`/`sh`/`env`/`xargs` removed from the
    allowlist (payload smuggling). Added `find -delete/-exec`, `${IFS}` evasion, and Python
    `os.system`/`subprocess`/`__import__` interpreter-smuggling detection.
  - `PathGuard`: relative symlinks resolved against the link's directory; protected patterns
    (`.env`, `.git/config`, …) matched per path component (`my.envelope.txt` no longer blocked).
  - Guard rollout gated by `ECC_HOOK_PROFILE`: `strict` blocks (fail-closed), `standard`
    warns (default), `minimal` off.

### Changed
- Packaging: fixed the `pyproject.toml` build backend; moved to true `src/claudekit/`
  src-layout; single version source via `importlib.metadata`.
- Prompt layer: planner ops.json schema now references the canonical
  `generate-operations-config` schema; `execute-operations-config` drives all changes through
  `execute-json-ops.py` (no manual Edit/Write).
- Docs: rewrote `docs/HOOKS.md` around `settings.json` + `ECC_HOOK_PROFILE` (the real model);
  corrected the canonical repo slug to `OmarMokhtar-Saad/claudekit` everywhere;
  `docs/ARCHITECTURE.md`/`SECURITY.md` now describe what actually runs.

### Added
- `/adapt` command + `project-adaptation` skill: adapt ClaudeKit to any project and
  language (including stacks without a dedicated template) — detect installation
  state, learn the project, configure `config.json` commands / `CLAUDE.md` /
  `CONSTITUTION.md` / hook profile / `.agentignore`, verify with evidence
  (hook block test, ops round-trip, `ck doctor`), and record adaptation decisions.
- CLI install-lifecycle commands built on the install manifest (`.claudekit-manifest.json`):
  `claudekit diff` (show locally-modified managed files), `claudekit update` (re-install over an
  existing project, warning before overwriting local edits; installer backs up first), and
  `claudekit uninstall` (remove managed files to a recoverable backup). Plus `ck init
  --full/--minimal/--yes` and `ck doctor --strict`.
- `MAX_DELETIONS` guard (max 3 `file_delete` operations per plan) in the ops validator.
- `scripts/gen-docs.py` — generates component counts from the filesystem and, with `--check`,
  fails CI when any doc hard-codes a stale count (the new `docs-drift` gate).
- CI: whole-suite test job, macOS matrix, `install.sh → doctor` integration job, coverage
  gate, `ruff`/`mypy` lint, dangling-hook-path check, and SHA-pinned actions + Dependabot.
- Wheel now bundles the runtime asset tree (`setup.py` → `<prefix>/share/claudekit`), so a
  plain `pip install` is self-contained and `ck init` works with no source checkout.

### Fixed
- Packaging: `find_claudekit_root` resolved to `src/` (not the repo root) after the src-layout
  move, breaking `ck init`; now walks up to `.claude/agents`. `CLAUDEKIT_HOME` is honored.
- `skills-registry.json`: `documenter` referenced a non-existent skill (`i18n-workflow` →
  `i18n-patterns`), which failed the validate-registry gate.
- Installer: template rendering used `sed s|{{X}}|$VAL|` — values with `&`/`|`/`\` (e.g.
  `npm run build && npm test`) corrupted output; replaced with literal Python substitution.
  C# detection now searches subdirs for `*.csproj`/`*.sln`. `set -E` so staging cleanup fires
  on a helper failure. `settings.local.json` is preserved across a reinstall.
- Hooks: `suggest-compact` daily reset was GNU-`date -r`-only (broken on macOS) — now stores the
  date in the counter file, with stale-lock cleanup. `format-typecheck` read edited files from
  the wrong log (Bash commands, not Edit/Write targets) — now uses a dedicated `edited-files.log`.
  `auto-checkpoint` stored a positional `stash@{0}` ref that pruned the wrong stash — now uses the
  stable stash SHA. Wired the dormant `file-guard`/`prompt-injection-scanner` as advisory hooks.
  Fixed the latently-red shellcheck CI job (`.shellcheckrc`).

## [2.1.0] — 2026-04-11

### Added

#### Agents (6 new — total: 28)
- **code-reviewer** (Opus) — Reviews actual code/diffs with 5 dimensions: Correctness, Security, Performance, Reliability, Code Quality; confidence-filtered findings with file:line references
- **build-error-resolver** (Sonnet) — Minimum-diff error fixer; THE ONE RULE: fix the error only; max 7 iterations; never uses `@ts-ignore`
- **loop-operator** (Sonnet) — Autonomous loop monitor with 3 intervention levels: Warn, Pause+Report, Emergency Stop; stagnation detection
- **opensource-sanitizer** (Sonnet) — Stage 1+2 of open-source pipeline; BLOCKER/WARNING classification across 6 categories (secrets, infra, PII, tooling, legal, artifacts)
- **opensource-packager** (Haiku) — Stage 3 of open-source pipeline; generates CLAUDE.md, README, LICENSE, .env.example, CONTRIBUTING.md, .github/ templates from actual code
- **model-router** (Haiku) — 4-dimension scoring rubric (reasoning depth, output complexity, error cost, domain novelty) → haiku/sonnet/opus recommendation

#### Skills (6 new — total: 73)
- **santa-method** — Adversarial dual-review: Skeptic (Opus) + Pragmatist (Sonnet) spawned simultaneously with no shared context (anti-anchoring)
- **hookify** — Analyzes behavior patterns → classifies tool call → generates prevention hook → settings.json diff → verification tests
- **context-keeper** — Structured save/resume: required fields, freshness validation (<4h full trust, 4-24h verify, >72h warn stale)
- **prp-plan** — Product Requirements Process plan phase: "A fresh agent with this plan should implement correctly without re-exploring"
- **gan-harness** — GAN-style generate-evaluate-iterate loop; anti-anchoring Evaluator spawned fresh each iteration; configurable threshold and max iterations
- **opensource-pipeline** — 3-stage hard-gated pipeline; Stage 2 only runs if Stage 1 PASSES; never modifies original source

#### Commands (13 new — total: 37)
- **/santa** — Dual adversarial review with anti-anchoring; `--strict` raises threshold to 95/100
- **/hookify** — Generate hook from behavior description or session transcript
- **/save-session** — Serialize session state to `.claude/session-context.md`
- **/resume-session** — Load and validate saved session context with freshness check
- **/model-route** — Route a task description to optimal model with scoring breakdown
- **/prp-plan** — Phase 1: deep recon → context-rich plan document (the "contract")
- **/prp-implement** — Phase 2: execute plan with per-step verification and 6-gate final check
- **/prp-commit** — Phase 3: natural-language file targeting → smart conventional commit
- **/prp-pr** — Phase 4: auto-discover PR template, generate description from commits and plan
- **/build-fix** — Fix build/type errors with minimum diff; max 7 iterations; never suppresses
- **/code-review** — Review files, directories, or GitHub PRs with ranked findings report
- **/gan-build** — GAN harness command: `--mode fast|standard|quality|strict`, `--threshold N`, `--max-iter N`
- **/opensource** — Full 3-stage open-source pipeline: `--sanitize-only`, `--package-only`, `--license MIT|Apache|GPL`
- **/loop-start** — Start monitored autonomous loop: `--agent <name>`, `--max-iter N`, `--stall-after N`

#### Hooks (6 new — total: 15)
- **config-protection.sh** (PreToolUse) — Blocks edits to ESLint, tsconfig, Prettier, Biome, pyproject and 15 other config files; respects `ECC_HOOK_PROFILE`
- **commit-quality.sh** (PreToolUse/Bash) — Warns on generic messages, debug artifacts; BLOCKS on staged secrets (`.env`, `.pem`, `.key`)
- **security-reminder.sh** (PreToolUse/Write) — Non-blocking warnings for `shell=True`, SQL concat, `innerHTML`, TLS disabled, weak crypto, permissive CORS
- **suggest-compact.sh** (PostToolUse, async) — Suggests `/compact` every 50 tool calls; daily counter reset
- **session-start.sh** (SessionStart) — Detects package manager, loads config commands, prints startup summary, auto-loads recent session context
- **format-typecheck.sh** (Stop, async) — Runs Biome/Prettier + `tsc --noEmit` on all JS/TS files edited in session; strict mode only

#### System
- **ECC_HOOK_PROFILE** env var — `minimal|standard|strict` controls hook activation without file edits
- **Anti-anchoring protocol** — Both Santa reviewers and GAN Evaluators spawned with no shared context or prior conversation history
- **PRP lifecycle** — 4-phase workflow (plan→implement→commit→PR) where each phase is a dedicated command with explicit handoff contract

### Fixed
- `pre-commit.sh` path: `find operations/ -name "ops.json"` → `find .claude/plans/ -name "ops-*.json"` (planner writes to `.claude/plans/`)
- `skills-registry.json` `agentMapping` structure: confirmed as dict (agent_name → list of skill IDs), not a list
- Documented component counts corrected to match the filesystem: 28 agents / 39 commands / 73 skills / 19 hooks, now generated and CI-enforced by `scripts/gen-docs.py`

## [2.0.0] — 2026-03-17

### Added
- **7 Behavioral Modes**: default, brainstorm, token-efficient, deep-research, implementation, review, orchestration
- **5 MCP Server Configurations**: Context7, Sequential Thinking, Playwright, Memory, Filesystem
- **Universal Command Flags**: --mode, --depth, --format, --persona, --save, --checkpoint
- **Spec-Driven Development Workflow**: /specify, /clarify, /analyze, /checklist commands
- **Security Hooks**: file-guard (195+ patterns), check-comment-replacement, prompt-injection-scanner
- **Checkpoint System**: /checkpoint create/restore/list with auto-checkpoint hook
- **Parallel Execution**: /spawn, /batch, /ship commands for parallel agent work
- **International Support**: READMEs in Arabic, Chinese, Spanish, French, Japanese, Korean
- **10 Advanced Skills**: token-optimization, codebase-mapping, session-continuity, autonomous-loop, context-priming, hook-profiling, safe-command-approval, usage-monitoring, prompt-injection-defense, incident-response
- **/translate command**: Multi-language documentation translation
- **/mode command**: Switch behavioral modes per session
- **/index command**: Generate project structure index
- **/load command**: Context loader for project components
- **/flags command**: Universal flags reference
- **.agentignore template**: Gitignore-style file for AI agent access control
- **i18n-workflow skill**: Internationalization patterns and RTL support
- **mcp-integration skill**: MCP server usage guidelines
- **spec-driven-development skill**: Specification-first workflow patterns
- **command-flags skill**: Universal flag parsing system

### Changed
- Bumped version to 2.0.0
- Expanded skill count from 45 to 55+
- Expanded command count from 17 to 27+
- Added modes directory to template structure
- Added mcp directory to template structure
- Added i18n directory with 6 language translations

## [1.1.0] - 2026-03-16

### Added
- 4 new agents: tester, security-scanner, devops, database-architect (total: 13)
- 9 new commands: /explore, /security, /deps, /rollback, /test, /deploy, /performance, /migrate, /batch (total: 17)
- 18 new skills including Trail of Bits-inspired security skills, enterprise patterns, and i18n/a11y (total: 45)
- 4 new language templates: Rust, C#, Ruby, PHP (total: 11)
- Official Claude Code hooks via .claude/settings.json (7 event types)
- Professional README with shields.io badges and comprehensive documentation

### Fixed
- 43+ bugs fixed across security, cross-references, and compliance
- All agent frontmatter updated with tools and example blocks per Claude Code official docs
- All skill frontmatter updated with disable-model-invocation, user-invocable, allowed-tools
- Hooks format migrated from custom config.json to official Claude Code settings.json
- Kotlin language detection now works correctly (moved before Java check)
- Template {{PROJECT_NAME}} substitution now works for all language templates
- Command injection vulnerabilities fixed in all hook scripts
- install.sh config.env sourcing security hardened

## [1.0.0] - 2026-03-16

### Added
- 9 specialized agents: coordinator, planner, reviewer, implementer, verifier, debugger, documenter, gitOps, explore
- 8 slash commands: /plan, /review, /implement, /verify, /debug, /docs, /git, /coordinator
- 27 generic skills covering planning, review, implementation, testing, debugging, git, and more
- 5 workflow hooks: pre-commit, post-implement, pre-plan, pre-push, post-tool-use
- Operations system with validate, execute, and restore scripts (CodeManifest v3.1.0)
- One-command installer (`install.sh`) with language detection
- 7 language templates: Python, TypeScript, Java, Go, Kotlin, Swift, Generic
- 2 complete examples: Python/FastAPI and TypeScript/Next.js
- CLAUDE.template.md and CONSTITUTION.template.md for project customization
- Shared agent templates and protocols
- Skills registry for agent-skill mapping
- Comprehensive documentation (Architecture, Customization, Agents, Skills, Hooks, Constitution Guide)
- CI/CD pipeline with GitHub Actions
- Issue and PR templates
