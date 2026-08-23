#!/usr/bin/env python3
"""Differential gate for the ops protected-file guard: no change may turn REJECT into ALLOW.

Why this exists, specifically. `check-validator-differential.py` carries the banner "No
change may turn a REJECT into an ALLOW" and CI runs it on every PR -- but its MODULE_PATH
is pinned to `src/claudekit/security/command_validator.py`. The OTHER deny-decision in this
repo, `shared.is_protected_file`, had no such gate, and the first change to widen it sailed
straight through: at the baseline a config deleting `docs/ARCHITECTURE.md` was REJECTED, at
the tip it was APPROVED, and every check in CI stayed green. That is the exact shape the
banner promises to catch. This is the missing half.

What it does: imports `shared.py` from a git baseline and from the working tree, runs the
same corpus of paths through `is_protected_file` in both, and fails if any path moved
protected -> unprotected. A widening is not forbidden; it must be DISCLOSED by adding an
entry to DISCLOSED_WIDENINGS below, which is reviewed like any other code.

What it is not: a proof. It checks a fixed corpus of paths, not every path a repo can hold.
A clean run means "no path in this corpus lost protection", never "the guard is sound".

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

MODULE_PATH = ".claude/operations/scripts/shared.py"

# Paths the guard is asked about. Identity documents at root and at depth, the component
# prose the kit maintains, and a spread of non-markdown files that were never in scope --
# included so a change that widens INTO them is visible too.
CORPUS: List[str] = [
    "README.md", "readme.md", "Readme.MD", "CHANGELOG.md", "CLAUDE.md", "AGENTS.md",
    "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "LICENSE", "LICENSE.md",
    "NOTICE.md", "MAINTAINERS.md", "GOVERNANCE.md", "AUTHORS.md", "SUPPORT.md",
    "docs/README.md", "docs/deep/CHANGELOG.md", "a/b/c/CLAUDE.md",
    ".gitignore", "Makefile", "makefile", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "requirements.txt", "package.json", "package-lock.json",
    "yarn.lock", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock",
    "tsconfig.json",
    "docs/ARCHITECTURE.md", ".ai/KNOWLEDGE_BASE.md", ".github/PULL_REQUEST_TEMPLATE.md",
    ".claude/skills/token-optimization/SKILL.md", ".claude/agents/code-reviewer.md",
    "templates/commands/analyze.md", "notes.md", "docs/design.md",
    "install.sh", "src/claudekit/cli/main.py", ".claude/settings.json",
    "sub\\README.md",  # ONE filename on POSIX -- pins that the gate reads it as the
                       # guard does, not as README.md inside sub/
    ".github/workflows/ci.yml", "MANIFEST.in", ".pre-commit-config.yaml",
]

# Widenings that are ALLOWED, each with the reason it was accepted. An entry here is a
# decision on the record, not a suppression: adding one takes the same review as changing
# the guard, and each must also be disclosed in CHANGELOG.md.
DISCLOSED_WIDENINGS: List[Dict[str, str]] = [
    {
        "path": "*.md that is not a named identity document",
        "why": "2026-08-23: the `*.md` glob froze every paragraph of prose in the tree, so "
               "the ops engine could not retire a component and the kit's own corpus (all "
               "markdown) was unmaintainable -- across 97 archived configs, zero deletions of "
               "any kind. Narrowed to the named identity documents. Ordinary prose is now "
               "deletable behind MAX_DELETIONS=3, a mandatory reason and a pre-delete backup; "
               "a project restores the old behaviour with CLAUDEKIT_EXTRA_PROTECTED='*.md'.",
    },
]

# Identity documents are the UNION of three sources, because each alone has a hole a
# review found by executing it:
#
#   * the baseline guard's literal patterns  -- but when the baseline is the old `*.md`
#     glob it contains NO literal `README.md`, so dropping README.md would be classified
#     as the disclosed markdown widening and reported OK. Measured; it regressed exactly
#     that way when derivation replaced the hardcoded list.
#   * the working tree's literal patterns    -- but a change that DELETES a name also
#     erases the evidence that the name was ever protected.
#   * a hardcoded floor                      -- which drifts on its own, as round-2
#     review demonstrated: add a name to the guard, forget this file, and a later
#     removal is swallowed.
#
# Union of all three: the floor covers the conventional documents whichever direction a
# change moves, and derivation from BOTH modules means a name added to the guard is
# picked up here without anyone remembering to.
IDENTITY_FLOOR = frozenset({
    "readme.md", "changelog.md", "claude.md", "agents.md", "contributing.md",
    "security.md", "code_of_conduct.md", "license", "license.md", "notice.md",
    "maintainers.md", "governance.md", "authors.md", "support.md",
})


def _identity_docs(*modules) -> frozenset:
    """Every non-glob pattern any of the given guards protects, plus the floor."""
    names = set(IDENTITY_FLOOR)
    for module in modules:
        names.update(p.lower() for p in module.PROTECTED_PATTERNS
                     if not any(ch in p for ch in "*?["))
    return frozenset(names)

def _git(repo_root: Path, *args: str) -> Optional[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=repo_root)
    return result.stdout.strip() if result.returncode == 0 else None


def _is_disclosed(path: str, identity_docs: frozenset, baseline_had_md_glob: bool) -> bool:
    """True when losing protection on this path is the disclosed widening.

    Expressed as the RULE, not as a list of sample paths. The first version named
    `docs/`-style prefixes and the gate promptly caught a root-level `notes.md` it had
    not thought of -- correctly, since that file did lose protection. Narrow
    disclosures do not make a gate stricter, they make it noisy, and a noisy gate gets
    suppressed.

    Two things keep the rule from becoming a blanket amnesty for markdown:

    * an identity document is never disclosed, so this cannot swallow the regression
      that actually matters; and
    * the blanket applies ONLY when the baseline still carried the `*.md` glob. Once
      this widening is behind `main`, the baseline has the narrow list, the condition
      goes false, and the disclosure retires itself instead of pre-disclosing every
      future `.md` unprotection for the life of the repo.

    Backslashes are deliberately NOT normalised. Round-2 review suggested it, on the
    grounds that `os.path.basename` does not split on `\\` on POSIX so `sub\\README.md`
    misses the identity check. Implementing it made the gate fail on a clean tree, and
    the gate was right: on POSIX `sub\\README.md` is ONE filename, `is_protected_file`
    does not read it as README.md either, and it genuinely lost protection as an
    ordinary markdown file. A gate that normalises where the guard it models does not
    reports a regression the guard cannot have. It models the guard; it does not
    correct it. (On Windows both split identically, so the two agree there too.)
    """
    if os.path.basename(path).lower() in identity_docs:
        return False
    return baseline_had_md_glob and path.lower().endswith(".md")


def _load(source: str, label: str):
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / ("shared_%s.py" % label)
        target.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("shared_%s" % label, target)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load %s" % label)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", default="auto",
                        help="git ref to compare against; 'auto' = merge-base with main")
    parser.add_argument("--require-baseline", action="store_true",
                        help="fail if the baseline cannot be resolved, instead of skipping")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    ref = args.baseline
    if ref == "auto":
        ref = (_git(repo_root, "merge-base", "origin/main", "HEAD")
               or _git(repo_root, "merge-base", "main", "HEAD") or "")
    if not ref:
        message = "could not resolve a baseline ref"
        print("SKIP: %s" % message)
        return 1 if args.require_baseline else 0

    head = _git(repo_root, "rev-parse", "HEAD")
    if head and _git(repo_root, "rev-parse", ref) == head:
        # The same trap the sibling gate documents: a baseline equal to HEAD diffs the
        # tree against itself and passes forever.
        print("SKIP: baseline %s resolves to HEAD - nothing to compare" % ref)
        return 1 if args.require_baseline else 0

    print("Baseline: %s (%s)" % (ref, args.baseline))

    result = subprocess.run(["git", "show", "%s:%s" % (ref, MODULE_PATH)],
                            capture_output=True, text=True, cwd=repo_root)
    if result.returncode != 0:
        print("SKIP: no %s at %s" % (MODULE_PATH, ref))
        return 1 if args.require_baseline else 0

    # The env must not leak into either side: CLAUDEKIT_EXTRA_PROTECTED would widen both
    # and could mask a real regression.
    os.environ.pop("CLAUDEKIT_EXTRA_PROTECTED", None)

    before = _load(result.stdout, "before")
    after = _load((repo_root / MODULE_PATH).read_text(encoding="utf-8"), "after")

    identity_docs = _identity_docs(before, after)
    baseline_had_md_glob = "*.md" in before.PROTECTED_PATTERNS

    # Ask about every name the BASELINE protected, not only the ones someone thought to
    # list. CORPUS is hand-written, so a pattern added to the guard after this script was
    # written would never be asked about, and dropping it again would pass silently --
    # the fixed corpus, not the disclosure rule, is the weaker half of that hole. Each
    # name is probed at the root and at depth, since the match is on basename.
    corpus = list(CORPUS)
    for name in sorted(identity_docs):
        for probe in (name, "docs/deep/%s" % name):
            if probe not in corpus:
                corpus.append(probe)
    if not baseline_had_md_glob:
        print("Baseline carries the narrow list: the 2026-08-23 `.md` widening is "
              "retired, and every path is now judged on its own.")

    regressions, disclosed, narrowings = [], [], []
    for path in corpus:
        was = before.is_protected_file(path)
        now = after.is_protected_file(path)
        if was and not now:
            bucket = (disclosed if _is_disclosed(path, identity_docs, baseline_had_md_glob)
                      else regressions)
            bucket.append(path)
        elif now and not was:
            narrowings.append(path)

    print("Corpus: %d paths (%d listed + %d derived from the baseline guard)"
          % (len(corpus), len(CORPUS), len(corpus) - len(CORPUS)))
    if narrowings:
        print("\nNewly PROTECTED (a tightening - always fine):")
        for path in narrowings:
            print("  + %s" % path)
    if disclosed:
        print("\nDisclosed widenings (%d):" % len(disclosed))
        for path in disclosed:
            print("  ~ %s" % path)

    if regressions:
        print("\nFAIL: %d path(s) lost protection and are NOT disclosed:" % len(regressions))
        for path in regressions:
            print("  - %s" % path)
        print("\nIf the widening is intended, add it to DISCLOSED_WIDENINGS in this script "
              "and to CHANGELOG.md. Both are reviewed like any other change.")
        return 1

    print("\nOK: no undisclosed path lost protection.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
