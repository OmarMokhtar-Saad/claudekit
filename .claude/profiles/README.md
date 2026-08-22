# `.claude/profiles/`

Layered profiles for the hook set, asset roster, MCP budget and stack facts.
Inspect them with `ck profile list` and `ck profile show <name> --resolved`.

## What a profile is here — and what it is not

A profile is a **declaration that is mechanically bound to the hooks' own guards**.
It is not (yet) the control. The eleven profile-guarded hooks still read
`ECC_HOOK_PROFILE` exactly as they always have; nothing in this directory changes
what a hook does. What it changes is that the answer to *"which profile is active
and what does that imply"* is now printable, and that the answer cannot drift:
`ck doctor` re-derives every hook's real per-profile mode from the shipped hook
file and fails if a profile here disagrees.

Saying this plainly matters more than it reads. A directory of JSON that looks
like configuration but silently controls nothing is exactly the kind of thing this
repo's review guide calls a `vacuous-check`.

## The four profiles

| Profile | Posture |
|---|---|
| `minimal` | Enforcement hooks stand down. What maintainers develop under. |
| `standard` | The out-of-box default, and the value every hook falls back to. |
| `strict` | Everything on, including the three strict-only gates. |
| `python` | `extends: standard` + Python stack facts and an MCP budget. |

`minimal`, `standard` and `strict` are the three values `ECC_HOOK_PROFILE`
actually takes. `python` is a stack profile: it declares no hook rows of its own.

## Layers

    base -> profile -> project-local -> override

Each layer replaces rows **by id**; a row an outer layer does not mention survives
from the layer beneath, and `ck profile show --resolved` prints which layer won
each row. `base` is a built-in identity (every hook `on`, no budget, no stack
facts) rather than a directory here, so `ck profile list` only ever shows real,
selectable profiles.

- **profile** — the selected `<name>/profile.json`, plus its `extends` chain.
- **project-local** — an optional `local.json` in this directory. Same schema, no
  `name`, no `extends`. Meant to be gitignored per project.
- **override** — `ck profile show --set hooks.<id>=off`, for one-off inspection.

## Row values

- `hooks.<id>` — `on` (runs, may block) · `advisory` (runs, cannot block) ·
  `off` (short-circuits). Three values because `reflection-gate` under `minimal`
  is genuinely the middle one.
- `agents.<id>` / `commands.<id>` — `on` / `off`, with `*` as the default row.
- `mcp.max_servers` / `mcp.max_tools` — non-negative integer or `null`.
- `stack.build_cmd` / `test_cmd` / `lint_cmd` / `coverage_cmd` — string or `null`.

**`agents`, `commands`, `mcp` and `stack` are declarative only in this release.**
No component reads them yet, and every shipped profile leaves the asset rosters at
the base `*: on` — a profile that claimed to disable an agent would be claiming a
selector that does not exist. The sections are present because the layer machinery
is one mechanism across all five, and because the next phase (skill/MCP generators)
consumes them.

## Adding or editing a profile

`schema_version` must be `1`. Unknown keys, unknown hook ids, out-of-range values,
a `name` that disagrees with the directory, and `extends` cycles all fail closed
with a named cause — there is no permissive fallback. After any edit:

    python3 -m pytest tests/test_profiles.py -q
    ck doctor --strict
