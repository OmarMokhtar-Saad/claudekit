# Phase 1 Plan — v2.1 "Fix What's Broken"

**Source:** `review/roadmap.md §1` + tasks `001–006`, `011` + §1.6 prompt-layer fixes.
**Target:** 4–6 weeks. **Overall repo score at audit:** 49/100.
**Thesis:** every item is a defect in something already advertised. No new features.

**Exit criteria:** `pip install claudekit && ck init && ck doctor` works clean from a fresh
machine; every enforcement hook demonstrably blocks in a self-test; no doc/version number
disagrees with the tree; CI cannot pass with a failing test.

---

## State verified 2026-07-05 (all P0 claims still true)

- `pyproject.toml:3` = `setuptools.backends._legacy:_Backend` → package **never buildable**.
- Version drift: pyproject `2.0.0`, `src/cli/main.py:13` = `1.1.0`, CHANGELOG tops `1.3.0`,
  `shared.py:3` = `3.1.0`. Zero git tags.
- `src/` is itself the package (wrong src-layout); entry points `src.cli.main:main`.
- `install.sh` never copies `settings.json` → hooks inert on every install.
- Blocking hooks end in `exit 1` (Claude Code blocks only on `exit 2`) → nothing ever blocked.
- `--dangerously-skip-permissions` in plan.md:30, review.md:55, refine.md:96/112/150.

---

## Dependency graph

- **001 packaging** is foundational: the `src/` → `src/claudekit/` rename changes the import
  path **002** wires; its single-version-source mechanism is what **006** depends on.
- **005 installer** must copy `settings.json`; without it **003 hook fixes** are invisible.
  The two land together to be verifiable.
- **004 skip-permissions** needs one empirical spike: does native Task transport load
  `.claude/agents/*.md` in the current CC release? That answer decides 004's steps + invocation docs.
- **011 CI** removes `|| true` day-one, but package-smoke / install-integration / docs-drift
  gates only go green after the tasks they guard land.

---

## Execution waves

### Wave A — Foundation
1. **001 Packaging** *(P0, 1–2d)* — build-backend → `setuptools.build_meta`; drop setuptools-scm;
   `src/{cli,security}` → `src/claudekit/{cli,security}`; single version via `importlib.metadata`;
   entry points `claudekit.cli.main:main`; fix `tests/test_cli.py:31` + `test_security.py` imports;
   optional-deps, PEP 639 license, py3.13 classifier, `requires-python>=3.9`; `package-smoke` CI job;
   tag `v2.1.0` (user-gated) + Trusted Publishing.
2. **011 (day-one slice)** — remove both `|| true`; run entire `tests/` dir. Sequence with 012's
   known red test (`test_max_deletions_exceeded`).
3. **006 (P0 subset)** — canonical repo slug; SECURITY.md → 2.x; CHANGELOG renumber. Each ≤1h.

### Wave B — Stop harming users
4. **004 Skip-permissions** *(P0, 2–3d)* — empirical invocation spike → `_shared/INVOCATION.md`;
   remove all 5 flag occurrences; standardize one transport; CI grep gate.
5. **005 Installer** *(P0, 1wk)* — staging-dir + backup + atomic swap (kills `rm -rf $DEST` trap);
   **copy/merge settings.json**; curl|bash guard; `--yes`; install manifest; `ck update`/`uninstall`;
   honest epilogue; `CLAUDEKIT_HOME` honored.
6. **003 Hooks** *(P0 subset <1d, full 4–6d)* — `lib.sh` shared helpers; blocking hooks → `exit 2`
   + stderr; fail-closed on JSON drift; stdin-JSON (revive telemetry/cost-tracker); ops filename
   split-brain; `\x27`/bash-3.2 fixes; wire dormant file-guard + injection-scanner.

### Wave C — Make guarantees real
7. **002 Security** *(P1, 3–5d)* — fix CommandValidator/PathGuard bypasses (config section,
   `bash -c`, `&&` chaining, symlink resolution); expose `claudekit check-command`; wire
   fail-closed PreToolUse under `ECC_HOOK_PROFILE=strict`; dedupe 3 impls; fix ARCHITECTURE.md.
8. **§1.6 Prompt-layer** — fix planner.md embedded ops.json schema (fails own validator);
   fix `execute-operations-config` Edit-tool contradiction; add `MAX_DELETIONS` guard.

### Wave D — Honest CI + docs
9. **006 (full)** — `scripts/gen-docs.py` + docs-drift CI; regenerate counts (28 agents / 52 cmds
   / 73 skills); rewrite docs/HOOKS.md around settings.json.
10. **011 (full)** — macOS matrix; package-smoke; install→doctor --strict integration; coverage
    gate; ruff/mypy; manifest-derived count checks; dangling-hook-path check.

---

## Effort
~4–6 weeks. P0 critical path (001 → 005 → 003 → 004) ≈ 2 weeks; remainder parallelizes.

## Open decisions (need owner input)
- **Canonical repo slug:** `omarmokhtar/claudekit` vs `OmarMokhtar-Saad/claudekit` (one 404s).
- **PyPI name:** `claudekit` collides with an npm package in the same niche — disambiguate before publish.
- **Security layer:** wire (recommended) vs delete (task 002 decision gate).
