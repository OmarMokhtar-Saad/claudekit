# Roadmap

Condensed from `review/roadmap.md` (the authoritative long-form, 2026-07-05) with Phase-1 completion applied. Priorities: [BACKLOG.md](BACKLOG.md); current snapshot: [STATUS.md](STATUS.md).

## Now — ship v2.1.0

Tag + PyPI publish (user-gated; recipe in [PLAYBOOK.md](PLAYBOOK.md)). Everything else in the v2.1 exit criteria is already met: clean `ck init && ck doctor`, demonstrable hook blocking, no doc/version drift, honest CI.

## Next — v3.0 "Real Product" (1–2 quarters)

| Theme | Task | Essence |
|-------|------|---------|
| Plugin packaging | 007 | `.claude-plugin/plugin.json` + marketplace.json; `/plugin install` becomes the primary channel; optional sub-plugin split (security/prp/opensource). **The strategic bet.** |
| Manifest-driven everything | 005/007 | Repo-root `claudekit.manifest.json` drives installer, doctor, CI counts, docs; `ck update` becomes a true three-way merge; managed (`.claude/claudekit/`) vs user (`.claude/local/`) split on disk. |
| Eval framework | 010 | Fixture repos + golden ops.json, `ck eval`, structured review/verify verdicts, hook-gated thresholds — the 90/100 gate stops being prompt theater; benchmark the token-reduction claim. |
| Corpus consolidation | 008 | Agents 28→~20, skills 73→~60, delete templates/skills dupes, commands ≤40 lines, registry-generated skill sections. |
| Context budget | 009 | ≤2 mandatory skill loads w/ digests; kill registry double-loading (~7K/session); one hook dispatcher per event (~100 ms/call). |
| Security completion | 002-rest/014 | Hook-enforced loop block-list; sandbox profile pack (interactive/gated/autonomous presets); signed releases, SHA256SUMS, SLSA, pinned MCP servers. |
| Tests & OSS health | 012/013 | Behavioral upgrades for v2.0 asset suites; CoC, CODEOWNERS, labels, demo GIF, MkDocs site. |
| DX | — | `ck lint`, `ck new skill|agent|command`, `--json`/`NO_COLOR`, consumer GitHub Action. |

## Later — 12–24 months (from roadmap §3)

Marketplace-first distribution with third-party sub-plugins gated by `ck lint` + eval CI · published nightly eval dashboards (prompt CI as a category first) · ClaudeKit MCP server exposing the ops engine (validate/execute/rollback as MCP tools) · real observability (`ck cost` from OTEL data, `ck trace` pipeline timelines) · Python-based cross-platform installer + single-dispatcher hooks (Windows support) · autonomy with containment (mechanical loop-operator wiring, sandbox-required autonomous mode, risk-based auto-escalation to Santa/GAN) · team features (shared constitutions, org marketplaces, review-score metrics).

## Sequencing logic

Publish first (credibility), consolidate second (everything after touches fewer files), evals third (grounds the quality claims the marketing depends on), plugin bet in parallel once the corpus is stable.
