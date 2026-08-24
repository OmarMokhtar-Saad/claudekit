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


def test_the_allowlist_runs_before_the_denylist():
    """Ordering is the mechanism: a later allowlist would never be reached."""
    body = GUARD.read_text()
    allow = body.index("# 0. Public-by-construction")
    certs = body.index("# 8. Certificates and private keys")
    assert allow < certs
