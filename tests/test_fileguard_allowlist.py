"""The file-guard allowlist frees public/test material and nothing else.

`file-guard.sh`'s extension set (`cert|crt|pem|key|p12|pfx`) had no escape hatch, so
`public.pem`, `id_rsa.pub`, CA bundles and every `.pem` under `tests/fixtures/` were
flagged as `certificates`. The classifier is wired through an ADVISORY hook --
`file-guard-gate.sh` exits 0 always and only runs under `ECC_HOOK_PROFILE=strict` -- so
the cost was never a blocked edit. It was a warning that cries wolf, and an advisory
nobody believes is worse than none.

Both directions are asserted here, because an allowlist is a widening and the failure
that matters is a real secret going quiet. `scripts/check-fileguard-differential.py` is
the gate that watches that across commits; this file pins the intended behaviour at a
point in time. The two are not redundant: the gate compares against a baseline and would
go green the moment a widening is disclosed, while these assertions state what the
classifier must do regardless.

Matching is by STEM and by PATH COMPONENT, never substring -- `publickeys.pem` and
`latest.pem` must stay flagged. Those two cases were the original point of this file, and
they were never the risk.

**The risk was scope, not substrings.** The first allowlist `return`ed before all thirteen
category branches, so a `tests/`/`fixtures/` path component was not a certificate
exemption -- it exempted `.env`, `credentials.json`, `id_rsa`, `wallet.dat`,
`terraform.tfstate`, `passwd`, k8s secrets and `pii/` too. An adversarial review executed
it and found ten regressions. Both this file and the differential gate passed, because
neither asserted a NON-certificate secret under a test component. The allowlist is now
reachable only when the extension is in `cert|crt|pem|key|p12|pfx|pub`, and the
`STILL_FLAGGED` block below pins one path per category so the same hole cannot reopen.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / ".claude" / "hooks" / "file-guard.sh"


def classify(path):
    """None when the guard reports the path clean, else the category it reports."""
    proc = subprocess.run(["bash", str(GUARD), path], capture_output=True, text=True)
    if proc.returncode == 0:
        return None
    out = proc.stdout + proc.stderr
    start = out.find("BLOCKED [")
    return out[start + 9:out.find("]", start)] if start >= 0 else "flagged-uncategorised"


FREED = [
    "public.pem", "public.crt", "id_rsa.pub", "server.key.pub",
    "ca-bundle.crt", "ca-certificates.crt",
    "tests/fixtures/test.pem", "tests/fixtures/example.key",
    "test/data.p12", "testdata/dummy.crt", "spec/fixtures/sample.p12",
    "src/__fixtures__/fake.pem",
    "example.pem", "sample.key", "dummy.crt",
    "customer_data_schema.sql", "docs/customer-data-model.md",
]

STILL_FLAGGED = [
    # EVERY CATEGORY UNDER A TEST COMPONENT. This block is the assertion this file was
    # missing: `FREED` contained `test/data.p12`, generalising past anything asserted, so
    # a rule that freed all thirteen categories under a test directory passed both this
    # file and the differential gate. Ten real secret shapes went silent. The allowlist is
    # now reachable only for the cert/key extensions that motivated it, and these pin it.
    ("tests/fixtures/.env", "env-files"),
    ("test/secrets.json", "api-tokens"),
    ("tests/credentials.json", "credential-files"),
    ("tests/id_rsa", "ssh-keys"),
    ("testdata/wallet.dat", "crypto-wallets"),
    ("home/tests/.aws/credentials", "cloud-configs"),
    ("tests/fixtures/passwd", "password-files"),
    ("testdata/prod.sqlite", "database-files"),
    ("test/.pgpass", "database-files"),
    ("tests/.npmrc", "credential-files"),
    ("tests/fixtures/vault-secrets.yml", "cicd-secrets"),
    # `pii/` and `production/` are unconditional: the schema/model exclusion corrects only
    # the `customer`+`data` predicate and must not reach past it.
    ("pii/model_training_data.csv", "production-data"),
    ("pii/customer_model.csv", "production-data"),
    ("pii/datamodel.csv", "production-data"),
    # A dump IS data. Anchored to the `-schema.`/`_schema.` shape, not the bare substring.
    ("customer-data-schema-dump.sql", "production-data"),
    ("model-customer-data.csv", "production-data"),
    # The near misses. These are the assertions that make the allowlist narrow.
    ("publickeys.pem", "certificates"),      # `public` as a substring, not a stem
    ("latest.pem", "certificates"),          # `test` inside a basename, not a component
    ("contest/prod.key", "certificates"),    # `test` inside a directory name
    ("samples.key", "certificates"),         # `sample` as a substring, not a stem
    # Genuine secrets, untouched.
    (".env", "env-files"),
    ("id_rsa", "ssh-keys"),
    ("server.key", "certificates"),
    ("private.pem", "certificates"),
    ("client.p12", "certificates"),
    ("credentials.json", "credential-files"),
    ("wallet.dat", "crypto-wallets"),
    ("passwd", "password-files"),
    ("production/customer-data.csv", "production-data"),
    ("pii/customers.csv", "production-data"),
    ("k8s/secret-db.yaml", "k8s-secrets"),
]


@pytest.mark.parametrize("path", FREED)
def test_public_and_test_material_is_not_flagged(path):
    assert classify(path) is None, f"{path} should no longer be flagged"


@pytest.mark.parametrize("path,category", STILL_FLAGGED)
def test_secrets_and_near_misses_stay_flagged(path, category):
    actual = classify(path)
    assert actual is not None, f"{path} lost its flag -- this is the regression that matters"
    assert actual == category, f"{path}: expected {category}, got {actual}"


# ---------------------------------------------------------------------------
# The generated invariant. This class of defect has now shipped THREE times:
#   v1  the allowlist sat above all 13 branches and exempted every category;
#   v2  it was gated on the EXTENSION, which is not the category -- classify()
#       returns on the first match, so every `.key`/`.pem` reached the certificate
#       branch before branches 9-13 could claim it (`k8s/tests/tls.key` went silent);
#   v3  (current) it is applied to the CLASSIFICATION, and only when no stronger
#       category also matches.
# Three occurrences of one class earn a mechanical check rather than more examples.
# Hand-picked paths cannot carry this: both previous corpora were thorough and both
# were blind, because each was written around the hole that had just been found.
#
# The property, stated once: a file that a NON-CERTIFICATE category owns must stay
# flagged no matter what certificate extension it carries or which test-shaped
# directory it sits in. Generated, so it cannot be blind to the next variation.
# ---------------------------------------------------------------------------

# One exemplar per non-certificate category, with the category it must keep.
CATEGORY_EXEMPLARS = [
    (".env", "env-files"),
    ("credentials.json", "credential-files"),
    ("id_rsa", "ssh-keys"),
    ("api_key.txt", "api-tokens"),
    (".aws/credentials", "cloud-configs"),
    ("prod.sqlite", "database-files"),
    ("vault-secrets.yml", "cicd-secrets"),
    ("passwd", "password-files"),
    ("wallet.dat", "crypto-wallets"),
    ("secrets/backup.bak", "sensitive-backups"),
    ("pii/customers.csv", "production-data"),
    ("k8s/secret-db.yaml", "k8s-secrets"),
]

TEST_PREFIXES = ["", "tests/", "fixtures/", "testdata/", "spec/fixtures/", "__fixtures__/"]
CERT_EXTENSIONS = ["", ".pem", ".key", ".crt", ".p12", ".pfx"]

# CHAINS, because branch 8 matches the LAST element of an arbitrarily long extension chain
# while the correction stripped exactly one. The single-suffix generator was blind to that
# and 541 tests passed with eight live regressions: `tests/credentials.json.pem.key`,
# `tests/passwd.pem.key`, `testdata/prod.sqlite.crt.pem` and friends. A generator that
# varies only the axis the LAST defect lived on is the previous two failures in a new coat.
CERT_CHAINS = [".pem.key", ".key.pem", ".crt.pem", ".pem.pem", ".pem.crt.key"]

# UPPERCASE, because the guard lowercases the extension in two places and nothing
# generated ever tested it.
CASE_VARIANTS = [".PEM", ".Key"]


def _generated_cases():
    for exemplar, category in CATEGORY_EXEMPLARS:
        for prefix in TEST_PREFIXES:
            for ext in CERT_EXTENSIONS + CERT_CHAINS + CASE_VARIANTS:
                yield f"{prefix}{exemplar}{ext}", category


@pytest.mark.parametrize("path,category", list(_generated_cases()))
def test_a_non_certificate_category_survives_any_cert_extension_anywhere(path, category):
    """A stronger category must beat the certificate allowlist, always.

    `.pub` is deliberately NOT in CERT_EXTENSIONS: a public key IS the half you
    publish, so `id_rsa.pub` being clean is intended behaviour and is asserted in
    FREED above -- not a hole. Every other certificate extension is a claim about
    the file's FORMAT and says nothing about whether it holds a secret.
    """
    actual = classify(path)
    assert actual is not None, (
        f"{path} lost its flag: a {category} file is still a {category} file when it "
        f"carries a certificate extension or sits under a test directory"
    )

# Directories that signal secrets override a test-shaped path. `k8s/tests/tls.key` is why:
# branch 13 needs the word "secret" in the path, so a TLS key called `tls.key` never
# reaches it, falls through to `certificates`, and a `tests/` component freed it. The
# DIFFERENTIAL GATE caught that one, not this file -- the ratchet earning its keep.
SECRET_DIRS = ["k8s", "kubernetes", "pii", "production", "prod", "secrets",
               "credentials", ".ssh", ".aws", ".gnupg", "vault", "keys"]


@pytest.mark.parametrize("directory", SECRET_DIRS)
@pytest.mark.parametrize("ext", [".pem", ".key", ".crt", ".p12", ".pfx", ".pem.key"])
def test_a_secret_directory_beats_a_test_component(directory, ext):
    """"No stronger category fired" is not the same as "nothing here is sensitive"."""
    path = f"{directory}/tests/fixtures/anonymous{ext}"
    assert classify(path) is not None, f"{path} was freed by its test component"


@pytest.mark.parametrize("directory", SECRET_DIRS)
@pytest.mark.parametrize("exemplar,category", CATEGORY_EXEMPLARS)
def test_a_secret_directory_crossed_with_every_category(directory, exemplar, category):
    """The veto and the chain-strip were never exercised TOGETHER: SECRET_DIRS was tested
    only against a basename of `anonymous`, so no generated case put a real category
    exemplar inside a secrets directory."""
    path = f"{directory}/tests/{exemplar}.pem.key"
    assert classify(path) is not None, f"{path} was freed"


@pytest.mark.parametrize("path", [
    # One per shape WITHIN a branch, not one per branch: branch 4 has four shapes
    # (`.token`, `.secret`, `secrets.json`, `api_key*`) and only `api_key.txt` was an
    # exemplar. Every entry below is a shape the guard really recognises -- verified by
    # classifying the bare name first. My first draft of this list assumed `*.token` and
    # `service-account.json` were categories; they are not, so a `.key` under `tests/`
    # freeing them is the INTENDED widening, not a regression. Asserting an expectation I
    # had not checked would have manufactured three defects.
    "tests/.token.pem.key", "tests/.secret.pem", "tests/secrets.json.pem.key",
    "tests/api_key_prod.key", "tests/.env.production.pem", "tests/.envrc.key",
    "tests/.htpasswd.key", "tests/known_hosts.pem", "tests/terraform.tfstate.pem",
    "tests/my.cnf.key", "tests/keystore.json.crt", "tests/id_ed25519.pem",
])
def test_within_category_branch_shapes_survive_a_cert_chain(path):
    """Coverage measured per BRANCH SHAPE rather than per category."""
    assert classify(path) is not None, f"{path} was freed"

# ---------------------------------------------------------------------------
# THE DERIVED CORPUS. Five rounds of review found the same class five times --
# `correction-narrower-than-the-predicate-it-corrects` -- and every round's corpus was
# written around the hole just found, so it was blind to the next one BY CONSTRUCTION:
#
#   r1  the allowlist sat above all 13 category branches
#   r2  it was gated on the file EXTENSION, which is not the CATEGORY
#   r3  the strip removed ONE suffix while branch 8 matches a chain
#   r4a the peel walked only chains made ENTIRELY of certificate extensions, so one
#       interposed `.gz`/`.bak` -- a compressed or backed-up key -- re-opened r3's hole
#   r4b the corpus was extended along r3's axis and not along r4's own change, so the
#       differential gate certified this commit's own widening as clean
#
# More hand-picked examples cannot close that; the hand-picking IS the class. So the
# lists below are EXTRACTED FROM THE GUARD AT TEST TIME and crossed. A correction that is
# narrower than the predicate it corrects now fails in the round it is written, because
# the cases come from the predicate rather than from the last bug.
#
# Read that as the load-bearing claim it is: if these extractions ever silently return
# empty, the cross product collapses and this file goes quietly green. That is what
# `test_the_extractions_are_not_empty` is for.
# ---------------------------------------------------------------------------

_GUARD_TEXT = GUARD.read_text()


def _cert_extensions():
    """Branch 8's extension set, read out of the guard.

    Anchored to `echo "certificates"`, NOT to a `case` following the section comment. My
    first version searched for the next `case` after `# 8. Certificates` and, because
    `.S` lets `.*?` cross the branch entirely, matched the production-data DESCRIPTION
    list (`sql|md|json|...|txt`) instead. 1,981 generated cases then asserted that
    appending a non-certificate final extension keeps a category -- which is not the
    invariant: branch 8 only fires when the LAST extension is a certificate one, so those
    paths are clean before and after and there was nothing to catch. A derived corpus is
    only as good as its derivation, and a wrong derivation manufactures defects as
    confidently as a blind corpus hides them.
    """
    idx = _GUARD_TEXT.index('echo "certificates"')
    window = _GUARD_TEXT[:idx]
    match = re.findall(r"^\s*([a-z0-9|]+)\)\s*$", window, re.M)
    assert match, "could not extract branch 8's extension set"
    exts = [e for e in match[-1].split("|") if e]
    assert "pem" in exts, f"extraction found the wrong case block: {exts}"
    return exts


def _secret_dirs():
    """The veto's directory list, read out of public_material()."""
    body = _GUARD_TEXT[_GUARD_TEXT.index("public_material() {"):]
    block = body[:body.index("esac", body.index("*/k8s/*"))]
    return sorted(set(re.findall(r"\*/([A-Za-z0-9._-]+)/\*", block)))


