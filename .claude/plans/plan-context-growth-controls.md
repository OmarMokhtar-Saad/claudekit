# Plan — context-growth controls: park the web, name the spiral, lower the window

**Tier 2** (several files, no security/schema surface). The parent wrote this plan and
`.claude/plans/ops-context-growth-controls.json` itself (spent, archived as `archive/plan-context-growth-controls.ops.json`), per the Token & Model Policy.
No planner agent: the measurements below were taken in this session, so a planner would
have had to re-derive them from transcripts that are already summarized here.

## The measurement

Session `hermes-agent-20260920-2108`, 30 requests, 1.84M billed tokens, avg context 61k,
prompt-cache hit rate 88.1% (the worst of the day). Body composition:

| part | share | n |
|---|---|---|
| text | 51% (118,430 chars) | 13 |
| `tool_result` | 44% (102,518 chars) | 40 |
| `tool_use` params | 1% | — |

Two findings drive this change.

**1. Five auto-compactions in 29 minutes, accelerating.** Pre-compaction token counts
66,867 / 68,600 / 70,524 / 67,639 / 66,927; intervals collapsing 10.5 → 6.9 → 2.4 →
2.2 min; compaction summaries growing 13,796 → 16,964 → 17,289 → 18,630 → 23,762 chars,
76% of all text in the session. Each summary is re-injected and is larger than the last,
so each cycle starts with less headroom than the one before. That is a spiral, and the
model cannot see it: after a compaction it wakes up with a tidy summary and no idea how
many times it has already done so. Compaction itself stays hugely net-positive — ungated
this session would have billed ~6.1M against an actual 1.84M — so the lever is the
GROWTH RATE, never the window ceiling.

**2. One URL fetched 4 of 10 times.** 10 WebFetch + 6 WebSearch; the repeats were not
recoveries from a failure, they were re-reads of a page whose text had scrolled out of
attention. A fetch bills the whole page in every later request until the next compaction,
so fetching one page four times costs far more than four pages once.

Whole-file reads were the third finding; `read-window-guard.py` already covers the `Read`
tool, and the Bash `cat` path is closed here by lowering the existing output cap rather
than by a new hook.

## Changes

### 1. New advisory hook `.claude/hooks/compaction-cadence.py`

Two events, one script. `PreCompact` appends `{ts, session, cwd, trigger}` to a ledger and
returns 0 — it never blocks, because blocking a compaction only overflows the context it
was called to relieve (hard rule 2 governs blocking hooks; this is deliberately not one).
`SessionStart` fires again with `source="compact"` immediately after a compaction; there
the hook reads the ledger for that session and, when the last gap is under
`CK_COMPACT_MIN_INTERVAL` (300s) or the session has compacted more than
`CK_COMPACT_MAX_CYCLES` (3) times, emits `hookSpecificOutput.additionalContext` telling
the model to finish or abandon the current step and hand back to the user.

`additionalContext` on `SessionStart` is the only channel that reaches the model after a
compaction: `PreCompact` cannot inject text, and an advisory hook's stderr is
transcript-only.

### 2. New advisory hook `.claude/hooks/web-park.py`

`PostToolUse` on `WebFetch|WebSearch`. The FIRST fetch of a URL (or query) is left intact
— the model asked for it — but a copy is written under the research dir and the path is
appended. A REPEAT of the same key in the same session is replaced by a pointer to that
file. Replacement goes through `hookSpecificOutput.updatedToolOutput` and preserves the
response's shape (bare string in, bare string out; dict in, same dict with one key
rewritten). An unrecognised shape is left alone, so the hook can never cost a fetch.

Escape hatch `CK_RAW_WEB=1`; dir override `CK_RESEARCH_DIR`.

### 3. `.claude/hooks/output-filters.json` — `bash-output-cap` 12,000 → 6,000

`read-window-guard.py` bounds the `Read` tool; `cat file.md` through Bash bypasses it
entirely and lands in `tool_result`. The five largest results in the measured session were
10,284 / 8,130 / 7,174 / 6,951 / 6,724 chars — every one of them under the old 12,000 cap.
6,000 trims all five. Nothing is lost silently: the cap keeps a head and a tail around an
inline marker naming the omitted byte count, and `CK_RAW_OUTPUT=1` disables it for one
command. The entry stays LAST in the file so `pytest-progress` still wins for pytest.

### 4. `.claude/settings.json` — `autoCompactWindow` 200000 → 100000

The kit ships 200000 at project level. `install.sh:319` copies that file wholesale into
every managed project, and a project setting outranks the user level — so a kit install
RAISES the window in any project whose owner had lowered it, silently. Measured on this
fleet: with the window at 100000 auto-compact fires at 66–79k and a qa-agents session's
average context fell 96k → 52k (−46%). The shipped value is the one the fleet should get
by default, so it is lowered at the source instead of patched per project.

`test_autocompact_window.py` already asserts a RANGE (`100_000 <= value <= 200_000`), so
only its title and docstring need to follow. `test_fleet_sync_autocompact.py` asserts the
exact literal in five places — four of them track the shipped value and change; the fifth
(line 115, `for value in ('"200000"', "true", "null", "200000.5")`) is a
non-integer-REJECTION loop whose strings are deliberately not the shipped value, and it
is left untouched.

## Files this plan writes

- `.claude/hooks/compaction-cadence.py` — new advisory hook (PreCompact + SessionStart)
- `.claude/hooks/web-park.py` — new advisory hook (PostToolUse/WebFetch|WebSearch)
- `.claude/hooks/dispatch-registry.json` — three inventory rows for the two hooks
- `.claude/hooks/output-filters.json` — cap 12000 → 6000
- `.claude/settings.json` — autoCompactWindow 200000 → 100000, plus the wiring for both
  new hooks (PostToolUse `WebFetch|WebSearch`, PreCompact, SessionStart)
- `tests/test_compaction_cadence.py` — new behavioural coverage
- `tests/test_web_park.py` — new behavioural coverage
- `tests/test_fleet_sync_autocompact.py` — shipped-value literals follow the settings file
- `tests/test_autocompact_window.py` — title and docstring follow the shipped value
- `CHANGELOG.md` — `[Unreleased]` entry

`docs/` component counts are regenerated by `python3 scripts/gen-docs.py --write`, never
hand-edited (hard rule 8).

## Wiring note (why the registry rows are not enough)

Only `PreToolUse` runs through `dispatch.sh` in this kit's `settings.json`; every other
event is wired directly. That matters here: `dispatch.sh` prefixes each advisory handler's
stdout with `[<id>] ` before printing it, which would make a hook's JSON unparseable. Both
new hooks emit `hookSpecificOutput` JSON, so both are wired DIRECTLY in `settings.json`,
exactly as `output_filter.py` already is. Their `dispatch-registry.json` rows are
inventory — they are what `tests/test_structure.py` reads to prove a published hook is
wired rather than inert.

## Verification

`python3 -m pytest tests/ -q` · `ruff check` · `mypy` · `gen-docs.py --check` ·
`gen-registry.py --check` · `gen-model-policy.py --check` · `check-context-floor.py
--check` · `check-plan-artifacts.py --check` · `gen-plan-index.py --check` ·
`shellcheck install.sh .claude/hooks/*.sh`

## Open, owner-gated

Both hooks have been running at user level (`~/.claude/hooks/`, `~/.claude-acct-b/hooks/`)
since 2026-09-20; this plan is what moves them into the kit so `install.sh` carries them.
Release tag and PyPI publish stay user-gated and are NOT part of this change.
