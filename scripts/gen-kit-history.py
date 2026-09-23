#!/usr/bin/env python3
"""Build .claude/.claudekit-history.json: the sha256 of every version the kit shipped.

`ck update` keeps a managed file whose bytes differ from the install receipt. Without a
history it cannot tell a project edit from a stale copy of an older kit version, so stale
copies were kept forever (46 on qa-agents, 2026-09-23). With it, the installer
(install_overrides.py `reconcile`) replaces a file whose hash the kit once shipped and
3-way merges a real edit, fetching the merge base from the kit's git by blob id.

Shape: ``{"format": 1, "through": "<version>", "releases": [...], "files":
{rel: {sha256: [version, git_blob]}}}``, ``rel`` relative to ``.claude/`` as in the
manifest. The window is the last RELEASES version bumps of pyproject.toml, and every commit
from the oldest of them through the newest (installs happen from any commit, not only
releases). A version is the pyproject version of the commit a blob first appeared in.

    python3 scripts/gen-kit-history.py            # write, through the latest release
    python3 scripts/gen-kit-history.py --check    # exit 1 when the file is stale
    python3 scripts/gen-kit-history.py --through HEAD --out FILE   # install.sh, git kits

Deterministic (no timestamps), so --check is exact. stdlib only, py3.9.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

RELEASES = 30
OUT = os.path.join(".claude", ".claudekit-history.json")
# What is managed is install_overrides.is_unmanaged's call, shared with install.sh's
# manifest writer and reconcile; the history file itself is the kit's, never a project's.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                                ".claude", "operations", "scripts"))
from install_overrides import is_unmanaged  # noqa: E402

VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.M)


def git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                          check=True).stdout


def version_at(root, commit):
    try:
        found = VERSION_LINE.search(git(root, "show", "%s:pyproject.toml" % commit))
    except subprocess.CalledProcessError:
        return None
    return found.group(1) if found else None


def releases(root, through):
    """[(commit, version)] of the last RELEASES version bumps reachable from ``through``,
    oldest first."""
    bumps = []
    for commit in git(root, "log", "--format=%H", "-G", r"^version *=", through, "--",
                      "pyproject.toml").split():
        version = version_at(root, commit)
        if version and (not bumps or bumps[-1][1] != version):
            bumps.append((commit, version))
        if len(bumps) == RELEASES:
            break
    return list(reversed(bumps))


def _managed(path):
    if not path.startswith(".claude/"):
        return None
    rel = path[len(".claude/"):]
    if rel == ".claudekit-history.json" or is_unmanaged(rel):
        return None
    return rel


def build(root, through):
    bumps = releases(root, "HEAD" if through == "release" else through)
    if not bumps:
        return {"format": 1, "through": None, "releases": [], "files": {}}
    first = bumps[0][0]
    end = bumps[-1][0] if through == "release" else through
    seen = {}  # (rel, blob) -> version it first shipped in
    version = bumps[0][1]
    for line in git(root, "ls-tree", "-r", first, "--", ".claude").splitlines():
        meta, path = line.split("\t", 1)
        rel = _managed(path)
        if rel and meta.split()[1] == "blob":
            seen.setdefault((rel, meta.split()[2]), version)
    log = git(root, "log", "--reverse", "--format=C %H", "--raw", "--no-abbrev",
              "--no-renames", "--first-parent", "%s..%s" % (first, end), "--", ".claude",
              "pyproject.toml")
    # A commit's raw lines follow its "C <sha>" line, sorted by path, so .claude/ comes
    # before pyproject.toml: collect the commit's blobs, then label them with its version.
    commit, pending = first, []

    def flush():
        for rel, blob in pending:
            seen.setdefault((rel, blob), version)
        del pending[:]

    for line in log.splitlines():
        if line.startswith("C "):
            flush()
            commit = line[2:]
            continue
        if not line.startswith(":"):
            continue
        meta, path = line.split("\t", 1)
        blob = meta.split()[3]
        if path == "pyproject.toml":
            version = version_at(root, commit) or version
            continue
        rel = _managed(path)
        if rel and set(blob) != {"0"}:
            pending.append((rel, blob))
    flush()
    blobs = sorted({blob for _, blob in seen})
    digests = _sha256_blobs(root, blobs)
    files = {}
    for (rel, blob), ver in sorted(seen.items()):
        files.setdefault(rel, {})[digests[blob]] = [ver, blob]
    through_version = version_at(root, end) or bumps[-1][1]
    return {"format": 1, "through": through_version,
            "releases": [v for _, v in bumps], "files": files}


def _sha256_blobs(root, blobs):
    """{blob: sha256 of its bytes}, through one `git cat-file --batch`."""
    proc = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                          input=("\n".join(blobs) + "\n").encode(), capture_output=True,
                          check=True)
    out, pos, digests = proc.stdout, 0, {}
    for blob in blobs:
        header_end = out.index(b"\n", pos)
        size = int(out[pos:header_end].split()[2])
        body = out[header_end + 1:header_end + 1 + size]
        digests[blob] = hashlib.sha256(body).hexdigest()
        pos = header_end + 1 + size + 1
    return digests


def render(data):
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the file is stale")
    parser.add_argument("--through", default="release",
                        help="last commit to include (default: the latest version bump)")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    parser.add_argument("--out", help="output path (default: %s under --root)" % OUT)
    args = parser.parse_args(argv)
    out = args.out or os.path.join(args.root, OUT)
    text = render(build(args.root, args.through))
    if args.check:
        try:
            with open(out, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = None
        if current != text:
            sys.stderr.write("%s is stale: run python3 scripts/gen-kit-history.py\n" % out)
            return 1
        print("kit history up to date (%s)" % out)
        return 0
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
