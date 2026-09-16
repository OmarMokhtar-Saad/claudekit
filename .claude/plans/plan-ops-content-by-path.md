# Implementation Plan: ops payload by path (`content_path`)

## Overview
A `file_create` operation and a `code_edit` edit action may reference their payload from a
file on disk instead of inlining it in ops.json, so a planner writes a large payload ONCE
(with Write) and never re-emits it inside the config. The reference is resolved in exactly
one place — a new `resolve_payload_refs()` in `.claude/operations/scripts/shared.py` — which
materialises the payload into the very key it stands in for (`content_path` → `content`),
so every existing guard, simulation, backup and rollback path sees precisely what an inline
payload would have produced.

## Phase 0: Design Precheck

**Ownership/data model.** The unit of approval in this engine is the ops.json file: the
reviewer reads it, `review-record.py --stamp-baseline` hashes it, and the executor refuses
to run a config whose hash is not the approved one. Introducing a payload that lives OUTSIDE
ops.json moves value out of the approved object, which is exactly the class of defect the
approval gate exists to catch. The files that carry this change's value are therefore
`shared.py` (the single resolution point), `operations-schema.json` (the contract),
`validate-config-json.py` and `execute-json-ops.py` (the two consumers), and
`tests/test_ops_content_by_path.py` (the proof). The approval-hash hole is closed by making
`<key>_sha256` **mandatory** alongside every `<key>_path`: the digest sits inside ops.json,
so the existing ops.json hash transitively covers the payload bytes, and `review-record.py`
needs no change at all.

**Rejection-brief search.** `review-record.py rejections search "ops content_path payload
schema validator executor"` returned 7 matches (exit 0); none concerns payload references.
The nearest validated prior is `e2e-lane-a` (MAJOR: mutation-proof overclaim — proofs
asserted but not executed). What this plan does differently: every guard below has a
behavioral test that runs the real validator/executor as a subprocess and asserts an exit
code plus an on-disk outcome; no guard is claimed as covered by inspection. Local memory
prior "ops add_after is literal concat" is honoured — every `add_after` payload here carries
its own leading newline.

## Scope
- **In Scope:** `content_path` for `file_create`; `replace_path` / `add_after_path` /
  `add_before_path` for a `code_edit` edit; the mandatory `<key>_sha256` companion; schema,
  validator, executor, dry-run reporting, tests, skill docs (both copies), planner rule,
  CHANGELOG.
- **Out of Scope:** the legacy `{"plan", "files"}` format (payload references are rejected
  there — modern format only); `review-record.py` and the approval/baseline machinery
  (deliberately untouched, see the design decision below); archiving payload files alongside
  archived plans; any `run_command` change.

## Prerequisites
- None. Python 3.9 stdlib only (`hashlib`, `re` are new imports in `shared.py`).
- `ECC_HOOK_PROFILE=minimal` in `.claude/settings.local.json` for local editing.

## Design decisions

1. **Resolve once, materialise into the inline key.** `resolve_payload_refs(config)` mutates
   the in-memory config so `content_path` becomes `content`. Every downstream guard
   (GUARD 18/26, `_validate_edits` simulation, `project_configs` projection, executor
   backups/rollback/diff) is untouched and therefore provably identical to the inline path.
   This is the minimal-diff design: two call sites plus one projection call site.
2. **`<key>_sha256` is REQUIRED, not optional.** The approval gate hashes ops.json only. A
   path-only reference could be rewritten after the verdict and the gate would still pass.
   Carrying the digest inside ops.json puts the payload back under the approval hash
   *transitively*. This is strictly simpler than teaching `--stamp-baseline` about a second
   class of file: no new record format, no new verification order, and it also protects the
   ad-hoc `--no-approval` path, which a baseline extension would not.
3. **Payload files are TRACKED, not gitignored.** No `.gitignore` rule is added. A digest is
   only auditable if the bytes it names survive; an ignored payload makes an archived plan
   and its review record unreproducible in a fresh clone (the same failure mode already
   recorded for ignored `.ops.json` snapshots). Home is
   `.claude/plans/payloads/<plan>/<name>`. The executor never deletes a payload file — it
   only reads it — so rollback and re-execution keep working; a test asserts this.
4. **Size cap `MAX_PAYLOAD_BYTES = 2 MiB`.** Inline content is implicitly bounded by the
   config a human reviews; a path reference is not, and an unbounded read is a trivial DoS.
   2 MiB is far above any legitimate source file.
5. **Modern format only.** A `*_path` key inside a legacy `files` entry is rejected with an
   explicit error rather than silently resolved, so the schema and the runtime agree.
6. **UTF-8 strict.** The payload is read as bytes, digested as bytes, then decoded strict;
   undecodable bytes and embedded NULs are refused.
7. **Fail closed.** On any resolution error the inline key is left absent, and both callers
   abort before any write; the executor emits `RESULT-JSON ... reason=payload-ref-error`.

## Implementation Steps

