# Implementation Plan: layered hook profiles + `ck profile`

Branch `perf/token-efficiency`, planned at HEAD `1a15f36`. Source task:
`handoff-4-profiles.md` (Phase 2 of the wave). Tier 3 — new public CLI verb and a
new on-disk config format. Every number below was measured at this ref.

## Overview

Replace the flat `ECC_HOOK_PROFILE` switch with a declared, layered, **inspectable**
profile format, without changing what a single hook does. Ship the resolver
(`src/claudekit/profiles.py`), four profile documents, the `ck profile` verb, a
`ck doctor` check that binds the declaration to the shipped hooks, and the
behavioural tests that prove all three required properties by mutation.

## Ground truth — re-verified at `1a15f36`, correcting the handoff

The handoff states `ECC_HOOK_PROFILE` is "one env var with two effective values
(`minimal` / full)". **That is wrong, and the correction changes deliverable 4.**
Measured:

- **Three** effective values: `minimal`, `standard` (the `${…:-standard}` default),
  `strict`. `full` is an *install mode* (`ck init --full`), not a profile value.
- **Eleven** hooks carry a guard, in **four** distinct forms: `= "X" && exit 0`,
  `!= "X" && exit 0`, a `PROFILE=` alias then `[ "$PROFILE" = … ]`, and two Python
  forms (`iron-law-gate.py:708` early-return, `reflection-gate.py:104`
  `blocking_enabled()`).
- `reflection-gate` under `minimal` is **not** off — it runs and cannot block. Any
  boolean hook model would misdescribe it, so modes are `on`/`advisory`/`off`.
- `.claude/profiles/` does not exist; `ck` has no `profile` subcommand (13 today).
- `gen-docs.py` derives its counts from hardcoded globs over `.claude/agents`,
  `.claude/commands`, `.claude/skills` and `.claude/hooks` — there is no
  `ASSET_DIRS` symbol in it (that name belongs to `install.sh`'s custom-asset
  preserve block). `.claude/profiles` is in neither, so counts and
  `check-context-floor.py` are structurally unaffected. Both are still run as
  evidence rather than assumed.

Derived truth table (produced by the scanner in Step 1, not by hand):

| hook | minimal | standard | strict |
|---|---|---|---|
| block-no-verify, command-guard, commit-quality, config-protection, iron-law-gate, ops-enforcement, security-reminder | off | on | on |
| file-guard-gate, injection-scan-gate, format-typecheck | off | off | on |
| reflection-gate | **advisory** | on | on |

## Scope

- **In scope:** `src/claudekit/profiles.py` (new), `.claude/profiles/` (4 profiles
  + README), `src/claudekit/cli/main.py` (`ck profile` + one doctor check),
  `.claude/hooks/format-typecheck.sh` + `.codex/hooks/format-typecheck.sh` (one
  guard line, see ITEM 3), `install.sh` (ship the directory),
  `tests/test_profiles.py` (new), `.ai/PROFILES.md` (new), `.ai/RESEARCH.md`,
  `.ai/BACKLOG.md`, `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md`, `CHANGELOG.md`.
- **Out of scope:** making hooks *read* profiles at runtime (eleven fail-closed
  scripts; own plan). Phases 3–5 of the handoff (skill/MCP generators, memory
  store, `ck adapt`). Phase 0 (event log, dispatcher, merge rule, spill) — nothing
  here depends on it. No agent, command or skill is added, renamed or deleted.
- **Net asset-count delta: 0.**

## Prerequisites

`.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` — present, verified.
No test fixtures are created outside `tmp_path`, so the `ops-enforcement.sh:43`
`$TMPDIR` exemption hazard does not arise.

---

## ITEM 1 — the resolver (`src/claudekit/profiles.py`)

Stdlib only (`ast`, `json`, `os`, `re`, `pathlib`, `typing`). Three parts:

**Schema + validation.** `SCHEMA_VERSION = 1`; sections `hooks`, `agents`,
`commands`, `mcp`, `stack`; `validate_doc()` raises `ProfileError` with a **named
cause** for a missing/unknown `schema_version`, an unknown top-level key, a
non-object section, an unknown hook id, an out-of-domain value, an `mcp` value that
is not a non-negative int or null, an unknown `stack` key, a `name` that disagrees
with its directory, an `extends` cycle, and an `extends` in the project-local
layer. There is no permissive fallback anywhere.

