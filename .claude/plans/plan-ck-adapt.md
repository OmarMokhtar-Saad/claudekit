# Plan — Phase 2: `ck adapt`, one entry that makes ClaudeKit work on any project

**Tier:** 3 (writes into a target project; reversibility and ownership are security-relevant)
**Slug:** `ck-adapt` — plan and ops filenames share it.
**Ops config:** `.claude/plans/ops-ck-adapt.json` — NOT yet authored. Phase 1b is green
(landed `34a4140`), and this plan is **APPROVED 92/100** (Plan Quality 88 / Architecture 95 /
Security 97) at base `b35cd22` after four review rounds: 61 (one global receipt rule), 74
(a split drawn by file name), 61 (5 blockers — membership leaks, classification after an
install that regenerates the manifest, a receipt re-stamp conferring delete rights, and a
false safety claim about `ck update`), 87/88 (local sweeps), then 92. The post-implementation
adversarial pass belongs to `code-reviewer`, which can execute: none of the 21 proofs below
was settled by reading.

## The task-008 answer, first, because it shapes everything

**Adaptation already exists at the prompt layer.** `.claude/commands/adapt.md` (48 lines)
and `.claude/skills/project-adaptation/SKILL.md` (85 lines) already tell a model how to
detect a project's four commands "from the project's own CI/Makefile/scripts… Prefer what
CI runs over what docs claim."

So `ck adapt` must NOT be a third adaptation asset. The split is by *kind of work*:

- **`ck adapt` (new CLI verb)** does what is deterministic and verifiable: detect the
  stack from files on disk, resolve a profile, wire MCP within the profile's budget, seed
  memory with `--evidence`, enable the hook set for the resolved posture, verify, and
  report with receipts. **On an adopted tree it does not INSTALL hooks** — they are
  already there and (A) means the installer is never reached; hook *enablement* via the
  posture profile is the only hook-shaped work on that branch.
- **The existing skill** keeps only what cannot be mechanised — the judgement calls, chiefly
  CLAUDE.md prose — and is rewritten to **invoke `ck adapt`** for the mechanical steps
  instead of describing them again.
- **`.claude/commands/adapt.md` is rewritten the same way.** Its Execution step 3
  (`adapt.md:33-38`) still owns the identical mechanical set — config.json commands,
  CLAUDE.md, CONSTITUTION, hook profile, `.agentignore` — so leaving it untouched would
  leave three surfaces, not two, and review said so. It keeps the judgement half and
  delegates the rest to the verb.

**Net asset delta: 0.** No new agent, command, or skill. One new CLI verb, one new module,
one rewritten skill body. If review finds this framing wrong, that is a scope decision for
the owner, not something to resolve by adding an asset.

## What it composes (and must not reimplement)

Everything needed already exists. `ck adapt` is composition:

| Step | Reuses | Not to be reimplemented |
| --- | --- | --- |
| Select profile | `profiles.py` `load_profile`, `list_profiles`, the `extends` resolver | profile resolution |
| Wire MCP | `mcp.py` `add_server`, `check_budget`, `budget` | the budget rule |
| Seed memory | `src/claudekit/memory.py` store + `--evidence` (sha256 stamped on write, `:373-412`) | evidence hashing |
| Install hooks (fresh branch only) | `install.sh` via the `cmd_init` path | the installer |
| Ownership | `cli/main.py` `_load_manifest`, `_classify_manifest` | the receipt check |

`_classify_manifest` already returns `(modified, missing, unchanged)` relative to
`.claude/`, which is exactly the primitive the reversibility requirement needs.

## Ownership: TWO classes, two rules — the load-bearing design decision

An earlier revision applied ONE rule to two file classes that need different ones, and
review measured the dead end: it **refused on every already-adopted project** and
**no-op'd on every fresh one**. Owner decision, 2026-08-22: split the write set. The
first attempt at the split drew the boundary by FILE NAME and review refuted that too —
`.claude/hooks/config.json` is simultaneously receipt-recorded (`install.sh:613-621` (`NEVER_MANAGED` at `:609`)
walks every file under `.claude/` and excludes only `NEVER_MANAGED` and `.pyc`) and
documented as per-project (`cli/main.py:614` `DIFF_IGNORED`), so it landed in both
classes and adapt's own Class 2 write would have made the NEXT adapt refuse. The
boundary is therefore drawn on the axis that actually determines ownership:

**Class 1 is whole-file kit-owned. Class 2 is partially kit-owned — regardless of
whether a receipt exists.**

### Class 1 — whole-file kit-owned: receipts govern, unchanged

Membership is **every key in `.claudekit-manifest.json["files"]`, minus the two Class 2
members that are receipted** — precisely
`files.keys() - {"local/CLAUDE.project.md", "hooks/config.json"}`. Stated as that literal
set because the arithmetic is otherwise ambiguous: manifest keys are relative to
`.claude/`, so `.mcp.json` (project root) and the memory store are **not in the key set at
all** and cannot be subtracted from it. Class 2 is 2 receipted members + 2 unreceipted
artifacts, not "three members". A complement, not an enumeration — that is the only definition that stays true
when the receipt walk changes, and it is what closes both holes review found. Naming
`MANAGED_DIRS` minus `DIFF_IGNORED` was the previous attempt and it left files receipted
but in NEITHER class: `settings.json` (it is `MANAGED_FILES`, `cli/main.py:612`, a sibling
constant that `_managed_files` unions in at `:644-663`), `.claude/local/CONSTITUTION.md`
(`install.sh:512`), `.claude/profiles/**` (`install.sh:243-253`) and
`.claude/knowledge/issues/README.md` (`install.sh:260-262`). The receipt walk records
everything under `.claude/` except `NEVER_MANAGED` and `.pyc` (`install.sh:613-621`), so
anchoring on the receipt is the only membership rule that cannot drift out of step with it.

