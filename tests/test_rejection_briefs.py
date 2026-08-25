"""Behavioural tests for the rejection retro loop.

Every test drives the real scripts through subprocess in a temp tree. Nothing here
asserts on function names or file structure: the question is always "what does the
tool DO", per CLAUDE.md.

Phase 0 half (this file grows with the later phases): the regression that makes every
later phase possible at all — a rejecting review round must produce a record. The live
corpus that motivated the change reads 80 records / 80 APPROVED / 79-of-80 single-round,
not because review always passes but because only the passing round was ever written.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Forced explicitly rather than inherited: a test that silently runs under whatever
# profile the developer happens to have exported proves nothing repeatable.
os.environ["ECC_HOOK_PROFILE"] = "minimal"

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / ".claude" / "operations" / "scripts"
RECORD = SCRIPTS / "review-record.py"
AGENTS = REPO / ".claude" / "agents"

REVISE_BLOCK = """The reviewer wrote a report first.

=== REVIEW ===
SCORE: 62
DECISION: REVISE
- [CRITICAL] ops.json anchor does not exist in the target file
- [MAJOR] no rollback described for the deletion
=== END REVIEW ===
"""


def run_record(cwd, *argv, stdin=None, env=None):
    environ = dict(os.environ)
    environ["ECC_HOOK_PROFILE"] = "minimal"
    if env:
        environ.update(env)
    return subprocess.run(
        [sys.executable, str(RECORD)] + [str(a) for a in argv],
        cwd=str(cwd), input=stdin, capture_output=True, text=True,
        timeout=60, env=environ,
    )


def make_tree(tmp_path, ops_name="ops-demo.json"):
    """A minimal repo-shaped tree: review-record.py locates its stores by walking up
    to the nearest ancestor holding a .claude/ directory."""
    plans = tmp_path / ".claude" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude" / "reports" / "reviews").mkdir(parents=True, exist_ok=True)
    plan = plans / "plan-demo.md"
    plan.write_text("# Plan: demo\n", encoding="utf-8")
    ops = plans / ops_name
    ops.write_text(
        '{"plan": "demo", "operations": [{"type": "code_edit", "path": "app.py",'
        ' "edits": [{"find": "a", "replace": "b"}]}]}\n',
        encoding="utf-8",
    )
    return plan, ops


def _json_load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def record_json(tmp_path, slug="demo"):
    return _json_load(tmp_path / ".claude" / "reports" / "reviews" / ("%s.json" % slug))


class TestRejectionRoundIsRecorded:
    """Spec test #9 — the Phase 0 regression.

    Nothing downstream of this exists if a rejecting round leaves no record: the brief
    trigger counts non-approving rounds, and it can only count rounds that were written.
    """

    def test_revise_verdict_produces_a_record(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            stdin=REVISE_BLOCK)
        assert result.returncode == 0, result.stderr
        record = record_json(tmp_path)
        assert record["decision"] == "REVISE"
        assert record["score"] == 62
        assert record["round"] == 1
        assert len(record["findings"]) == 2

    def test_recording_a_rejection_still_refuses_execution(self, tmp_path):
        """Writing a rejection must never be mistaken for authorising one."""
        plan, ops = make_tree(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-", stdin=REVISE_BLOCK)
        check = run_record(tmp_path, "check", plan, ops)
        assert check.returncode == 4, check.stdout + check.stderr

    def test_rejection_then_approval_keeps_the_rejection_in_history(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-", stdin=REVISE_BLOCK)
        run_record(tmp_path, "write", plan, ops, "--score", "95", "--decision", "APPROVED")
        record = record_json(tmp_path)
        assert record["round"] == 2
        assert [r["decision"] for r in record["rounds"]] == ["REVISE"]


class TestReviewerPromptsEmitOnEveryRound:
    """The prompts are the producers of the signal; if they lose the every-round rule
    the store goes quiet and no test downstream would notice."""

    def test_reviewer_states_the_every_round_rule(self):
        text = (AGENTS / "reviewer.md").read_text(encoding="utf-8")
        assert "EVERY round" in text
        assert "rejections included" in text

    def test_code_reviewer_has_an_anchored_verdict_block(self):
        text = (AGENTS / "code-reviewer.md").read_text(encoding="utf-8")
        assert "=== REVIEW ===" in text
        assert "=== END REVIEW ===" in text
        assert "EVERY round" in text

    def test_code_reviewer_mapping_uses_only_parseable_decisions(self):
        """Every DECISION spelling the mapping table can produce must be one the
        parser accepts, or the block records nothing and Phase 0 is a no-op."""
        record_src = RECORD.read_text(encoding="utf-8")
        text = (AGENTS / "code-reviewer.md").read_text(encoding="utf-8")
        assert 'VALID_DECISIONS = ("APPROVED", "CONDITIONAL", "REVISE", "REJECTED")' \
            in record_src
        for spelling in ("APPROVED", "REVISE", "REJECTED"):
            assert "| %s |" % spelling in text

    def test_code_reviewer_still_refuses_to_treat_the_number_as_a_rubric(self):
        """The derived score is a gate token. If this framing is lost, the
        blocking-count exit rule erodes back into scoring."""
        text = (AGENTS / "code-reviewer.md").read_text(encoding="utf-8")
        assert "gate token, not a quality rubric" in text


# --------------------------------------------------------------------------- capture

import json as _json  # noqa: E402  (kept local to the capture half, added by phase 2)
import re as _re  # noqa: E402

REJECTIONS = (".claude", "knowledge", "rejections")
SESSION = "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b"


def revise_block(score=62, findings=("ops.json anchor does not exist",)):
    lines = ["=== REVIEW ===", "SCORE: %d" % score, "DECISION: REVISE"]
    lines += ["- [CRITICAL] %s" % f for f in findings]
    lines += ["=== END REVIEW ===", ""]
    return "\n".join(lines)


def brief_dir(tmp_path):
    return tmp_path.joinpath(*REJECTIONS)


def index_rows(tmp_path):
    path = brief_dir(tmp_path) / "INDEX.jsonl"
    if not path.exists():
        return []
    return [_json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reject_twice(tmp_path, session=SESSION):
    plan, ops = make_tree(tmp_path)
    for score in (62, 71):
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   "--session-id", session, stdin=revise_block(score))
    return plan, ops


class TestBriefTrigger:
    """Spec tests #1 and #2 - the trigger fires on the 2nd non-approving round, and
    only while the current round is itself non-approving."""

    def test_two_revise_rounds_produce_a_brief(self, tmp_path):
        reject_twice(tmp_path)
        brief = brief_dir(tmp_path) / "demo.md"
        assert brief.exists(), "no brief after two REVISE rounds"
        assert "Round 2" in brief.read_text(encoding="utf-8")

    def test_one_index_line_per_rejecting_round_from_the_trigger_on(self, tmp_path):
        reject_twice(tmp_path)
        rows = index_rows(tmp_path)
        assert len(rows) == 1, rows
        assert rows[0]["round"] == 2
        assert rows[0]["rejecting_rounds"] == 2

    def test_third_rejection_appends_exactly_one_more_line(self, tmp_path):
        plan, ops = reject_twice(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   "--session-id", SESSION, stdin=revise_block(80))
        rows = index_rows(tmp_path)
        assert [r["round"] for r in rows] == [2, 3]

    def test_revise_then_approved_writes_no_brief(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   stdin=revise_block())
        run_record(tmp_path, "write", plan, ops, "--score", "95", "--decision", "APPROVED")
        assert not (brief_dir(tmp_path) / "demo.md").exists()
        assert index_rows(tmp_path) == []


class TestBriefSafety:
    """Spec tests #3 and #4 - briefs are TRACKED files."""

    def test_path_shaped_finding_is_refused_or_digested(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        hostile = "leaked /Users/someone/secrets/id_rsa in the plan"
        for score in (62, 71):
            run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                       stdin=revise_block(score, findings=(hostile,)))
        blob = (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8")
        blob += (brief_dir(tmp_path) / "INDEX.jsonl").read_text(encoding="utf-8")
        assert "/Users/someone/secrets/id_rsa" not in blob

    def test_credential_shaped_finding_is_refused_or_digested(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        secret = "sk-ant-api03-" + ("A1b2C3d4" * 6)
        for score in (62, 71):
            run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                       stdin=revise_block(score, findings=(secret,)))
        blob = (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8")
        blob += (brief_dir(tmp_path) / "INDEX.jsonl").read_text(encoding="utf-8")
        assert secret not in blob

    def test_session_uuid_is_present_and_resolvable_shaped(self, tmp_path):
        reject_twice(tmp_path)
        rows = index_rows(tmp_path)
        assert rows[0]["session_id"] == SESSION
        # resolvable = it is a transcript FILENAME, not a digest of one
        assert _re.match(r"^[0-9a-fA-F-]{8,64}$", rows[0]["session_id"])

    def test_no_raw_session_token_lands_in_the_store(self, tmp_path):
        """A SessionStart reflection token is a long opaque hex run. Nothing on this
        path reads one, and the store must show no such run to prove it."""
        reject_twice(tmp_path)
        blob = (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8")
        blob += (brief_dir(tmp_path) / "INDEX.jsonl").read_text(encoding="utf-8")
        for run in _re.findall(r"[0-9a-f]{32,}", blob):
            assert False, "opaque token-shaped run in a tracked brief: %s" % run[:12]

    def test_no_absolute_path_lands_in_the_store(self, tmp_path):
        reject_twice(tmp_path)
        blob = (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8")
        blob += (brief_dir(tmp_path) / "INDEX.jsonl").read_text(encoding="utf-8")
        assert str(tmp_path) not in blob


class TestIdempotency:
    """Spec test #5 - key is ops_slug + round."""

    def test_rerunning_write_for_the_same_round_adds_no_line(self, tmp_path):
        """Spec test #5 proper: re-ISSUE round 2, do not advance to round 3.

        A replay that lands on a new round number never touches the slug+round guard at
        all -- it just appends a legitimately new line. To exercise the guard the record
        has to be rewound to the state that produced round 2, which is exactly what a
        re-run of a crashed/retried write looks like.
        """
        plan, ops = make_tree(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   "--session-id", SESSION, stdin=revise_block(62))
        after_round_1 = (tmp_path / ".claude" / "reports" / "reviews" / "demo.json"
                         ).read_text(encoding="utf-8")
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   "--session-id", SESSION, stdin=revise_block(71))
        rows_before = index_rows(tmp_path)
        brief_before = (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8")
        assert [r["round"] for r in rows_before] == [2]

        # rewind, then replay the identical round-2 write
        (tmp_path / ".claude" / "reports" / "reviews" / "demo.json").write_text(
            after_round_1, encoding="utf-8")
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            "--session-id", SESSION, stdin=revise_block(71))
        assert result.returncode == 0, result.stderr
        assert record_json(tmp_path)["round"] == 2, "the replay must re-issue round 2"
        assert index_rows(tmp_path) == rows_before, "INDEX line duplicated for one round"
        assert (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8") == brief_before

    def test_a_later_round_appends_exactly_one_line(self, tmp_path):
        plan, ops = reject_twice(tmp_path)
        rows_before = index_rows(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   "--session-id", SESSION, stdin=revise_block(75))
        rows_after = index_rows(tmp_path)
        assert len(rows_after) == len(rows_before) + 1
        assert len({(r["slug"], r["round"]) for r in rows_after}) == len(rows_after)

    def test_markdown_sections_and_index_rows_stay_one_to_one(self, tmp_path):
        """The two stores are keyed the same way (slug + round). If they ever diverge,
        one of them is lying about how many times this plan was rejected."""
        plan, ops = reject_twice(tmp_path)
        for score in (75, 80):
            run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                       "--session-id", SESSION, stdin=revise_block(score))
        rows = index_rows(tmp_path)
        brief = (brief_dir(tmp_path) / "demo.md").read_text(encoding="utf-8")
        assert len(rows) == brief.count("<!-- round: ")
        for row in rows:
            assert "<!-- round: %d -->" % row["round"] in brief


class TestVerdictProvenance:
    """A reviewer-judged 60 and a table-derived 60 are the same integer and mean nothing
    alike. Unlabelled, they flatten the exact trajectory this feature exists to read."""

    def test_default_origin_is_rubric(self, tmp_path):
        reject_twice(tmp_path)
        assert index_rows(tmp_path)[0]["verdict_origin"] == "rubric"
        assert record_json(tmp_path)["verdict_origin"] == "rubric"

    def test_gate_token_origin_is_recorded_and_survives_into_history(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        for score in (60, 60):
            run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                       "--session-id", SESSION, "--verdict-origin", "gate-token",
                       stdin=revise_block(score))
        assert index_rows(tmp_path)[0]["verdict_origin"] == "gate-token"
        record = record_json(tmp_path)
        assert record["rounds"][0]["verdict_origin"] == "gate-token"

    def test_analyst_is_told_to_exclude_gate_token_scores_from_trends(self):
        agent = AGENTS / "flow-analyst.md"
        if not agent.exists():
            return  # analyst phase not applied yet
        text = agent.read_text(encoding="utf-8")
        assert "verdict_origin" in text and "gate-token" in text


class TestCorruptIndexIsSurvivable:
    """Spec test #8 - the store must never be able to break the approval path."""

    def test_corrupt_line_is_skipped_with_a_note_and_write_still_succeeds(self, tmp_path):
        plan, ops = reject_twice(tmp_path)
        index = brief_dir(tmp_path) / "INDEX.jsonl"
        index.write_text("{not json at all\n" + index.read_text(encoding="utf-8"),
                         encoding="utf-8")
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            "--session-id", SESSION, stdin=revise_block(80))
        assert result.returncode == 0, result.stderr
        assert "corrupt INDEX.jsonl line" in result.stderr
        assert record_json(tmp_path)["round"] == 3

    def test_unwritable_store_still_records_the_verdict(self, tmp_path):
        """The load-bearing property: brief emission is fail-soft. If it ever becomes
        able to fail the write, execution approvals start disappearing."""
        plan, ops = make_tree(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   stdin=revise_block(62))
        blocked = brief_dir(tmp_path)
        blocked.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_text("not a directory\n", encoding="utf-8")
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            stdin=revise_block(71))
        assert result.returncode == 0, result.stdout + result.stderr
        assert record_json(tmp_path)["round"] == 2
        assert "IS recorded" in result.stderr or "NOTE:" in result.stderr


# ----------------------------------------------------------------------------- miner

import shutil as _shutil  # noqa: E402  (miner half, added by phase 3)

MINER = SCRIPTS / "transcript-miner.py"


def write_transcript(home, session, slug):
    """A transcript fixture in the SHAPES THE REAL CORPUS USES.

    Verified against 2002 live transcripts: `message.content` is always a LIST of typed
    blocks, and ~36% of entries are `attachment`/`system` records with no message that
    carry hook payloads and absolute host paths. The previous fixture used a bare string
    for `content` -- a shape with zero occurrences in real data -- so it exercised a
    branch production never takes and hid both the raw-JSON dump and the path leak.
    """
    project = home / ".claude" / "projects" / "some-project"
    project.mkdir(parents=True, exist_ok=True)
    path = project / ("%s.jsonl" % session)
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "planner wrote ops-%s.json" % slug}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "SECRET-REASONING-BLOCK", "signature": "x"}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "id": "t1",
             "input": {"command": "cat /Users/someone/.ssh/id_rsa"}}]}},
        # harness bookkeeping: no message, absolute paths inside. Real files are full of
        # these, and they must never reach the output.
        {"type": "attachment", "attachment": {
            "type": "hook_success", "hookName": "Stop",
            "stdout": "transcript_path=/Users/someone/.claude/projects/x/y.jsonl",
            "command": "bash /Users/someone/hooks/on-stop.sh"}},
        # The highest-risk channel: tool output is where .env reads, `env` dumps and
        # git remotes with tokens actually appear.
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content":
                "ANTHROPIC_API_KEY=sk-ant-api03-" + "A1b2C3d4" * 6 + " "
                "GITHUB_TOKEN=ghp_" + "aB3dE6gH9jK2mN5pQ8sT1vW4xY7zA0bC" + " "
                "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text",
             "text": "reviewing %s\n=== REVIEW ===\nSCORE: 62\n"
                     "DECISION: REVISE\n=== END REVIEW ===" % slug}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
             "content": "Error: anchor not found in target file"}]}},

    ]
    path.write_text("".join(_json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def run_miner(cwd, home, *argv):
    environ = dict(os.environ)
    environ["ECC_HOOK_PROFILE"] = "minimal"
    environ["HOME"] = str(home)
    return subprocess.run([sys.executable, str(MINER)] + [str(a) for a in argv],
                          cwd=str(cwd), capture_output=True, text=True,
                          timeout=60, env=environ)


class TestTranscriptMiner:
    """Spec test #7 - returns the verdict window; a missing transcript degrades."""

    def test_returns_the_verdict_window(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert result.returncode == 0, result.stderr
        assert "=== REVIEW ===" in result.stdout
        assert "DECISION: REVISE" in result.stdout

    def test_reports_tool_failures_in_the_window(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert "tool failures" in result.stdout
        assert "anchor not found" in result.stdout

    def test_absolute_transcript_path_is_not_printed(self, tmp_path):
        """The output is routinely pasted into files that get committed."""
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert str(home) not in result.stdout

    def test_missing_transcript_exits_3_and_names_the_degradation(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        result = run_miner(tmp_path, home, "0000aaaa-1111-2222-3333-444455556666",
                           "--around", "demo")
        assert result.returncode == 3
        assert "normal, not a failure" in result.stderr
        assert "brief-only" in result.stderr

    def test_a_non_uuid_session_id_is_a_usage_error_not_a_glob(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        result = run_miner(tmp_path, home, "../../etc", "--around", "demo")
        assert result.returncode == 1

    def test_harness_entries_are_never_dumped_as_raw_json(self, tmp_path):
        """Run against a real transcript, the old fallthrough printed whole attachment
        records -- hook stdout, terminal escapes, absolute paths -- into output whose
        entire purpose is to stay small and quotable."""
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert "hook_success" not in result.stdout
        assert "parentUuid" not in result.stdout

    def test_no_host_path_survives_to_stdout(self, tmp_path):
        """The docstring always promised this; only the transcript's own path was
        actually suppressed. Real entries carry host paths in tool output."""
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert "/Users/someone" not in result.stdout
        assert str(home) not in result.stdout

    def test_credentials_in_tool_output_do_not_survive(self, tmp_path):
        """Tool results are quotable into `.claude/reports/retro/<date>.md`, which is
        TRACKED. The briefs get credential scrubbing; this channel is strictly
        higher-risk raw output and must not get less."""
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert result.returncode == 0, result.stderr
        for secret in ("sk-ant-api03-", "ghp_aB3dE6gH", "AKIAIOSFODNN7EXAMPLE"):
            assert secret not in result.stdout, secret
        assert "<redacted>" in result.stdout

    def test_it_refuses_to_emit_without_the_shared_scrubber(self, tmp_path):
        """Fail CLOSED. A missing reflection.py must not silently downgrade to printing
        raw tool output -- and the scrubber is deliberately not reimplemented here, so
        there is exactly one definition of what a secret looks like."""
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        isolated = tmp_path / "isolated" / ".claude" / "operations" / "scripts"
        isolated.mkdir(parents=True)
        _shutil.copy2(str(MINER), str(isolated / "transcript-miner.py"))
        env = dict(os.environ)
        env["ECC_HOOK_PROFILE"] = "minimal"
        env["HOME"] = str(home)
        result = subprocess.run(
            [sys.executable, str(isolated / "transcript-miner.py"), SESSION,
             "--around", "demo"],
            cwd=str(tmp_path / "isolated"), capture_output=True, text=True,
            timeout=60, env=env)
        assert result.returncode == 1, result.stdout
        assert "refusing to emit" in result.stderr

    def test_thinking_blocks_are_not_emitted(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert "SECRET-REASONING-BLOCK" not in result.stdout

    def test_tool_use_input_is_reduced_to_the_tool_name(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo")
        assert "id_rsa" not in result.stdout
        assert "[tool_use Bash]" in result.stdout

    def test_list_works_without_around(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--list")
        assert result.returncode == 0, result.stderr
        assert SESSION in result.stdout
        assert str(home) not in result.stdout

    def test_around_is_required_without_list(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION)
        assert result.returncode == 1

    def test_output_is_bounded(self, tmp_path):
        home = tmp_path / "home"
        write_transcript(home, SESSION, "demo")
        result = run_miner(tmp_path, home, SESSION, "--around", "demo", "--max-lines", "3")
        assert len(result.stdout.splitlines()) <= 6


# ---------------------------------------------------------------------------- closure

PLANNER = AGENTS / "planner.md"


class TestRejectionsSearch:
    """Spec test #6 - the retrieval half. Exit codes are the contract: planner.md
    branches on them exactly as debugger.md does for the issue ledger."""

    def test_no_match_exits_3(self, tmp_path):
        make_tree(tmp_path)
        result = run_record(tmp_path, "rejections", "search", "nothing-like-this-exists")
        assert result.returncode == 3
        assert "Silence is NOT evidence" in result.stdout

    def test_hit_exits_0_and_names_the_brief(self, tmp_path):
        reject_twice(tmp_path)
        result = run_record(tmp_path, "rejections", "search", "anchor")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "demo" in result.stdout
        assert "demo.md" in result.stdout

    def test_hit_reports_the_session_so_the_transcript_stays_reachable(self, tmp_path):
        reject_twice(tmp_path)
        result = run_record(tmp_path, "rejections", "search", "anchor")
        assert SESSION in result.stdout

    def test_results_are_framed_as_priors_not_rules(self, tmp_path):
        reject_twice(tmp_path)
        result = run_record(tmp_path, "rejections", "search", "anchor")
        assert "PRIORS, not proofs" in result.stdout

    def test_brief_path_is_printed_relative(self, tmp_path):
        """planner.md Phase 0 pastes this output into plan files that get committed."""
        reject_twice(tmp_path)
        result = run_record(tmp_path, "rejections", "search", "anchor")
        assert str(tmp_path) not in result.stdout
        assert ".claude/knowledge/rejections/demo.md" in result.stdout

    def test_corrupt_index_does_not_crash_search(self, tmp_path):
        reject_twice(tmp_path)
        index = brief_dir(tmp_path) / "INDEX.jsonl"
        index.write_text("}}broken\n" + index.read_text(encoding="utf-8"), encoding="utf-8")
        result = run_record(tmp_path, "rejections", "search", "anchor")
        assert result.returncode == 0
        assert "corrupt INDEX.jsonl line" in result.stderr


class TestLoopIsClosed:
    """An archive nothing reads changes no behaviour. The planner's Phase 0 call is
    what makes the store a feedback loop."""

    def test_planner_phase_0_searches_the_briefs(self):
        text = PLANNER.read_text(encoding="utf-8")
        assert "rejections search" in text
        assert "Silence is NOT evidence" in text

    def test_planner_treats_a_brief_as_a_prior_not_a_proof(self):
        text = PLANNER.read_text(encoding="utf-8")
        assert "PRIOR, not a proof" in text


class TestCodeReviewVerdictHasAConsumer:
    """A verdict block emitted into a channel nothing reads changes nothing. Before
    this, /code-review referenced review-record.py nowhere."""

    def test_code_review_command_records_the_verdict(self):
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        # The command calls the recording SUBCOMMAND now; the write itself moved into
        # review-record.py, which is what got /code-review back under its line budget.
        assert "review-record.py record-code-review" in text

    def test_code_review_records_only_non_approving_verdicts(self):
        """Safety property: an APPROVE from a DIFF review must never satisfy the
        execution gate for an ops.json it never scored."""
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        assert "--only-non-approving" in text

    def test_the_command_does_no_verdict_parsing_of_its_own(self):
        """A second parser is a second scope, and two scopes disagree.

        Guarded at TOKEN level, not by a literal blacklist: a reintroduced parse spelled
        `grep -q DECISION`, `awk`, or `case "$x" in *APPROVED*)` sails straight past a list
        of four exact strings.
        """
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        fence = text.split("### Step 5c", 1)[1].split("\n### ", 1)[0]
        fence = fence.split("```bash", 1)[1].split("```", 1)[0]
        for token in ("sed", "grep", "awk", "cut", "DECISION", "SCORE", "APPROVED"):
            assert not re.search(r"\b%s\b" % token, fence), (
                "verdict parsing is creeping back into the shell: %r" % token)


class TestCodeReviewFilterSharesTheParsersScope:
    """The shipped snippet is executed here, not read.

    The shell filter and review-record.py's parser must agree about WHERE a decision
    lives. parse_verdict reads only the last `=== REVIEW ===` block; a filter with a
    wider scope lets prose decide whether an APPROVED verdict gets written to the top
    level of a record that gates execution.
    """

    @staticmethod
    def extract_fence(step):
        """The shipped fence for a step, or a NAMED failure.

        A missing step used to surface as IndexError. The point of these tests is that a
        dead path is diagnosable, so the absence of the path says so in words.
        """
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        marker = "### %s" % step
        assert marker in text, "code-review.md has no %s -- the recording path is dead" % step
        section = text.split(marker, 1)[1].split("\n### ", 1)[0]
        assert "```bash" in section, "%s has no runnable bash fence" % step
        return section.split("```bash", 1)[1].split("```", 1)[0]

    @staticmethod
    def extract_snippet():
        return TestCodeReviewFilterSharesTheParsersScope.extract_fence("Step 5c")

    PLACEHOLDER = "REPLACE THIS LINE WITH THE REPORT ABOVE, VERBATIM, INCLUDING ITS VERDICT BLOCK"

    @classmethod
    def run_snippet(cls, tmp_path, review_output):
        """Run every Step-5x fence IN THE ORDER THE DOCUMENT LISTS THEM.

        The order is DISCOVERED from the shipped file, never hardcoded here. An earlier
        harness ran producer-then-recorder while the document said recorder-then-producer
        (the recorder was Step 3b, before Step 4) -- so in production the recorder ran
        first, found no report and skipped, while the suite stayed green. Three earlier
        rounds were the same shape: the harness supplying what production lacked. Here
        the harness cannot express an order the document does not have.
        """
        scripts = tmp_path / ".claude" / "operations" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(RECORD), str(scripts / "review-record.py"))
        make_tree(tmp_path)
        env = dict(os.environ)
        env["ECC_HOOK_PROFILE"] = "minimal"
        for leaked in ("PLAN_FILE", "REVIEW_OUT", "OPS_FILE", "review_output"):
            env.pop(leaked, None)

        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        steps = re.findall(r"(?m)^### (Step 5[a-z])\b", text)
        assert steps == ["Step 5b", "Step 5c"], (
            "document order changed: %s -- the producer must precede the recorder" % steps)

        result = None
        for step in steps:
            fence = cls.extract_fence(step)
            if cls.PLACEHOLDER in fence:
                fence = fence.replace(cls.PLACEHOLDER, review_output)
            result = subprocess.run(["bash", "-c", fence], cwd=str(tmp_path),
                                    capture_output=True, text=True, timeout=60, env=env)
            assert result.returncode == 0, (step, result.stderr)
            if step == "Step 5b":
                assert (tmp_path / ".claude" / "reports" / "last-code-review.txt").is_file(), (
                    "Step 5b did not produce the report Step 5c reads -- the recording "
                    "path is inert in production")
        record = tmp_path / ".claude" / "reports" / "reviews" / "demo.json"
        return result, record

    def test_the_producer_precedes_the_recorder_in_the_document(self):
        """An agent executes this command top to bottom.

        The recorder used to be Step 3b, anchored before Step 4, while its producer was
        Step 5b -- shipped order 3b, 4, 5, 5b, so the recorder ran BEFORE anything wrote
        the report, found nothing, and skipped. The suite passed because the harness ran
        producer-then-recorder, an order the DOCUMENT did not have. Same end-to-end gap
        as rounds 3-5, expressed as ordering. Document order is now the contract.
        """
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        assert "### Step 3b" not in text, "the recorder must not reappear before its producer"
        assert text.index("### Step 5b") < text.index("### Step 5c"),             "the recorder is documented before the producer that feeds it"
        assert text.index("### Step 5c") < text.index("## Usage Examples")

    def test_step_5b_writes_exactly_the_path_step_5c_reads(self):
        """A static cross-check, so the two steps cannot drift apart silently even if
        both keep working in isolation."""
        producer = self.extract_fence("Step 5b")
        recorder = self.extract_snippet()
        pattern = r'REVIEW_OUT="\$\{REVIEW_OUT:-([^}"]+)\}"'
        produced = re.search(pattern, producer)
        recorded = re.search(pattern, recorder)
        assert produced and recorded, "REVIEW_OUT default missing from one of the steps"
        assert produced.group(1) == recorded.group(1), (
            "Step 5b writes %r but Step 5c reads %r"
            % (produced.group(1), recorded.group(1)))

    def test_a_missing_report_is_announced_not_skipped_in_silence(self, tmp_path):
        """Every defect in this chain survived by skipping quietly."""
        scripts = tmp_path / ".claude" / "operations" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(RECORD), str(scripts / "review-record.py"))
        make_tree(tmp_path)
        env = dict(os.environ)
        env["ECC_HOOK_PROFILE"] = "minimal"
        for leaked in ("PLAN_FILE", "REVIEW_OUT", "OPS_FILE", "review_output"):
            env.pop(leaked, None)
        result = subprocess.run(["bash", "-c", self.extract_snippet()], cwd=str(tmp_path),
                                capture_output=True, text=True, timeout=60, env=env)
        assert "nothing recorded" in result.stderr
        assert not (tmp_path / ".claude" / "reports" / "reviews" / "demo.json").exists()

    def test_the_resolved_plan_is_echoed(self, tmp_path):
        result, _record = self.run_snippet(
            tmp_path, "=== REVIEW ===\nSCORE: 62\nDECISION: REVISE\n=== END REVIEW ===\n")
        assert "plan-demo.md" in result.stderr
        assert "ops-demo.json" in result.stderr

    def test_the_fence_binds_every_variable_it_uses(self):
        """The inert-in-production regression.

        A fence that reads $PLAN_FILE without ever assigning it does nothing at all, and
        does it silently. This asserts on the shipped text, so no test fixture can hide it.
        """
        fence = self.extract_snippet()
        used = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", fence))
        assigned = set(re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)=", fence))
        assigned |= set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-", fence))
        assigned |= {"ARGUMENTS"}  # supplied by the command harness itself
        unbound = used - assigned
        assert not unbound, "Step 5c reads unbound variable(s): %s" % sorted(unbound)

    def test_the_fence_passes_the_inputs_it_documents(self):
        """Replaces an assertion that the PROSE named REVIEW_OUT and PLAN_FILE. Prose
        naming two inputs the invocation never passes is exactly the shape of defect this
        step already shipped twice -- documented, and inert. So the assertion moved to the
        invocation: the recorder must actually hand the script the two files the prose
        promises, or the step records nothing while reading as if it does."""
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        step = text.split("### Step 5c", 1)[1].split("\n### ", 1)[0]
        fence = step.split("```bash", 1)[1].split("```", 1)[0]
        call = fence.split("record-code-review", 1)[1]
        assert '--report "$REVIEW_OUT"' in call, call
        assert '--plan "$PLAN_FILE"' in call, call
        prose = step.split("```bash", 1)[0]
        for name in ("REVIEW_OUT", "PLAN_FILE"):
            assert name in prose, "%s is passed but never explained to the reader" % name

    def test_the_verdict_writer_has_a_keyword_api_and_no_namespace_is_built(self):
        """The recorded nit: cmd_record_code_review hand-built an argparse.Namespace, so
        cmd_write's contract was enforced by inspection. A weaker test would assert the
        new function exists; this one asserts the OLD construction is gone, which is the
        thing that could silently come back."""
        source = RECORD.read_text(encoding="utf-8")
        assert "argparse.Namespace(" not in source
        out = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys;"
             "spec=importlib.util.spec_from_file_location('rr', sys.argv[1]);"
             "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
             "import inspect;p=inspect.signature(m.write_verdict).parameters;"
             "print(','.join(p))", str(RECORD)],
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        for name in ("plan", "ops", "from_review", "score", "decision", "session_id",
                     "verdict_origin", "only_non_approving"):
            assert name in out.stdout, (name, out.stdout)

    def test_cannot_review_rounds_are_told_to_skip_the_step(self):
        """CANNOT REVIEW emits no block by design, so parse_verdict fails and the write
        exits 1. The fix is prose telling the round to skip -- NOT widening the case arm,
        which would swallow real errors."""
        text = (REPO / ".claude" / "commands" / "code-review.md").read_text(encoding="utf-8")
        step = text.split("### Step 5c", 1)[1].split("\n### ", 1)[0]
        assert "CANNOT REVIEW" in step
        # Stronger than the old "no 1) arm inside the case": the recording step no
        # longer branches on an exit code in shell AT ALL -- review-record.py owns the
        # outcome, including which outcomes are quiet.
        fence = self.extract_snippet()
        for smell in ("case $status", "$?", "exit 5"):
            assert smell not in fence, smell

    def test_prose_rejection_with_an_approving_block_records_nothing(self, tmp_path):
        """The whole point of the fix: a re-review quoting a prior verdict must not be
        able to smuggle an APPROVED verdict onto the execution gate."""
        review = (
            "Round 2. The previous round said DECISION: REJECTED and I have re-checked it.\n"
            "\n=== REVIEW ===\nSCORE: 95\nDECISION: APPROVED\n=== END REVIEW ===\n"
        )
        result, record = self.run_snippet(tmp_path, review)
        assert result.returncode == 0, result.stderr
        assert not record.exists(), (
            "an APPROVED block was recorded because prose outside it said REJECTED — "
            "the shell filter's scope is wider than parse_verdict's")

    def test_a_rejecting_block_is_recorded(self, tmp_path):
        review = "prose\n\n=== REVIEW ===\nSCORE: 62\nDECISION: REVISE\n=== END REVIEW ===\n"
        result, record = self.run_snippet(tmp_path, review)
        assert result.returncode == 0, result.stderr
        assert record.exists(), result.stdout + result.stderr
        assert _json_load(record)["decision"] == "REVISE"

    def test_the_last_block_wins_just_like_the_parser(self, tmp_path):
        """Two blocks, approving last: parse_verdict would record APPROVED, so the
        filter must refuse the write rather than let it through."""
        review = (
            "=== REVIEW ===\nSCORE: 60\nDECISION: REJECTED\n=== END REVIEW ===\n"
            "\nafter the fix:\n"
            "=== REVIEW ===\nSCORE: 95\nDECISION: APPROVED\n=== END REVIEW ===\n"
        )
        result, record = self.run_snippet(tmp_path, review)
        assert result.returncode == 0, result.stderr
        assert not record.exists()

    def test_two_blocks_with_different_anchor_whitespace_record_nothing(self, tmp_path):
        """THE regression for round 4.

        `_BLOCK_RE` uses `\\s*`, so `===<TAB>REVIEW<TAB>===` is a real block to the
        parser and parse_verdict takes it as blocks[-1] -> APPROVED. The shell filter
        this step used to carry matched only space-separated anchors, so its range closed
        on block 1 and it saw REJECTED -- filter and parser reading DIFFERENT blocks, with
        the approval landing at the top level of the record that gates execution. There is
        no verdict logic in the shell any more; this proves it stays that way.
        """
        review = (
            "=== REVIEW ===\nSCORE: 40\nDECISION: REJECTED\n=== END REVIEW ===\n"
            "\nlater round:\n"
            "===\tREVIEW\t===\nSCORE: 96\nDECISION: APPROVED\n===\tEND REVIEW\t===\n"
        )
        result, record = self.run_snippet(tmp_path, review)
        assert result.returncode == 0, result.stderr
        assert not record.exists(), (
            "an APPROVED verdict was recorded from a tab-anchored block: the shell and "
            "the parser are reading different blocks again")

    def test_an_approving_verdict_is_refused_quietly_not_loudly(self, tmp_path):
        """A passing code review is the common case; it must not look like a failure."""
        review = "=== REVIEW ===\nSCORE: 95\nDECISION: APPROVED\n=== END REVIEW ===\n"
        result, record = self.run_snippet(tmp_path, review)
        assert not record.exists()
        assert "WARNING" not in result.stderr, result.stderr


class TestOnlyNonApprovingGate:
    """The gate itself, independent of any caller."""

    def test_approved_is_refused_with_exit_5(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            "--only-non-approving",
                            stdin="=== REVIEW ===\nSCORE: 95\nDECISION: APPROVED\n"
                                  "=== END REVIEW ===\n")
        assert result.returncode == 5, result.stdout + result.stderr
        assert "EXPECTED outcome" in result.stderr
        assert not (tmp_path / ".claude" / "reports" / "reviews" / "demo.json").exists()

    def test_conditional_is_recorded_not_refused(self, tmp_path):
        """CONDITIONAL cannot authorise execution (cmd_check needs the literal APPROVED),
        so refusing it would protect nothing and would drop a genuinely non-approving
        round out of the rejection corpus. The predicate means one thing: could this
        verdict authorise execution?"""
        plan, ops = make_tree(tmp_path)
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            "--only-non-approving",
                            stdin="=== REVIEW ===\nSCORE: 85\nDECISION: CONDITIONAL\n"
                                  "=== END REVIEW ===\n")
        assert result.returncode == 0, result.stdout + result.stderr
        assert record_json(tmp_path)["decision"] == "CONDITIONAL"
        check = run_record(tmp_path, "check", plan, ops)
        assert check.returncode == 4, "a recorded CONDITIONAL must still not authorise"

    def test_rejecting_verdicts_still_record(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                            "--only-non-approving", stdin=REVISE_BLOCK)
        assert result.returncode == 0, result.stderr
        assert record_json(tmp_path)["decision"] == "REVISE"

    def test_the_gate_reads_the_same_block_the_writer_does(self, tmp_path):
        """Two blocks, approving LAST: parse_verdict records blocks[-1], so the gate
        must refuse -- whatever whitespace the anchors use."""
        plan, ops = make_tree(tmp_path)
        for anchors in (("=== REVIEW ===", "=== END REVIEW ==="),
                        ("===\tREVIEW\t===", "===\tEND REVIEW\t===")):
            stdin = ("=== REVIEW ===\nSCORE: 40\nDECISION: REJECTED\n=== END REVIEW ===\n"
                     "\n%s\nSCORE: 96\nDECISION: APPROVED\n%s\n" % anchors)
            result = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                                "--only-non-approving", stdin=stdin)
            assert result.returncode == 5, (anchors, result.stdout + result.stderr)

    def test_without_the_flag_nothing_changes(self, tmp_path):
        plan, ops = make_tree(tmp_path)
        result = run_record(tmp_path, "write", plan, ops, "--score", "95",
                            "--decision", "APPROVED")
        assert result.returncode == 0
        assert record_json(tmp_path)["decision"] == "APPROVED"


# --------------------------------------------------------------------------- item D
#
# Backfill. The fixture below is written in the shapes the REAL corpus uses -- entries with
# `message.content` as a LIST of typed blocks, a tool_result, an attachment record -- because
# the miner has already been bitten once by a fixture shaped to the code instead of to
# reality. CLAUDEKIT_TRANSCRIPT_ROOT only relocates the scan; it supplies no data.

VERDICT_TEXT = ("Reviewing ops-legacy-thing.json now.\n\n"
                "=== REVIEW ===\nSCORE: 55\nDECISION: REJECTED\n"
                "- [CRITICAL] the anchor in ops-legacy-thing.json does not exist\n"
                "=== END REVIEW ===\n")


def _transcript(directory, name, texts, extra=()):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    entries = []
    for text in texts:
        entries.append({"type": "assistant",
                        "message": {"content": [{"type": "text", "text": text}]}})
    entries.extend(extra)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def _backfill_env(tmp_path):
    env = _no_session_env(tmp_path)
    env["CLAUDEKIT_TRANSCRIPT_ROOT"] = str(tmp_path / "transcripts")
    return env


def _corpus_tree(tmp_path):
    make_tree(tmp_path)
    return tmp_path / "transcripts"


class TestBackfillReconstructsWithoutPretending:
    def test_the_default_run_writes_nothing(self, tmp_path):
        """A weaker test runs --dry-run explicitly and proves nothing about the DEFAULT,
        which is the only thing that matters: the failure mode is a first run that
        silently rewrote the corpus."""
        root = _corpus_tree(tmp_path)
        _transcript(root, "11111111-2222-3333-4444-555555555555.jsonl", [VERDICT_TEXT])
        out = run_record(tmp_path, "rejections", "backfill", env=_backfill_env(tmp_path))
        assert out.returncode == 0, out.stderr
        assert "rows to write:           1" in out.stdout, out.stdout
        assert "DRY RUN" in out.stdout
        assert not (tmp_path / ".claude" / "knowledge" / "rejections"
                    / "INDEX.jsonl").is_file()

    def test_written_rows_are_marked_reconstructed_and_re_runs_are_idempotent(self, tmp_path):
        """Backfilled rows that looked like live ones would silently lower the confidence
        of every later analysis; a re-run that duplicated them would inflate the
        sample-size gate the retro depends on."""
        root = _corpus_tree(tmp_path)
        env = _backfill_env(tmp_path)
        _transcript(root, "11111111-2222-3333-4444-555555555555.jsonl", [VERDICT_TEXT])
        assert run_record(tmp_path, "rejections", "backfill", "--write",
                          env=env).returncode == 0
        rows = _index_rows(tmp_path)
        assert len(rows) == 1
        assert rows[0]["source"] == "backfill"
        assert rows[0]["verdict_origin"] == "reconstructed"
        assert rows[0]["round"] < 0, "a reconstructed round must never collide with a live one"
        run_record(tmp_path, "rejections", "backfill", "--write", env=env)
        assert len(_index_rows(tmp_path)) == 1

    def test_a_verdict_it_cannot_attribute_is_counted_never_guessed(self, tmp_path):
        """Two candidate slugs in the window. Assigning the likeliest is the same
        fabrication the session-id resolver refuses, in a second place."""
        root = _corpus_tree(tmp_path)
        text = VERDICT_TEXT.replace("Reviewing ops-legacy-thing.json now.",
                                    "Reviewing ops-legacy-thing.json and ops-other-thing.json")
        _transcript(root, "22222222-2222-3333-4444-555555555555.jsonl", [text])
        out = run_record(tmp_path, "rejections", "backfill", "--write",
                         env=_backfill_env(tmp_path))
        assert "unattributable:        1" in out.stdout, out.stdout
        assert _index_rows(tmp_path) == []

    def test_an_approving_verdict_is_never_backfilled(self, tmp_path):
        root = _corpus_tree(tmp_path)
        approving = ("About ops-legacy-thing.json\n\n=== REVIEW ===\nSCORE: 95\n"
                     "DECISION: APPROVED\n=== END REVIEW ===\n")
        _transcript(root, "33333333-2222-3333-4444-555555555555.jsonl", [approving])
        out = run_record(tmp_path, "rejections", "backfill", "--write",
                         env=_backfill_env(tmp_path))
        assert "approving (skipped):   1" in out.stdout, out.stdout
        assert _index_rows(tmp_path) == []

    def test_a_credential_in_a_transcript_never_reaches_stdout_or_the_brief(self, tmp_path):
        """Scrubbing must happen BEFORE emission, and to every channel -- the report and
        the tracked brief. A test that only checked the brief would pass while the dry-run
        report printed the token to a terminal and into a pasted retro."""
        root = _corpus_tree(tmp_path)
        secret = "sk-ant-" + ("a" * 40)
        text = VERDICT_TEXT.replace("does not exist", "leaked %s here" % secret)
        _transcript(root, "44444444-2222-3333-4444-555555555555.jsonl", [text],
                    extra=[{"type": "user", "message": {"content": [
                        {"type": "tool_result", "content": "TOKEN=%s" % secret}]}}])
        out = run_record(tmp_path, "rejections", "backfill", "--write",
                         env=_backfill_env(tmp_path))
        assert secret not in out.stdout and secret not in out.stderr
        store = tmp_path / ".claude" / "knowledge" / "rejections"
        for path in store.rglob("*"):
            if path.is_file():
                assert secret not in path.read_text(encoding="utf-8"), path

    def test_a_dotted_ops_filename_keys_under_the_slug_the_live_record_uses(self, tmp_path):
        """ops-<x>.ops.json must key as <x>, exactly as ops_slug() keys the live record.
        A backfilled row under "<x>.ops" can never join its own history, and the trend
        folding it exists for silently never happens -- with nothing failing."""
        root = _corpus_tree(tmp_path)
        text = VERDICT_TEXT.replace("ops-legacy-thing.json", "ops-legacy-thing.ops.json")
        _transcript(root, "55555555-2222-3333-4444-555555555555.jsonl", [text])
        assert run_record(tmp_path, "rejections", "backfill", "--write",
                          env=_backfill_env(tmp_path)).returncode == 0
        rows = _index_rows(tmp_path)
        assert rows and rows[0]["slug"] == "legacy-thing", rows

    def test_the_report_names_the_scope_before_anything_is_written(self, tmp_path):
        """The unscoped version read 99 projects and proposed rows from two unrelated
        repositories. An operator approving --write must SEE which project is being read;
        a scope that is only in a docstring is not a control."""
        root = _corpus_tree(tmp_path)
        _transcript(root, "66666666-2222-3333-4444-555555555555.jsonl", [VERDICT_TEXT])
        out = run_record(tmp_path, "rejections", "backfill", env=_backfill_env(tmp_path))
        assert "project scope:" in out.stdout
        assert "transcripts available:   1 for THIS project" in out.stdout, out.stdout

    def test_another_projects_transcripts_are_never_read(self, tmp_path):
        """The CRITICAL this scoping fixes: every kitted project writes ops-<slug>.json,
        so the slug filter scopes NOTHING. Without a project-scoped root, the foreign
        transcript below is mined and its findings land in this repo's tracked store."""
        make_tree(tmp_path)
        mine = tmp_path / "transcripts" / "mine"
        theirs = tmp_path / "transcripts" / "theirs"
        _transcript(mine, "77777777-2222-3333-4444-555555555555.jsonl", [VERDICT_TEXT])
        _transcript(theirs, "88888888-2222-3333-4444-555555555555.jsonl",
                    [VERDICT_TEXT.replace("legacy-thing", "someone-elses-thing")])
        env = _no_session_env(tmp_path)
        env["CLAUDEKIT_TRANSCRIPT_ROOT"] = str(mine)
        out = run_record(tmp_path, "rejections", "backfill", "--write", env=env)
        assert out.returncode == 0, out.stderr
        rows = _index_rows(tmp_path)
        assert [r["slug"] for r in rows] == ["legacy-thing"], rows
        for path in (tmp_path / ".claude" / "knowledge" / "rejections").rglob("*"):
            if path.is_file():
                assert "someone-elses-thing" not in path.read_text(encoding="utf-8")

    def test_subagent_transcripts_are_never_scanned(self, tmp_path):
        """agent-*.jsonl is not a session. Mining one attributes a subagent's work to a
        session that never did it -- and its filename is not a session id at all."""
        root = _corpus_tree(tmp_path)
        _transcript(root, "agent-abcdef0123456789.jsonl", [VERDICT_TEXT])
        out = run_record(tmp_path, "rejections", "backfill", "--write",
                         env=_backfill_env(tmp_path))
        assert "transcripts available:   0 for THIS project" in out.stdout, out.stdout
        assert _index_rows(tmp_path) == []



# --------------------------------------------------------------------------- item B
#
# `rejections classify` is the ONLY writer of defect_type/trigger. Every test below is
# about the property that makes the distribution worth reading: nothing is ever inferred.

def _classify(tmp_path, *argv, env=None):
    return run_record(tmp_path, "rejections", "classify", *argv, env=env)


def _classification_rows(tmp_path):
    return [r for r in _index_rows(tmp_path) if r.get("row_type") == "classification"]


class TestClassificationIsNeverGuessed:
    def _corpus(self, tmp_path):
        env = _no_session_env(tmp_path)
        _two_rejecting_rounds(tmp_path, env)
        return env

    def test_it_refuses_a_round_that_was_never_recorded(self, tmp_path):
        """A weaker test only checks the happy path. This one asserts the refusal that
        keeps the corpus honest: a classification for a non-existent round would be a
        label with nothing under it."""
        env = self._corpus(tmp_path)
        out = _classify(tmp_path, "demo", "99", "--type", "file-ownership",
                        "--trigger", "ownership-map", env=env)
        assert out.returncode == 3, out.stdout + out.stderr
        assert _classification_rows(tmp_path) == []

    def test_it_refuses_a_type_outside_the_vocabulary(self, tmp_path):
        """Free text in defect_type makes the distribution unqueryable again -- the exact
        condition this subcommand exists to end.

        Asserts the SPECIFIC refusal (argparse's exit 2, and the rejected value named in
        the message), never merely `returncode != 0`. A bare non-zero assertion passes on
        any error at all -- including a mistyped slug that never reached the vocabulary
        check, which is precisely how this class of test passes while proving nothing."""
        env = self._corpus(tmp_path)
        out = _classify(tmp_path, "demo", "2", "--type", "vibes",
                        "--trigger", "ownership-map", env=env)
        assert out.returncode == 2, out.stdout + out.stderr
        assert "vibes" in out.stderr and "--type" in out.stderr, out.stderr
        assert _classification_rows(tmp_path) == []

    def test_the_happy_path_actually_writes(self, tmp_path):
        """The guard against every other test in this class passing vacuously: if the
        slug, the round or the store path is wrong, `classify` returns 3 and writes
        nothing, and a suite that only asserts refusals cannot tell the difference."""
        env = self._corpus(tmp_path)
        out = _classify(tmp_path, "demo", "2", "--type", "drifted-anchor",
                        "--trigger", "anchor-check", env=env)
        assert out.returncode == 0, out.stdout + out.stderr
        rows = _classification_rows(tmp_path)
        assert len(rows) == 1 and rows[0]["defect_type"] == "drifted-anchor"
        brief = (tmp_path / ".claude" / "knowledge" / "rejections" / "demo.md")
        assert "Classification (round 2)" in brief.read_text(encoding="utf-8")

    def test_re_classifying_appends_and_the_reader_takes_the_last(self, tmp_path):
        """Asserts the FIRST row is still on disk. A writer that corrected in place would
        pass any test that only read the final value."""
        env = self._corpus(tmp_path)
        assert _classify(tmp_path, "demo", "2", "--type", "drifted-anchor",
                         "--trigger", "anchor-check", env=env).returncode == 0
        assert _classify(tmp_path, "demo", "2", "--type", "untested-behaviour",
                         "--trigger", "test-coverage", env=env).returncode == 0
        rows = _classification_rows(tmp_path)
        assert [r["defect_type"] for r in rows] == ["drifted-anchor", "untested-behaviour"]
        out = run_record(tmp_path, "rejections", "search", "demo", env=env)
        assert "defect_type=untested-behaviour" in out.stdout, out.stdout

    def test_stats_never_imputes_an_unclassified_round(self, tmp_path):
        """The failure this guards is a confident distribution over data that does not
        exist: unclassified silently counted as `other`.

        A THIRD rejecting round is written on purpose. The brief trigger fires on the
        second one, so two rounds produce exactly ONE brief row -- and a corpus with
        nothing left unclassified cannot demonstrate non-imputation at all. The first
        version of this test asserted `unclassified=1` against a one-row corpus and
        failed, which is the assertion doing its job: the count has to be real."""
        env = self._corpus(tmp_path)
        plan, ops = make_tree(tmp_path)
        run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                   stdin=REVISE_BLOCK, env=env)
        rows = [r for r in _index_rows(tmp_path) if r.get("row_type", "brief") == "brief"]
        assert [r["round"] for r in rows] == [2, 3], rows
        assert _classify(tmp_path, "demo", "2", "--type", "scope-overflow",
                         "--trigger", "phase-count", env=env).returncode == 0
        out = run_record(tmp_path, "rejections", "stats", "--by-type", env=env)
        assert "classified=1 of 2" in out.stdout, out.stdout
        assert "scope-overflow=1" in out.stdout
        assert "unclassified=1" in out.stdout and "NOT imputed" in out.stdout
        assert "other=" not in out.stdout

    def test_a_classification_row_is_not_counted_as_a_brief(self, tmp_path):
        env = self._corpus(tmp_path)
        before = run_record(tmp_path, "rejections", "stats", env=env).stdout
        assert _classify(tmp_path, "demo", "2", "--type", "other",
                         "--trigger", "rubric-general", env=env).returncode == 0
        assert len(_classification_rows(tmp_path)) == 1
        after = run_record(tmp_path, "rejections", "stats", env=env).stdout
        assert before.split()[0] == after.split()[0], (before, after)

    def test_the_prompt_and_the_script_share_one_vocabulary(self):
        """Corpus assertion. Two lists that must agree drift the moment only one of them
        is edited, and nothing else would notice."""
        script = RECORD.read_text(encoding="utf-8")
        vocab = script.split("DEFECT_TYPES = (", 1)[1].split(")", 1)[0]
        tokens = [t.strip().strip('",\'') for t in vocab.split() if t.strip(' ",')]
        prompt = (AGENTS / "flow-analyst.md").read_text(encoding="utf-8")
        for token in tokens:
            assert token and token in prompt, token



# --------------------------------------------------------------------------- item A
#
# The session-id gap. Every test here runs with CLAUDE_SESSION_ID and CLAUDEKIT_SESSION_ID
# STRIPPED, because that is the shipped condition -- nothing exports them, which is why the
# one live brief in this store records `session: unknown`. A test that exported one would
# prove that a path nobody takes works.

GATE = REPO / ".claude" / "hooks" / "reflection-gate.py"


def _no_session_env(tmp_path):
    """Production conditions + an isolated ledger root. The env var below relocates
    reflection.py's own store (its documented override); it supplies no DATA the shipped
    path would otherwise be missing."""
    env = {"CLAUDE_SESSION_ID": "", "CLAUDEKIT_SESSION_ID": "",
           "CLAUDEKIT_REFLECTION_DIR": str(tmp_path / "ledger")}
    (tmp_path / "ledger").mkdir(parents=True, exist_ok=True)
    return env


def _run_session_start(tmp_path, session_id, env):
    """Execute the SHIPPED SessionStart hook, so the pointer under test is the one
    production writes -- not a fixture shaped to whatever the reader wants."""
    environ = dict(os.environ)
    environ["ECC_HOOK_PROFILE"] = "minimal"
    environ.update(env)
    payload = json.dumps({"hook_event_name": "SessionStart", "session_id": session_id,
                          "transcript_path": "/somewhere/%s.jsonl" % session_id})
    return subprocess.run([sys.executable, str(GATE)], input=payload, cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=60, env=environ)


def _two_rejecting_rounds(tmp_path, env):
    plan, ops = make_tree(tmp_path)
    first = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                       stdin=REVISE_BLOCK, env=env)
    second = run_record(tmp_path, "write", plan, ops, "--from-review", "-",
                        stdin=REVISE_BLOCK, env=env)
    return first, second


def _index_rows(tmp_path):
    path = tmp_path / ".claude" / "knowledge" / "rejections" / "INDEX.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


class TestTheSessionIdIsProvenOrUnknown:
    def test_with_no_env_and_no_pointer_it_records_unknown_AND_warns(self, tmp_path):
        """A weaker test asserts only the VALUE. That passes on a silent degrade, which
        is the defect itself: the live brief already said `unknown` and nothing said so
        out loud. The warning is the deliverable."""
        env = _no_session_env(tmp_path)
        _, second = _two_rejecting_rounds(tmp_path, env)
        rows = _index_rows(tmp_path)
        assert rows and rows[-1]["session_id"] == "unknown"
        assert "session: unknown" in second.stderr
        assert second.returncode == 0, "the verdict must still be recorded"

    def test_the_pointer_the_real_hook_writes_is_the_id_the_brief_records(self, tmp_path):
        """Executes the shipped hook. A weaker test hand-writes the pointer file and
        passes even if reflection-gate.py never records one, or if writer and reader
        disagree about the format."""
        env = _no_session_env(tmp_path)
        sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        hook = _run_session_start(tmp_path, sid, env)
        assert hook.returncode in (0, 2), hook.stderr
        _two_rejecting_rounds(tmp_path, env)
        rows = _index_rows(tmp_path)
        assert rows and rows[-1]["session_id"] == sid, rows

    def test_two_concurrent_sessions_resolve_to_unknown_not_to_one_of_them(self, tmp_path):
        """The measured environment: concurrent sessions in one project. A resolver that
        took matches[0] -- or the newest -- passes every other test in this class and
        fails only this one."""
        env = _no_session_env(tmp_path)
        for sid in ("aaaaaaaa-1111-2222-3333-444444444444",
                    "bbbbbbbb-1111-2222-3333-444444444444"):
            _run_session_start(tmp_path, sid, env)
        _, second = _two_rejecting_rounds(tmp_path, env)
        rows = _index_rows(tmp_path)
        assert rows and rows[-1]["session_id"] == "unknown", rows
        assert "session: unknown" in second.stderr

    def test_a_pointer_from_another_process_tree_is_never_used(self, tmp_path):
        """Asserts the absence of a WRONG id, which is the property that matters. A test
        asserting merely that SOME id was recorded would accept the mtime fabrication."""
        env = _no_session_env(tmp_path)
        pointer = tmp_path / "ledger" / "session-pointers.jsonl"
        pointer.write_text(json.dumps({
            "schemaVersion": 1, "session_id": "cccccccc-1111-2222-3333-444444444444",
            "pids": [999999], "transcript": "x.jsonl",
            "epoch": int(__import__("time").time())}) + "\n", encoding="utf-8")
        _two_rejecting_rounds(tmp_path, env)
        rows = _index_rows(tmp_path)
        assert rows and rows[-1]["session_id"] == "unknown", rows

    def test_a_pointer_it_cannot_read_poisons_instead_of_falling_through(self, tmp_path):
        """The demonstrated bug: writer and reader disagreed about what a valid session id
        IS (reflection.valid_session accepts any non-empty string; the reader wants a
        transcript filename). The reader SKIPPED the unreadable row and resolved to an
        older, stale pointer that also shared ancestry -- a WRONG id, silently.

        The malformed pointer is written by hand on purpose: the shipped hook now refuses
        to write one, so this asserts the reader's own refusal, which is what protects the
        store if the two definitions ever drift again.
        """
        env = _no_session_env(tmp_path)
        stale = "dddddddd-1111-2222-3333-444444444444"
        _run_session_start(tmp_path, stale, env)
        pointer = tmp_path / "ledger" / "session-pointers.jsonl"
        rows = [line for line in pointer.read_text(encoding="utf-8").splitlines() if line]
        mine = json.loads(rows[-1])
        rows.append(json.dumps(dict(mine, session_id="not-a-transcript-name")))
        pointer.write_text("\n".join(rows) + "\n", encoding="utf-8")
        _, second = _two_rejecting_rounds(tmp_path, env)
        recorded = _index_rows(tmp_path)[-1]["session_id"]
        assert recorded != stale, "resolved to a stale pointer it should have refused"
        assert recorded == "unknown", recorded
        assert "session: unknown" in second.stderr

    def test_the_hook_refuses_to_write_an_id_the_reader_cannot_use(self, tmp_path):
        """One definition, enforced at the write end too, so the poison above is a
        backstop rather than the only guard."""
        env = _no_session_env(tmp_path)
        _run_session_start(tmp_path, "not-a-transcript-name", env)
        pointer = tmp_path / "ledger" / "session-pointers.jsonl"
        assert not pointer.is_file() or "not-a-transcript-name" not in pointer.read_text(
            encoding="utf-8")

    def test_stats_reports_how_much_of_the_corpus_is_unresolvable(self, tmp_path):
        env = _no_session_env(tmp_path)
        _two_rejecting_rounds(tmp_path, env)
        out = run_record(tmp_path, "rejections", "stats", env=env)
        assert "unresolved_sessions=1" in out.stdout, out.stdout + out.stderr


class TestTheCallSitesPassItExplicitly:
    CALLERS = {"review.md": 125, "refine.md": 466, "code-review.md": 140}

    def test_every_recording_call_site_passes_session_id(self):
        for name in self.CALLERS:
            text = (REPO / ".claude" / "commands" / name).read_text(encoding="utf-8")
            assert "--session-id" in text, name

    def test_the_flag_was_added_line_neutrally(self):
        """These three commands sit at exactly their ck-lint baseline. Adding a LINE to
        any of them breaks a gate that is currently green, so the flag goes on a line
        that already existed -- and that is asserted, not remembered."""
        for name, budget in self.CALLERS.items():
            text = (REPO / ".claude" / "commands" / name).read_text(encoding="utf-8")
            assert len(text.split("\n")) - 1 <= budget, name