**Composition.** `LAYERS = ("base", "profile", "project-local", "override")`.
`base_layer()` is a built-in identity (all eleven hooks `on`, `*: on` rosters, null
budget, null stack) — deliberately **not** a directory, so `ck profile list` shows
only selectable profiles. `resolve()` applies base, then the `extends` chain
base-most first, then `.claude/profiles/local.json`, then `--set` overrides,
recording the winning layer on every row. `select_name()` reads the explicit
argument, then `ECC_HOOK_PROFILE`, then `standard` — which is how deliverable 5 is
satisfied: the env var is the selector, unchanged.

**The binding — `scan_hook_guards()`.** Re-derives `profile -> mode` from a hook's
own text. Shell: regex over non-comment lines that actually dereference the
variable (`${ECC_HOOK_PROFILE` or `"$PROFILE"`), so prose that merely *names* it —
`command-guard.sh:69` tells the user to `set ECC_HOOK_PROFILE=strict` — is not a
candidate. One narrowly-recognised non-enablement form (`… && deny`, the
strict-only escalation at `command-guard.sh:67`). Python: `ast`, so docstrings that
name the variable (`iron-law-gate.py:58`, `reflection-gate.py:43`) cannot be
mistaken for guards; every `Constant` equal to `ECC_HOOK_PROFILE` whose line was
not consumed by a recognised comparison is reported.

**The `unrecognised` return value is the point.** A guard in a shape the scanner
does not model is *reported*, not silently ignored. This is the added-clause
recurrence class `.ai/REVIEW_GUIDE.md` already records: a mirror that detects a
CHANGED clause but not an ADDED one becomes quietly wrong. Verified: the scanner
returns **zero** unrecognised lines across all eleven hooks today, and flagged
`command-guard.sh:67` on its first run until that form was modelled explicitly.

**Review round 1 falsified that invariant, and the fix is the reason this item is
worth its length.** The shell candidate test was a *substring* check for
`${ECC_HOOK_PROFILE`. A guard written the brace-less way —
`[ "$ECC_HOOK_PROFILE" = "minimal" ] && exit 0`, ordinary bash — matched neither
sigil, so it was skipped **without being recorded as unknown**: neither recognised
nor reported, which is strictly worse than unrecognised and is precisely the silent
drift the mechanism exists to prevent. The candidate test is now the regex
`\$\{?ECC_HOOK_PROFILE\b|"\$PROFILE"`. Two consequences, both deliberate:
the brace-less form and the defaultless `${ECC_HOOK_PROFILE}` form are now
*reported* rather than silently accepted — they have different unset semantics
(empty, not `standard`) and must not be quietly treated as equivalent to the form
the hooks actually use. Measured after the fix: all eleven real hooks still scan
with zero unrecognised lines, and all three escaping shapes are reported.

**Round 2 found the same defect one alternative to the right.** The alias pattern
was `"$PROFILE"` — quoted — so `[ $PROFILE = "minimal" ]`, unquoted and valid shell,
using the alias this module already models, fell into the identical hole. Neither
alternative requires quotes now. Two instances of one class in two rounds is the
argument for the shape the candidate test finally has: match the **dereference**,
and let the form regexes decide what is *recognised*. Probed after the fix and all
reported, none silent: brace-less, defaultless, `${…:?}`, `[[ ]]`, the `test`
builtin, `case`, and the unquoted alias.

This defect was found by reviewing the module — twice — not by a hook someday
written that way. It is recorded here because "the binding is airtight" is a claim
this plan ships in three documents, and it was false both times it was written.
The honest generalisation: a candidate filter and a recogniser are two different
jobs, and every bug here came from the filter quietly doing the recogniser's.

`check_declarations(root)` = declaration vs. derived, for every installed profile.

## ITEM 2 — the four profiles

`minimal` (ten `off` + `reflection-gate: advisory`), `standard` (the three
strict-only gates `off`; everything else survives from base), `strict` (**no hook
rows at all** — strict *is* base, and an empty section is the honest way to say
so), `python` (`extends: standard`, adds `mcp` budget + four stack facts, declares
no hook rows).