0. **No manifest -> REFUSE, and write nothing.** `_load_manifest` (`cli/main.py:636-641`)
   returns `None` both when the receipt is absent AND when it is unparseable, swallowing
   `JSONDecodeError` and `OSError` identically. Without this rule the complement is the
   EMPTY set: Class 1 is empty, rule 2 can never fire, and adapt writes into a tree of
   entirely unknown provenance — Round A's failure inverted, refusing nowhere exactly
   where provenance is least known. Legacy receipt-less installs demonstrably exist:
   `cmd_update` handles them explicitly ("pre-manifest (legacy) install"). So a tree with
   `.claude/` present and no usable receipt gets detection and a report, never a write,
   and the message distinguishes **absent** from **unparseable** because the remedies
   differ. There is no override flag past this, and none is added: a `--force` that wrote into unknown provenance would simply undo the rule.
1. Classify every intended target with `_classify_manifest` before writing anything.
2. **Any intended target that is `modified` -> REFUSE the whole run.** Not "skip that
   file": mixed ownership means unknown provenance, and a partial adapt over
   project-specific content is the failure the fleet rule exists to prevent.
3. `unchanged` (kit-owned, untouched) may be rewritten.
4. `NEVER_MANAGED` (`hooks.log`, `settings.local.json`, `.claudekit-manifest.json`) stays
   untouchable — `install.sh:604-609` records why: recording them once made `ck update`
   overwrite per-project permission allowlists and cost a hand-preservation pass across
   17 projects.

### Class 2 — partially kit-owned: a bounded region, and a re-stamped receipt

Two receipted members and two unreceipted artifacts, each with a stated mechanism.

**The receipt has two meanings, and Class 2 needs only one of them.** `install.sh:586-591`
records the manifest as a **delete-authorising** receipt: "anything recorded here is
something the kit claims the right to delete later" — which is why `NEVER_MANAGED` exists.
So writing into a partially-owned file must not hand `ck uninstall` permission to delete
the user's bytes.

**The ownership class lives in CODE, not in the receipt.** An earlier revision put
`"partial": true` beside the hash in `manifest["files"]`, and review measured three
independent failures, each fatal:

1. `manifest["files"]` is a flat `rel -> sha256-string` map and `_classify_manifest`
   compares `actual == expected` against that string. An object-valued entry makes every
   Class 2 file classify `modified` **forever**, so adapt refuses on its second run —
   Round B's defect reached by a new route. `cmd_uninstall`'s receipt rewrite, `cmd_diff`'s
   compare, and `install.sh:621` all assume strings too.
2. **`ck uninstall --force` bypasses a per-entry skip entirely.** `cli/main.py:829-830`:
   under `--force`, `removable` is *every listed path that exists*, not `unchanged`.
   `NEVER_MANAGED` is safe from `--force` only because it is never listed at all.
3. `install.sh:598-645` rebuilds `files` from a bare directory walk, so **any install or
   `ck update` silently discards the flag** and `ck uninstall` silently regains delete
   rights. A safety property that evaporates on the most routine command is not a safety
   property.

All three vanish with one constant, placed beside the ones that already solve this problem
(`cli/main.py:609-615`, next to `MANAGED_FILES` / `DIFF_IGNORED`):

    PARTIAL_OWNED = {"local/CLAUDE.project.md", "hooks/config.json"}

`cmd_uninstall` filters these **above** the `--force` branch, unconditionally, carrying the
same "must stay in step with" comment `install.sh:608,666` already models for
`NEVER_MANAGED` / `SKIP_NAMES`. The manifest keeps plain string hashes, so classification
and adapt's ordinary hash re-stamp work untouched, `cmd_diff` and `ck doctor` are
unaffected, and regeneration has nothing to drop.

**(a) `.claude/local/CLAUDE.project.md` — a marked region.** Owner decision: this file
and **only** this file. Not the root `CLAUDE.md`, which is the project's front door,
unreceipted by definition, and writing into it across 16 downstream repos is precisely
the risk the fleet rule exists to prevent. `CLAUDE.project.md` is what the kit already
renders (`install.sh:486,499`), it is receipted, so updating it is squarely the re-stamp
case above and needs no new ownership concept — and it is where the template dialect
already lives, so the parser handles one dialect in the file it owns.

The convention is the one this repo already has, and both markers as written TODAY carry
the version —
`CLAUDE.md:64` is `<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 START -->` and `:77` is
`<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 END -->`. An earlier revision wrote the END form
without the version, which would have made the writer emit what the parser rejects. Verified: **no writer for
it anywhere** — no match in `src/`, `install.sh`, `.claude/operations/scripts/`, or
`scripts/`. `ck adapt` becomes that writer.

- **Inside the markers is the kit's** and may be rewritten in place.
- **Outside is the user's** and is never touched.
- From `scripts/gen-docs.py:24-25,41-42,148-151` only ONE half transfers: **literal
  anchors and fail-closed parsing**. The other half does NOT — gen-docs replaces regions
  in files the repo owns entirely, under a CI `--check` gate that regenerates on drift.
  Adapt writes files the USER owns, with no regenerator and no gate, so "if it looks
  wrong, regenerate it" is exactly the wrong instinct here. No regex against user prose;
  exact literals only.

