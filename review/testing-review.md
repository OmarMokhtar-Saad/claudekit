# ClaudeKit — Testing Review (QA Architect)

## Suite execution (actually run)

Environment: Python 3.12, pytest + pytest-timeout, `jsonschema` installed from `tests/requirements.txt`.

Command: `python3 -m pytest tests/ -q --timeout=30`

**Result: 1 FAILED, 422 passed** (~423 tests collected across 14 files; parametrization inflates the raw count well beyond the 137 `def test_` functions).

- `tests/test_validator.py::TestFileOperationsValidation::test_max_deletions_exceeded` — **FAILING**. The test builds 4 `file_delete` operations and asserts the validator returns a "too many" error. The current `validate_file_operations` in `.claude/operations/scripts/validate-config-json.py` enforces per-op guards (protected file, reason length, null bytes, traversal, existence) but has **no aggregate max-deletions cap**, so the assertion `any("too many" in e.lower())` is `False`. This is a real product gap, not just a broken test: an ops config can delete an unbounded number of files in one shot. Fix the code (add a `MAX_DELETIONS` cap, e.g. 3) rather than deleting the test.

All other suites pass: `test_install.py` (11), `test_cli.py` (6), `test_security.py` (13), structure/mcp/i18n/modes/skills/spec/checkpoint/security_hooks.

## What is tested vs. what matters

The suite is **~85% structure/existence tests, ~15% behavior tests**. Concretely:

**Structure tests (low value — assert files exist / contain a substring):**
- `test_structure.py` (32 fns): every assertion is `os.path.exists` / `startswith('---')` / `count('---') >= 2`. Verifies inventory, not correctness.
- `test_checkpoint.py`, `test_i18n.py`, `test_mcp.py`, `test_modes.py`, `test_new_commands.py`, `test_new_skills.py`, `test_spec_driven.py`, `test_security_hooks.py` — all assert markdown files exist, have frontmatter, or contain a keyword (`assert ".env" in content`, `assert "RTL" in content`). These pass forever regardless of whether the prompt asset actually works, and give a false sense of coverage. A typo that guts a hook's logic but keeps the keyword string passes green.
- Grep confirms 11 of 14 test files rely on `os.path.exists/isfile/isdir`.

**Behavior tests (the real value):**
- `test_security.py` — genuinely exercises `CommandValidator` and `PathGuard` logic (allow/block/patterns/traversal/null-byte/depth). Best file in the suite.
- `test_validator.py` — imports `validate-config-json.py` and drives `validate_json_config`, `detect_config_format`, `validate_file_operations` with real inputs. Second best (and the one that surfaced the real bug).
- `test_install.py` — actually runs `install.sh` into a temp dir and asserts outputs. Good, but see gaps below.
- `test_cli.py` — spawns the CLI as a subprocess and checks return codes/output. Behavioral but shallow (mostly "returncode in (0,1)").

## Coverage of src/cli and src/security

Ran `coverage` over `test_security.py` + `test_cli.py`:

| Module | Stmts | Cover | Note |
|---|---|---|---|
| `src/security/command_validator.py` | 36 | **92%** | Well covered |
| `src/security/path_guard.py` | 48 | **73%** | Symlink branch, dir-depth `ValueError` path uncovered |
| `src/cli/main.py` | 272 | **0%** | Tests spawn it as a subprocess, so coverage instrumentation never sees it. Effective in-process coverage is ~zero; only smoke-level (help/version/returncode) behavior is checked. `cmd_doctor`, `cmd_config` key traversal, `cmd_agents` frontmatter parsing, `cmd_rollback/validate/execute` arg plumbing are untested for actual output. |

Critical caveat: `src/security/*` has **92%/73% coverage but is dead code** — grep shows `CommandValidator`/`PathGuard` are referenced only by `test_security.py` and `docs/ARCHITECTURE.md`. Nothing in `install.sh`, the bash hooks, or the CLI imports them. So the best-tested code in the repo is not wired into the running system. The tests validate a library nobody calls.

## CI matrix gaps (.github/workflows/ci.yml)

- Matrix is Python `3.8/3.10/3.12` on **ubuntu-latest only**. No macOS runner — yet `install.sh` and `path_guard.py` have macOS-specific branches (`/System`, `/Library` in SYSTEM_PATHS; `Package.swift` detection). Bash on macOS is 3.2 (no associative arrays); the installer's arrays/`declare` could break and CI would never catch it. **Add `macos-latest` to the matrix.**
- No Windows runner. `pyproject.toml` advertises 3.8–3.12 and the code has `C:\Windows` path guards that are never exercised.
- CI runs only `test_structure.py`, `test_validator.py`, `test_install.py` in the matrix job; `test_cli.py` and `test_security.py` run in a **separate single-version job with `|| true`** — failures there are swallowed and never fail the build. That is why the `test_validator` failure would surface but a `test_security` regression would not. Remove `|| true`.
- `test_i18n`, `test_mcp`, `test_modes`, `test_new_*`, `test_spec_driven`, `test_checkpoint`, `test_security_hooks` are **not run in CI at all** — they only pass locally. Wire the whole `tests/` dir into one matrix job.
- No coverage gate in CI despite CLAUDE.md/CONSTITUTION claiming 80%/70%/90% thresholds. Coverage is aspirational, not enforced.

## Missing test categories