def _test_components():
    """The test-shaped path components the allowlist frees."""
    body = _GUARD_TEXT[_GUARD_TEXT.index("public_material() {"):]
    start = body.index("*/test/*")
    return sorted(set(re.findall(r"\*/([A-Za-z0-9._/-]+)/\*", body[start:start + 400])))


CERT_EXTS_FROM_GUARD = _cert_extensions()
SECRET_DIRS_FROM_GUARD = _secret_dirs()
TEST_DIRS_FROM_GUARD = _test_components()

# Suffixes that are NOT certificate extensions but routinely wrap one. The r4 defect lived
# entirely in this set: the peel loop stopped at the first of them.
WRAPPER_EXTS = ["gz", "bak", "tar", "zip", "bz2", "xz", "enc", "b64", "old", "orig"]


def test_the_extractions_are_not_empty():
    """A derived corpus that derives nothing is the vacuity this whole file guards against."""
    assert len(CERT_EXTS_FROM_GUARD) >= 6, CERT_EXTS_FROM_GUARD
    assert "pem" in CERT_EXTS_FROM_GUARD and "key" in CERT_EXTS_FROM_GUARD
    assert len(SECRET_DIRS_FROM_GUARD) >= 15, SECRET_DIRS_FROM_GUARD
    assert "k8s" in SECRET_DIRS_FROM_GUARD and "secrets" in SECRET_DIRS_FROM_GUARD
    assert len(TEST_DIRS_FROM_GUARD) >= 5, TEST_DIRS_FROM_GUARD