**(b) `.claude/hooks/config.json` — key-subtree ownership.** JSON cannot carry an HTML
comment, so the marker convention cannot reach it; the JSON analogue already exists at
`install.sh:523-534`, which does `config.setdefault('project', {})`, assigns the four
`*_cmd` keys, and preserves every other key. Adapt reuses that shape, so this is
composition rather than a second mechanism: adapt owns
`project.build_cmd|test_cmd|lint_cmd|coverage_cmd` and **nothing else**; unknown keys are
preserved in value and re-emitted; a `config.json` that is not valid JSON fails closed
and writes nothing (`install.sh:547-549` records why the pristine SOURCE must be read
rather than a possibly-truncated destination). Adapt also inherits the behaviour at
`install.sh:542-563`, which is **blank-then-refuse**, not refuse: if the command rewrite
fails, the four `*_cmd` keys are written EMPTY from the pristine source, and only if that
fallback write also fails does the install refuse and clean up. Both branches matter, and
proof 16 asserts both — an earlier draft of that proof asserted refusal alone and would
have gone red against correct behaviour. The point either way: never ship ClaudeKit's own
`pytest`/`ruff` commands into someone else's push hook.

**(c) `.mcp.json` and the seeded memory store — no markers needed.** `mcp.add_server`
already refuses before writing (`mcp.py:206-207`) and the memory store is append-only
(`memory.py:373-412`; `:317-322` is only `memory_dir`/`store_path`). Neither is under `MANAGED_DIRS`, so neither is Class 1.

### The marker/fleet-sync boundary, stated

`ck adapt` owns the region in `.claude/local/CLAUDE.project.md`. **Fleet-sync keeps the
root `CLAUDE.md` region it appends today** and is not retired by this plan. Decision 1
removes the overlap, so there is no co-ownership: two writers maintaining two different
files. The eventual consolidation is filed as a follow-up, recorded as a task-008 debt we
are **choosing to carry rather than one we missed**.

### The marker parser: what it must get right

All mutation-provable, all driving the real CLI against a real temp project.

1. **It keys on the `START` / `END` form for one named region id, and IGNORES every other
   `CLAUDEKIT:`-prefixed comment.** "Exact literal" cannot be taken literally, because the
   VERSION lives inside the START marker (`CLAUDE.md:64`:
   `<!-- CLAUDEKIT:TOKEN-MODEL-POLICY v3 START -->`) and requirement 4 has to detect a
   version it does not yet know. So the rule is **line-structured tokenization, not regex
   over user prose**: strip the line, require it to start with `<!-- CLAUDEKIT:<ID> ` and
   end with `START -->`, and parse an OPTIONAL `vN ` from between. **The version is optional
   on BOTH markers, symmetrically** — the END form is tokenized the same way: prefix
   `<!-- CLAUDEKIT:<ID> `, optional `vN `, suffix `END -->`. Requiring it on START was an
   asymmetry with a bug in it: a legacy region with no version would fail the mandatory
   check, not be recognised as a region at all, and collect a SECOND appended region on
   every run — the idempotence failure the optional-END concession existed to prevent. Deterministic, anchored at both
   ends, and it never runs a pattern across the user's text. This is not a nicety. All 11
   `templates/*/CLAUDE.md` carry a DIFFERENT dialect —
   `<!-- CLAUDEKIT:PARALLEL-AGENTS-POLICY v1 -->` … `<!-- /CLAUDEKIT:PARALLEL-AGENTS-POLICY -->`,
   a slash-close with no `START`/`END` — and those templates are exactly what install
   renders into a target (`install.sh:486`). A parser that treats any `CLAUDEKIT:` comment
   as its own would read that as malformed and, under rule 2 below, **refuse on every
   freshly installed project**. A verb that cannot run on a new install is worse than no
   verb. Proof: plant a `PARALLEL-AGENTS-POLICY v1` block in the target and assert adapt
   neither refuses nor touches it.
2. **Malformed, nested, or unterminated markers fail closed and write NOTHING** — a START
   with no END, an END before its START, two STARTs, a nested pair: refuse, name the file,
   leave it byte-identical. A parser that "does its best" on a malformed region is how a
   user's prose gets eaten.
3. **A file with no markers gets them APPENDED, never a rewrite.** The bytes before the
   appended region must be identical to the bytes before the run, with no trailing-newline
   "tidying".
4. **The region carries a version tag** (`vN`), so a stale block is DETECTABLE rather than
   silently replaced: adapt reports "region at v2, writer emits v3" — and, for a region an
   older writer left unversioned, "region present, version absent; writer emits v3". The
   writer always EMITS a version; the parser always ACCEPTS its absence.
5. **CRLF is handled on read AND on write.** A `\r` before `-->` breaks a literal-anchor
   match, so a Windows-checked-out file would get a SECOND appended region on every run —
   defeating requirement 3 and proofs 1 and 3 together. Line-structured tokenization strips
   it on read; the **writer re-emits the file's dominant line ending**, or a CRLF file
   silently acquires mixed endings while proof 1 still passes. Idempotence is proven twice:
   once on an LF file, once on a CRLF file, and the CRLF proof asserts the endings, not
   just the hash.