`agents`/`commands`/`mcp`/`stack` are **declarative only in this release** — no
component reads them, and every shipped profile leaves the rosters at base `*: on`.
A row claiming to disable an agent would claim a selector that does not exist. Said
plainly in both READMEs rather than left for a reader to discover.

**Deviation, declared:** four profiles, not the three the handoff asked for. Its
arithmetic rested on the two-value ground truth corrected above; behaviour-
preserving mappings of a three-valued variable need three profiles, and the stack
profile is the fourth. The constraint's intent (no profile-per-stack explosion)
holds: exactly one stack profile, and it forks nothing.

## ITEM 3 — `format-typecheck.sh`: a defect the gate found on its first run

The `python` declaration would not verify. `format-typecheck.sh:7-9` guards with a
**positive list** (`= "minimal"`, `= "standard"`) directly under a comment reading
`runs in strict only`. Every value outside that list — a typo, a new profile name,
`STRICT` — falls through and runs an expensive Stop-time format+typecheck. Both
sibling strict-only gates (`file-guard-gate.sh:20`, `injection-scan-gate.sh:20`)
use the negative form.

Replace the two lines with `[ "${ECC_HOOK_PROFILE:-standard}" != "strict" ] && exit 0`.
**Identical on all three real values** (minimal off, standard off, strict on);
differs only for values that were never valid, where it now stands the hook down
instead of running it. The hook is async and non-blocking, so the blast radius is
an expensive no-op that stops happening. Mirrored to `.codex/hooks/`.

*Observation, not fixed here:* `.codex/hooks/format-typecheck.sh` has separately
drifted from `.claude/` — it is missing the leading-dash argument-injection anchor
(`case "$filepath" in -*)`). That is a security-relevant mirror drift with its own
cause and its own fix; it gets a `.ai/BACKLOG.md` entry, not a silent ride-along.

## ITEM 4 — `ck profile`, and the doctor check

`ck profile list` — every installed profile, its description, which is active, and
the raw `ECC_HOOK_PROFILE`/default that decided it. `ck profile show [name]` — the
raw document; `--resolved` — every row with its winning layer; `--json` — the same,
machine-readable; `--set SECTION.ID=VALUE` — the override layer. Any `ProfileError`
prints its named cause to **stderr** and exits **1** (this is a CLI, not a blocking
hook; `exit 2` is reserved for hooks and must not be diluted).

`ck doctor` gains one check running `check_declarations()`. Absent
`.claude/profiles/` is `"skip"` (a pre-profile install is not unhealthy); a present
but malformed or drifted set is a **failure**, so `--strict` reddens.

## ITEM 5 — installer

`mkdir -p` gains `profiles`, and the full-mode block copies each profile directory
plus the README. The manifest walks the destination tree, so profiles are receipted
(and therefore `ck uninstall`-able and `ck diff`-visible) with no manifest change.

## ITEM 6 — docs

New `.ai/PROFILES.md` (layer order, the binding and its limits, the
`format-typecheck` finding, the declared deviations, the zero asset delta).
`.claude/profiles/README.md` (user-facing). `.ai/RESEARCH.md`: C5 moves *Retained —
unranked* → **Adopted, scoped**. `CHANGELOG.md` `[Unreleased]`: `ck profile` and
the `format-typecheck` guard are user-visible. Plus `.ai/BACKLOG.md` (the `.codex`
drift), `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md`.

---

## Verification

| # | Command | Expectation |
|---|---|---|
| 1 | `pytest tests/test_profiles.py -q` | green (35 cases incl. M7/M8/M9) |
| 2 | `pytest tests/ -q` | 1,646 + new, zero failures |
| 3 | `ruff check src/ tests/ scripts/` · `mypy` | clean (line-length 100, py3.9) |
| 4 | `gen-docs.py --check` · `gen-registry.py --check` · `gen-model-policy.py --check` | no-ops; run as evidence |
| 5 | `check-context-floor.py` | floor unchanged |
| 6 | `shellcheck install.sh .claude/hooks/*.sh` | clean (ITEM 3 + ITEM 5 touch shell) |
| 7 | `ck doctor --strict` | passes, including the new check |
| 8 | `ck profile list` / `show python --resolved` | real output pasted into the commit |

## Mutants and flipped cases

