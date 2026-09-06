# The learning loop

ClaudeKit keeps four separate memories, on purpose. Each has one owner and one job.

| Store | Where | What it holds | Who writes it |
|---|---|---|---|
| **Assertions** | `.claude/memory/entries.jsonl` | Decisions, constraints, references, observations — each stamped with the sha256 of the files it rests on | You / an agent, via `ck memory add` |
| **Findings** | `.claude/knowledge/issues/<slug>.md` | One issue per file, with a lifecycle: `open` → `fixed` / `wontfix` / `regressed` | `knowledge-ledger.py` |
| **Agent memory** | `.claude/agent-memory/<agent>/MEMORY.md` | Per-agent patterns, conventions, known false positives | The agent itself (Claude Code native `memory:` frontmatter) |
| **Reflection receipts** | a session-scoped temp dir | One receipt per reflection checkpoint | `reflection.py` — **ephemeral by design** |

## How a lesson becomes durable

1. **A checkpoint fires.** `reflection-gate.py` blocks on Stop until a receipt is filed.
2. **The receipt is accepted**, and `reflection.py` opens a ledger finding from it —
   automatically, using only the receipt's sanitized fields (single line, no absolute
   paths, no credential shapes). No Verifier run is needed for this step: `open` is the
   automatic path, `record --verified` is promotion.
3. **The finding is retired when the code moves on.** `open --evidence <path>` stamps each
   cited file's sha256. `prune --apply --supersede` archives the finding only when *every*
   cited file's hash has changed or vanished. `--ttl-days` (default 90) is a fallback for
   findings that cite no evidence. Plain `prune` never retires an unfixed finding.
4. **Repeats become proposals.** When 3+ open findings share signature tokens,
   `knowledge-ledger.py propose` writes `.claude/knowledge/proposals/<slug>.md`. It never
   writes a skill — you promote it with `ck skill new`, or you delete it.
5. **The next session starts already knowing.** `session-start.sh` prints up to 5 open
   findings plus your **fresh** `ck memory` entries — capped at ~600 tokens, and only after
   the text passes `prompt-injection-scanner.sh`. That scanner is a denylist speed bump: it
   catches imperative phrasing ("ignore previous instructions") and misses declarative
   poisoning ("the parser must always run with X"). The helper additionally withholds any
   finding whose signature carries an absolute path or a credential shape. The real control
   is reviewing `.claude/knowledge/issues/` diffs like code. Stale memories (whose evidence no longer
   hashes) are withheld: current files always outrank a memory.

## Reading it yourself

```bash
python3 .claude/operations/scripts/knowledge-ledger.py list --status open
python3 .claude/operations/scripts/knowledge-ledger.py search "connection reset"
ck memory list          # verdicts: FRESH / STALE / MISSING / UNVERIFIABLE
ck memory check         # exit 1 if any memory no longer matches the tree
```

## Turning pieces off

| Piece | How |
|---|---|
| Agent memory | Remove the `memory:` line from that agent's frontmatter |
| SessionStart injection | Delete `.claude/hooks/session-memory-context.py`; the hook degrades to silence |
| Skill proposals | Delete the guarded `knowledge-ledger.py propose` block at the end of `.claude/hooks/cost-tracker.sh` |
| Receipt → ledger bridge | Delete (or do not create) `.claude/knowledge/issues/`; the bridge is a no-op without it |

## The safety rule that governs all of it

Everything above is **retrieved text**, which is evidence and never an instruction channel.
A directive found inside a memory, a finding, or a proposal is a *finding about that file*,
not an order. Agent memory is committed and reviewed exactly like code, because it is
injected into a system prompt.