6. **A marker inside a fenced code block is not a region — it is SKIPPED, not a refusal.**
   This repo's own docs quote these markers verbatim, so a user documenting the convention
   must not have their prose rewritten. But refusing on a fenced START carrying adapt's OWN
   id would brick the verb permanently for that project, with no recovery path — the user
   cannot know which line to delete, and every later run refuses identically. So: a fenced
   START is not a region at all. Adapt looks for a real region outside every fence and, if
   there is none, appends one below (requirement 3). The report names the fenced line by
   `file:line` so the reader can see it was recognised and deliberately ignored.
7. **Explicit `encoding="utf-8"` on every read and write** (`profiles.py:176` gets this
   right; copy it). Locale-dependent decoding raises on non-UTF-8 prose and must fail
   closed, never partially write.
8. **Atomic replacement** — write a temp file in the same directory and `os.replace`, so
   an interrupted or concurrent run cannot leave a half-written file. Non-negotiable:
   this writes into other people's repositories.

### Step ordering — per branch, because (A) gives the two branches different shapes

Two constraints pull in opposite directions and the previous revision got the balance
wrong in both places:

- `install.sh:598-645` **regenerates the whole manifest** after it writes. So classifying
  AFTER install is tautological: every file hashes `unchanged` by construction and Class 1
  rule 2 can never fire. "Install before classify" was over-applied — it was only ever
  needed for profile resolution.
- `profiles.py:158` resolves `<root>/.claude/profiles`, which `install.sh:243` is what
  creates. So profile resolution genuinely cannot precede install on a fresh tree.

The order that satisfies both:

**Fresh (`.claude/` absent):** detect -> `cmd_init` -> **re-check rule 0 against the receipt
it produced** -> profile resolve -> MCP -> memory -> Class 2 writes -> verify -> report.

**Adopted (`.claude/` present):** detect -> classify against the PRE-EXISTING manifest ->
refuse or proceed -> profile resolve -> MCP -> memory -> Class 2 writes -> verify -> report.
**No install step at all** — that is what (A) means, and stating one order for both branches
contradicted the decision.

**The fresh branch installs FULL mode.** `cmd_init` has a minimal path too
(`cli/main.py:287-301` detects such installs), and if adapt's fresh branch could invoke it
the gap below would reappear on the branch this paragraph exempts. It cannot: adapt installs
full mode, because the profiles tree it needs next is created only there.

**The adopted-minimal case, which (A) creates.** `install.sh:239-243` creates
`.claude/profiles/` inside the FULL-mode block, so a tree installed `--minimal` has no
profiles directory, and on the adopted branch nothing creates one. `list_profiles` returns
`[]` for a missing directory (`profiles.py:165-166`), so profile resolution — and with it the
MCP budget step that proof 17 rests on — has nothing to resolve. Adapt must say so by name:
the report records "no profiles installed (minimal install); MCP budget unbounded" and the
MCP step reports `skipped (reason)` rather than `done`. Silence there would be a budget
claimed and not enforced, which is the dishonest-report failure this plan's own contract
forbids.

The refusal decision is made on the tree as adapt found it, which is the only state that
carries the user's provenance. The profile half of the order is what proof 17 rests on; the
budget details, including which profile can actually carry one, are stated there rather
than duplicated here.

### The installer is destructive, and `ck update` IS the destructive path

The previous revision claimed adapt would use "`ck update` semantics" on an existing tree
and so "NEVER reach the swap". That was false, and it was the plan's central safety
argument. `cmd_update` (`cli/main.py:926`) is literally
`bash install.sh <target> --<mode> --force --yes`, which reaches `install.sh:577-581`
unconditionally: an existing `.claude/` is `mv`d to `.claude.bak-<ts>` and a staging tree
is moved into place, consulting no manifest. Consequences, all measured from the code:

- An unreceipted user file under `.claude/` is **relocated** into the backup, not
  preserved — only a heuristic subset under `agents/commands/skills` is copied back
  (`install.sh:678-683`), and of `NEVER_MANAGED` only `settings.local.json` is carried
  across (`:571-573`); `hooks.log` goes with the backup.
- `.claude/local/CLAUDE.project.md` is **re-rendered wholesale** from the template
  (`install.sh:483-500`), so a user's prose outside the marked region is gone before the
  marker parser ever runs.
- `hooks/config.json` is written into a **freshly staged** file (`install.sh:516-535`), so
  hand-added keys do not survive. A hash re-stamp fixes classification, never clobbering.

**Decision: (A).** `ck adapt` never invokes the installer over an existing `.claude/`.

- **`.claude/` ABSENT -> fresh:** run `cmd_init`, then **re-evaluate rule 0 against the
  receipt it produced** — reload the manifest and refuse if it is still absent or
  unparseable. Asserting that `cmd_init` created a receipt is not the same as checking, and
  it does not hold: `install.sh:602` runs the manifest generator as
  `... && print_ok "Install manifest written" || print_warn "Manifest generation failed"`,
  so **manifest generation is NON-FATAL** and a fresh install can complete with exit 0 and
  no receipt at all. Without the re-check, adapt then writes Class 2 into a tree with no
  provenance — exactly what rule 0 exists to prevent, reached through the branch that looks
  safe, one layer below the "fresh means no manifest" trap. The same re-check covers
  `install.sh:558-562`, which can `exit 1` after `_cleanup_on_failure` and leave a partial
  tree. **The refusal report must say what the tree now holds.** The installer has already
  written a full kit, so "refused" over a materially changed tree is misleading unless the
  report names it — an unreceipted kit install — and names the recovery (`ck diff`, or
  re-running init). Refusing honestly includes saying what already happened.
