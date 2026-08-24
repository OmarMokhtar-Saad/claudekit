# Implementation Plan: the four live `cli/main.py` findings

**Status:** EXECUTED 2026-08-24. 4 ops configs. Tier 2 (one module + one test file; user-visible CLI
output changes, so `CHANGELOG.md` gets an entry).

Four of the eleven findings confirmed live by `plan-backlog-triage-pass.md`. All four are in
`src/claudekit/cli/main.py`; the enforcement-layer three from that list are deliberately
excluded and stay owner-gated.

| # | Finding | Site today |
| --- | --- | --- |
| 1 | `cmd_config` parses `config.json` unguarded | `main.py:1836` |
| 2 | `subprocess.run` with no `timeout=` | `main.py:325` (`bash --version`), `:340` (`git --version`) |
| 3 | `cmd_rollback`'s `elif`/`else` branches are identical | `main.py:717-720` |
| 4 | ANSI colour is unconditional | `main.py:44-59` |

## 1 — a malformed `config.json` should be an error, not a traceback

`cmd_config` guards `config_path.exists()` and then calls
`json.loads(config_path.read_text())` with nothing around it. Every other reader in this
module already catches `json.JSONDecodeError` (`:207`, `:479`, `:518`, `:593`, `:812`), so
this is the odd one out rather than a design choice. A user with a truncated
`.claude/hooks/config.json` gets a Python traceback from a command whose whole job is to
read that file. Fix: catch `JSONDecodeError` **and** `OSError`, print the path and the
parser's message via `err()`, return 1.

## 2 — `ck doctor` must not hang on a wedged binary

Both calls run with `capture_output=True` and no timeout, so a `bash` or `git` that never
exits hangs `ck doctor` forever with no output — and doctor is the command people run when
something is already wrong. Fix: `timeout=5` on both, and catch
`subprocess.TimeoutExpired` alongside the existing `FileNotFoundError`, reporting it as a
distinct condition ("did not respond") rather than as absence, because "installed but
wedged" and "not installed" are different problems with different fixes.

## 3 — collapse the identical branches, and say what the default means

    if args.backup:   cmd.extend(["--backup", args.backup])
    elif args.list:   cmd.append("--list")
    else:             cmd.append("--list")

The `elif` and `else` bodies are byte-identical, so `args.list` is read and thrown away.
**Behaviour is preserved exactly** — listing is the deliberate default when no backup is
named, and that intent gets written down instead of being implied by a dead branch.

## 4 — colour, and the test that depends on its absence

`class C` emits escape codes unconditionally, so every `ck` command writes ANSI into pipes,
files and CI logs. Fix, in the conventional precedence: `NO_COLOR` set (any value, per
no-color.org) disables; a non-tty `stdout` disables; `FORCE_COLOR`/`CLICOLOR_FORCE`
re-enables regardless. Computed once at import.

**This one has a real consumer and that is the interesting part.**
`tests/test_gate_scope.py:33-34` asserts doctor's output contains
`"\033[0;32m[✓]\033[0m"`, under `subprocess.run(capture_output=True)` — i.e. into a pipe.
Those two assertions currently encode the defect as the contract: *doctor always emits ANSI,
even when nothing can render it.* They are updated to assert the plain `[✓]` / `[✗]` marks,
which is what that file's own comment already says it wants ("match the verdict line, not
the exit code") and is strictly more readable.

No other test or script in the repo greps for an escape sequence — checked, not assumed.

## Testing

Behavioural, one per finding, and each mutation-proven by reverting the fix:

1. A truncated `config.json` + `ck config --key x` → rc 1, the path and a parse message on
   stderr, and **no traceback text** in the output.
2. A fake `bash` on PATH that sleeps → doctor returns rather than hanging, and says the
   binary did not respond. Run with a generous test timeout so a regression fails the test
   instead of wedging the suite.
3. `ck rollback` with neither `--backup` nor `--list` still passes `--list` to
   `restore-backup.py`, asserted on the argv the child receives.
4. `NO_COLOR=1` → no escape byte in output; piped (no tty) → none; `FORCE_COLOR=1` while
   piped → escapes present.

## Not in scope

`ExecutionLock` on Windows, `file-guard.sh`'s extension blocking, and
`config.schema.json`'s "195+ patterns" claim — the enforcement-layer three, owner-gated.
The four hook findings go in their own plan.

## Mutation proofs, run against the shipped module

| Mutant | Result |
| --- | --- |
| `cmd_config`'s guard removed | `test_truncated_config_reports_the_path_and_exits_1` RED |
| `timeout=PROBE_TIMEOUT` removed from both probes | the wedged-binary tests RED — and they fail by **hitting the test's own 60s `subprocess` timeout**, i.e. the mutant reproduces the hang on demand |
| the rollback `else` reverted to `elif args.list` | `test_no_backup_and_no_list_flag_still_lists` RED |
| `_COLOUR = True` | 3 of the 5 colour tests RED (piped, `NO_COLOR=1`, `NO_COLOR=""`) |
| shipped | 25 passed (this file + `test_gate_scope.py`) |

## The one test this change had to alter, and why that is a finding

`tests/test_gate_scope.py:33-34` asserted doctor's output contained
`"\033[0;32m[✓]\033[0m"` — while capturing through a pipe. Those two assertions
**required colour to be unconditional**: they encoded the defect as the contract, and they
were the only thing in the repo that would have "caught" this fix. Now they match the plain
marks, which is what that file's own comment already said it wanted. No other test or
script greps an escape sequence — checked with `grep -rn '033\['`, not assumed.

## Definition of Done

The full `CLAUDE.md` gate list, plus a `CHANGELOG.md` `[Unreleased]` entry: the colour
change and the two error paths are user-visible.
