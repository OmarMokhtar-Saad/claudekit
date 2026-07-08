# FAQ — Questions a New Maintainer Will Ask

**Why is the PyPI name `claude-kit` but everything else `claudekit`?**
The PyPI name was taken. CLI (`claudekit`/`ck`), import package, and repo keep `claudekit`. Deliberate; don't unify.

**Is there Python "application code" here, or is this all prompts?**
Both. The product is the prompt/hook corpus; `src/claudekit/` is the delivery shell (CLI) plus the security layer. The operations scripts in `.claude/operations/scripts/` ship *into user projects* and stay dependency-free.

**Why does the repo block my edits when I work on it?**
It runs its own enforcement hooks. Set `ECC_HOOK_PROFILE=minimal` via `.claude/settings.local.json` ([DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md)).

**Why do both `*.ops.json` and `ops-*.json` exist?**
Historic split-brain that once made validation match zero files. Both are now valid; `lib.sh` OPS_FIND_EXPR is the single pattern. Don't standardize one away without migrating everything.

**Why 2.1.0 when CHANGELOG shows a 1.3.0 dated after 2.0.0?**
Versioning mistake, corrected: that entry was renumbered 2.1.0 with a note. Versions are monotonic from now on.

**Are the 90/100 and 80/100 gates real?**
They're consistently prompted, but not mechanically enforced or calibrated yet — that's task 010. Don't describe them as hard guarantees in docs.

**Is the security layer a sandbox?**
No, and it must never be described as one. Denylist speed bump; honest framing is a project value (see [SECURITY_GUIDE.md](SECURITY_GUIDE.md)).

**Which docs are for whom?**
README + `docs/` = users of the kit. `.ai/` + CLAUDE.md + CONTRIBUTING = maintainers. `review/` = frozen audit history. Templates/examples = artifacts users receive.

**Where do I find what to work on?**
[BACKLOG.md](BACKLOG.md) (prioritized) → `review/tasks/0XX-*.md` (file-level specs).

**Why not merge the obviously duplicate agents/skills right now?**
Deletions change user-visible surface — owner sign-off first (task 008). Prep work (migration table) is welcome.

**Can I publish a release?**
No — user-gated. Prepare everything ([PLAYBOOK.md](PLAYBOOK.md)); the owner pushes the tag (or explicitly approves).

**Why zero runtime dependencies?**
Product feature: installs are copy-not-link, self-contained, supply-chain-minimal. jsonschema is an optional extra only.

**What breaks most often?**
macOS/bash-3.2 shell issues, path resolution after layout moves, registry dangling refs after renames, docs-count drift. All CI-gated now.

**What's the single most dangerous file to edit carelessly?**
`.claude/operations/scripts/validate-config-json.py` (weakened guards silently remove user-facing safety), followed by `.claude/settings.json` (mis-wired hooks = enforcement vanishes) and `install.sh` (user-data destruction history).

**Who is the human in the loop?**
Omar Mokhtar (owner). Release timing, asset deletions/renames, and the plugin-packaging bet are his calls.
