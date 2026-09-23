# ClaudeKit CLI Reference

## Installation

```bash
pip install -e .
```

This makes `claudekit` (and shorthand `ck`) available globally.

## Commands

### `claudekit init [target] [options]`

Initialize ClaudeKit in a project directory.

```bash
claudekit init .                          # Current directory, full mode
claudekit init /path/to/project --minimal # Minimal install
claudekit init . --language typescript    # Pre-configure for TypeScript
claudekit init . --force                  # Overwrite existing installation
```

**Options:**
| Flag | Description |
|------|-------------|
| `--mode full\|minimal` | Installation mode (default: full) |
| `--language LANG` | Pre-configure for language |
| `--force` | Overwrite existing installation |

### `claudekit doctor`

Run health checks on the current ClaudeKit installation.

```bash
claudekit doctor                  # exit 0 on pass/warn, 1 on failure
claudekit doctor --strict         # treat warnings as failures (exit 1)
claudekit doctor --min-score 90   # exit 1 if the readiness score is below 90
claudekit doctor ../other-project # check another project (default: current directory)
```

Checks: Python version, Bash, Git, agents, commands, skills, hooks, registry integrity, config validity, and `.claude/skills-profile.json` when present.

The last line is a verdict and the next step, e.g.
``FAIL 1/9 failed — next: run `ck init` ``. The step is the command a failing check
declares (`ck init`, `ck update`, `chmod +x ...`); a check with no single unconditional
command points at its line instead. The streamed detail above it is unchanged.

Every run ends with a **readiness score** out of 100, so two healthy installs
no longer read identically green. The line names its denominator, because the
denominator is what makes two scores comparable or not:

```
  Readiness: 95/100 (29 applicable, 0 not)      # a fresh --full install
  Readiness: 100/100 (13 applicable, 10 not)    # a fresh --minimal install
```

A passing check is full credit and a warning is half; checks that do not apply
to your install (`Skipped`) are left out of the score entirely, so a
`--minimal` install is not penalised for what it was never meant to have.

**That means scores compare within an install mode, not across them** — and, as
above, a `--minimal` install normally scores *higher* than the `--full` install
that contains it. Nothing is wrong when that happens: `--minimal` drops the
checks capable of warning, while a fresh `--full` install keeps three warnings
for the project commands you have not configured yet. Those are the same
warnings `install.sh` closes on, and they are deliberate — configure
`build/test/lint_cmd` in `.claude/hooks/config.json` and the full install goes
green.

`--min-score N` turns the number into a gate — useful as the exit condition for
`/adapt`, or as a fleet floor in CI **for one install mode**. It can only *add*
a failure: an install with a failing check still exits 1 regardless of the floor
you set.

### `claudekit diff [target]`

Show which ClaudeKit-managed files you've locally modified, using the install
manifest (`.claude/.claudekit-manifest.json`, per-file sha256). When the kit
source is also available, modified files are refined into `locally modified`
(you edited it), `kit-updated` (the file already matches a newer kit), or
`both changed`; files you added under `agents/ commands/ skills/ hooks/` are
listed as `custom`.

Pre-manifest installs (before v2.1) don't error: `diff` falls back to comparing
the project's managed assets directly against the kit source, classifying each
file as `identical` / `differs` / `custom` / `not installed`. Provenance is
unknown in this mode — `differs` may be a local edit or just an older kit
version.

```bash
claudekit diff              # report modified/missing/unchanged/custom files
```

### `claudekit update [target]`