### Step 1: Resolution point
- **File:** `.claude/operations/scripts/shared.py`
- **Action:** Modify
- **Details:** add `import hashlib` / `import re`; export `resolve_payload_refs` and
  `MAX_PAYLOAD_BYTES` from `__all__`; append `MAX_PAYLOAD_BYTES`, `PAYLOAD_KEYS`, `_HEX64`,
  `_has_refs()`, `_resolve_one()` and `resolve_payload_refs()`. Checks, in order:
  non-empty NUL-free relative reference → inline-key mutual exclusion → mandatory 64-hex
  `<key>_sha256` → not absolute → `realpath` inside the project root (so `..` and escaping
  symlinks are both caught) → existing regular file → size cap → digest match → UTF-8
  decode → NUL scan → materialise.

### Step 2: Schema contract
- **File:** `.claude/operations/scripts/operations-schema.json`
- **Action:** Modify
- **Details:** `file_create` drops `content` from `required` and gains a nested `oneOf`
  (`content` alone XOR `content_path` + `content_sha256`); edit items gain
  `<action>_path` / `<action>_sha256` properties and three more `oneOf` branches, so
  `replace` + `replace_path` together match two branches and are rejected.

### Step 3: Validator
- **File:** `.claude/operations/scripts/validate-config-json.py`
- **Action:** Modify
- **Details:** import `resolve_payload_refs`; call it in `validate_json_config` after schema
  validation and before `detect_config_format`, returning its errors verbatim; call it in
  `project_configs` so `--after` projections see resolved payloads too.

### Step 4: Executor
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify
- **Details:** import `resolve_payload_refs`; resolve `raw_config` before
  `normalize_config`, aborting with `payload-ref-error` on any problem; in
  `execute_file_create`'s dry-run branch print `Payload: <content_path> (N bytes)`.

### Step 5: Behavioral tests
- **File:** `tests/test_ops_content_by_path.py`
- **Action:** Create
- **Details:** subprocess tests in `tmp_path` repos, `ECC_HOOK_PROFILE=minimal` forced;
  see Testing Strategy.

### Step 6: Schema docs (Claude copy)
- **File:** `.claude/skills/generate-operations-config/SKILL.md`
- **Action:** Modify
- **Details:** optional-field columns for `file_create` and the edit actions table, a
  "payload by reference" subsection with one example, and a self-check line.

### Step 7: Schema docs (Codex mirror)
- **File:** `.agents/skills/generate-operations-config/SKILL.md`
- **Action:** Modify
- **Details:** same rows and subsection, `.claude` → `.Codex` substitution applied.

### Step 8: Planner rule (byte-neutral)
- **File:** `.claude/agents/planner.md`
- **Action:** Modify
- **Details:** add Anchor Extraction Discipline item 6 (+244 bytes) offset by three trims in
  the same file (−95 Forbidden Actions, −78 Phase 3 parenthetical, −19 ops-rules bullet,
  −51 Tiered Briefing lead-in) for a net **+1 byte**: 42957 → 42958 of the 43000-byte
  pipeline-agent budget.

### Step 9: CHANGELOG
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Details:** one `[Unreleased]` bullet naming the keys, the mandatory digest, and the
  approval-hash reasoning.

## Testing Strategy
`tests/test_ops_content_by_path.py`, all behavioral (real scripts, real exit codes):
- validator PASSES a correct `content_path` + `content_sha256` config;
- validator REJECTS: missing `_sha256`; digest mismatch (the approval-gate proof); both
  inline and `_path` present; `../` escape; a symlink pointing outside the root; a missing
  payload; a directory as payload; non-UTF-8 bytes; a payload reference in a legacy `files`
  config;
- executor creates the file with bytes identical to the payload, and the payload file still
  exists afterwards (rollback-safety proof);
- executor `--dry-run` prints the payload source path and byte size and writes nothing;
- executor applies `replace_path` in a `code_edit` and refuses (non-zero, no write) when the
  digest mismatches;
- control: an inline `content` config behaves exactly as before.

Gates: `python3 -m pytest tests/ -q`, `ruff check`, `mypy`, `python3 scripts/check-context-floor.py --check`,
`python3 scripts/check-plan-artifacts.py --check`.

## Rollback Plan
`python3 .claude/operations/scripts/restore-backup.py` against this plan's backup directory
restores all eight modified files; `tests/test_ops_content_by_path.py` is a new file and is
removed by the same transaction. No data migration, no format change to existing configs:
every config without a `*_path` key takes the identical code path it takes today.

## Risk Assessment
- **Low:** docs, CHANGELOG, planner.md (byte-neutral, gate-checked); the inline path is
  untouched by construction.
- **Medium:** schema `oneOf` nesting — a malformed `file_create` now reports through the
  outer `oneOf` error message; the validator's own Python guards remain the real
  enforcement (jsonschema is optional in zero-dependency installs), and both layers are
  tested.
- **High:** payload path traversal/symlink escape, and the approval hash. Both are the
  subject of dedicated negative tests; the digest requirement is what keeps the review
  verdict binding.
- **UNVERIFIED:** `.claude/project-graph.json` was not consulted (not part of the discovery
  budget for this task); `shared.py` is imported by both ops scripts and is a de facto hub —
  the blast radius of a defect there is the whole engine, which is why resolution is a pure
  function with no side effects beyond the passed-in dict.
