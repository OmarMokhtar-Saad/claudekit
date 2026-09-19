# Plan: the shadow check must separate a rebind from a mutation

**Ops config:** `.claude/plans/ops-precompile-shadow-false-positive.json` (2 operations)

Phase 0 of `plan-contrib-governance.md`. Those four phases cannot execute until this
lands: each creates a test file, and every new test file currently reds the parse gate.

**Revision 3.** Revision 1 scored 60/REJECTED — it exempted the idiom by subtracting a
name set at the end of `shadowed()`, whitelisting that name file-wide. Revision 2 scored
75/REVISE — the site-scoped rework killed both of those Criticals, but the exemption was
still too coarse on two axes. Revision 3 narrows both.

## The defect

`ops_precompile._module_bound` collects assignment targets with `ast.walk(t)`, which
descends into `Subscript` and `Attribute` targets and picks up the base `Name`. So
`os.environ["X"] = v` — a store *through* `os` — is recorded as a rebinding *of* `os`,
and `shadowed()` reports that the import is not what runs.

Corpus scan over `tests/`, `scripts/`, `src/`, `.claude/operations/scripts/`,
`.claude/hooks/`: **4 files flagged, 4 false positives, 0 true positives** — confirmed
independently by review, which read every site.

- `tests/test_rejection_briefs.py:23`, `tests/test_heldout_set.py:15` — module-level
  `os.environ["ECC_HOOK_PROFILE"] = "minimal"`, the form CLAUDE.md *requires* of tests
- `tests/test_preserve_assets.py:18` — `sys.modules["preserve_assets"] = ...`
- `.claude/hooks/iron-law-gate.py:111-114` — the optional-import idiom

The gate is differential, so an existing file only reds when edited. A *created* file has
no baseline and every shadow reads as new — which is why four phases of unrelated work
all failed identically on their new test files.

## The change

`.claude/operations/scripts/ops_precompile.py`, one op, five edits:

1. Add `_bind_names(target, out)` — descends `Tuple`/`List`/`Starred`, stops at
   `Subscript`/`Attribute`. Add `_catches_import_error` and `_fallback_names`.
   `_module_bound` gains a `skip` parameter.
2. `_guarded = _fallback_names(node) if isinstance(node, ast.Try) else frozenset()`,
   computed per node so only *this* try's handlers exempt *this* try's imports.
3. Annotate `_assigned: set` (keeps mypy inference after edit 4).
4. The `global` branch uses `_bind_names`.
5. The main branch binds into a local set, subtracts `_child_skip`, and threads
   `_child_skip` into the recursion.

`shadowed()` is **unchanged** — it still returns `imported & bound`.

## The exemption

The optional-import idiom genuinely rebinds the name, so it must be exempted, but the
exemption is applied to the **binding site**, never to the name:

- `skip` is threaded *down* the traversal and only widens when recursing into an
  `ExceptHandler` of a guarded `try`.
- `_module_bound` already stops at `def`/`class`, so a fallback inside a function can
  never reach a module-level binding. C2 falls out of the same mechanism as C1.
- A rebind in the try **body** is not a fallback — that code runs unconditionally.
- `_catches_import_error` requires a named type that can catch an import failure:
  `ImportError`, `ModuleNotFoundError`, `Exception`, `BaseException`. `except ValueError:`
  and a bare `except:` do not qualify. `Exception` is included because the shipped
  `.claude/hooks/iron-law-gate.py:113` uses exactly that form on purpose.
- **The guarded try body must be import-only.** `except Exception:` implies "the import
  failed" only when the body can raise nothing else; let it do other fallible work and the
  handler runs with the import having *succeeded*, so its rebind is live. Measured:
  `try: import yaml; CONFIG = yaml.safe_load(open(...)) / except Exception: yaml = None`
  reported clean until this guard existed. Narrowing on the **body** rather than on the
  exception type is what keeps iron-law-gate.py exempt — its body is a single import — and
  is why revision 2's "the widening is forced" reasoning was wrong.
- **Each handler is judged on its own.** `_child_skip` re-checks the handler it is about
  to descend into. Widening for every `ExceptHandler` child let a sibling
  `except ImportError: pass` launder an `except ValueError: html = 'clobbered'`.

## Acceptance criteria

- `tests/test_ops_precompile_shadow.py` — 30 tests, green
- `ruff check src/ tests/ scripts/ .claude/operations/scripts/` — clean
- `mypy` — `Success: no issues found in 42 source files` (revision 1 regressed this to 2
  `var-annotated` errors; edit 3 is why it no longer does)
- `python3 -m pytest tests/ -q` — zero failures
- All four `ops-contrib-governance-p*.json` reach `--dry-run` without a parse-gate refusal

## Mutation evidence (measured, not asserted)

Revision 1's plan claimed "positive controls red if the fix is reverted". That was false:
reverting `_bind_names` leaves all five green, because the old code *over*-reports. Each
mutant below was run against the shipped test file; baseline is 28 passed.

| Mutant | Result | Killed by |
|---|---|---|
| `_bind_names` → old `ast.walk` body | 5 failed | the four store-is-not-a-rebind tests + the corpus test |
| file-wide subtraction (**the rejected revision-1 design**) | 7 failed | all four laundering tests, try-body, function-scope, nested-scope, real-`iron-law-gate` |
| drop `Tuple`/`List` descent | 2 failed | tuple + starred controls |
| any handler counts as a fallback | 2 failed | `except ValueError:` and bare-`except:` controls |
| fallback names also cover the try body | 1 failed | try-body control |
| locate `Try` with `ast.walk` (scope boundary removed) | 1 failed | `test_a_nested_fallback_cannot_exempt_the_enclosing_handler` |
| drop the import-only body guard | 1 failed | `test_a_try_body_that_does_other_work_is_not_a_fallback` |
| widen `_child_skip` for every handler child | 1 failed | `test_a_sibling_handler_does_not_lend_its_guard_to_another` |

Rows 6-8 each exist because a mutant survived everything else. Rows 7 and 8 were added in
revision 3: review demonstrated that both fixes were invisible to the revision-2 suite,
which passed 28/28 with and without them. Each new test is now its mutant's sole killer.

## Known limitation (accepted, not fixed)

A fallback written through `global` inside the handler —
`except ImportError: def _f(): global html; html = None` — is still reported. The
`FunctionDef` branch returns before `_child_skip` exists, so the `global` collection never
consults `skip`. This is a false positive, the conservative direction for a gate, and no
file in the 198-file corpus hits it.

## Rollback

`git revert` of this commit. One file plus one new test; no migration, no deletions, no
protected path touched.

## Risk

Widening an exemption in a gate is how gates go inert — and revision 1 is the proof, so
this is a measured risk, not a hypothetical one. Mitigated by the seven laundering and
scope tests above, each demonstrated to kill the rejected design, plus the corpus ratchet.