Re-install ClaudeKit over an existing project. Detects locally-modified managed
files and warns before overwriting; the installer stages + backs up the previous
`.claude/` first (recoverable). Reuses the mode/language from the manifest.
Project-custom assets (files under `agents/ commands/ skills/` that the kit
doesn't manage) are preserved across the update.

Pre-manifest installs work too: `update` warns, asks for confirmation (or
`--yes`), reinstalls in full mode, and writes a manifest so the next update is
precise.

```bash
claudekit update            # prompts if local edits would be overwritten
claudekit update --yes      # non-interactive
```

### `claudekit fleet <list|diff|update|verify>`

Survey and update every kitted project under one root, so syncing a kit change into
the fleet is one permitted command instead of a hand-written script per change.

A project is a fleet member when it is an **immediate child** of `--root` (default: the
parent of the current project) and carries `.claude/.claudekit-manifest.json`. Membership
is never a hardcoded list: a list cannot distinguish "up to date" from "forgotten". The
walk does not recurse, and it skips backup directories (`*.bak-*`), the kit source itself
and any git worktree of it. `--include`/`--exclude` take glob patterns on the directory
name (repeatable).

```bash
ck fleet list                      # repo, branch, manifest version/mode, dirty count
ck fleet diff                      # per project: untouched / locally-modified / missing
ck fleet update --dry-run          # a real plan: what would be overwritten and preserved
ck fleet update --yes              # run `ck update` per project (each backs up first)
ck fleet verify                    # exit 1 if any project drifted from the kit source
```

`update` reuses `ck update` per project, so backups and the preservation of local edits are
exactly as documented above, and it exits non-zero if any project failed. `verify` treats a
file as drift when it is byte-different from the kit source *while still matching its
manifest hash* (untouched downstream, but stale); a file the manifest already records as
locally modified is allowed.

`fleet` never runs git. Committing downstream is yours to do — after an update it prints the
suggested line per project:

```
git -C <repo> add -A .claude .agents .gitignore
```

### `claudekit uninstall [target]`

Remove ClaudeKit-managed files (per the manifest), moving them to a timestamped
`backups/uninstall-<stamp>/` first so the removal is recoverable.

```bash
claudekit uninstall --dry-run   # list what would be removed
claudekit uninstall --yes       # remove (non-interactive)
```

### `claudekit eject [target]`

Leave ClaudeKit management while keeping every file. `init`/`update` adopt a
project and `uninstall` removes the kit from it; `eject` is the step in
between, for a project that wants to keep its assets and stop tracking the kit.

```bash
claudekit eject --dry-run   # report what would change
claudekit eject --yes       # eject (non-interactive)
```

It removes exactly one file — the manifest — after writing its full contents
into `.claude/.claudekit-ejected.json` in its place. No asset is rewritten or
deleted, and local modifications are preserved by design (unlike `uninstall`,
eject has no reason to refuse on them). Afterwards:

- `claudekit diff` compares against the kit source rather than a receipt,
  because provenance is genuinely unknown once the receipt is gone.
- `claudekit uninstall` reports that there is nothing kit-owned to remove.
- `claudekit update` re-adopts the project, so ejecting is reversible.

The eject record keeps every path and digest the manifest held, so the
provenance survives even though the manifest does not.

### `claudekit eval`

Run behavioral evals against the prompt corpus (task 010): each eval spawns a real agent
in an isolated fixture workspace and asserts on its *behavior* — artifacts extractable and
valid, refutation catches planted defects, no fabricated verification numbers, reported
counts match executed ground truth. Complements the structural test suite, which only
asserts the prompt text.

```bash
claudekit eval --list       # available evals
claudekit eval --dry-run    # validate definitions + workspace build (free)
claudekit eval              # run all (real API calls, ~$0.2–1.5 per eval)
claudekit eval --only planner-delivers-artifacts
```

Definitions live in `evals/definitions/*.json`; fixtures in `evals/fixtures/`. Run after
any prompt-corpus change and before releases.

### `claudekit check-command "<cmd>"` / `claudekit check-path <path>`

Validate a shell command or file path against the security layer (a denylist
speed bump — see `docs/HOOKS.md` and `SECURITY.md`). Exit 0 = allow, 2 = block.

```bash
claudekit check-command "rm -rf /"       # exit 2, reason on stderr
claudekit check-path /etc/passwd         # exit 2
```

### `claudekit validate <ops.json>`

Validate an operations config file.

```bash
claudekit validate operations/my-plan/ops.json
claudekit validate ops.json --verbose
```

### `claudekit execute <ops.json>`

Execute an operations config with automatic backup.

```bash
claudekit execute ops.json --dry-run    # Preview changes
claudekit execute ops.json              # Apply changes
claudekit execute ops.json --verbose    # Debug output
```

### `claudekit implement <ops.json>`

Run the whole implementation path for one operations config: validate -> dry-run ->
execute -> the validation commands the owning plan names for itself. It stops at the
first stage that does not exit 0 and prints exactly one `RESULT:` line.

```bash
claudekit implement .claude/plans/ops-my-change.json
claudekit implement ops.json --no-approval      # skip the review-record gate
claudekit implement ops.json --plan PLAN.md     # name the plan explicitly
```

The plan is resolved from the config name (`ops-<slug>.json` -> `plan-<slug>.md`,
beside the config and then in `.claude/plans/`). Its validation commands are the first
fenced block under a `## Validation commands`, `## Testing Strategy`, `## Tests` or
`## Verification` heading. They run **without a shell**, so a command carrying a pipe,
redirect or chain is reported as skipped rather than reinterpreted.

### `claudekit flow "<task>"`

The whole pipeline, headless, in one command: `claude -p --agent planner` writes the
plan and its ops.json (saved under `.claude/plans/` from the agent's stdout, since
headless agents cannot write there), `--agent reviewer` scores it, `review-record.py
write --from-review` records the verdict, `execute-json-ops.py` applies it with the
approval gate on and runs the plan's validation commands, and `--agent verifier` gets
that captured output so it verifies instead of rerunning. Every agent runs with its
scoped `--allowedTools` and `--output-format json`; the usage block of each run is the
table printed at the end (turns, average context per turn, rebilled input tokens,
cost). A review that does not authorise execution stops the chain with exit 2 and no
edit to the tree.

```bash
ck flow "add a --json flag to ck doctor"
ck flow "..." --python /path/to/.venv/bin/python   # interpreter for the ops scripts
ck flow "..." --model reviewer=sonnet --model verifier=haiku
ck flow "..." --slug doctor-json --claude /opt/bin/claude   # or $CK_CLAUDE_BIN
```

In a git worktree `--python` defaults to the main checkout's `.venv/bin/python` when it
exists. Artifacts: `plan-<slug>.md`, `.ops.json`, `.review.md`, `.verify.md` under
`.claude/plans/`.

### `claudekit rollback`

Rollback from a previous backup.

```bash
claudekit rollback --list               # List available backups
claudekit rollback --backup backups/my-plan-20260316-120000  # Restore
claudekit rollback --backup <dir> --dry-run  # Preview restore
```

### `claudekit agents`

List all installed agents with their metadata.

```bash
claudekit agents
```

### `claudekit config [key]`

Show or query configuration.

```bash
claudekit config                        # Show full config
claudekit config project.build_cmd      # Query specific key
```

### `claudekit skill new <name> --description "<trigger line>"`

Scaffold a skill **and register it** in `.claude/skills/skills-registry.json`. The two
are one act: an unregistered skill is drift, so there is no flag that writes the
directory alone.

```bash
claudekit skill new widget-forge --description "Use when forging widgets"
claudekit skill new internal-notes --description "..." --invisible   # no always-on cost
```

Refused, with the numbers, when the description would push the always-on context floor
over budget — a description is charged to every session, forever.

### `claudekit skill audit` / `skill profile init` / `skill card` / `skill match`

Measure how the installed skills fit **this** project. All four are read-only analysis:
none of them edits a skill, installs one, or changes what a model sees. The one verb
that does change what a model sees is `claudekit skill apply`, below.

```bash
claudekit skill audit                   # stacks, per-skill tokens, relevant/irrelevant/broken
claudekit skill audit --json --save     # also writes .claude/reports/skills/audit.json
claudekit skill profile init            # writes .claude/skills-profile.json if absent
claudekit skill card > my-project.json  # sanitized cards for this project's own skills
claudekit skill card --publish          # write them to ~/.claudekit/registry/cards/<project>.json
claudekit skill match                   # suggest skills other projects published, by tag overlap
claudekit skill match --registry cards/ --min-score 0.2   # another directory, stricter floor
```

- **audit** detects the project's stacks (the same manifest detection `claudekit adapt`
  uses, plus a count of source files: 20 or more `.java` files means `java`), estimates
  each skill's tokens as chars/4, and buckets it: *relevant*, *irrelevant* (tagged for a
  stack this project does not have), or *broken* (no frontmatter, no name or description,
  or a relative link to a file that does not exist). Bodies over `--max-lines` (300) or
  `--max-tokens` (2000) are flagged. A skill is never called irrelevant when no stack was
  detected. Nothing is written unless you pass `--save`.
