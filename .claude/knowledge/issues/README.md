# Issue Knowledge Ledger (project-local)

One markdown file per issue this project has **found**, and — once it is fixed and verified —
per issue it has **solved**, so a later session looks the answer up instead of re-diagnosing a
bug we already know about.

- **Scope:** project-local only. Cross-project promotion to `~/.claude/skills/learned/` is a
  deliberate future phase — do not write outside this directory.
- **No index, no vector store.** Retrieval is plain keyword/signature grep
  (`.claude/operations/scripts/knowledge-ledger.py`), stdlib-only, zero runtime deps.
- **Never auto-injected.** The ledger is *pulled* by the debugger agent (Phase 0) on demand;
  it is never appended to CLAUDE.md or preloaded into context.

## Entry format

File name: `<slug>.md`, slug matching `^[a-z0-9][a-z0-9._-]{0,63}$`.

```markdown
---
signature: "AttributeError: 'NoneType' object has no attribute 'items' in ops executor"
root_cause: "extract_json_field returned '' and the caller never checked"
fix: "fail closed on parse error (rc 3) and assert dict before .items()"
files: [.claude/hooks/lib.sh, tests/test_hooks_behavioral.py]
date: 2026-08-01
status: fixed          # open | fixed | wontfix | regressed
origin: code           # code | workflow | project
plan: plan-some-slug   # optional: the plan that closes this finding
severity: medium       # optional, free text
verified: true         # written ONLY by `record`
---

# <slug>

## Signature / ## Root cause / ## Fix / ## Files / ## Scoring
```

`signature` is the searchable error string or symptom phrase. `files` is what pruning uses.

### Lifecycle

```
        open ──record(--verified, score>=T)──> fixed
         │                                       │
         └──close --status wontfix──> wontfix     └──open --reopen──> regressed ──record──> fixed
```

- **A missing `status:` key reads as `fixed`.** Every entry written before the key existed
  carries `verified: true`, so that is the only reading that keeps history honest.
- `verified: true` has exactly **one** writer: `record`. `open` and `close` always write
  `verified: false`.
- `origin: workflow` covers defects this repo previously had nowhere to put — bad agent
  routing, hook misfires, phantom agents. `project` is process/environment; `code` is code.
- Nothing reaches `fixed` except through `record`. That invariant is the point of the split.

## Writing an entry (the gate)

Entries are written **only** at the Verifier PASS checkpoint of the
Implementer -> Verifier -> GitOps pipeline, and only when the reusability/novelty rubric in
`.claude/skills/continuous-learning/SKILL.md` clears the threshold (**combined >= 10** by default; the script reads
`continuous_learning.issue_ledger.min_combined_score` from `.claude/hooks/config.json` and falls
back to 10 when that key is absent):

```bash
python3 .claude/operations/scripts/knowledge-ledger.py record \
  --slug null-deref-in-ops-executor \
  --signature "AttributeError: 'NoneType' object has no attribute 'items'" \
  --root-cause "..." --fix "..." \
  --files ".claude/hooks/lib.sh,tests/test_hooks_behavioral.py" \
  --reusability 7 --novelty 8 --verified
```

The script refuses (exit 1) without `--verified`, below the rubric threshold, or when the
signature is already recorded.

## Opening a finding (no gate, because it claims nothing)

A finding you have *not* fixed — a review finding, a workflow defect, a known bug you are
deferring — is recorded immediately, with **no** rubric score and `verified: false`:

```bash
python3 .claude/operations/scripts/knowledge-ledger.py open \
  --slug reviewer-cannot-execute \
  --signature "reviewer agent has no Bash, so a verdict cannot gate execution" \
  --origin workflow --plan plan-agent-tool-grants --severity high \
  --files ".claude/agents/reviewer.md"
```

**Why two subcommands and not one flag:** the value of the ledger is that `fixed` means
*verified*. If `open` were a flag on `record`, the write gate would have a bypass. It is a
separate command with its own contract instead, and it refuses (exit 1) over an existing
`fixed`/`wontfix` entry unless you pass `--reopen` (which writes `status: regressed`).
Duplicate signatures are refused across both writers.

Retiring a finding you will not fix:

```bash
python3 .claude/operations/scripts/knowledge-ledger.py close \
  --slug reviewer-cannot-execute --status wontfix \
  --reason "the agent is being deleted in the next release"
```

`close` requires `--reason` and never sets `verified: true`.

## Reading (debugger Phase 0)

```bash
python3 .claude/operations/scripts/knowledge-ledger.py search "AttributeError NoneType items"
```

Exit 0 = match printed (report the known root cause/fix); exit 3 = no match, diagnose fresh.

## Hygiene

Ledger pruning rides the periodic backlog/docs-drift sweep (see `.ai/BACKLOG.md`, P3):

```bash
python3 .claude/operations/scripts/knowledge-ledger.py prune          # report (exit 1 if stale)
python3 .claude/operations/scripts/knowledge-ledger.py prune --apply  # move to ./archive/
```

An entry is stale when **every** file in its `files:` list no longer exists. Entries with an
empty `files:` list are never auto-pruned.

Entries whose status is `open` or `regressed` are **never archived** — a still-unfixed finding
whose files all moved is a real signal, not garbage. They are reported under a separate
`STALE-OPEN` heading and prune exits 1 until they are re-scoped, recorded as fixed, or closed.
