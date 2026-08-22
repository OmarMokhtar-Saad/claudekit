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
from conftest import scoped_env

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / ".claude" / "hooks" / "reflection.py"


def load_module():
    """Import reflection.py fresh. The ledger and inbox locations come from the
    `reflection_env` fixture, which restores the caller's values on teardown."""
    spec = importlib.util.spec_from_file_location("ck_reflection", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ref(reflection_env):
    return load_module()


SESSION = "session-under-test-0001"


def fail(ref, target="target-a", failure_class="tool-failure", observation=None):
    return ref.record_failure(
        SESSION, phase="tool-outcome", target=target, failure_class=failure_class,
        platform="testos", observation_id=observation,
    )


def receipt_diagnostic(ref, proc, env):
    """Evidence for the UNEXPLAINED intermittent tracked in .ai/BACKLOG.md:
    test_receipt_via_json_stdin_clears_the_checkpoint has failed three times with the CLI
    itself exiting 0, and has never reproduced on demand. This builds the capture the
    BACKLOG entry asks for and hands it to the assertion as its message, so a CI red
    carries its own evidence and nobody has to reproduce it.

    There is no separate checkpoint file: pending_checkpoint() is a pure reduction over
    active_entries(), which reads the ledger JSONL - so the ledger bytes, the derived
    active set and the returned checkpoint are all dumped.

    Records state only. It claims NO cause, it is not a retry, and it must never become
    one."""
    ledger = ref.ledger_path(SESSION)
    inbox = ref.inbox_path(SESSION)
    try:
        raw = ledger.read_text(encoding="utf-8")
    except OSError as exc:
        raw = "<unreadable: %s>" % exc
    return "\n".join([
        "",
        "ledger_dir:     %s" % ref.ledger_dir(),
        "ledger_path:    %s (exists=%s)" % (ledger, ledger.exists()),
        "child env dir:  %r" % env.get("CLAUDEKIT_REFLECTION_DIR"),
        "inbox_path:     %s (exists=%s)" % (inbox, inbox.exists()),
        "ledger bytes:   %s" % raw,
        "active entries: %s" % json.dumps(ref.active_entries(SESSION), indent=2),
        "pending:        %s" % json.dumps(ref.pending_checkpoint(SESSION), indent=2),
        "cli returncode: %s" % proc.returncode,
        "cli stdout:     %s" % proc.stdout,
        "cli stderr:     %s" % proc.stderr,
    ])


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
    def test_absolute_path_never_reaches_the_ledger(self, ref):
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

    def test_ledger_lives_outside_the_repository(self, ref):
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
    def run(self, *args):
        # os.environ already carries the per-test ledger/inbox from `reflection_env`;
        # the child must see exactly the same ledger the parent asserts against.
        env = dict(os.environ)
        return subprocess.run(
            [sys.executable, str(MODULE_PATH)] + list(args),
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_status_reports_a_pending_checkpoint(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        proc = self.run("status", "--session-id", SESSION)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["checkpoint"]["trigger"] == "second-failure"

    def test_receipt_via_cli_clears_the_checkpoint(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        token = ref.read_session_token(SESSION)
        payload = json.dumps(valid_receipt(ref))
        proc = self.run("receipt", "--session-id", SESSION,
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
        proc = self.run("receipt", "--session-id", SESSION,
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
        env = dict(os.environ)
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "receipt", "--session-id", SESSION,
             "--session-token", token, "--json-stdin"],
            input=json.dumps(valid_receipt(ref)), capture_output=True, text=True,
            env=env, timeout=30,
        )
        assert proc.returncode == 0, receipt_diagnostic(ref, proc, env)
        assert ref.pending_checkpoint(SESSION) is None, receipt_diagnostic(
            ref, proc, env)

    def test_cli_refuses_a_bad_receipt_with_exit_2(self, ref):
        fail(ref, target="a")
        fail(ref, target="b")
        proc = self.run("receipt", "--session-id", SESSION,
                        "--session-token", "bogus-token-value-000000", "--json", "{}")
        assert proc.returncode == 2
        assert "refused" in proc.stderr

    def test_cli_trigger_cannot_forge_the_derived_learning_loop_value(self, ref):
        proc = self.run("trigger", "--session-id", SESSION,
                        "--trigger", "learning-loop")
        assert proc.returncode != 0


# ------------------------------------------------------------------- isolation


class TestIsolation:
    """BOUND TESTS for the fixture itself. Every assertion above is only meaningful if
    the ledger a test reads is the ledger that test wrote - these prove it."""

    def test_each_test_starts_from_an_empty_per_test_ledger(self, ref, tmp_path):
        assert ref.ledger_dir() == tmp_path / "ledger"
        assert not ref.ledger_path(SESSION).exists()
        assert ref.pending_checkpoint(SESSION) is None

    def test_the_fixture_restores_an_ambient_ledger_dir(self, tmp_path):
        """Revert `scoped_env` to a bare `os.environ.pop` and this fails: a later test
        in the same process would lose the caller's value and fall back to the real,
        shared OS temp dir."""
        sentinel = str(tmp_path / "ambient")
        with scoped_env(CLAUDEKIT_REFLECTION_DIR=sentinel):
            with scoped_env(CLAUDEKIT_REFLECTION_DIR=str(tmp_path / "inner")):
                assert os.environ["CLAUDEKIT_REFLECTION_DIR"] == str(tmp_path / "inner")
            assert os.environ["CLAUDEKIT_REFLECTION_DIR"] == sentinel

    def test_a_reflection_test_does_not_destroy_an_ambient_ledger_dir(self, tmp_path):
        """REGRESSION BOUND TEST for the defect this file was fixed for.

        The `ref` fixtures here and in test_reflection_gate.py used to end with a bare
        `os.environ.pop(...)`. That deletes a PROCESS-GLOBAL value: any test running
        later in the same process with an ambient CLAUDEKIT_REFLECTION_DIR exported
        would lose it and silently retarget the real, host-shared OS temp ledger. The
        only way to observe that is from outside the process, so this test runs a real
        pytest process with the variables exported and asserts a probe collected AFTER a
        reflection test still sees them. Put the `pop` back in either fixture teardown
        and this test goes red.
        """
        probe = tmp_path / "test_ambient_probe.py"
        probe.write_text(
            "import os\n\n\n"
            "def test_ambient_reflection_env_survives():\n"
            "    assert os.environ.get('CLAUDEKIT_REFLECTION_DIR') == '/ambient/sentinel/dir'\n"
            "    assert os.environ.get('CLAUDEKIT_REFLECTION_INBOX') == '/ambient/sentinel/inbox'\n",
            encoding="utf-8",
        )
        # One cheap `ref`-using test from EACH reflection file - never a whole file:
        # running this file inside itself would recurse. Both fixtures carry the same
        # defect, so both are guarded.
        here = Path(__file__)
        victims = [
            str(here) + "::TestPrivacy::test_session_token_is_owner_only",
            str(here.parent / "test_reflection_gate.py") + "::TestFailureRecording::test_failure_is_persisted",
        ]
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
            + victims + [str(probe)],
            capture_output=True, text=True, timeout=120,
            env=dict(os.environ,
                     CLAUDEKIT_REFLECTION_DIR="/ambient/sentinel/dir",
                     CLAUDEKIT_REFLECTION_INBOX="/ambient/sentinel/inbox",
                     ECC_HOOK_PROFILE="minimal"),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_the_fixture_restores_absence(self, tmp_path):
        """The other half: a variable the caller did NOT set must not exist afterwards."""
        marker = "CLAUDEKIT_REFLECTION_DIR_ABSENT_PROBE"
        assert marker not in os.environ
        with scoped_env(**{marker: str(tmp_path)}):
            assert os.environ[marker] == str(tmp_path)
        assert marker not in os.environ

# ------------------------------------------------- fallback root (no env override)


class TestFallbackRootIsolation:
    """BOUND TESTS for the machine-shared temp fallback - the code path the fixture
    normally hides.

    Every test here deliberately REMOVES CLAUDEKIT_REFLECTION_DIR so `ledger_dir()`'s
    fallback is the thing under test, and pins TMPDIR inside tmp_path so the developer's
    real ledger is still never touched. ECC_HOOK_PROFILE stays forced by `reflection_env`.
    """

    @pytest.fixture()
    def fallback(self, ref, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDEKIT_REFLECTION_DIR", raising=False)
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        monkeypatch.setenv("TMPDIR", str(tmp))
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        return ref

    def test_two_projects_with_the_same_session_id_do_not_collide(
        self, fallback, tmp_path, monkeypatch
    ):
        """THE DEFECT. One flat root keyed only by sha256(session_id) meant two checkouts
        on one machine appended to the same file."""
        seen = []
        for name in ("alpha", "beta"):
            root = tmp_path / name
            root.mkdir()
            monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
            assert fallback.ensure_ledger_dir() is not None
            assert fallback.append_entry(SESSION, {"project": name})
            seen.append((name, fallback.ledger_path(SESSION)))
        assert seen[0][1] != seen[1][1]
        for name, path in seen:
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
            assert len(lines) == 1, lines
            assert json.loads(lines[0])["project"] == name

    def test_a_session_ledger_persists_across_separate_hook_invocations(
        self, fallback, tmp_path
    ):
        """REGRESSION FOR THE CHECKPOINT MECHANISM. The ledger is written by one hook
        process and read by a LATER one in the same session. Derive the path from
        anything per-invocation - pid, time, mkdtemp - and this goes red while every
        in-process test stays green."""
        env = dict(os.environ)
        env.pop("CLAUDEKIT_REFLECTION_DIR", None)
        env.pop("CLAUDEKIT_REFLECTION_INBOX", None)
        env["TMPDIR"] = str(tmp_path / "tmp")
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path / "project")
        env["ECC_HOOK_PROFILE"] = "minimal"
        write = subprocess.run(
            [sys.executable, str(MODULE_PATH), "trigger",
             "--session-id", SESSION, "--trigger", "third-fix"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert write.returncode == 0, write.stdout + write.stderr
        read = subprocess.run(
            [sys.executable, str(MODULE_PATH), "status", "--session-id", SESSION],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert read.returncode == 0, read.stdout + read.stderr
        assert json.loads(read.stdout)["checkpoint"], read.stdout

    def test_the_fallback_root_is_private_to_this_user(self, fallback):
        path = fallback.ensure_ledger_dir()
        assert path is not None
        for component in (path.parent, path):
            info = os.lstat(str(component))
            assert stat.S_IMODE(info.st_mode) == 0o700, oct(info.st_mode)
            assert info.st_uid == os.getuid()

    def test_a_pre_created_world_writable_root_is_refused(self, fallback):
        """The `/tmp` (mode 1777) case: another uid creates the predictable directory
        first. `mkdir(exist_ok=True)` accepts it silently; we must not."""
        hostile = fallback.ledger_dir().parent
        hostile.mkdir(parents=True)
        os.chmod(str(hostile), 0o777)
        assert fallback.ensure_ledger_dir() is None
        assert fallback.append_entry(SESSION, {"never": "written"}) is False

    def test_a_symlink_planted_at_the_root_is_refused_not_followed(
        self, fallback, tmp_path
    ):
        """`Path.mkdir(exist_ok=True)` follows a symlink to a directory - that is how a
        predictable temp path becomes an arbitrary-write primitive."""
        target = tmp_path / "attacker_controlled"
        target.mkdir()
        link = fallback.ledger_dir().parent
        os.symlink(str(target), str(link))
        assert fallback.ensure_ledger_dir() is None
        assert fallback.append_entry(SESSION, {"never": "written"}) is False
        assert list(target.iterdir()) == []

    def test_a_root_owned_by_someone_else_is_refused(self, fallback, monkeypatch):
        """chown needs root, so the check's own notion of `us` is moved instead: the
        directory below is ours, and is therefore FOREIGN from the code's point of
        view."""
        monkeypatch.setattr(fallback, "_current_uid", lambda: os.getuid() + 1)
        foreign = fallback.ledger_dir()
        foreign.mkdir(parents=True)
        os.chmod(str(foreign), 0o700)
        os.chmod(str(foreign.parent), 0o700)
        assert fallback.ensure_ledger_dir() is None
        assert fallback.append_entry(SESSION, {"never": "written"}) is False

    def test_a_hostile_root_yields_no_entries_and_no_token(self, fallback):
        """Read side. Without this guard a planted `<key>.token` wins the O_EXCL race and
        every receipt HMAC becomes forgeable by whoever planted it."""
        root = fallback.ledger_dir()
        root.mkdir(parents=True)
        os.chmod(str(root), 0o777)
        fallback.ledger_path(SESSION).write_text(
            json.dumps({"type": "failure", "id": "planted"}) + "\n", encoding="utf-8")
        fallback.token_path(SESSION).write_text("x" * 40, encoding="utf-8")
        assert fallback.entries(SESSION) == []
        assert fallback.read_session_token(SESSION) is None

    def test_a_degraded_root_is_not_silent(self, fallback, capsys):
        """MINOR-turned-property: reflection may degrade, but it may not degrade QUIETLY -
        off-and-silent is the exact failure mode that disqualifies "refuse unless
        configured" in the plan. Once per process, on stderr, never as a block."""
        root = fallback.ledger_dir()
        root.mkdir(parents=True)
        os.chmod(str(root), 0o777)
        assert fallback.ledger_dir_trusted() is False
        first = capsys.readouterr().err
        assert "not private to this user" in first
        assert fallback.ledger_dir_trusted() is False
        assert capsys.readouterr().err == ""

    def test_the_inbox_stays_project_local_on_the_fallback(self, fallback, monkeypatch):
        """The inbox must NOT move with the ledger root: the PreToolUse gate allows a
        Write to exactly `<project>/.claude/reflection/inbox-<key>.json`."""
        monkeypatch.delenv("CLAUDEKIT_REFLECTION_INBOX", raising=False)
        inbox = fallback.inbox_path(SESSION)
        project = Path(os.environ["CLAUDE_PROJECT_DIR"])
        assert inbox.parent == project / ".claude" / "reflection"
        assert fallback.ledger_dir() not in inbox.parents


class TestExplicitOverrideUnchanged:
    def test_an_override_is_used_verbatim_and_is_not_permission_audited(
        self, ref, tmp_path
    ):
        """BOUND TEST for the `reflection_env` contract: no uid or project segment is
        appended to an explicit root, and its mode is the operator's business."""
        root = tmp_path / "ledger"
        assert ref.ledger_dir() == root
        assert ref.ensure_ledger_dir() == root
        os.chmod(str(root), 0o755)
        assert ref.ledger_dir_trusted() is True
        assert ref.append_entry(SESSION, {"ok": 1})
        assert len(ref.entries(SESSION)) == 1