- **profile init** writes `.claude/skills-profile.json` with the irrelevant skills listed
  under `disabled`. It refuses if the file exists -- it is your file. Keys: `packs`,
  `disabled`, `overlays` (skill name -> project-relative file), `roles`. Install, update
  and fleet sync leave it untouched. `disabled` is enforced by `claudekit skill apply`;
  `disabled_mode` (`off`, the default, or `user-invocable-only`) picks the value it
  writes; `packs` and `roles` are validated for shape only.
- **card** prints metadata cards -- name, `stack_tags`, description, estimated tokens --
  for skills the install manifest does not list as kit-owned. No body and no path leaves.
  A description that looks like a secret, credential or home-directory path is withheld
  (named on stderr, never quoted). Without an install manifest it refuses. A project skill
  declares its stacks in frontmatter: `stack_tags: [python, go]` (explicit always wins;
  `stack_tags: []` opts out). Without it, tags are derived: a word-boundary scan of the
  skill's name, description and body for stack words (java, kotlin, python, typescript,
  android, ios, appium, selenium, intellij, spring boot, gradle, maven, pytest, react,
  ...), unioned with the project's detected stacks. Kit skills are never derived.
  `--publish` writes the cards to the user-level registry -- `$CLAUDEKIT_REGISTRY` (must
  be absolute) or `~/.claudekit/registry/cards/` -- as `<project>.json`, atomically,
  replacing that project's previous file. `--project <id>` overrides the directory name.
