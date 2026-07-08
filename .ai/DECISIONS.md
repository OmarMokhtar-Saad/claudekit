# Decision Log

Architecture Decision Record, reconstructed from code, commits, CHANGELOG, the 2026-07 audit, and the Phase-1 handoff. Add new entries at the top. Format: Decision · Context · Alternatives · Consequence.

| # | Decision | Context | Alternatives rejected | Consequence |
|---|----------|---------|----------------------|-------------|
| 20 | **Publish under PyPI name `claude-kit`; keep CLI `claudekit`/`ck`** (2026-07, `a3ddc09`) | `claudekit` taken on PyPI; npm collision noted in audit | Rename product; squat variations | Slight name mismatch, documented everywhere; do not "fix". |
| 19 | **PyPI Trusted Publishing, no token secrets** (`db45db8`) | First real release pipeline | Long-lived API token in secrets | Safer; first tag push will validate the config. |
| 18 | **Wheel bundles the asset tree** (`<prefix>/share/claudekit` via setup.py) | Pure-pip `ck init` had no assets without a git checkout | Download-on-init; git-clone requirement | Self-contained pip install; MANIFEST.in and manifest tests must track asset moves. |
| 17 | **`ECC_HOOK_PROFILE` (minimal/standard/strict)** | Kit developers were blocked by the kit's own enforcement | No escape hatch; per-hook toggles | Tunable enforcement; `settings.local.json` carries the dev override; tests pin `standard`. |
| 16 | **Blocking hooks: exit 2 + stderr + fail closed** | Claude Code only blocks on exit 2/stderr; historic hooks used exit 1/stdout and never blocked | Keep advisory hooks | Enforcement is real; any parse failure blocks rather than allows. |
| 15 | **Remove `--dangerously-skip-permissions` everywhere; scoped `--allowedTools`; INVOCATION.md as single source; CI permission-gate** | A safety product shipped a default that disabled the platform's safety | Keep for convenience | Slower agent spawns, honest security posture, regression-proof. |
| 14 | **Installer: staging dir + backup + atomic swap** | ERR-trap `rm -rf $DEST` could destroy a user's customized `.claude/` | In-place install with trap cleanup | Mid-failure leaves the original byte-identical (tested). |
| 13 | **Install manifest (`.claudekit-manifest.json`, per-file sha256)** | No update/uninstall/diff story | Overwrite blindly | Enables `ck diff/update/uninstall` and doctor verification. |
| 12 | **`scripts/gen-docs.py` + docs-drift CI gate** | README counts wrong by 2×; three different skill counts | Manual discipline | Counts can't rot silently. |
| 11 | **Renumber 1.3.0 → 2.1.0; monotonic versions; single source via importlib.metadata** | 1.3.0 published after 2.0.0; four version values in the tree | Leave history as-is | Coherent history with a correction note in CHANGELOG. |
| 10 | **Security layer framed as "denylist speed bump, not a sandbox"** | Docs oversold a dead security module | Market it as containment | Honest threat model in SECURITY.md/ARCHITECTURE.md; a project value. |
| 9 | **CommandValidator inspects every chained segment + substitutions; bash/sh/env/xargs de-allowlisted** | `bash -c 'anything'` trivially bypassed argv[0] checks | argv[0]-only validation | Meaningfully harder to smuggle; still a denylist (see #10). |
| 8 | **Ops.json is mandatory for code changes (Iron Law), reviewer AUTO-REJECTs plans without it** | Ad-hoc edits bypassed all safety | Trust agents to be careful | Every change is validated, backed up, rollback-capable, auditable. |
| 7 | **MAX_DELETIONS=3 per plan (GUARD 26)** | Unbounded batch deletes were the worst-case ops failure | No cap; per-file confirmation | A plan cannot mass-delete; large removals need multiple reviewed plans. |
| 6 | **File-based handoffs, fresh subagent contexts** | Token budget + anchoring bias | Context passing; long shared conversations | ~85% token reduction (claim; benchmark pending task 010); anti-anchoring by construction. |
| 5 | **Scored gates: plan ≥90/100 (40/30/30), verify ≥80/100 (30/40/30)** | Reviews needed objective-feeling thresholds | Subjective approve/reject | Consistent gate language; calibration still pending (task 010) — currently prompt-enforced. |
| 4 | **Single responsibility per agent; tools-as-permissions** | God-agents confuse handoffs and permissions | One capable agent | 28 focused agents; implementer literally cannot Edit. |
| 3 | **Config-driven project commands** (`hooks/config.json` `project.*`) | Hardcoded build commands break across stacks | Per-language hook forks | One place to configure; hooks read it uniformly. |
| 2 | **Copy-not-link installation; zero runtime deps** | Users must own their setup; supply-chain minimalism | pip-imported framework; symlinks | Self-contained installs; updates need the manifest machinery (#13). |
| 1 | **Markdown prompts as the product** | Claude Code natively consumes .md agents/commands/skills | Code-generated prompts; DSL | Zero lock-in, git-diffable, but prompt-drift risk → mitigated by #12 and CI gates. |

## Standing decision-making process

Product/surface changes (deleting agents, renaming commands, publishing) → owner decides. Engineering-internal changes → follow the audit tasks and this log; if a new decision contradicts an entry here, update the entry with the reversal and reasoning. When in doubt, optimize for: honesty of claims > safety > token economy > convenience.