- **`.claude/` PRESENT -> adopted:** detection, the Class 1 pre-flight, the Class 2 writes,
  verify, report. The installer is never reached, so the swap is unreachable by
  construction rather than by claim.

**"Fresh" means `.claude/` does not exist. It never means "no manifest."** This is the
requirement that keeps (A) honest: a tree with a hand-made `.claude/agents/` and no
receipt, routed to `cmd_init` on the strength of the missing manifest, gets `mv`'d into
`.claude.bak-*` at `install.sh:577-581` with only a heuristic subset copied back — the
worst outcome this plan exists to prevent, reached through the branch that looks safe.
Receipt-less trees with a `.claude/` are the Class 1 rule 0 refusal above, not a fresh
install.

What (A) gives up, stated plainly: adapt cannot refresh kit assets on an adopted tree.
`ck update` already does that and nothing here asks adapt to. The verb's value —
detection, the four commands, MCP, memory, an honest receipted report — is delivered in
full on both branches. Refusing to invoke a destructive installer is not a reduced verb;
it is the verb described honestly.

(A) also discharges two findings for free: proof 14 becomes satisfiable, because with no
swap `hooks.log` is not relocated; and hard rule 4's "no deletions" becomes true of
**effect** as well as of adapt's own code.

**(B) is refused, not deferred.** A second per-file copy path beside `install.sh`'s swap is
two installer semantics in one codebase — task 008's anti-pattern by construction. If a
non-destructive update is wanted it is its own proposal, "rebuild `ck update` without the
swap", which REPLACES `install.sh:577-581` rather than sitting beside it, and is separately
owner-gated. It must not be reached through `ck adapt`.

## Detection

Read-only, from files on disk, in CI-first order (matching the skill's existing rule that
what CI runs beats what docs claim):