- **match** reads every `*.json` card file in the registry (default: the user-level one
  above; `--registry DIR` for another), re-validates each card, skips this project's own
  card file, and suggests cards not already installed whose `stack_tags` overlap this
  project's tags (detected stacks plus its own skills' tags). Score is Jaccard overlap;
  suggestions under `--min-score` (default 0.1) are dropped. A card that shares only a
  base language (java, kotlin, python, typescript, go, rust) is dropped too; pass
  `--include-language-only` to keep it. Each line shows the score and the source
  project. It never installs anything.

`claudekit doctor` checks `.claude/skills-profile.json` when it exists: a malformed file
or an overlay path outside the project fails; a skill name that is no longer installed
warns (and names its rename, if the registry has one).

### `claudekit skill apply` / `skill apply --restore`

Enforce the profile's `disabled` list so those skills stop costing always-on context.

```bash
claudekit skill apply            # write skillOverrides for the profile's disabled skills
claudekit skill apply --restore  # remove every override apply wrote
```

`apply` uses Claude Code's `skillOverrides` setting. For each installed skill in
`disabled` it sets the override to `off` (or `user-invocable-only`, if the profile says
`"disabled_mode": "user-invocable-only"`) in `.claude/settings.local.json` -- the
project-local, gitignored settings file. No skill file is edited, so `claudekit diff`
reports nothing. A hidden skill is still installed.

- **Merges, never clobbers.** Every other key is preserved, including `env`
  (`ECC_HOOK_PROFILE`) and `permissions`. An override you set yourself is never taken
  over or removed. The file is rewritten with 2-space JSON indentation when something
  changes. An unparseable or symlinked settings file is refused.
- **Records what it owns.** The names apply manages live in `.claude/skills-applied.json`.
  `--restore`, or removing a name from `disabled` and re-running `apply`, removes an
  override only while it still holds the value apply wrote.
- **Protected.** `golden-rule`, `security-checklist`, `prompt-injection-defense`,
  `verification-before-completion`, `using-superpowers`, any skill the registry marks
  mandatory, any skill an installed agent preloads through `skills:` frontmatter (a hidden
  skill cannot be preloaded) and any skill an agent loads as mandatory. A profile naming
  one is refused whole, before anything is written -- the profile is a file in your
  repository, and hiding the safety rails is what a hostile change would try.
