# Layered Profiles — maintainer notes

> Audience: maintainers. The user-facing half is [`.claude/profiles/README.md`](../.claude/profiles/README.md).
> Landed 2026-08-21 on `perf/token-efficiency`. Promotes candidate **C5**
> (dsh layered settings) from *Retained — unranked* to *Adopted, scoped*.

## Layer order, and why it is written down here

    base -> profile -> project-local -> override

`src/claudekit/profiles.py` exposes this as `LAYERS`, the CLI prints it in the
`ck profile show --resolved` header, and `tests/test_profiles.py::
test_layer_order_constant_is_the_one_the_resolver_uses` pins the tuple. One list,
three consumers — the same discipline `model-policy.json` uses for tiers.

Each layer replaces rows **by id**. The tests that matter are not the ones that
prove an override wins (easy) but the ones that prove an *untouched row survives
and is attributed to the layer it came from* — `strict` declares no hook rows at
all, so every one of its eleven rows must resolve from `base` and say `base`.

## The binding, and what it is worth

`profiles.py::scan_hook_guards` re-derives each hook's per-profile mode from the
hook's own text: shell guards by regex over non-comment lines that actually
dereference the variable, Python guards through `ast` (so comments and docstrings
that merely name `ECC_HOOK_PROFILE` cannot be mistaken for guards — `iron-law-gate`
and `reflection-gate` both have such docstrings). `check_declarations()` compares
that to what each profile declares; `ck doctor` runs it.

The load-bearing half is the **`unrecognised` return value**. A guard written in a
shape the scanner does not model is *reported*, not ignored. That is the direct
application of the `unreviewed-expansion` / added-clause lesson in
[`REVIEW_GUIDE.md`](REVIEW_GUIDE.md): a mirror that only notices a CHANGED clause
silently becomes wrong the first time someone ADDS one. Two tests mutate the
shipped artifact rather than assert the happy path — one flips a declared row and
requires `check_declarations` to name it, one adds a `case`-statement guard in an
unmodelled shape and requires it to surface.

**The scanner's scope, stated so nobody mistakes M7/M8/M9 for a guarantee.**
`scan_hook_guards` is a *textual dereference* heuristic, not data-flow analysis. It
sees lines that dereference `$ECC_HOOK_PROFILE` or the `$PROFILE` alias with a `$`,
in any quoting. It would **not** see indirect expansion (`V=ECC_HOOK_PROFILE;
[ "${!V}" = … ]`), an environment read routed through `printenv`/`grep`, or a value
smuggled in through a differently-named alias. Those are outside the boundary by
design — a shell-source heuristic cannot close them — and they are written down
here because two review rounds of this module were spent on gaps that *were* inside
the boundary, and the difference between "we don't handle that" and "we thought we
did" is the whole point of the `unrecognised` channel.

What the binding is **not**: it does not make profiles a control. Hooks still
self-select from the env var. Written down here so nobody later reads
`.claude/profiles/` as the thing that turns hooks off.

## `format-typecheck.sh` — a real defect the gate found on its first run

The declaration for `python` (which `extends: standard`) would not verify. Cause:
`format-typecheck.sh` guarded with a **positive list** —

    [ "${ECC_HOOK_PROFILE:-standard}" = "minimal"  ] && exit 0
    [ "${ECC_HOOK_PROFILE:-standard}" = "standard" ] && exit 0

— directly under a comment reading `runs in strict only`. Any value outside that
list (a typo, a new profile name, `STRICT`) fell through and ran an expensive
Stop-time format + typecheck. Its two sibling strict-only gates,
`file-guard-gate.sh` and `injection-scan-gate.sh`, both use the negative form.
Normalised to `!= "strict"`, which is **identical on all three real values**
(`minimal` off, `standard` off, `strict` on) and stands the hook down for
everything else. Mirrored into `.codex/hooks/`.

This is the argument for the whole phase in one paragraph: three review rounds of
the hook batch read that file and found nothing, because nothing is wrong with
either line in isolation. Writing down what the profiles are *supposed* to be and
checking it mechanically found it in the first run.

## Scope deviations from `handoff-4-profiles.md`, and why

1. **Four profiles, not three.** The handoff's ground truth said `ECC_HOOK_PROFILE`
   was "one env var with two effective values (`minimal` / full)". Measured: it has
   **three** (`minimal`, `standard` — the default — `strict`) read by 11 hooks in 4
   guard forms, and `full` is an *install mode*, not a profile value. Deliverable 4
   asked for behaviour-preserving mappings of what the env var does today; that
   cannot be done with two. So: three posture profiles + one stack profile. The
   constraint's intent — no profile-per-stack explosion — holds: exactly one stack
   profile ships and it declares no hook rows.
2. **`agents`/`commands`/`mcp`/`stack` are declarative only.** See the README. The
   alternative was to ship rows implying a selector that does not exist.
3. **Not built, on purpose:** hooks reading profiles at runtime. That is a change
   to eleven fail-closed enforcement scripts and needs its own plan; deliverable 5
   (`ECC_HOOK_PROFILE=minimal` keeps working unchanged) is satisfied *by
   construction* precisely because this phase did not touch them.

## Net asset-count delta

**Zero.** Profiles are not in `ASSET_DIRS` (`agents`, `commands`, `skills`), so
`gen-docs.py` counts are untouched, and `check-context-floor.py` is unaffected —
nothing here is always-on prompt text. Profiles let assets be *selected*, and in
this phase not even that; they multiply nothing.
