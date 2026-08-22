# Plan — `ck mcp add --probe` (addendum, owner-gated)

**Tier:** 3 (executes third-party code)
**Slug:** `mcp-probe-addendum` — declared by `.claude/plans/ops-mcp-probe.json`, whose
filename deliberately does not match: the probe is an addendum to a shipped plan, not a
plan of its own lineage.
**Status:** QUEUED, not executed. Owner-gated and unchanged by the change that added
this document.

## Why this exists as a separate config

`--probe` was **cut from the core** of `ops-generators-that-cannot-drift.json` at that
plan's round-1 finding C2 ("`--probe` mitigation does not mitigate"), applied in its
revision 2, and prepared separately so the core carried no execution surface at all.
The fork is the owner's; neither branch was chosen there.

## What the config carries

Two operations, both `file_create`:

- **`src/claudekit/mcp_probe.py`** — the probe itself. It executes third-party code, so
  its framing stays honest: the denylist allowlists `npx`/`node`/`docker` and gives no
  isolation. A typed-out acknowledgement flag, a scrubbed environment (PATH/HOME/LANG
  only), and `Popen` + `killpg(TERM -> KILL)` are the mitigations, not a sandbox.
- **`tests/test_mcp_probe.py`** — its behavioural coverage.

## Why this document exists at all

`scripts/check-plan-artifacts.py` resolves a config's plan by filename **and** by the
config's declared `plan` field. Before that, a config whose declared slug matched no
document was reported OK with every operation unchecked — this config was the live
instance, and both paths above were invisible to the gate. Recording them here is what
makes the gate able to see them; a config no plan describes cannot be reviewed against
one.

## Out of scope

Executing this config (owner-gated). The `--probe` design itself, settled at the
round-1 C2 correction of `plan-generators-that-cannot-drift.md`.
