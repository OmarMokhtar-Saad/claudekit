---
name: release-integrity
description: Use when a repo publishes versioned artifacts (a zip, wheel, image, or tag) — the four deterministic gates that keep a published release identical to the tree it claims to come from.
---

# Release Integrity

Four gates. All deterministic, all runnable in CI, none requiring a model.
Review is not one of them: review catches judgment errors, and every failure
below is a mechanical one that review reliably misses.

## Why these four

Measured on a real published project across four days: twelve releases, no CI,
and a `MANIFEST.sha256` committed at a tag that does not reproduce from that
tag's own tree (one file committed LF, hashed CRLF). A release shipped a
manifest recording the wrong tree and was reverted four hours later in a PATCH
version, silently withdrawing two shipped modules from users. The CHANGELOG had
exactly one version section — every release renamed the heading — so none of it
was visible in history.

## Gate 1 — the artifact reproduces from its own tag

Rebuild from a clean checkout of the tag (not the working tree) and require
byte-identity with what was published.

```bash
git archive "$TAG" | (mkdir -p /tmp/rebuilt && tar -x -C /tmp/rebuilt)
diff -r /tmp/rebuilt "$PUBLISHED_TREE"
```

Line endings are the usual culprit. Commit a `.gitattributes` (`* text=auto`
plus explicit `eol=crlf` for `.cmd`/`.bat`/`.ps1`) so the packaged bytes and
the committed bytes cannot diverge. A manifest that only verifies on the
machine that built it is not an integrity check.

## Gate 2 — every removal is declared

A file deleted since the previous tag, that appeared in the PREVIOUS tag's
manifest, must be listed in the repo's removed-paths ledger in the SAME commit.
Otherwise the file is stranded on every install that took the earlier release:
the prune pass admits a path only on evidence from the old manifest, and that
manifest has been overwritten.

```bash
git diff --diff-filter=D --name-only "$PREV_TAG..$TAG" \
  | while read -r f; do
      grep -q "^$f$" REMOVED_PATHS || { echo "undeclared removal: $f"; exit 1; }
    done
```

## Gate 3 — the changelog gained a section

Require a NEW `## [x.y.z]` heading, not a renamed one:

```bash
[ "$(git show "$TAG:CHANGELOG.md" | grep -c '^## \[')" \
  -gt "$(git show "$PREV_TAG:CHANGELOG.md" | grep -c '^## \[')" ]
```

## Gate 4 — the version is strictly monotonic

Compare the new version against the highest existing tag and reject equal or
lower. Two agents bumping a VERSION file independently produce duplicate and
regressing releases; only a check catches it.

## Applying it

`templates/release-gate.yml` is a parameterised GitHub Actions workflow
implementing all four. Adapt the paths; keep the gates. Run them on the tag,
before the artifact is published — a gate that runs after publication only
tells you what your users already found.
