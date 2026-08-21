# Adoption matrix

Why this file exists: settled decisions were being re-litigated because the
*rejections* were never written down. A pattern appears here exactly once, with a
verdict and the artifact that proves the verdict — or the reason there is none.

**Verdicts.** *Adopted* — implemented here, with a named local proof.
*Retained* — accepted as sound and queued, with the blocking dependency named.
*Rejected* — deliberately not taken; the reason is binding until someone
overturns it with new evidence, not with a fresh opinion.

Sources read directly (GitHub API, 2026-08-21), not summarized from write-ups:

- `ShaftHQ/SHAFT_ENGINE/chaos-engine` — a provider-neutral peer of ClaudeKit (Python, MIT).
- `deepseek-ai/deepseek-harness` ("dsh") — the harness layer beneath us (TypeScript, MIT).

Full candidate catalog with value/effort scoring:
[`.claude/reports/research/adoption-candidates.md`](../.claude/reports/research/adoption-candidates.md)
· supporting analysis: [`deepseek-harness.md`](../.claude/reports/research/deepseek-harness.md).

---

## 2026-08-21 — wave 2

| # | Source | Pattern | Verdict | Local proof / owner |
|---|--------|---------|---------|---------------------|
| A2 | ChaosEngine `delegation.md` | Capability tiers, never vendor names, resolved in one table | **Adopted, scoped** | Mechanical for the 29 agent frontmatter lines (`.claude/model-policy.json`, `scripts/gen-model-policy.py --check`) and for every hand-written `--model` literal (`test_model_policy.py::EveryHandWrittenModelNameIsAccountedFor`). **Not** adopted for command invocation sites themselves — those keep concrete models by necessity (no resolver ships downstream) and are enumerated as recorded overrides rather than removed. |
| A3 | ChaosEngine `roles.md` | Role (accountability) chosen separately from capability level | **Adopted** | `accountable_for` + `tier` are distinct fields per role in `model-policy.json` |
| A7 | ChaosEngine trust boundaries | Evidence precedence ladder; retrieved text is evidence, not instruction | **Adopted — prose only, no mechanical check** | `CLAUDE.md` "Evidence precedence". The test only asserts the sentence is present; nothing enforces that agents obey it, and there is currently no way to. Stated here rather than dressed up as a gate. |
| B3 | ChaosEngine `RESEARCH.md` | Dated adoption matrix that records rejections | **Adopted** | this file |
| A5 | dsh `test-support` | Record-once/replay-many fixtures + deterministic fault server, so evals run keyless in CI | **Retained** | Task 010 / wave-2 phase 2; `evals/` skeleton exists, the replay engine does not |
| A6 | ChaosEngine `lifecycle-hooks.md` | "A sentence in the entrypoint is not a load" — the installer must register the event | **Retained** | wave-2 phase 2; the concrete instance is the `disable-model-invocation` contradiction in `.ai/BACKLOG.md` |
| B1 | ChaosEngine `install.py` | Per-file SHA-256 install receipts; unknown/mixed ownership fails closed | **Retained** | wave-2 phase 3; mechanizes the hand-run fleet rule across 16 kitted projects |
| B2 | ChaosEngine (SLSA 1.2) | Commit-pinned install; bounded retries; failed download leaves last good install intact | **Retained** | wave-2 phase 3 |
| A1 | ChaosEngine `guard.py` | Mechanical Definition-of-Done at the Stop hook | **Retained — blocked** | Needs the durable typed event log + single hook dispatcher (enforcement-runtime lane). Recorded in `.ai/BACKLOG.md`. |
| A4 | ChaosEngine `reflection-checkpoints.md` | Failure-fingerprint circuit breaker (same vs different fingerprint) | **Retained — blocked** | Same dependency as A1. Today `loop-operator` does this by prompt judgement. |
| C1–C11 | both | Plan-as-logged-state, Ralph-as-tool, runtime invariants, SQLite FTS session query, layered settings, storage forms, ethics DP1–DP4, work-item contract, orchestrate-by-counting, test-support promotion, cleanup scopes | **Retained — unranked** | Noted in the candidate catalog; none has a local proof owner yet. Do not start without one. |
| — | dsh | Cordis-style plugin system | **Rejected** | Harness-layer concern. ClaudeKit is a policy and enforcement layer with no model client; a plugin runtime would add the coupling the tier table just removed. |
| — | dsh | Capability seams / model adapters | **Rejected** | Presupposes we call models. We do not, and must not gain a client — that is the harness's job. The tier table (A2) gets provider neutrality without a runtime. |
| — | dsh | Sandboxing / agent loop / session runtime | **Rejected** | Same boundary. Also: our security framing is deliberately "denylist speed bump, not a sandbox", and shipping a partial sandbox would make that claim dishonest. |
| — | dsh | Node/TypeScript runtime, npm dependency | **Rejected** | Violates the standing constraints: Python stdlib only, no runtime dependencies, bash 3.2/macOS-safe. |
| — | dsh `goals`/`todos` | Durable goals + todo store | **Rejected (scope)** | ChaosEngine reached the same conclusion independently on 2026-08-15. Ranked below the event log, the merge rule, and the Stop gate. |

### Cross-cutting note

ChaosEngine reviewed dsh on 2026-08-15 and concluded it "adopts the architectural
invariants, not the preview runtime". Two teams reaching that split independently is
the strongest evidence in this table — it is why the Rejected rows above are grouped
around a single boundary (harness vs policy layer) rather than judged one by one.

### Near-duplicate roles this wave exposed

Writing one `accountable_for` sentence per role made overlap visible. Flagged for
task 008 (consolidation), **not** acted on here — merging roles changes routing
behaviour and needs its own plan:

- `code-reviewer` / `python-reviewer` / `typescript-reviewer` — one accountability,
  three language skins.
- `documenter` / `doc-updater` — "author new docs" vs "sync existing docs" is a task
  attribute, not a role boundary.
- `code-simplifier` / `refactor-cleaner` — both own "behaviour preserved, structure improved".

Net asset change this wave: **0** (29 roles before, 29 after). The tier table adds
capability *choice* without adding assets.