def _derived_chain_cases():
    """{category exemplar} x {test prefix} x {chain drawn from cert-exts U wrappers}."""
    for exemplar, category in CATEGORY_EXEMPLARS:
        for prefix in ("tests/", "fixtures/", "testdata/"):
            for wrapper in WRAPPER_EXTS:
                for cert in CERT_EXTS_FROM_GUARD:
                    yield f"{prefix}{exemplar}.{wrapper}.{cert}", category


@pytest.mark.parametrize("path,category", list(_derived_chain_cases()))
def test_a_wrapped_secret_keeps_its_category(path, category):
    """`tests/credentials.json.gz.key` is `tests/credentials.json.key` plus three
    characters, and it was clean. Peeling must not stop at a non-certificate link."""
    assert classify(path) is not None, f"{path} was freed by an interposed wrapper suffix"


def _derived_veto_cases():
    """{secret dir} x {both cases} x {freed basename} -- the axis r4b was blind to."""
    for directory in SECRET_DIRS_FROM_GUARD:
        for form in (directory, directory.upper()):
            for name in ("example.pem", "sample.key", "dummy.crt", "test.pem"):
                yield f"{form}/tests/fixtures/{name}"


@pytest.mark.parametrize("path", list(_derived_veto_cases()))
def test_a_secret_directory_beats_every_name_assertion(path):
    """`secrets/example.key` was clean: an author's filename prefix outranked the veto.
    Also covers case, since the veto was case-sensitive on a case-insensitive filesystem."""
    assert classify(path) is not None, f"{path} was freed inside a secret directory"

