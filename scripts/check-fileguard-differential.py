#!/usr/bin/env python3
"""Differential gate for the file-guard classifier: no change may un-flag a secret.

Why this exists, specifically. `check-validator-differential.py` guards
`command_validator.py`; `check-protected-differential.py` guards
`shared.is_protected_file`. `.claude/hooks/file-guard.sh` -- the third deny-shaped
decision in this repo -- had no such gate, and the first widening of it was about to be
made (a `public.pem` / test-fixture allowlist) with nothing watching. That is the exact
shape `check-protected-differential.py`'s own docstring records going wrong once already:
"the first change to widen it sailed straight through".

The subject is shell, not Python, so this gate runs the classifier as a SUBPROCESS on both
sides rather than importing it. It compares the CATEGORY each side reports, not just the
exit code: a path that stays flagged but changes category is a reclassification worth
seeing, while a path that goes flagged -> clean is a widening that must be disclosed.

Honest scope, in the same terms hard rule 6 demands of the guard itself: file-guard is a
denylist speed bump wrapped in an ADVISORY hook (`file-guard-gate.sh` exits 0 always and
only runs under `ECC_HOOK_PROFILE=strict`). This gate protects the classifier's coverage,
not the repo. A clean run means "no path in this corpus lost its flag", never "secrets
cannot be edited".

Zero third-party dependencies; Python 3.9+.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GUARD_PATH = ".claude/hooks/file-guard.sh"

# Where the guard used to live. Batch 1 PROMOTED it out of `templates/hooks/`, so a
# baseline older than that promotion has no `.claude/hooks/file-guard.sh` at all and the
# gate SKIPPED -- measured against `origin/main` on the first run of this script, which
# is exactly the silent pass the sibling gates warn about. A renamed subject is not an
# absent one.
LEGACY_GUARD_PATHS = ["templates/hooks/file-guard.sh"]

# Paths the classifier is asked about: genuine secrets that must STAY flagged, the
# public/test names an allowlist is meant to free, and ordinary files that were never
# in scope -- so a change that widens INTO them shows up as a tightening.
CORPUS: List[str] = [
    # Genuine secrets. A regression here is the failure this gate exists for.
    #
    # THE BLOCK BELOW EXISTS BECAUSE THIS CORPUS FAILED ONCE, ON THE FIRST WIDENING IT
    # WAS WRITTEN TO POLICE. Not one of the original "genuine secret" entries carried a
    # `test`/`tests`/`testdata`/`fixtures` path component, while all four component-bearing
    # entries were `.pem`/`.key`/`.p12`/`.crt` -- the allowlist's own targets. So a rule
    # that freed EVERY category under a test directory produced `OK: no undisclosed path
    # lost its flag` while ten real secret shapes went silent. A corpus drawn from the
    # change under test can only confirm it. Every category must therefore appear under a
    # test component as well as at the root.
    # Cert-EXTENSIONED members of other categories. The corpus lacked every one of these
    # because it was rebuilt around the previous hole: v2's allowlist was gated on the
    # extension, so a corpus whose test-component entries all avoided that extension set
    # could not see the hole. `k8s/tests/tls.key` is the canonical checked-in TLS secret.
    "k8s/tests/tls.key", "tests/fixtures/.ssh/deploy.key", "tests/api_key.key",
    "pii/tests/customers.key", "production/tests/data.key",
    "tests/credentials.json.pem", "testdata/wallet.dat.key", "fixtures/prod.sqlite.crt",
    "secrets/tests/db.bak.p12",
    # CHAINED certificate suffixes. Branch 8 matches the LAST element of an arbitrarily
    # long chain while the correction stripped exactly one, so appending a second suffix to
    # the entry directly above freed it. The corpus held the n=1 form and not the n=2 form.
    "tests/credentials.json.pem.key", "tests/passwd.pem.key", "tests/id_rsa.pem.key",
    "testdata/prod.sqlite.crt.pem", "tests/wallet.dat.pem.crt.key",
    "tests/secrets.json.pem.key",
    # Secret directories the first list missed: singular forms and the conventional homes
    # of the very file branch 8 is about.
    "k8s/tests/tls.key", ".kube/tests/tls.key", "secret/tests/x.pem",
    "certs/tests/server.key", "ssl/tests/x.key", "private/tests/x.pem",
    ".ssh/deploy.key.pub", ".ssh/authorized_keys.pub",
    "tests/fixtures/.env", "test/secrets.json", "tests/credentials.json",
    "tests/id_rsa", "testdata/wallet.dat", "spec/fixtures/terraform.tfstate",
    "home/tests/.aws/credentials", "k8s/tests/secret-db.yaml",
    "tests/fixtures/passwd", "__fixtures__/server.key.gpg", "testdata/prod.sqlite",
    "tests/.npmrc", "test/.pgpass", "tests/fixtures/vault-secrets.yml",
    # `pii/` and `production/` must not be freed by the schema/model exclusion.
    "pii/model_training_data.csv", "pii/customer_model.csv", "pii/datamodel.csv",
    "customer-data-schema-dump.sql", "model-customer-data.csv",
    ".env", ".env.local", "config/.env.production", "secrets.yaml",
    "id_rsa", "server.key", "private.pem", "client.p12", "cert.pfx",
    "keystore.json", "wallet.dat", "credentials.json", ".npmrc", ".pypirc",
    ".aws/credentials", ".ssh/id_ed25519", "vault-secrets.yml",
    ".github/secrets/deploy.json", "passwd", "shadow", ".htpasswd",
    "prod.sqlite", "database.sqlite3", ".pgpass", "my.cnf",
    "k8s/secret-db.yaml", "kubernetes/secrets.yaml", "pii/customers.csv",
    "production/customer-data.csv", "secrets/backup.bak",
    "credentials/old.backup", "password.txt",
    # Public-by-construction and test material: the allowlist targets.
    "public.pem", "id_rsa.pub", "ca-bundle.crt", "ca-certificates.crt",
    "tests/fixtures/test.pem", "tests/fixtures/example.key",
    "spec/fixtures/sample.p12", "testdata/dummy.crt",
    "customer_data_schema.sql", "docs/customer-data-model.md",
    # Never in scope.
    "README.md", "src/main.py", "package.json", "install.sh",
    ".claude/hooks/lib.sh", "docs/ARCHITECTURE.md",
]

# Widenings that are ALLOWED, each with the reason. An entry here is a decision on the
# record, not a suppression: adding one takes the same review as changing the guard.
DISCLOSED_WIDENINGS: List[Dict[str, str]] = [
    {
        "path": "public.pem",
        "why": "2026-08-24: the extension set (`cert|crt|pem|key|p12|pfx`) had no escape hatch, so `public.pem`, `id_rsa.pub` and the conventional CA bundle names classified as `certificates`. These are public by construction -- a public key is the half you publish. file-guard is wired through an ADVISORY hook (`file-guard-gate.sh` exits 0 always, `strict` profile only), so the cost of a false flag is a warning nobody believes, which is worse than no warning. Freed by STEM, not substring: `publickeys.pem` is still flagged.",
    },
    {
        "path": "id_rsa.pub",
        "why": "2026-08-24: the extension set (`cert|crt|pem|key|p12|pfx`) had no escape hatch, so `public.pem`, `id_rsa.pub` and the conventional CA bundle names classified as `certificates`. These are public by construction -- a public key is the half you publish. file-guard is wired through an ADVISORY hook (`file-guard-gate.sh` exits 0 always, `strict` profile only), so the cost of a false flag is a warning nobody believes, which is worse than no warning. Freed by STEM, not substring: `publickeys.pem` is still flagged.",
    },
    {
        "path": "ca-bundle.crt",
        "why": "2026-08-24: the extension set (`cert|crt|pem|key|p12|pfx`) had no escape hatch, so `public.pem`, `id_rsa.pub` and the conventional CA bundle names classified as `certificates`. These are public by construction -- a public key is the half you publish. file-guard is wired through an ADVISORY hook (`file-guard-gate.sh` exits 0 always, `strict` profile only), so the cost of a false flag is a warning nobody believes, which is worse than no warning. Freed by STEM, not substring: `publickeys.pem` is still flagged.",
    },
    {
        "path": "ca-certificates.crt",
        "why": "2026-08-24: the extension set (`cert|crt|pem|key|p12|pfx`) had no escape hatch, so `public.pem`, `id_rsa.pub` and the conventional CA bundle names classified as `certificates`. These are public by construction -- a public key is the half you publish. file-guard is wired through an ADVISORY hook (`file-guard-gate.sh` exits 0 always, `strict` profile only), so the cost of a false flag is a warning nobody believes, which is worse than no warning. Freed by STEM, not substring: `publickeys.pem` is still flagged.",
    },
    {
        "path": "tests/fixtures/test.pem",
        "why": "2026-08-24: same change. Test material under a `test`/`tests`/`testdata`/`fixtures` PATH COMPONENT, and `example.*`/`sample.*`/`dummy.*` basenames. A component match, not a substring: `latest.pem` is still flagged. A repo that wants the old behaviour keeps `ECC_HOOK_PROFILE` off `strict`, where none of this runs at all.",
    },
    {
        "path": "tests/fixtures/example.key",
        "why": "2026-08-24: same change. Test material under a `test`/`tests`/`testdata`/`fixtures` PATH COMPONENT, and `example.*`/`sample.*`/`dummy.*` basenames. A component match, not a substring: `latest.pem` is still flagged. A repo that wants the old behaviour keeps `ECC_HOOK_PROFILE` off `strict`, where none of this runs at all.",
    },
    {
        "path": "spec/fixtures/sample.p12",
        "why": "2026-08-24: same change. Test material under a `test`/`tests`/`testdata`/`fixtures` PATH COMPONENT, and `example.*`/`sample.*`/`dummy.*` basenames. A component match, not a substring: `latest.pem` is still flagged. A repo that wants the old behaviour keeps `ECC_HOOK_PROFILE` off `strict`, where none of this runs at all.",
    },
    {
        "path": "testdata/dummy.crt",
        "why": "2026-08-24: same change. Test material under a `test`/`tests`/`testdata`/`fixtures` PATH COMPONENT, and `example.*`/`sample.*`/`dummy.*` basenames. A component match, not a substring: `latest.pem` is still flagged. A repo that wants the old behaviour keeps `ECC_HOOK_PROFILE` off `strict`, where none of this runs at all.",
    },
    {
        "path": "customer_data_schema.sql",
        "why": "2026-08-24: `*\"customer\"*\"data\"*` matched `customer_data_schema.sql` and `customer-data-model.md`. A schema or a model doc DESCRIBES data; it is not data. Narrowed by excluding the two words that mean 'shape of' rather than by dropping the pattern, so `production/customer-data.csv` is still flagged -- verified in the corpus above.",
    },
    {
        "path": "docs/customer-data-model.md",
        "why": "2026-08-24: `*\"customer\"*\"data\"*` matched `customer_data_schema.sql` and `customer-data-model.md`. A schema or a model doc DESCRIBES data; it is not data. Narrowed by excluding the two words that mean 'shape of' rather than by dropping the pattern, so `production/customer-data.csv` is still flagged -- verified in the corpus above.",
    },
]

# `[a-z0-9-]`, with the digit: `k8s-secrets` did not match, so a legitimate category was
# reported as the `flagged-uncategorised` sentinel meant for a BROKEN guard -- and a
# genuinely unparseable output became indistinguishable from a normal one.
# Root-level, category-diverse, none under a test component: any guard that classifies at
# all flags these. Used as the vacuity floor for a baseline (see main()).
BASELINE_FLOOR = [
    ".env", "id_rsa", "credentials.json", "secrets.yaml", "private.pem",
    "wallet.dat", "passwd", ".npmrc", "prod.sqlite", ".pgpass",
    "k8s/secret-db.yaml", "pii/customers.csv",
]

_CATEGORY = re.compile(r"BLOCKED \[([a-z0-9-]+)\]")


def _git(repo_root: Path, *args: str) -> Optional[str]:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=repo_root)
    return result.stdout.strip() if result.returncode == 0 else None


def classify(guard: Path, path: str) -> Optional[str]:
    """The category this guard reports for `path`, or None when it reports clean.

    The guard is invoked from a directory that is NOT the repo, because a classifier
    that consults the filesystem would otherwise answer differently for a path that
    happens to exist here -- and the answer must depend on the name alone.
    """
    proc = subprocess.run(["bash", str(guard), path], capture_output=True, text=True,
                          cwd=str(guard.parent))
    if proc.returncode == 0:
        return None
    match = _CATEGORY.search(proc.stdout + proc.stderr)
    # Flagged but unparseable is reported as a sentinel rather than as clean: reading an
    # unrecognised format as "not flagged" would turn a broken guard into a green gate.
    return match.group(1) if match else "flagged-uncategorised"


def _is_disclosed(path: str) -> bool:
    return any(entry.get("path") == path for entry in DISCLOSED_WIDENINGS)


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
        print("SKIP: could not resolve a baseline ref")
        return 1 if args.require_baseline else 0

    head = _git(repo_root, "rev-parse", "HEAD")
    if head and _git(repo_root, "rev-parse", ref) == head:
        # The trap both sibling gates document: a baseline equal to HEAD diffs the tree
        # against itself and passes forever.
        print("SKIP: baseline %s resolves to HEAD - nothing to compare" % ref)
        return 1 if args.require_baseline else 0

    print("Baseline: %s (%s)" % (ref, args.baseline))

    shown = None
    baseline_path = GUARD_PATH
    for candidate in [GUARD_PATH] + LEGACY_GUARD_PATHS:
        attempt = subprocess.run(["git", "show", "%s:%s" % (ref, candidate)],
                                 capture_output=True, text=True, cwd=repo_root)
        if attempt.returncode == 0:
            shown, baseline_path = attempt, candidate
            break
    if shown is None:
        print("SKIP: no file-guard.sh at %s (tried %s)"
              % (ref, ", ".join([GUARD_PATH] + LEGACY_GUARD_PATHS)))
        return 1 if args.require_baseline else 0
    if baseline_path != GUARD_PATH:
        print("Baseline guard found at its pre-promotion path: %s" % baseline_path)

    with tempfile.TemporaryDirectory() as tmp:
        before_path = Path(tmp) / "file-guard.sh"
        before_path.write_text(shown.stdout, encoding="utf-8")
        after_path = repo_root / GUARD_PATH

        # A baseline that classifies NOTHING makes every path look already-clean, so no
        # regression can be recorded and the gate prints OK. `bash` on an empty script
        # exits 0, so a truncated or empty `git show` would do exactly that. Refuse to
        # trust a baseline that cannot flag a canonical secret.
        for canary in (".env", "id_rsa"):
            if classify(before_path, canary) is None:
                print("FAIL: the baseline guard does not flag %s -- it is empty, "
                      "truncated or broken, and comparing against it would pass "
                      "vacuously." % canary)
                return 1
        # Two named canaries are not enough: a baseline flagging ONLY those two makes every
        # other corpus path look already-clean, so no regression can be recorded and the
        # gate prints OK. The floor is a fixed set of ROOT-LEVEL canonical secrets rather
        # than a fraction of CORPUS, deliberately: a fraction also fires when the baseline
        # merely has a BUG that frees some paths (measured: `d945278` flags 31 of 76,
        # because that is the commit whose allowlist this gate exists to have caught), and
        # conflating "broken baseline" with "buggy baseline" would make the gate refuse to
        # run in exactly the case it is for. These twelve are category-diverse and none
        # sits under a test component, so any guard that classifies at all flags them.
        # Per-CATEGORY as well as per-path. A fixed 12-path floor proves the baseline is
        # not empty; it never proves it is representative, so a baseline flagging exactly
        # those paths and nothing else passed while making the other 64 corpus paths look
        # already-clean. Requiring at least one flagged path per category the baseline
        # knows about closes that window cheaply.
        baseline_categories = {classify(before_path, p) for p in CORPUS}
        baseline_categories.discard(None)
        if len(baseline_categories) < 8:
            print("FAIL: the baseline guard produces only %d distinct categories across "
                  "the corpus (%s). It classifies too little to reveal a regression."
                  % (len(baseline_categories), ", ".join(sorted(baseline_categories))))
            return 1
        floor_missing = [p for p in BASELINE_FLOOR if classify(before_path, p) is None]
        if len(floor_missing) > 2:
            print("FAIL: the baseline guard does not flag %d of %d canonical root-level "
                  "secrets (%s). It is empty, truncated or broken, and comparing against "
                  "it would pass vacuously."
                  % (len(floor_missing), len(BASELINE_FLOOR), ", ".join(floor_missing)))
            return 1

        regressions: List[Tuple[str, str]] = []
        disclosed: List[Tuple[str, str]] = []
        tightenings: List[Tuple[str, str]] = []
        reclassified: List[Tuple[str, str, str]] = []

        for path in CORPUS:
            was = classify(before_path, path)
            now = classify(after_path, path)
            if was and not now:
                (disclosed if _is_disclosed(path) else regressions).append((path, was))
            elif now and not was:
                tightenings.append((path, now))
            elif was and now and was != now:
                reclassified.append((path, was, now))

    print("Corpus: %d paths" % len(CORPUS))
    if tightenings:
        print("\nNewly flagged (a tightening - always fine):")
        for path, cat in tightenings:
            print("  + %s [%s]" % (path, cat))
    if reclassified:
        print("\nReclassified (still flagged, different category):")
        for path, was, now in reclassified:
            print("  ~ %s [%s -> %s]" % (path, was, now))
    if disclosed:
        print("\nDisclosed widenings (%d):" % len(disclosed))
        for path, cat in disclosed:
            print("  ~ %s [was %s]" % (path, cat))

    if regressions:
        print("\nFAIL: %d path(s) lost their flag and are NOT disclosed:" % len(regressions))
        for path, cat in regressions:
            print("  - %s [was %s]" % (path, cat))
        print("\nIf the widening is intended, add it to DISCLOSED_WIDENINGS in this "
              "script and to CHANGELOG.md. Both are reviewed like any other change.")
        return 1

    print("\nOK: no undisclosed path lost its flag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
