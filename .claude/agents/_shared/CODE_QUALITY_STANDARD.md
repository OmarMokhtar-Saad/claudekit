# Code Quality Standard (Clean Code + SOLID)

The single source of truth for code-quality rules. Every role agent points here;
do not copy these rules into an agent file — link to this one.

## Scope: new code only

A rule applies to code the change **adds or modifies**. Violations that already
existed are grandfathered: they are reported as context, never block, and never
force an unrelated refactor. A change must not make an existing violation worse
(a 60-line function that grows to 70 lines is a new violation).

## Measurable limits (blocking)

| Rule | Limit | How to measure |
|---|---|---|
| Function length | ≤ 50 lines (body, excluding docstring) | AST / editor |
| Cyclomatic complexity | ≤ 10 per function | Python: `ruff check --select C901`; JS/TS: eslint `complexity`; JVM: detekt / PMD |
| Parameters | ≤ 5 per function (excluding `self`/`cls`) | Python: `ruff --select PLR0913` |
| Nesting depth | ≤ 4 levels | review / linter |
| File length | ≤ 500 lines for a NEW file; an existing file must not grow past it through this change | `wc -l` |
| Error handling | no catch-all that swallows (`except Exception: pass`, empty `catch`) | grep / `ruff --select BLE,S110` |
| Duplication | no copy-pasted block ≥ 6 lines of logic | review |

Measure only the changed functions. Scope to the diff, e.g. for Python:
`git diff --name-only <base> -- '*.py' | xargs ruff check --select C901,PLR0912,PLR0913,PLR0915`
(ruff defaults already match: max-complexity 10, max-args 5)
then keep only findings whose line falls in a changed hunk.

## Design principles (judgment, cite file:line)

- **S — Single Responsibility.** One reason to change per function/class/module. A function that parses, validates, persists and formats is four functions.
- **O — Open/Closed.** Adding a new case should mean adding code (a registry entry, a strategy, a table row), not editing a long `if/elif` chain.
- **L — Liskov Substitution.** A subclass/implementation honours its parent's contract: no narrowed inputs, no widened errors, no `NotImplementedError` in an override.
- **I — Interface Segregation.** Callers depend on the narrow slice they use; a 10-argument function or a fat config object passed everywhere is a smell.
- **D — Dependency Inversion.** Core logic depends on abstractions (Protocol/interface/injected callable), not on concrete I/O, clients, or global settings; side effects live at the edges.
- **Clean code.** Intention-revealing names; no magic numbers (name the constant); no dead or commented-out code; comments explain *why*, not *what*; one level of abstraction per function; early returns over deep nesting.

## Severity mapping

| Finding | Severity |
|---|---|
| New code breaks a measurable limit | MAJOR / P1 — blocks approval |
| New code clearly violates S, O or D (god function, edit-the-chain design, concrete I/O inside core logic) | MAJOR / P1 — blocks approval |
| L or I violation, naming, magic number, weak comment | MINOR / P2 — must be listed, does not block |
| Pre-existing violation in touched file | INFO — list once, never blocks |

## Legitimate exceptions

A limit may be exceeded only with a one-line justification at the site
(e.g. `# noqa: C901 -- flat dispatch table, one branch per tool`) AND the
reviewer accepting it. Generated code, migrations and test data tables are exempt.

## Per-role duties

- **planner** — the plan names the units each change creates, states each one's single responsibility, and says how new cases will be added (O). A plan that puts new logic into a function already over the limits must split it or justify why not.
- **reviewer** (plans) — reject (MAJOR) a plan whose design implies a limit breach or an S/O/D violation; check the planner's quality statement exists.
- **implementer** — after applying, measure the changed functions; report the numbers in the output. A breach is a STOP-and-report, not a silent pass.
- **code-reviewer** — run the measurement on the diff, cite numbers and file:line, apply the severity table above; a MAJOR quality finding means REVISE.
- **verifier** — include the diff-scoped measurement in the quality score; any new blocking violation fails the quality dimension.
- **tester** — tests follow the same limits; one behaviour per test, Arrange/Act/Assert, no logic (loops/branches) in test bodies beyond parametrisation.
- **refactor-cleaner** — this standard is the target state; a refactor must not add a new violation while removing another.
