"""Behavioral tests for the reflection ledger library (.claude/hooks/reflection.py).

These assert PROPERTIES, not structure:
  * privacy - an absolute path or a secret-shaped string never reaches the ledger bytes;
  * reduction - the checkpoint rule is a pure function of the ledger;
  * unforgeability - a receipt that is not HMAC'd with the session token, or that is not
    bound to the exact active set it claims to discharge, does not clear anything.

The ledger is redirected with CLAUDEKIT_REFLECTION_DIR so no test ever touches the real
per-session state under the OS temp dir.
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / ".claude" / "hooks" / "reflection.py"


def load_module(tmp_path):
    """Import reflection.py fresh with the ledger and inbox pointed at a temp dir."""
    os.environ["CLAUDEKIT_REFLECTION_DIR"] = str(tmp_path)
    os.environ["CLAUDEKIT_REFLECTION_INBOX"] = str(tmp_path / "inbox")
    spec = importlib.util.spec_from_file_location("ck_reflection", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ref(tmp_path):
    module = load_module(tmp_path)
    yield module
    os.environ.pop("CLAUDEKIT_REFLECTION_DIR", None)
    os.environ.pop("CLAUDEKIT_REFLECTION_INBOX", None)


SESSION = "session-under-test-0001"


def fail(ref, target="target-a", failure_class="tool-failure", observation=None):
    return ref.record_failure(
        SESSION, phase="tool-outcome", target=target, failure_class=failure_class,
        platform="testos", observation_id=observation,
    )


# --------------------------------------------------------------------- privacy

SECRET = "api_key=AKIAIOSFODNN7EXAMPLE"
ABSPATH = "/Users/someone/secrets/prod/config.yml"
# Keyword-free, prefix-free credentials: these match NO keyword in the secret list and
# would survive verbatim into the ledger without the shape/entropy guard.
BARE_HEX = "9f3c1a7e42b8d05f6c9e1a3b7d5f0821"
BARE_B64URL = "Xq7Zp2Lm9Rt4Vb8Nc3Kd6Jf1Hg5Yw0Sa"
BARE_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123def456"
# All-lowercase, non-hex, no underscore, 40 chars: matches no keyword, is not hex, and
# has no case mix - the residual gap the single-case rule closes.
BARE_SINGLECASE = "kxrmzqvtpwbsdfhjlncgyaeiuoqzxwvtrpmkjhgf"


class TestPrivacy:
    def test_absolute_path_never_reaches_the_ledger(self, ref, tmp_path):
        fail(ref, target=ABSPATH)
        blob = ref.ledger_path(SESSION).read_text(encoding="utf-8")
        assert "/Users/someone" not in blob
        assert "config.yml" not in blob
        assert "digest-" in blob

    def test_secret_shaped_string_never_reaches_the_ledger(self, ref):
        fail(ref, target=SECRET)
        blob = ref.ledger_path(SESSION).read_text(encoding="utf-8")
        assert "AKIAIOSFODNN7EXAMPLE" not in blob
        assert "api_key" not in blob

    @pytest.mark.parametrize(
        "token", [BARE_HEX, BARE_B64URL, BARE_JWT, BARE_SINGLECASE])
    def test_bare_high_entropy_token_never_reaches_the_ledger(self, ref, token):
        """BOUND TEST for the shape/entropy guard.

        None of these values matches a keyword in `_SECRET` and none is an absolute path.
        Without `looks_like_credential()` they fall through `re.sub` verbatim into a JSONL
        file that outlives the transcript and sits outside the repo. Delete the guard and
        this test fails.
        """
        assert ref.looks_like_credential(token) is True
        fail(ref, target="fetch %s from the cache" % token)
        blob = ref.ledger_path(SESSION).read_text(encoding="utf-8")
        assert token not in blob
        assert token.casefold() not in blob.casefold()
        assert "digest-" in blob

    def test_ordinary_prose_and_identifiers_are_not_digested(self, ref):
        """The guard must not be so eager that the ledger stops being readable."""
        for benign in ("tool-outcome", "pytest-collection-error", "command-outcome",
                       "test_reflection_ledger_py", "unknown-platform",
                       "test_reflection_gate_py_behavioural_subprocess_case",
                       "interrupted", "tool-failure"):
            assert ref.looks_like_credential(benign) is False, benign
        assert not ref.bounded_token("pytest-collection-error").startswith("digest-")

    def test_internally_produced_digests_are_not_re_digested(self, ref):
        """`command-<sha>` / `digest-<sha>` are shapes this module produced itself and are
        already sanitized; re-digesting them would only make the ledger unreadable."""
        internal = "command-" + "a1b2c3d4e5f60718293a"
        assert ref.looks_like_credential(internal) is False
        assert ref.bounded_token(internal) == internal

    def test_free_text_receipt_fields_reject_rather_than_digest(self, ref):
        with pytest.raises(ValueError):
            ref._safe_text("failedAssumption", "the bug lives in " + ABSPATH)
        with pytest.raises(ValueError):
            ref._safe_text("failedAssumption", "we passed the wrong bearer token")
        with pytest.raises(ValueError):
            ref._safe_text("failedAssumption", "we passed %s as the header" % BARE_HEX)

    def test_ledger_lives_outside_the_repository(self, ref, tmp_path):
        assert REPO not in ref.ledger_path(SESSION).parents

    def test_session_token_is_owner_only(self, ref):
        ref.ensure_session_token(SESSION)
        mode = stat.S_IMODE(ref.token_path(SESSION).stat().st_mode)
        assert mode == 0o600, oct(mode)


# ----------------------------------------------------------------- fingerprint


class TestFingerprint:
    def test_same_inputs_collide(self, ref):
        a = fail(ref, target="same")
        b = fail(ref, target="same")
        assert a["fingerprint"] == b["fingerprint"]

    def test_different_failure_class_does_not_collide(self, ref):
        a = fail(ref, target="same", failure_class="tool-failure")
        b = fail(ref, target="same", failure_class="timeout")
        assert a["fingerprint"] != b["fingerprint"]

    def test_observation_id_makes_recording_idempotent(self, ref):
        a = fail(ref, observation="tool_use_123")
        b = fail(ref, observation="tool_use_123")
        assert a["failureId"] == b["failureId"]
        failures = [e for e in ref.entries(SESSION) if e.get("kind") == "task-failure"]
        assert len(failures) == 1


# ------------------------------------------------------------------ reduction


class TestCheckpointReduction:
    def test_no_failure_is_no_checkpoint(self, ref):
        assert ref.pending_checkpoint(SESSION) is None

    def test_one_failure_is_no_checkpoint(self, ref):
        fail(ref)
        assert ref.pending_checkpoint(SESSION) is None

    def test_two_distinct_failures_raise_a_task_checkpoint(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        cp = ref.pending_checkpoint(SESSION)
        assert cp["depth"] == "task"
        assert cp["trigger"] == "second-failure"
        assert cp["attemptCount"] == 2

    def test_two_identical_failures_raise_a_deep_checkpoint(self, ref):
        fail(ref, target="a")
        fail(ref, target="a")
        cp = ref.pending_checkpoint(SESSION)
        assert cp["depth"] == "deep"
        assert cp["trigger"] == "repeated-fingerprint"

    def test_explicit_trigger_wins_and_is_deep(self, ref):
        fail(ref, target="a")
        ref.record_trigger(SESSION, "user-correction")
        cp = ref.pending_checkpoint(SESSION)
        assert cp["depth"] == "deep"
        assert cp["trigger"] == "user-correction"

    def test_non_attempt_does_not_burn_the_counter(self, ref):
        first = fail(ref, target="a")
        fail(ref, target="b")
        assert ref.pending_checkpoint(SESSION) is not None
        ref.mark_non_attempt(SESSION, first["failureId"], "setup-error")
        assert ref.pending_checkpoint(SESSION) is None

    def test_non_attempt_rejects_an_unknown_failure_id(self, ref):
        with pytest.raises(ValueError):
            ref.mark_non_attempt(SESSION, "failure-nope", "setup-error")

    def test_non_attempt_rejects_an_off_enum_reason(self, ref):
        entry = fail(ref)
        with pytest.raises(ValueError):
            ref.mark_non_attempt(SESSION, entry["failureId"], "i-did-not-feel-like-it")


# -------------------------------------------------------------------- receipts


def valid_receipt(ref, trigger="second-failure", fingerprints=None):
    cp = ref.pending_checkpoint(SESSION)
    return {
        "schemaVersion": ref.SCHEMA_VERSION,
        "taskId": "task-under-test",
        "trigger": trigger,
        "failureFingerprints": (
            fingerprints if fingerprints is not None else cp["failureFingerprints"]
        ),
        "failedAssumption": "assumed the fixture was seeded before the call",
        "approachesCompared": ["seed in fixture", "seed in the call site"],
        "chosenExperiment": "seed in the fixture and rerun the single failing test",
        "proofCommandOrCheck": "pytest -q tests/test_reflection_ledger.py",
        "proofOutcome": "the previously failing assertion now passes",
        "durableDisposition": "nothing-durable",
    }


class TestReceipts:
    def test_valid_receipt_clears_the_checkpoint(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        ref.record_receipt(SESSION, valid_receipt(ref), token)
        assert ref.pending_checkpoint(SESSION) is None

    def test_wrong_session_token_is_refused(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        with pytest.raises(ValueError):
            ref.record_receipt(SESSION, valid_receipt(ref), "not-the-real-token-xxxxxxxx")
        assert ref.pending_checkpoint(SESSION) is not None

    def test_forged_receipt_line_does_not_clear_the_checkpoint(self, ref):
        """The whole point of the HMAC: hand-writing a plausible receipt into the ledger
        must not discharge a duty."""
        fail(ref, target="a")
        fail(ref, target="b")
        active = ref.active_entries(SESSION)
        forged = {
            "schemaVersion": ref.SCHEMA_VERSION,
            "kind": "reflection-receipt",
            "sessionHash": ref._session_hash(SESSION),
            "checkpointDigest": ref.checkpoint_digest(active),
            "trigger": "second-failure",
            "durableDisposition": "nothing-durable",
            "receiptHash": "0" * 64,
        }
        ref.append_entry(SESSION, forged)
        assert ref.pending_checkpoint(SESSION) is not None

    def test_receipt_bound_to_a_stale_active_set_does_not_clear(self, ref):
        """A receipt must clear the checkpoint it actually owes, not an earlier one."""
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        stale = ref.record_receipt(SESSION, valid_receipt(ref), token)
        fail(ref, target="c")
        fail(ref, target="d")
        replay = dict(stale)
        ref.append_entry(SESSION, replay)
        assert ref.pending_checkpoint(SESSION) is not None

    def test_receipt_requires_at_least_two_approaches(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = valid_receipt(ref)
        payload["approachesCompared"] = ["only one idea"]
        with pytest.raises(ValueError):
            ref.record_receipt(SESSION, payload, token)

    def test_receipt_rejects_an_unfinished_proof(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = valid_receipt(ref)
        payload["proofOutcome"] = "pending"
        with pytest.raises(ValueError):
            ref.record_receipt(SESSION, payload, token)

    def test_receipt_rejects_mismatched_fingerprints(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = valid_receipt(ref, fingerprints=["deadbeef"])
        with pytest.raises(ValueError):
            ref.record_receipt(SESSION, payload, token)

    def test_receipt_rejects_unknown_fields(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = valid_receipt(ref)
        payload["cleared"] = True
        with pytest.raises(ValueError):
            ref.record_receipt(SESSION, payload, token)

    def test_nothing_durable_is_a_valid_disposition(self, ref):
        assert "nothing-durable" in ref.DISPOSITIONS

    def test_receipt_without_a_pending_duty_is_refused(self, ref):
        ref.ensure_session_token(SESSION)
        token = ref.read_session_token(SESSION)
        payload = {
            "schemaVersion": ref.SCHEMA_VERSION,
            "taskId": "t", "trigger": "second-failure", "failureFingerprints": [],
            "failedAssumption": "a", "approachesCompared": ["a", "b"],
            "chosenExperiment": "c", "proofCommandOrCheck": "d", "proofOutcome": "e",
            "durableDisposition": "nothing-durable",
        }
        with pytest.raises(ValueError):
            ref.record_receipt(SESSION, payload, token)


# --------------------------------------------------------------- learning loop


class TestLearningLoop:
    def test_mutation_without_routing_is_pending(self, ref):
        assert ref.learning_loop_pending(SESSION) is False
        ref.record_activity(SESSION, "mutation-or-delivery")
        assert ref.learning_loop_pending(SESSION) is True

    def test_a_learning_loop_receipt_routes_it(self, ref):
        ref.ensure_session_token(SESSION)
        ref.record_activity(SESSION, "mutation-or-delivery")
        token = ref.read_session_token(SESSION)
        payload = valid_receipt(ref, trigger="learning-loop", fingerprints=[])
        ref.record_receipt(SESSION, payload, token)
        assert ref.learning_loop_pending(SESSION) is False


# --------------------------------------------------------------------- the CLI


class TestCli:
    def run(self, tmp_path, *args):
        env = dict(os.environ, CLAUDEKIT_REFLECTION_DIR=str(tmp_path),
                   CLAUDEKIT_REFLECTION_INBOX=str(tmp_path / "inbox"))
        return subprocess.run(
            [sys.executable, str(MODULE_PATH)] + list(args),
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_status_reports_a_pending_checkpoint(self, ref, tmp_path):
        fail(ref, target="a")
        fail(ref, target="b")
        proc = self.run(tmp_path, "status", "--session-id", SESSION)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["checkpoint"]["trigger"] == "second-failure"

    def test_receipt_via_cli_clears_the_checkpoint(self, ref, tmp_path):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = json.dumps(valid_receipt(ref))
        proc = self.run(tmp_path, "receipt", "--session-id", SESSION,
                        "--session-token", token, "--json", payload)
        assert proc.returncode == 0, proc.stderr
        assert ref.pending_checkpoint(SESSION) is None

    def test_receipt_via_inbox_keeps_free_text_out_of_the_command_line(self, ref, tmp_path):
        """MAJOR-3 decoupling: the argv carries flags only, never receipt prose - so
        command-guard.sh cannot refuse a receipt that legitimately names subprocess.run."""
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = valid_receipt(ref)
        payload["failedAssumption"] = "assumed subprocess.run inherited the parent env"
        inbox = ref.inbox_path(SESSION)
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text(json.dumps(payload), encoding="utf-8")
        proc = self.run(tmp_path, "receipt", "--session-id", SESSION,
                        "--session-token", token, "--inbox")
        assert proc.returncode == 0, proc.stderr
        assert "subprocess.run" not in " ".join(
            ["receipt", "--session-id", SESSION, "--session-token", token, "--inbox"]
        )
        assert ref.pending_checkpoint(SESSION) is None
        assert not inbox.exists(), "the drop box must be consumed, never replayable"

    def test_receipt_via_json_stdin_clears_the_checkpoint(self, ref, tmp_path):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        env = dict(os.environ, CLAUDEKIT_REFLECTION_DIR=str(tmp_path),
                   CLAUDEKIT_REFLECTION_INBOX=str(tmp_path / "inbox"))
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "receipt", "--session-id", SESSION,
             "--session-token", token, "--json-stdin"],
            input=json.dumps(valid_receipt(ref)), capture_output=True, text=True,
            env=env, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        assert ref.pending_checkpoint(SESSION) is None

    def test_cli_refuses_a_bad_receipt_with_exit_2(self, ref, tmp_path):
        fail(ref, target="a")
        fail(ref, target="b")
        proc = self.run(tmp_path, "receipt", "--session-id", SESSION,
                        "--session-token", "bogus-token-value-000000", "--json", "{}")
        assert proc.returncode == 2
        assert "refused" in proc.stderr

    def test_cli_trigger_cannot_forge_the_derived_learning_loop_value(self, ref, tmp_path):
        proc = self.run(tmp_path, "trigger", "--session-id", SESSION,
                        "--trigger", "learning-loop")
        assert proc.returncode != 0