- **update / init** re-apply the profile after reinstalling (settings.local.json itself is
  preserved by the installer).
- **doctor** reports how many skills `skillOverrides` hides and the estimated always-on
  tokens saved (chars/4); warns when the profile and the settings diverge; and fails when
  `settings.json` or `settings.local.json` hides a protected skill, profile or not.

### `claudekit mcp add <name> --tools N -- <argv>` / `claudekit mcp list`

Register an MCP server against the active profile's `mcp` budget (`max_servers`,
`max_tools`) and refuse — naming current vs limit — when it would exceed it. A server's
tool schemas are injected into every session, so this is an always-on cost, not a
per-use one.

```bash
claudekit mcp add context7 --tools 2 -- npx -y @upstash/context7-mcp@3.2.5
claudekit mcp list
```

`--tools` is required and has no default: a default of zero would make the `max_tools`
budget pass for free. The count comes from the server's own documentation — ClaudeKit
does not run the server to measure it, because that would mean executing third-party
code from a `ck` verb. Servers already listed in `.mcp.json` by hand count towards
`max_servers`; if one has no recorded tool count, `mcp add` refuses rather than treating
the unknown as zero. Recording it is the remedy and needs no extra verb: `claudekit mcp
add <that name> --tools N` **adopts** a server already present in `.mcp.json` — it writes
the tool count and changes no configuration. Because adoption records a cost you are
already paying rather than adding one, the budget reports an over-budget result as a
warning instead of refusing it; the next genuine addition is refused normally.
`claudekit mcp list` shows config-only servers with an `unknown` tool count, so what you
see matches what the budget counts.

`claudekit skill new` finishes by naming `python3 scripts/gen-docs.py`: component counts
are generator-owned, and a new skill changes the skill count, so that generator has to be
re-run in a checkout of this repo. Installed projects have no `scripts/` tree and get
`ck doctor` instead.

### `claudekit profile list` / `claudekit profile show [name] [--resolved]`

Inspect layered hook/asset profiles. `--resolved` prints the composed result with each
row attributed to the layer that won it.


### `claudekit profile <list|show> [name]`

Inspect layered hook/asset profiles. Profiles **declare** the hook set and are bound to
the hooks' own guards by `claudekit doctor`; they do not drive the hooks, which still read
`ECC_HOOK_PROFILE`. See `.claude/profiles/README.md`.

```bash
claudekit profile list                     # installed profiles, and which is active
claudekit profile show python              # the raw profile document
claudekit profile show python --resolved   # composed, with each row's winning layer
claudekit profile show python --json       # same, machine-readable
claudekit profile show minimal --set hooks.ops-enforcement=on   # override layer
```

Layers compose `base -> profile -> project-local -> override`, each replacing rows by id.
An unknown or malformed profile fails closed with a named cause and exits 1.

### `claudekit memory <add|list|show|check>`

Project-local memory in `.claude/memory/entries.jsonl`, with two rules enforced
mechanically rather than trusted:

- **Evidence precedence.** Each memory stamps the sha256 of every file it cites. `check`
  re-derives them, so a memory whose evidence changed reports `STALE` and one citing
  nothing reports `UNVERIFIABLE` — never `FRESH`. Current files outrank memories.
- **Retrieved text is evidence, not instructions.** Imperative shapes in a body are
  surfaced on every read path as **findings**, under that heading. The store never acts
  on them. It is a shape scanner, not an injection defence — it names its blind spots
  (questions, passive voice, other languages, unusual filler openers, deliberate
  obfuscation) and you should read a memory as untrusted text regardless.

Secrets, credential-shaped tokens, private absolute paths, transcripts and raw log dumps
are refused **before** anything is written.

```bash
claudekit memory add --kind decision --title "Why X" --body "..." --evidence src/x.py
claudekit memory list           # every memory with its freshness verdict
claudekit memory show <id>      # body, evidence status, directive findings
claudekit memory check          # exit 1 if any memory no longer matches the tree
```

`--kind` is one of `decision`, `constraint`, `reference`, `observation`.
