"""The cause of `.ai/BACKLOG.md`'s UNEXPLAINED receipt intermittent.

`secrets.token_urlsafe` draws from the base64url alphabet, which contains `-`, so
about 1.5% of session tokens BEGIN with one. Every caller passed the token as
`--session-token <value>`, and argparse reads a leading-dash value as the next
OPTION -- exit 2 with `argument --session-token: expected one argument`, which is
the signature the BACKLOG recorded on 2026-08-24 and could not explain.

Unreproducible for weeks because the coin flip is inside the secret. These tests
make it deterministic in both directions: the generator no longer emits one, and
the `=` form survives one that already exists on disk.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REFLECTION = REPO / ".claude" / "hooks" / "reflection.py"


def _module():
    spec = importlib.util.spec_from_file_location("ck_reflection_tokentest", REFLECTION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTheGeneratorCannotEmitAFlagShapedToken:
    def test_no_token_starts_with_a_dash(self):
        """5000 draws. The old generator produced ~1.5% leading dashes."""
        mod = _module()
        tokens = [mod._new_token() for _ in range(5000)]
        offenders = [t for t in tokens if t.startswith("-")]
        assert not offenders, offenders[:3]

    def test_the_secret_is_not_shortened_to_achieve_that(self):
        """Redraw, not strip: stripping the first character would cost entropy."""
        mod = _module()
        lengths = {len(mod._new_token()) for _ in range(500)}
        assert lengths == {32}, lengths

    def test_the_raw_alphabet_really_does_produce_dashes(self):
        """Pins the PREMISE, so this suite fails if the finding stops being true.

        Without this, a future `token_urlsafe` whose alphabet excluded `-` would
        leave the three tests above passing vacuously.
        """
        import secrets
        leading = sum(secrets.token_urlsafe(24).startswith("-") for _ in range(20000))
        assert leading > 0, (
            "token_urlsafe no longer emits leading dashes; the guard above is now "
            "belt-and-braces rather than a fix, and this file should say so")


class TestTheCliSurvivesAFlagShapedToken:
    """Defence in depth for tokens ALREADY on disk, which the generator cannot reach."""

    def _run(self, *args):
        return subprocess.run([sys.executable, str(REFLECTION), *args],
                              capture_output=True, text=True, timeout=60)

    def test_space_separated_form_is_the_trap(self):
        """The reproduction. Not a wish: this is what every caller used to do."""
        proc = self._run("receipt", "--session-id", "x",
                         "--session-token", "-dashfirst", "--inbox")
        assert proc.returncode == 2
        assert "expected one argument" in proc.stderr, proc.stderr

    def test_equals_form_accepts_it(self):
        proc = self._run("receipt", "--session-id", "x",
                         "--session-token=-dashfirst", "--inbox")
        # Rejected later, on its merits (no such inbox) -- never by the parser.
        assert proc.returncode != 2 or "expected one argument" not in proc.stderr, (
            proc.stderr)

    def test_every_real_token_call_site_uses_the_equals_form(self):
        """The five sites that pass a GENERATED token; two others pass a literal."""
        text = (REPO / "tests" / "test_reflection_ledger.py").read_text(encoding="utf-8")
        assert '"--session-token", token' not in text, (
            "a site still passes a generated token space-separated, which is the "
            "shape that fails ~1.5% of the time")
        assert text.count('f"--session-token={token}"') == 5, text.count(
            'f"--session-token={token}"')