def test_the_allowlist_is_applied_to_the_classification_not_ahead_of_it():
    """Structure is the mechanism, and the structure changed twice for the same reason.

    The allowlist used to sit at the top of `classify()`, where it exempted every
    category. It now lives in `check_file()`, applied only once `classify()` has said
    `certificates` AND no stronger category claims the file. This asserts that shape
    directly, because it is the property the two prior defects violated.
    """
    body = GUARD.read_text()
    assert "public_material" in body

    # BEHAVIOURAL, not textual. The previous version of this test asserted only where
    # `public_material` appears in the source, and a mutant that restored full v1 semantics
    # INSIDE check_file() -- `if public_material "$filepath"; then category=""; fi` ahead of
    # the certificates branch -- passed all three of its assertions while freeing every
    # category again. Its slice bound was vacuous too: move `public_material` above
    # `classify` and the slice is empty, so the assertion holds on an empty string.
    #
    # So the property is asserted by RUNNING the guard: a secret under a test directory
    # must stay flagged, which is exactly what an allowlist applied too early breaks.
    for path, _category in STILL_FLAGGED[:12]:
        assert classify(path) is not None, (
            f"{path} is clean -- the allowlist is being applied before the classification"
        )
    # The structural half is kept only as a hint, and bounded to classify()'s OWN body --
    # from its opening brace to the first closing brace in column 0. Slicing to the next
    # named function is what made the earlier version fragile: it went vacuous when
    # `public_material` was defined ABOVE `classify`, and it went falsely red when
    # `public_material` was defined between `classify` and `check_file`. A function body
    # is the thing being asserted about, so it is the thing to extract.
    start = body.index("classify() {")
    classifier = body[start:body.index("\n}\n", start)]
    assert "public_material" not in classifier, (
        "the allowlist is inside classify() again -- classify() returns on the first "
        "match, so an exemption there applies to every category below it"
    )