1. `.github/workflows/*.yml` — the commands CI actually executes.
2. `Makefile` targets, then `package.json` `scripts`, `pyproject.toml`, `tox.ini`,
   `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `Gemfile`.
3. VCS state: whether a `.git` exists, and whether the tree is dirty.

Detection **never executes** a discovered command. It reports what it found and where from,
so a wrong guess is visible rather than run.

**No matching stack.** Fall back to a documented default profile and **say so in the
report** — "no stack profile matched; MCP budget unbounded; posture `standard`; wrote no build/test commands" is a
successful adapt, not a silent one. Required by the handoff and proven by proof 18.

**No git repository.** `ck adapt` proceeds, because reversibility rests on the receipts
rather than on git, and refusing would block a legitimate case. But it prints an explicit
line saying there is no VCS safety net, and the receipt rules above are enforced unchanged.
**Owner decision, 2026-08-22: proceed with the warning.** The alternative (refuse
without `--allow-no-vcs`) was considered and declined; no `--allow-no-vcs` flag is built.

## Honest on partial success

The report is the deliverable, and it must never overstate. Each step reports
`done` / `skipped (reason)` / `failed (reason)`, and the exit code is non-zero if any step
failed. A run where MCP wiring breached the budget and was refused, but everything else
completed, exits 0 with the skip named — never "adapt complete".

## Must be proven by mutation, not asserted

Every proof drives the real CLI against a real temp project; structural assertions do not
count. For each, revert the corresponding source behaviour and show the test go red.

1. **Idempotent on an LF file.** Two runs; the second changes nothing. Compared on a
   sha256 tree manifest EXCLUDING `.claudekit-manifest.json` (`install.sh:637` stamps
   `installed_at` every run), `.claude.bak-*` (`install.sh:578` creates one per run),
   `hooks.log`, `backups/` (`cli/main.py:841`), `.claude/locks/` and
   `operations/**/state.json` (`install.sh:703-707`), and runtime state
   (`cli/main.py:615`) — a naive whole-tree hash always
   differs, so the assertion is that the manifest's `files` map is byte-identical.
2. **A version-less legacy region is recognised, not duplicated.** Plant
   `<!-- CLAUDEKIT:<ID> START -->` … `<!-- CLAUDEKIT:<ID> END -->` with no `vN`, run adapt
   twice, and assert the region is rewritten IN PLACE both times, no second region is
   appended, and the report says "region present, version absent; writer emits vN". Without
   this the optional-version rule is asserted only in prose, and the failure it prevents —
   an unrecognised region collecting a new one on every run — has no test. Proof 21's
   fixtures are both `v3`, so they cannot cover it.
3. **Idempotent on a CRLF file.** The same assertion against a `CLAUDE.project.md` with
   CRLF line endings. Unpatched, a `\r` before `-->` breaks the literal anchor and a
   SECOND region is appended on every run; proof 1 alone cannot see it.
4. **The template dialect is left alone.** Plant
   `<!-- CLAUDEKIT:PARALLEL-AGENTS-POLICY v1 -->` … `<!-- /CLAUDEKIT:PARALLEL-AGENTS-POLICY -->`
   in the target — what `install.sh:486` really renders — and assert adapt neither
   refuses nor modifies those bytes. Without this the verb refuses on every fresh install.
5. **Class 1 refuses on mixed ownership.** Modify a receipt-owned whole-file kit asset;
   adapt refuses, names it, and **wrote nothing** (tree hash unchanged).
6. **A hand-tuned `config.json` does NOT refuse, and is not clobbered.** Run adapt, edit
   `project.test_cmd` by hand, run adapt again: the second run must not refuse (it is
   Class 2 by the literal set at the top of the ownership section, not Class 1 —
   `DIFF_IGNORED` stopped being the boundary two revisions ago) and every key adapt does not own must survive
   byte-for-byte. This is the failure the by-name boundary would have shipped.
7. **`ck uninstall` never removes a `PARTIAL_OWNED` file, `--force` included.**
   `cli/main.py:829-830` makes `removable` every listed path that exists under `--force`,
   so a skip placed below that branch would be bypassed; the filter sits above it. Revert
   the filter and this must go red under BOTH `ck uninstall` and `ck uninstall --force` —
   the force case is the one that matters, and it is the one a naive fix misses.
   (The former re-stamp proof, "a Class 2 write re-stamps its manifest entry", is folded into
   proof 6: under `PARTIAL_OWNED` the re-stamp is a plain hash update with no separate
   observable, so asserting it twice asserts nothing twice.)
8. **Malformed / nested / unterminated markers fail closed** — four shapes, each leaving
   the file byte-identical.
9. **No markers -> appended, not rewritten.** Bytes before the region unchanged, no
   trailing-newline tidying.
10. **A marker inside a fenced code block is SKIPPED, not refused and not rewritten.**
    Swept to match rule 6, which reversed this: plant a fenced START carrying adapt's OWN
    id, then assert (a) the fenced bytes are untouched, (b) a real region outside every
    fence is used, or appended below when there is none, and (c) the report names the fenced
    `file:line` so a reader sees it was recognised and deliberately ignored. Asserting a
    refusal here would go red against correct behaviour — the same defect this plan already
    records twice, for the old proofs 13 and 15.
11. **A stale region version is reported, not silently replaced.**
12. **Non-UTF-8 prose fails closed** and writes nothing — never a partial write.
13. **The write is atomic**, proven through a real seam rather than a described one:
    monkeypatch `os.replace` to raise, then assert the original bytes are intact and no
    `.tmp` residue survives. "Interrupt it" names no injection point and cannot fail as
    written.
14. **`NEVER_MANAGED` survives adapt byte-identical** — `settings.local.json` and
    `hooks.log`. The exact 17-project regression at `install.sh:604-609`, with no proof
    today; the single highest-value test here. Satisfiable because (A) is decided: with the
    installer unreachable on an adopted tree there is no swap, so `hooks.log` is never
    relocated. (An earlier revision recorded this proof as FALSE as written, which was true
    only while the installer question was open.)
15. **Detection never EXECUTES a discovered command.** Two sentinels, not one: a
    `Makefile` target that would create one, and a `.github/workflows/*.yml` `run:` string
    that would create the other. Assert both absent — a Makefile sentinel alone does not
    prove no workflow string reached a shell.
16. **Adapt blanks, then refuses** — both branches of `install.sh:542-563`: the keys go
    EMPTY when the rewrite fails, and the run refuses only when the fallback write fails
    too. Asserting refusal alone would go red against correct behaviour.
17. **MCP budget breach is refused and reported**, the remaining steps still complete, and
    exit code and report agree. **The proof uses `python/profile.json:9-11`
    (`max_servers: 3`, `max_tools: 40`).** It cannot use a posture profile: `standard`,
    `strict` and `minimal` ALL declare `"mcp": {}`, which resolves to no budget at all
    (`profiles.py:149`), so a breach is unreachable through them and the proof could not
    fail. Which forces a design statement the plan owed anyway — **adapt resolves the
    STACK profile for budget purposes** (the axis detection produces), and the posture
    profile governs hook enablement only. If no stack profile matches, the report says the
    MCP budget is unbounded rather than implying one was enforced.
18. **Unknown stack falls back and says so.**
19. **A failed step exits non-zero**, distinct from a skip, which exits 0.
20. **No git repository: proceeds** (owner decision), printing the exact "no VCS safety
    net" line, and a receipt is still written. Asserted on the EXACT line and on a
    non-zero-length receipt — "proceeds with a warning" passes trivially against a loose
    substring that any warning satisfies.
21. **The writer emits the dialect already on disk.** Emit-then-parse cannot fail when
    writer and parser share a constant, so this asserts two things a shared constant cannot
    satisfy: the writer's output against **literal expected bytes** for both markers
    (`<!-- CLAUDEKIT:<ID> vN START -->` / `<!-- CLAUDEKIT:<ID> vN END -->`), and the parser
    against the REAL lines on disk — `CLAUDE.md:64` and `:77` used as fixtures. That is
    what binds the writer to the convention that already exists rather than to itself.

## What the config writes — named, because a plan that hides its largest artifact cannot be reviewed for it

`check-plan-artifacts.py` refused the first config authored against this plan for
exactly that reason, on its first real use. Every operation, named:

- **`src/claudekit/adapt.py`** (new module) — the marker parser (line-structured
  tokenization, optional version on both markers, real fence tracking, CRLF- and
  mixed-ending-preserving splice, mode-preserving atomic write), CI-first detection
  that executes nothing and derives the four commands with their provenance,
  `vcs_dirty` on the far side of the "executes nothing" line, `classify_ownership` as
  the receipt COMPLEMENT, the Class 1 pre-flight, the `hooks/config.json` key-subtree
  writer, and the `Report` whose `skipped` is not a failure.
- **`tests/test_adapt.py`** (new) — the behavioural proofs. The unit half (parser,
  ownership complement, atomic-write seam, the writer's literal bytes against the real
  markers in this repo's `CLAUDE.md`) plus a **CLI half** that drives
  `python -m claudekit.cli.main` as a subprocess against a tree a real `ck init`
  produced: idempotence (LF, CRLF, mixed, unbalanced fence), the Class 1 refusal,
  `NEVER_MANAGED` survival, the hand-tuned `config.json`, the MCP breach, the fenced
  `file:line`, the two detection sentinels, and every uninstall path.
- **`src/claudekit/cli/main.py`** — `PARTIAL_OWNED` beside `DIFF_IGNORED`; the
  uninstall filter applied to `listed` AND to the classification while keeping those
  files RECEIPTED in the rewrite, with survivors unioned into that rewrite so the
  receipt is never unlinked over a file still on disk; `cmd_adapt` with every step
  wired; the manifest re-stamp; the `adapt` subparser and dispatch entry.
- **`tests/test_install_receipts.py`** — two existing expectations updated to the
  PARTIAL_OWNED contract (the receipt now survives a clean uninstall and describes the
  survivors), and a new class covering the registry reconcile below.
- **`install.sh`** — the skills registry is reconciled with what was actually
  installed. Unrelated to adapt, but it is what made `ck doctor --strict` exit 1 on a
  freshly installed tree, and this plan's DoD names that command.
- **`.claude/commands/adapt.md`** and
  **`.claude/skills/project-adaptation/SKILL.md`** — rewritten to delegate the
  mechanical half to the verb and keep the judgement half. Net asset delta 0.
- **`CHANGELOG.md`** — `[Unreleased]`, for a new user-visible CLI verb.
- **`.ai/CHANGELOG_AI.md`** and **`.ai/SESSION_STATE.md`** — the maintainer
  record and the resume point, shipped WITH the change rather than after it, so
  the tree never carries code whose session record says it is not there yet.

## Divergences from this plan, stated rather than buried

1. **Proof 16's blank-then-refuse is implemented as blank-OR-refuse, deliberately.**
   `install.sh:542-563` can blank the four keys because it holds a PRISTINE source and
   writes into a freshly staged file. Adapt has neither: on an adopted tree the only
   copy of an unparseable `config.json` is the USER's bytes, so blanking it would
   destroy content the installer never risks. So the two branches are: an unevidenced
   key is written EMPTY rather than left stale (the blanking half, on the ordinary
   path), and invalid JSON refuses and writes nothing. Both are asserted through the
   CLI. Asserting install.sh's exact pair here would have gone red against the safer
   behaviour.
2. **`Detection.dirty` is computed by `vcs_dirty`, not by `detect`.** Detection's
   contract is that it executes nothing, and reading dirtiness runs `git`. It is a
   fixed VCS query rather than a discovered command, but it is still an execution, so
   it lives in a separate function a reader can see rather than inside the one whose
   contract forbids it. `None` means "unknowable", and the report prints that.
3. **An unevidenced command key is KEPT, not blanked.** `install.sh:495-497` writes
   all four keys EMPTY and never ships ClaudeKit's own `pytest`/`ruff`, so on an
   adopted tree a non-empty value is the USER's. Blanking it destroyed their
   configuration on every run, and `project-adaptation` Phase 2 tells them to set
   exactly those keys — the verb and the skill contradicted each other. Only an
   evidenced value overwrites; kept keys are named in the report. (Found by
   adversarially reviewing this change, not by any proof in this plan.)
4. **EVERY command adapt writes is filtered for shell metacharacters, by name.** Adapt
   writes into `hooks/config.json` and pre-commit / pre-push / post-implement EXECUTE
   what is there, so a `run:` string in the TARGET repository is attacker-controlled
   input to a shell that fires on the user's next push. Measured: `run: pytest ;
   touch /tmp/PWNED_BY_ADAPT` was derived and written verbatim. Detection still
   executed nothing and the report still named it, but a report is read once and a
   hook runs every time. Profile values are NOT filtered — they ship with the kit or
   are written by the user — and `cd web && npm test` still works, because the `cd`
   prefix is stripped before the rule applies.

   **Corrected after round 1 of code review (62/100, REVISE).** The profile exemption
   in the sentence above was WRONG and the reviewer proved it end to end:
   `profiles.profiles_dir` resolves `<TARGET>/.claude/profiles`, so a profile is a
   file in the repository being adapted, and a NEW one is unreceipted —
   `_classify_manifest` reports only MODIFIED receipted files, so the Class 1
   pre-flight never sees it. A `typescript/profile.json` carrying
   `npm run build; python3 -c "open('/tmp/PWNED_PROFILE','w').write('x')"` reached
   `hooks/config.json`, and `post-implement.sh` executed it. Worse, the exemption had
   a GREEN TEST asserting it, which is worse than no test. **Now every value is
   filtered whatever its source.** The cost is nil — every shipped profile value is
   metacharacter-free — and a profile that genuinely needs composition is refused by
   name rather than silently rewritten.

   **Scope of the claim, stated narrowly (hard rule 6).** The screen stops shell
   COMPOSITION, not a hostile single command: round 2 measured that an unreceipted
   profile with `build_cmd = "python3 .evil.py"` passes, is written, and a hook runs
   it — equally true of the derivation path, so it is the verb's threat model rather
   than a regression. What the screen buys is that a command cannot smuggle a SECOND
   action past the one the report shows the user. Screening writes through
   `CommandValidator` at write time is filed as a follow-up, not claimed here.

   **Round 2 (84/100, CONDITIONAL) found the regression test for this CRITICAL
   VACUOUS.** `assert payload not in json.dumps(config)` cannot fail: `json.dumps`
   escapes the payload's own quotes. The reviewer applied the re-exemption mutant,
   fully restoring the vulnerability, and the test still PASSED. It now asserts the
   VALUE (`config["project"]["build_cmd"] == ""` and `payload not in
   config["project"].values()`) and goes red under that mutant. A regression test for
   a CRITICAL that cannot fail is coverage in appearance only.
5. **Runtime state is not written into the region.** `dirty` was, which made the verb
   self-referentially non-idempotent wherever `.claude/` is TRACKED — this repo and
   every downstream repo: run 1 saw a clean tree, wrote the region, dirtied the tree,
   and run 2 added a line run 1 had not. Proof 1's fixture has no `.git`, so it could
   not see it. The report prints `dirty=`; the document does not.
6. **The MCP step reports the budget; it adds no server.** Proof 17's breach case is
   asserted against `python/profile.json`'s `max_servers: 3` with four servers in
   `.mcp.json`: the step reports `skipped` with the numbers quoted, the remaining
   steps still complete, and the run exits 0.

## Delivered vs deferred, stated rather than implied

Delivered: detection **and the four derived commands, with provenance**, the ownership
split, the Class 1 refusal, the marked region in `CLAUDE.project.md`, the
`config.json` key-subtree writer **called from the verb**, profile resolution on both
axes, the MCP budget step, the memory record, the manifest re-stamp, the honest report,
the `PARTIAL_OWNED` protection, and the task-008 rewrite of the command and the skill.

**Nothing is deferred.** The fresh branch now runs `cmd_init` itself, as the step
ordering above specifies — owner-approved 2026-08-23 ("finish them all"). It installs
FULL mode (`install.sh:239-243` creates `.claude/profiles/` only there, and profile
resolution is the next step), then re-checks Rule 0 against the receipt the installer
actually produced rather than asserting one, and names an UNRECEIPTED kit install
together with its recovery. The safety argument is unchanged and is why the installer
is reachable on this branch and only here: "fresh" means `.claude/` is **absent**, so
`install.sh:577-581`'s `mv .claude .claude.bak-<ts>` has nothing to move. A tree with a
hand-made `.claude/` and no receipt is still a refusal — asserted on the user's bytes,
on the absence of any `.claude.bak-*`, and on the installer never having run.

The one follow-up this session filed is also **delivered**:
`.claude/plans/plan-adapt-eject-interaction.md`. `ck eject` landed as `afc4ba8`
mid-session, so `cmd_adapt` now recognises an ejected tree, keeps its read-only half,
writes nothing, and stops advising `ck init` — which over an existing `.claude/` is the
destructive swap decision (A) exists to make unreachable. Two structural changes came
with it: the read-only half (profile, commands, MCP) is factored into
`_adapt_read_only`, so the ejected branch reuses it instead of carrying a second copy,
and the step order now matches the ordering stated above — profile -> MCP -> memory ->
Class 2 writes — which the first implementation did not.

**This config is rebased onto `afc4ba8`, not `14cf45e`.** Applying the `14cf45e` version
over `afc4ba8` silently deleted `"eject": cmd_eject` from the dispatch dict while every
`find` anchor still matched exactly once, because a context-carrying edit re-emits stale
context. Uniqueness is not sufficiency; the stamped `baseline` is what catches it.

## Hard constraints

- **ClaudeKit is NOT a harness.** No model client, no agent loop, no session runtime, no
  sandbox. `ck adapt` configures a project; it does not run an agent. If it starts to look
  like it needs one, that is a misread — stop and report.
- Python **stdlib only**; no runtime dependency. bash 3.2 / macOS-safe.
- Hooks stay shell-form `type: command`; blocking = `exit 2` + stderr, fail closed.
- Protected files stay protected; MAX_DELETIONS=3. `ck adapt` issues **no deletion
  operations**, and under (A) that is true of its **effect** as well as its code: the
  installer's swap is unreachable on both branches — an adopted tree never reaches the
  installer, and a fresh tree has no `.claude/` to relocate — so nothing is moved into
  `.claude.bak-*` by anything adapt does. This was hedged while the installer question was
  open; it is decided, so the hedge is gone.
- Never hand-edit component counts. A new CLI verb does not move a count; a new skill would,
  and there is no new skill.
- Do not reopen settled rejections in `.ai/RESEARCH.md` without new evidence.

## Definition of Done

Archive the spent config FIRST (`test_delivery_contract_smoke.py` validates queued configs
against `HEAD`), then all eight gates, plus `ck doctor --strict` on a tree adapted by the new
verb. Re-run gates AFTER committing — the secret self-scan enumerates `git ls-files` and has
reddened this branch four times.

## Filed as follow-ups, deliberately

- **Marker-writer consolidation across the fleet.** `ck adapt` owns the region in
  `.claude/local/CLAUDE.project.md`; fleet-sync keeps the root `CLAUDE.md` region it
  appends today. Two writers maintaining two different files is a **task-008 debt we are
  choosing to carry, not one we missed** — recorded so a later reader does not mistake it
  for an oversight. Retiring the fleet-sync marker path across the 16 downstream repos is
  owner-gated and not part of this plan.
- `templates/*/CLAUDE.md` dialect unification (all 11 use the slash-close form).

## Out of scope

Fleet-sync to the 16 downstream repos (owner-gated, and explicitly not part of building the
verb). The v2.1.0 tag and PyPI publish. Task 008's broader consolidation sign-off — this plan
only declines to *add* to the duplication.