Each is applied and reverted one at a time; every one MUTATES A SHIPPED ARTIFACT.

- **M1 — drifted declaration.** Flip `minimal.hooks.ops-enforcement` to `on`.
  **Flips:** `test_a_drifted_declaration_is_reported`,
  `test_every_declaration_matches_the_hooks_own_guards`,
  `test_doctor_fails_when_a_profile_has_drifted_from_the_hooks`. **Must not flip:**
  the layer-precedence and fail-closed cases.
- **M2 — ADDED guard in an unmodelled shape.** Insert
  `case "${ECC_HOOK_PROFILE:-standard}" in fancy) exit 0 ;; esac` into
  `commit-quality.sh`. **Flips:** `test_an_unmodelled_guard_form_is_reported_not_ignored`.
  This is the case a token-presence mirror cannot catch, and the reason the scanner
  returns `unrecognised` at all.
- **M7 — brace-less guard (the shape that escaped review round 1).** Insert
  `[ "$ECC_HOOK_PROFILE" = "minimal" ] && exit 0` into `commit-quality.sh`.
  **Flips:** `test_a_braceless_guard_is_reported_not_silently_skipped`. Against the
  pre-review scanner this mutant flips **nothing at all** — that is the gap, and it
  is why M2 (which only exercised a `case` statement) was insufficient coverage of
  the *class* rather than of one shape.
- **M8 — braced guard with no `:-standard` default.** Same insertion with
  `${ECC_HOOK_PROFILE}`. **Flips:**
  `test_a_braced_guard_without_the_default_is_reported`. Distinct from M7 because
  the semantics differ (unset → empty), so silent acceptance would be a wrong
  answer rather than merely an unmodelled one.
- **M9 — unquoted alias (the round-2 escape).** Rewrite `command-guard.sh:33` as
  `[ $PROFILE = "minimal" ] && exit 0`. **Flips:**
  `test_an_unquoted_alias_guard_is_reported`. Against the round-2 scanner this
  flips nothing.
- **M3 — revert ITEM 3.** Restore the positive-list guard. **Flips:**
  `test_every_declaration_matches_the_hooks_own_guards` (`python` diverges) and the
  doctor check. Proves ITEM 3 is load-bearing rather than tidying.
- **M4 — drop a layer.** Make `resolve()` skip `local.json`. **Flips:**
  `test_project_local_layer_beats_the_profile`. **Must not flip:** base/profile cases.
- **M5 — permissive fallback.** Make `load_profile` return `{}` instead of raising
  on an unknown name. **Flips:** every `fails_closed` case and both CLI
  `returncode == 1` cases.
- **M6 — hook-guard reality.** Change `ops-enforcement.sh` to `exit 0` unguarded.
  **Flips:** `test_ops_enforcement_really_stands_down_under_minimal_and_blocks_otherwise`
  at the `standard` arm — the anchor that keeps the whole gate from being a mirror
  of a mirror.
- **Would pass against unfixed code:** nothing. `tests/test_profiles.py` is new and
  its subject does not exist at `1a15f36`; that is stated so the reviewer does not
  read the absence of a pre-existing-green list as an omission.

## Rollback

`git revert` the single commit, or per item: ITEM 3 is one line in two files and is
independent; ITEMS 1/2/4/6 are additive (new module, new directory, new subcommand,
new docs) and removing them restores exactly today's behaviour, because **no hook
reads any of it**. ITEM 5 is two lines of installer.

## Risk

- **Low:** ITEMS 1, 2, 6 — additive, no existing code path reads them.
- **Low-medium:** ITEM 4 — touches `cmd_doctor`, which `--strict` gates in CI. The
  new check `"skip"`s when `.claude/profiles/` is absent, so every existing installed
  tree and every doctor test that predates profiles is unaffected.
- **Medium:** ITEM 3 — the only behaviour change in the plan. Bounded: identical on
  all three real values, and the hook is async/non-blocking.
- **High:** none.
- **Blast radius:** `ck doctor` is the widest — a malformed profile is now a health
  failure. That is the intended enforcement, and it is why absent-profiles is a skip
  rather than a fail.
- **Explicitly not done:** hooks do not read profiles; nothing about the security
  layer, the ops engine, or the Iron Law is touched.
