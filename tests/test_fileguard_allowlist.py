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


def _generated_cases():
    for exemplar, category in CATEGORY_EXEMPLARS:
        for prefix in TEST_PREFIXES:
            for ext in CERT_EXTENSIONS:
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
@pytest.mark.parametrize("ext", [".pem", ".key", ".crt", ".p12", ".pfx"])
def test_a_secret_directory_beats_a_test_component(directory, ext):
    """"No stronger category fired" is not the same as "nothing here is sensitive"."""
    path = f"{directory}/tests/fixtures/anonymous{ext}"
    assert classify(path) is not None, f"{path} was freed by its test component"

def test_the_allowlist_is_applied_to_the_classification_not_ahead_of_it():
    """Structure is the mechanism, and the structure changed twice for the same reason.

    The allowlist used to sit at the top of `classify()`, where it exempted every
    category. It now lives in `check_file()`, applied only once `classify()` has said
    `certificates` AND no stronger category claims the file. This asserts that shape
    directly, because it is the property the two prior defects violated.
    """
    body = GUARD.read_text()
    assert "public_material" in body
    # The allowlist must NOT be inside classify(): everything between `classify() {` and
    # `check_file() {` is the classifier, and a return-early exemption there is the bug.
    classifier = body[body.index("classify() {"):body.index("public_material() {")]
    assert "public_material" not in classifier, (
        "the allowlist is inside classify() again -- classify() returns on the first "
        "match, so an exemption there applies to every category below it"
    )
    assert "stronger=$(classify" in body, "the stronger-category check is gone"
