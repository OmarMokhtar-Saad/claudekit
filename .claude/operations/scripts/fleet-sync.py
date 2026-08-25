#!/usr/bin/env python3
"""Phase B of plan-fleet-skill-enhancement: distribute Phase A across the kitted fleet.

Runs OUTSIDE the operations engine by necessity -- execute-json-ops.py refuses paths
outside the repo root, and every target here is a different repository. So the safety
properties the engine would have given us are rebuilt explicitly: --dry-run first, a
per-project skip-and-log rule instead of a force, a diff-guard before any delete, and
every downstream repo left UNCOMMITTED for the owner.

Binding rules (fleet memory + plan section 4.B):
  - surgical only; never overwrite a file carrying project-specific content
  - a diverged anchor is a SKIP with a logged reason, never a force
  - never commit downstream, never merge downstream back
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone

ROOT = os.path.expanduser("~/IdeaProjects")
KIT = os.path.join(ROOT, "claudekit")
KIT_SKILLS = os.path.join(KIT, ".claude", "skills")

# Measured 2026-08-25 from tracked files, .claude/ excluded. The plan's matrix said
# AppiumLens was Kotlin (it is 2054 Java files to 2 .kts build scripts) and did not
# give qaforge-ai or AppiumLens their second stack. Threshold: >=20 tracked files.
STACKS = {
    "ai-agent-system":     ["python"],
    "ApiForge":            ["java"],
    "AppiumLens":          ["java", "python"],
    "AutomationApp":       ["java"],
    "Eatizaz":             ["java"],
    "Lean":                ["java"],
    "LeanApis":            ["java"],
    "MobileUIAutomator":   ["java"],
    "qa-agents":           ["python"],
    "qaforge-ai":          ["java", "python"],
    "SehhatyApp":          ["java"],
    "shsmartassistant-qa": ["kotlin"],
}

SUPERSEDED = {
    "autonomous-loops": "autonomous-loop",
    "context-priming": "context-keeper",
    "session-continuity": "context-keeper",
    "dependency-audit": "supply-chain-audit",
    "verification-loop": "verification-before-completion",
    "i18n-workflow": "i18n-patterns",
}
NOVELTY_ABORT_PCT = 20.0

ROUTING_ANCHOR = ("- **differential-security-review** — load when reviewing a diff or PR "
                  "for security regressions")
GAP_LENS_LINES = (
    "\n- **verification-gap-lens** — load when the diff changes behavior and you must "
    "judge whether any\n  test would fail if that behavior regressed (dimension 5, and "
    'every "has no test" claim)')
CHECKLIST_LINE = {
    "python":     "\n- **python-review-checklist** — load when the diff contains `.py`/`.pyi` files",
    "typescript": "\n- **typescript-review-checklist** — load when the diff contains `.ts`/`.tsx`/`.mts`/`.cts` files",
    "java":       "\n- **java-review-checklist** — load when the diff contains `.java` files",
    "kotlin":     "\n- **kotlin-review-checklist** — load when the diff contains `.kt`/`.kts` files",
}


def tree_digest(path):
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for f in sorted(files):
            fp = os.path.join(root, f)
            h.update(os.path.relpath(fp, path).encode())
            with open(fp, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def novelty_pct(local_dir, survey_entry):
    """Novel-line share of the local copy against the modal fleet snapshot.

    The plan says "vs the old kit version", but claudekit no longer ships these skills
    -- that is what the rename means -- so there is no old kit to diff against. The
    modal fleet copy is the available stand-in and a better one: when 11 of 12 projects
    are byte-identical, that IS the pristine version, measured rather than assumed.
    """
    import difflib
    modal_h, snap, n = survey_entry
    if modal_h is None or not snap:
        return 100.0, "no fleet baseline to compare against -- not deleting blind"
    if tree_digest(local_dir) == modal_h:
        return 0.0, f"identical to the modal fleet copy ({n} projects)"
    worst, worst_file = 0.0, None
    local = {}
    for root, dirs, files in os.walk(local_dir):
        for f in files:
            fp = os.path.join(root, f)
            local[os.path.relpath(fp, local_dir)] = open(
                fp, encoding="utf-8", errors="replace").read()
    for fn in sorted(set(snap) | set(local)):
        if fn not in snap or fn not in local:
            return 100.0, f"{fn} exists on only one side"
        A, B = snap[fn].splitlines(), local[fn].splitlines()
        sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
        novel = sum(j2 - j1 for tag, i1, i2, j1, j2 in sm.get_opcodes()
                    if tag in ("insert", "replace"))
        pct = 100.0 * novel / max(1, len(B))
        if pct > worst:
            worst, worst_file = pct, fn
    return worst, (f"{worst:.1f}% novel vs modal in {worst_file}" if worst_file
                   else "no novel lines vs modal")


def live_references(project, skill):
    """Files under .claude/ that still LOAD this skill by name.

    The plan's diff-guard asks whether the local copy was customised. It does not ask
    the question that actually breaks a fleet: whether anything still loads the skill.
    Measured before the first delete -- three of the six superseded skills are named in
    84 Skill Loading directives across the fleet, and downstream registries carry no
    `renamed` alias map to resolve the old name once the directory is gone.
    """
    import re
    base = os.path.join(ROOT, project, ".claude")
    pat = re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(skill))
    out = []
    for sub in ("agents", "commands", "hooks", "modes"):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in sorted(files):
                fp = os.path.join(root, f)
                try:
                    if pat.search(open(fp, encoding="utf-8", errors="replace").read()):
                        out.append(os.path.relpath(fp, base))
                except Exception:
                    pass
    return out


def survey_superseded(projects):
    """Per superseded skill: the modal copy's CONTENT, plus how many projects share it.

    Content, not a path. The first version cached the modal copy's DIRECTORY and the
    real run then deleted it -- so the second project compared against a directory the
    first project had already removed, and crashed. A snapshot cannot be invalidated by
    the deletes it exists to authorise.
    """
    out = {}
    for dup in SUPERSEDED:
        variants = {}
        for p in projects:
            d = os.path.join(ROOT, p, ".claude", "skills", dup)
            if os.path.isdir(d):
                variants.setdefault(tree_digest(d), []).append(d)
        if not variants:
            out[dup] = (None, {}, 0)
            continue
        modal_h, modal_dirs = max(variants.items(), key=lambda kv: len(kv[1]))
        snap = {}
        for root, dirs, files in os.walk(modal_dirs[0]):
            for f in files:
                fp = os.path.join(root, f)
                snap[os.path.relpath(fp, modal_dirs[0])] = open(
                    fp, encoding="utf-8", errors="replace").read()
        out[dup] = (modal_h, snap, len(modal_dirs))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default=os.path.join(
        KIT, ".claude", "reports", "fleet-sync-2026-08-25.md"))
    args = ap.parse_args()
    dry = args.dry_run

    projects = sorted(STACKS)
    peers = survey_superseded(projects)
    log = {p: {"added": [], "edited": [], "deleted": [], "skipped": []} for p in projects}

    for p in projects:
        S = os.path.join(ROOT, p, ".claude", "skills")
        A = os.path.join(ROOT, p, ".claude", "agents", "code-reviewer.md")
        L = log[p]

        # ---- B1: copy the skills this project's stack earns -------------------
        wanted = ["verification-gap-lens"] + [f"{s}-review-checklist" for s in STACKS[p]]
        for skill in wanted:
            src, dst = os.path.join(KIT_SKILLS, skill), os.path.join(S, skill)
            if not os.path.isdir(src):
                L["skipped"].append(f"{skill}: not present in claudekit")
                continue
            if os.path.isdir(dst):
                if tree_digest(src) == tree_digest(dst):
                    L["skipped"].append(f"{skill}: already present and identical")
                else:
                    L["skipped"].append(
                        f"{skill}: already present but DIFFERS -- left alone "
                        f"(may carry project-specific content)")
                continue
            if not dry:
                shutil.copytree(src, dst)
            L["added"].append(skill)

        # ---- B2: routing block ------------------------------------------------
        if not os.path.isfile(A):
            L["skipped"].append("code-reviewer.md: absent -- no routing edit")
        else:
            body = open(A, encoding="utf-8").read()
            if ROUTING_ANCHOR not in body:
                L["skipped"].append(
                    "code-reviewer.md: routing anchor not found -- diverged beyond "
                    "recognition, NOT forced")
            elif body.count(ROUTING_ANCHOR) != 1:
                L["skipped"].append(
                    f"code-reviewer.md: anchor appears {body.count(ROUTING_ANCHOR)}x "
                    f"-- ambiguous, NOT forced")
            else:
                addition = ""
                if "verification-gap-lens" not in body:
                    addition += GAP_LENS_LINES
                for s in STACKS[p]:
                    name = f"{s}-review-checklist"
                    if name not in body:
                        addition += CHECKLIST_LINE[s]
                if not addition:
                    L["skipped"].append("code-reviewer.md: routing already current")
                else:
                    if not dry:
                        with open(A, "w", encoding="utf-8") as fh:
                            fh.write(body.replace(ROUTING_ANCHOR,
                                                  ROUTING_ANCHOR + addition, 1))
                    L["edited"].append(
                        f"code-reviewer.md: +{addition.count(chr(10)+'- ')} routing line(s)")

        # ---- B3: owner-approved dedupe, diff-guarded --------------------------
        for dup, succ in SUPERSEDED.items():
            d = os.path.join(S, dup)
            if not os.path.isdir(d):
                continue
            if not os.path.isdir(os.path.join(S, succ)):
                L["skipped"].append(
                    f"{dup}: successor '{succ}' NOT present -- delete would remove "
                    f"capability, aborted")
                continue
            refs = live_references(p, dup)
            if refs:
                L["skipped"].append(
                    f"{dup}: HELD -- still loaded by {len(refs)} file(s) "
                    f"({', '.join(refs[:3])}{' ...' if len(refs) > 3 else ''}) and there "
                    f"is no `renamed` alias map downstream, so deleting it would leave "
                    f"dangling skill loads. Needs a reference rewrite, which is not in "
                    f"the approved delete list.")
                continue
            pct, why = novelty_pct(d, peers[dup])
            if pct > NOVELTY_ABORT_PCT:
                L["skipped"].append(f"{dup}: diff-guard ABORT -- {why}")
                continue
            if not dry:
                shutil.rmtree(d)
            L["deleted"].append(f"{dup} (-> {succ}; {why})")

        # ---- B4: registry sidecar --------------------------------------------
        R = os.path.join(S, "skills-registry.json")
        if not os.path.isfile(R):
            L["skipped"].append("skills-registry.json: absent -- left absent")
        else:
            # State-based, NOT gated on `L["added"]`. The first version only touched the
            # registry when THIS run copied something, so a project whose skills landed
            # in an earlier partial run kept a registry that named none of them -- the
            # re-run skipped the copy as "already present" and therefore skipped the
            # rows too. Reconcile against what is on disk instead of against what this
            # run happened to do.
            try:
                reg = json.load(open(R, encoding="utf-8"))
                known = {s["id"] for s in reg.get("skills", [])}
                new = []
                for skill in wanted:
                    if not os.path.isdir(os.path.join(S, skill)):
                        continue
                    if skill in known:
                        continue
                    md = os.path.join(KIT_SKILLS, skill, "SKILL.md")
                    desc = ""
                    for line in open(md, encoding="utf-8"):
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"')
                            break
                    reg.setdefault("skills", []).append({
                        "id": skill,
                        "name": " ".join(w.capitalize() for w in skill.split("-")),
                        "path": f"skills/{skill}/SKILL.md",
                        "mandatory": False,
                        "usedBy": ["code-reviewer"],
                        "description": desc,
                    })
                    new.append(skill)
                # A skill THIS RUN deleted must not linger as a dangling registry
                # row. Scoped to exactly those, deliberately: sweeping every row
                # whose directory is missing would also delete rows that were
                # already dangling before this run, which is not ours to decide --
                # and under --dry-run, where nothing was copied, it would have
                # deleted the very rows just added.
                deleted_ids = {d.split(" ")[0] for d in L["deleted"]}
                # Also sweep rows for a superseded skill this run found already gone
                # (an earlier partial run deleted the directory but not the row).
                deleted_ids |= {d for d in SUPERSEDED
                                if not os.path.isdir(os.path.join(S, d))}
                gone = [s["id"] for s in reg.get("skills", [])
                        if s["id"] in deleted_ids]
                if gone:
                    reg["skills"] = [s for s in reg["skills"] if s["id"] not in gone]
                if (new or gone) and not dry:
                    with open(R, "w", encoding="utf-8") as fh:
                        json.dump(reg, fh, indent=2)
                        fh.write("\n")
                if new or gone:
                    L["edited"].append(
                        f"skills-registry.json: +{len(new)} row(s), -{len(gone)} dangling")
            except Exception as e:
                L["skipped"].append(f"skills-registry.json: not updated ({e})")

    # ---- B5: the report the owner reviews before committing anything ----------
    lines = [
        "# Fleet sync — Phase B of plan-fleet-skill-enhancement",
        "",
        f"**Run:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"**Mode:** {'DRY RUN — nothing written' if dry else 'EXECUTED'}",
        f"**Projects:** {len(projects)} kitted repos. `rest-framework` is excluded "
        f"(Phase C1, deferred by the owner to its own session); `qa-agent-pro` is "
        f"excluded (Phase C2, skipped by the owner).",
        "",
        "**Every downstream repo is left UNCOMMITTED.** Nothing here is pushed, "
        "committed, or merged back. To undo any project entirely: "
        "`git -C <project> checkout -- .claude/` plus `git clean -fd .claude/skills/` "
        "for the newly added directories (they are untracked until you add them).",
        "",
        "> Note: every one of these repos already carried uncommitted changes before "
        "this run, from earlier fleet syncs. The counts below are what THIS run did, "
        "not the repo's total dirt.",
        "",
        "## Corrections to the plan's matrix (measured, not assumed)",
        "",
        "The plan's §2.1 stack table was wrong in three places. Counts are tracked "
        "files with `.claude/` excluded:",
        "",
        "| Project | Plan said | Measured | Action |",
        "|---|---|---|---|",
        "| AppiumLens | Kotlin/Gradle | **2054 `.java`**, 2 `.kts` (build scripts), 29 `.py` | java + python, NOT kotlin |",
        "| qaforge-ai | Python | 83 `.py`, **34 `.java`** | python + java |",
        "| ApiForge | \"src is Java\" | 27 `.java`, 0 `.py` | java (confirmed) |",
        "",
        "The recurring \"~34 `.py`\" that made every Java project look dual-stack is "
        "ClaudeKit's own `.claude/operations/scripts/` plus `.claude.bak-*` copies — "
        "kit tooling, not project source.",
        "",
        "## Per project",
        "",
    ]
    for p in projects:
        L = log[p]
        lines.append(f"### {p}  ·  stack: {', '.join(STACKS[p])}")
        lines.append("")
        for key, label in (("added", "Added"), ("edited", "Edited"),
                           ("deleted", "Deleted"), ("skipped", "Skipped")):
            if L[key]:
                lines.append(f"**{label}:**")
                for item in L[key]:
                    lines.append(f"- {item}")
                lines.append("")
        if not any(L.values()):
            lines.append("_No change._\n")
    tot = {k: sum(len(log[p][k]) for p in projects)
           for k in ("added", "edited", "deleted", "skipped")}
    lines += ["## Totals", "",
              f"- Skills added: **{tot['added']}**",
              f"- Files edited: **{tot['edited']}**",
              f"- Superseded skills deleted: **{tot['deleted']}**",
              f"- Skipped (logged, never forced): **{tot['skipped']}**", ""]

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines[-8:]))
    print(f"\nReport: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
