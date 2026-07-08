# Testing Guide

**Run:** `python3 -m pytest tests/ -q` → 516 passing (parametrization expands the ~231 test functions). Deps: `tests/requirements.txt` / `pip install -e ".[dev]"`. CI runs the full suite on ubuntu+macos × py3.9/3.10/3.12/3.13.

## Philosophy

Behavioral over structural — earned the hard way: the pre-audit suite was ~85% file-existence checks while the package didn't install and hooks didn't block (testing-review, 42/100). A good ClaudeKit test **executes the artifact**: runs the hook in a subprocess with a crafted stdin payload and asserts the exit code; builds the wheel and installs it in a clean venv; stages a secret and proves the commit blocks. Structure tests still exist as cheap tripwires but must never be the only coverage for a behavior.

## Test map

| File | Proves |
|------|--------|
| `test_hooks_behavioral.py` (33) | Blocking hooks exit 2 with stderr under `ECC_HOOK_PROFILE=standard`; allow-paths exit 0; fail-closed on malformed payloads. **The enforcement truth suite.** |
| `test_security.py` (35) | CommandValidator bypass corpus (chaining, substitution, IFS evasion, interpreter smuggling), PathGuard (symlinks, component matching, depth). Coverage gate ≥85% on this module. |
| `test_security_hooks.py` (12) | command-guard wiring: profile behavior (strict block / standard warn / minimal off). |
| `test_validator.py` (19) | Ops guards incl. MAX_DELETIONS, protected files, ambiguous find, schema rejection. |
| `test_install.py` (17) | Installer: staging/backup/atomic swap, byte-identical on mid-failure, settings.json installed, manifest written, sed-escaping, `--yes`. |
| `test_packaging.py` (7) | Wheel builds, entry points, version single-sourcing, assets bundled (share/claudekit). |
| `test_cli.py` (17) | `ck` subcommands incl. doctor, diff/update/uninstall manifest flows, CLAUDEKIT_HOME, find_claudekit_root regression. |
| `test_structure.py` (32) | Tree invariants: counts, frontmatter presence, no dangling references. |
| `test_registry.py` (3) | skills-registry ↔ filesystem consistency. |
| `test_checkpoint.py` (7), `test_modes.py` (9), `test_mcp.py` (11), `test_i18n.py` (10), `test_spec_driven.py` (5), `test_new_commands.py` (6), `test_new_skills.py` (8) | v2.0-era asset suites (modes, MCP templates, i18n READMEs, spec-driven flow) — the most existence-flavored remaining files; upgrade targets for task 012. |

## Rules for new tests

1. New hook/guard/validator behavior → subprocess-level behavioral test (both directions: blocks bad, allows good).
2. Bug fix → regression test named after the failure (see `test_max_deletions_exceeded` history — it shipped red once; CI now cannot pass with a red test).
3. Force the profile explicitly (`env={"ECC_HOOK_PROFILE": "standard"}`) — never depend on ambient env.
4. macOS-sensitive shell behavior → keep assertions portable; CI's macOS lane is the referee.
5. No `|| true`, no skips without an issue reference.

## Coverage

`pytest --cov` configured via dev extras; CI enforces **security module ≥85%** (the one hard gate). `.coverage` at repo root is a local artifact — don't commit meaningful thresholds elsewhere without adding them to CI.

## Gaps (task 012)

CLI in-process coverage thin (subprocess tests dominate) · prompt/eval coverage = 0 until task 010 (`evals/` with fixture repos + golden ops.json) · v2.0 asset suites need behavioral upgrades · no mutation/property testing on the validator yet (`property-based-testing` skill exists; kit doesn't apply it to itself).