1. **No golden/regression tests for markdown assets.** 73 skills, 29 agents, 37 commands ship as prompts executed by an agent with shell access, and nothing tests their *content semantics* — only that a keyword is present. A skill could be rewritten to instruct auto-approval of `rm -rf` and every test stays green. There is no snapshot/golden test, no frontmatter schema validation (required keys, valid `model:` values, `allowed-tools` sanity), no check that agent→skill references in `skills-registry.json` resolve (that lives only in a CI shell one-liner, not pytest).
2. **`install.sh` untested paths:** `--full` mode (only `--minimal` is tested), `--with-mcp`, `--with-i18n`, `--force` overwrite-of-existing, the interactive `read` prompts, the `_cleanup_on_failure` ERR trap, language detection for go/rust/kotlin/swift/csharp/ruby/php (only python & typescript tested), CLAUDE.md/CONSTITUTION.md template rendering (sed substitution correctness), and the `config.env` parser's allowlist filtering. **The installer does not copy `.claude/settings.json`, and no test asserts settings.json exists post-install — so the missing-hook-wiring bug (see security review) is invisible to the suite.**
3. **No negative/adversarial security tests** for the bash hooks themselves (file-guard, prompt-injection-scanner) — `test_security_hooks.py` only checks they exist, are executable, have a shebang, and contain keywords. It never *runs* them against a malicious path/payload to confirm they block.
4. **CommandValidator bypasses untested** (see security review): `python3 -c "malicious"`, `bash -c "rm -rf /"` (bash is allowlisted!), `git !dangerous`, unicode homoglyphs, `$IFS` splitting. Existing tests only cover the happy path and obvious `rm`/`sudo`.
5. **No flaky patterns detected** in current tests (good) — they are deterministic, temp-dir isolated, and fast (~0.5s). The risk is the opposite: they are *too* stable because they assert almost nothing.

## Target test pyramid

Current shape is an inverted funnel of file-existence checks. Target:

- **~70% unit (behavior):** `command_validator`, `path_guard`, `validate-config-json` guards, CLI command functions called **in-process** (import `main` and call `cmd_doctor(args)` with a fabricated `args`, capture stdout) — not via subprocess.
- **~20% integration:** full `install.sh` runs across every mode/language/flag combo into temp dirs; hook scripts executed end-to-end against crafted inputs; ops execute→rollback round-trip.
- **~10% asset-golden/contract:** frontmatter schema validation for every agent/command/skill; registry cross-reference resolution; prompt-injection scanner run against a corpus of known-bad strings; a "dangerous-instruction" lint that greps every markdown asset for `rm -rf`, `--dangerously`, "auto-approve without confirmation", "skip review" and fails on unexpected matches.

## 15 highest-value missing tests

1. `install.sh --full` installs skills, hooks (chmod +x), modes, and **copies `.claude/settings.json`** — assert settings.json present and valid JSON. (Would catch the hook-wiring gap.)
2. `validate_file_operations` rejects >N deletions (fix the currently-failing test by fixing the code; add the `MAX_DELETIONS` guard).
3. `CommandValidator` blocks `bash -c 'rm -rf /'` and `python3 -c 'import os;os.system("rm -rf /")'` — proves allowlisted interpreters can't smuggle payloads.
4. `PathGuard` symlink-escape test: create a symlink inside project pointing to `/etc/passwd`, assert blocked (covers the uncovered symlink branch).
5. `PathGuard` blocks unicode/`..%2f` encoded traversal and rejects paths where `..` normalizes back inside root but the raw string escapes.
6. Golden frontmatter-schema test: every `.claude/agents/*.md` and `commands/*.md` parses to valid YAML with required keys and an allowed `model` value.
7. Registry integrity test (in pytest, not CI shell): every `agentMapping` skill id exists in `skills` and every skill dir has a `SKILL.md`.
8. Dangerous-instruction lint: grep all shipped markdown for auto-approve / bypass-confirmation / `rm -rf` / `--dangerously` and fail on new occurrences (allowlist the legitimate ones in prompt-injection-defense).
9. `prompt-injection-scanner.sh` run against a fixture of 25 injection strings — assert exit 1; and against benign text — assert exit 0.
10. `file-guard.sh` run against `.env`, `~/.ssh/id_rsa`, `terraform.tfstate`, `.aws/credentials` — assert exit 1; against `src/main.py` — assert exit 0.
11. CLI `doctor` output correctness: run in a fully-installed temp project, assert it reports the right agent/command/skill counts and exits 0 (in-process for coverage).
12. CLI `config <dotted.key>` traversal returns the right value and errors on missing keys.
13. `install.sh --force` overwrites an existing `.claude/` and the `_cleanup_on_failure` trap removes a partial install when a copy step fails (simulate by making a source unreadable).
14. Language-detection matrix: parametrized test creating `go.mod`, `Cargo.toml`, `Package.swift`, `*.csproj`, `Gemfile`, `composer.json`, `build.gradle.kts` and asserting the detected language.
15. `config.env` parser security test: a template `config.env` containing `EVIL=$(touch /tmp/pwned)` and `PATH=/evil` must be ignored by the installer's allowlist (`BUILD_CMD|TEST_CMD|...`) — proves no arbitrary variable injection.

## Score

**Test Coverage: 42/100** — Suite runs fast and clean-ish, `test_security`/`test_validator`/`test_install` are genuinely good, and a real bug was surfaced. But the bulk is file-existence theater, the best-covered module (`src/security`) is dead code, CLI in-process coverage is ~0%, macOS/Windows and full-suite CI are absent, security-critical asset content is untested, and a shipped test is currently red.
