"""Behavioral tests for the per-issue knowledge ledger.

These run the real script as a subprocess against a temp ledger directory and assert
outcomes (exit codes, files on disk), not the presence of keywords in prose.

Contract under test:
  * WRITE GATE: an entry is written only when the Verifier passed (--verified) AND the
    continuous-learning rubric scores reusability + novelty >= the configured threshold.
    Duplicate signatures are refused. Slugs cannot escape the ledger directory.
  * THRESHOLD CONFIG: the threshold comes from `.claude/hooks/config.json`
    (`continuous_learning.issue_ledger.min_combined_score`), falling back to 10 when the
    key is absent or unusable — so the documented config block cannot drift from the gate.
  * FILES ROUND-TRIP: a `--files` token that would corrupt the `files: [...]` frontmatter
    prune parses back is refused, never silently mangled.
  * RETRIEVAL: keyword/signature grep returns exit 0 with the entry on a match and exit 3
    on no match (so the debugger knows to diagnose from scratch).
  * PRUNE: an entry whose referenced files are all gone is reported (exit 1) and archived
    with --apply; a live entry is never touched.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "knowledge-ledger.py"
LEDGER = REPO / ".claude" / "knowledge" / "issues"

GOOD = dict(
    slug="null-deref-in-ops-executor",
    signature="AttributeError: 'NoneType' object has no attribute 'items'",
    root_cause="extract_json_field returned an empty string and the caller never checked",
    fix="fail closed on parse error and assert dict before .items()",
    files="src/claudekit/security/__init__.py",
    reusability="7",
    novelty="8",
)


def run(args, ledger, root=None):
    env = dict(os.environ, CLAUDEKIT_LEDGER_DIR=str(ledger))
    env["CLAUDEKIT_PROJECT_ROOT"] = str(root if root is not None else REPO)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True, timeout=60, env=env,
    )


def record_args(verified=True, **overrides):
    data = dict(GOOD)
    data.update(overrides)
    args = [
        "record",
        "--slug", data["slug"],
        "--signature", data["signature"],
        "--root-cause", data["root_cause"],
        "--fix", data["fix"],
        "--files", data["files"],
        "--reusability", str(data["reusability"]),
        "--novelty", str(data["novelty"]),
    ]
    if verified:
        args.append("--verified")
    return args


def write_config(root, payload):
    """Materialize a project root carrying .claude/hooks/config.json."""
    config = root / ".claude" / "hooks" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(payload), encoding="utf-8")
    return root


class TestShipped:
    def test_script_is_executable_python(self):
        assert SCRIPT.is_file(), "knowledge-ledger.py must ship in operations/scripts"
        p = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        for sub in ("search", "record", "list", "prune"):
            assert sub in p.stdout, "missing subcommand: %s" % sub

    def test_ledger_directory_documents_its_format(self):
        readme = LEDGER / "README.md"
        assert readme.is_file(), "ledger needs a README documenting the entry contract"
        text = readme.read_text(encoding="utf-8")
        for key in ("signature", "root_cause", "fix", "files", "date", "verified"):
            assert key in text, "README must document frontmatter key: %s" % key


class TestWriteGate:
    def test_unverified_write_is_refused(self, tmp_path):
        p = run(record_args(verified=False), tmp_path)
        assert p.returncode == 1, p.stdout + p.stderr
        assert "verified" in p.stderr.lower()
        assert list(tmp_path.glob("*.md")) == []

    def test_below_rubric_threshold_is_refused(self, tmp_path):
        p = run(record_args(reusability="3", novelty="2"), tmp_path)
        assert p.returncode == 1, p.stdout + p.stderr
        assert "novelty" in p.stderr.lower()
        assert list(tmp_path.glob("*.md")) == []

    def test_verified_and_scored_write_creates_entry(self, tmp_path):
        p = run(record_args(), tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        entry = tmp_path / "null-deref-in-ops-executor.md"
        assert entry.is_file()
        text = entry.read_text(encoding="utf-8")
        assert text.startswith("---")
        for key in ("signature:", "root_cause:", "fix:", "files:", "date:", "verified: true"):
            assert key in text, "missing frontmatter key: %s" % key

    def test_duplicate_signature_is_refused_then_forced(self, tmp_path):
        assert run(record_args(), tmp_path).returncode == 0
        dup = run(record_args(slug="other-slug"), tmp_path)
        assert dup.returncode == 1, dup.stdout + dup.stderr
        assert "already recorded" in dup.stderr
        assert not (tmp_path / "other-slug.md").exists()
        again = run(record_args() + ["--force"], tmp_path)
        assert again.returncode == 0, again.stdout + again.stderr

    def test_traversal_slug_is_rejected(self, tmp_path):
        p = run(record_args(slug="../../escaped"), tmp_path)
        assert p.returncode == 2, p.stdout + p.stderr
        assert not (tmp_path.parent / "escaped.md").exists()


class TestThresholdComesFromConfig:
    """The threshold documented in continuous-learning/SKILL.md must be the one enforced."""

    def test_config_can_raise_the_threshold(self, tmp_path):
        root = write_config(tmp_path / "root", {
            "continuous_learning": {"issue_ledger": {"min_combined_score": 20}}
        })
        ledger = tmp_path / "ledger"
        # 7 + 8 = 15 clears the default 10 but not the configured 20.
        p = run(record_args(), ledger, root=root)
        assert p.returncode == 1, p.stdout + p.stderr
        assert "< 20" in p.stderr, p.stderr
        assert not (ledger / "null-deref-in-ops-executor.md").exists()

    def test_config_can_lower_the_threshold(self, tmp_path):
        root = write_config(tmp_path / "root", {
            "continuous_learning": {"issue_ledger": {"min_combined_score": 4}}
        })
        ledger = tmp_path / "ledger"
        p = run(record_args(reusability="3", novelty="2"), ledger, root=root)
        assert p.returncode == 0, p.stdout + p.stderr
        assert (ledger / "null-deref-in-ops-executor.md").is_file()

    def test_missing_key_falls_back_to_ten(self, tmp_path):
        root = write_config(tmp_path / "root", {"global": {"logLevel": "info"}})
        ledger = tmp_path / "ledger"
        assert run(record_args(reusability="4", novelty="5"), ledger, root=root).returncode == 1
        assert run(record_args(reusability="5", novelty="5"), ledger, root=root).returncode == 0

    def test_malformed_config_falls_back_instead_of_crashing(self, tmp_path):
        root = tmp_path / "root"
        config = root / ".claude" / "hooks" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("{not json at all", encoding="utf-8")
        ledger = tmp_path / "ledger"
        p = run(record_args(), ledger, root=root)
        assert p.returncode == 0, p.stdout + p.stderr

    def test_non_integer_threshold_falls_back(self, tmp_path):
        root = write_config(tmp_path / "root", {
            "continuous_learning": {"issue_ledger": {"min_combined_score": "many"}}
        })
        ledger = tmp_path / "ledger"
        assert run(record_args(reusability="1", novelty="1"), ledger, root=root).returncode == 1
        assert run(record_args(), ledger, root=root).returncode == 0


class TestFilesRoundTrip:
    """`files:` is written by record and parsed back by prune - it must survive the trip."""

    def test_bracket_in_file_token_is_rejected(self, tmp_path):
        p = run(record_args(files="src/a[0].py"), tmp_path)
        assert p.returncode == 2, p.stdout + p.stderr
        assert "files" in p.stderr.lower()
        assert list(tmp_path.glob("*.md")) == []

    def test_quote_in_file_token_is_rejected(self, tmp_path):
        p = run(record_args(files='src/we"ird.py'), tmp_path)
        assert p.returncode == 2, p.stdout + p.stderr
        assert list(tmp_path.glob("*.md")) == []

    def test_newline_in_file_token_is_rejected(self, tmp_path):
        p = run(record_args(files="src/a.py\nfiles: [fake]"), tmp_path)
        assert p.returncode == 2, p.stdout + p.stderr
        assert list(tmp_path.glob("*.md")) == []

    def test_accepted_files_parse_back_exactly(self, tmp_path):
        assert run(record_args(files="src/a.py, src/b.py"), tmp_path).returncode == 0
        line = [ln for ln in (tmp_path / "null-deref-in-ops-executor.md")
                .read_text(encoding="utf-8").splitlines() if ln.startswith("files:")][0]
        assert line == "files: [src/a.py, src/b.py]", line


class TestRetrieval:
    def test_match_returns_zero_and_reports_known_fix(self, tmp_path):
        assert run(record_args(), tmp_path).returncode == 0
        p = run(["search", "AttributeError NoneType items"], tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "null-deref-in-ops-executor" in p.stdout
        assert "extract_json_field" in p.stdout

    def test_no_match_returns_three_so_caller_diagnoses_fresh(self, tmp_path):
        assert run(record_args(), tmp_path).returncode == 0
        p = run(["search", "kubernetes ingress certificate rotation"], tmp_path)
        assert p.returncode == 3, p.stdout + p.stderr
        assert "no match" in p.stdout.lower()

    def test_empty_ledger_returns_three(self, tmp_path):
        p = run(["search", "anything at all"], tmp_path)
        assert p.returncode == 3, p.stdout + p.stderr

    def test_signature_match_ranks_above_incidental_body_match(self, tmp_path):
        assert run(record_args(), tmp_path).returncode == 0
        assert run(record_args(
            slug="flaky-timeout",
            signature="test suite times out on slow machines",
            root_cause="a fixture sleeps instead of polling; mentions items and NoneType",
        ), tmp_path).returncode == 0
        p = run(["search", "AttributeError: 'NoneType' object has no attribute 'items'"],
                tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        first = p.stdout.index("null-deref-in-ops-executor")
        second = p.stdout.index("flaky-timeout")
        assert first < second, "signature hit must outrank an incidental body hit"


class TestPrune:
    def test_live_entry_is_never_pruned(self, tmp_path):
        assert run(record_args(), tmp_path).returncode == 0
        p = run(["prune"], tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "clean" in p.stdout

    def test_stale_entry_is_reported_then_archived(self, tmp_path):
        assert run(record_args(files="src/gone/deleted_module.py"), tmp_path).returncode == 0
        report = run(["prune"], tmp_path)
        assert report.returncode == 1, report.stdout + report.stderr
        assert "null-deref-in-ops-executor.md" in report.stdout
        assert (tmp_path / "null-deref-in-ops-executor.md").exists(), "report must not delete"
        applied = run(["prune", "--apply"], tmp_path)
        assert applied.returncode == 0, applied.stdout + applied.stderr
        assert not (tmp_path / "null-deref-in-ops-executor.md").exists()
        assert (tmp_path / "archive" / "null-deref-in-ops-executor.md").is_file()

    def test_entry_without_files_is_not_pruned(self, tmp_path):
        assert run(record_args(files=""), tmp_path).returncode == 0
        p = run(["prune"], tmp_path)
        assert p.returncode == 0, p.stdout + p.stderr


class TestAgentWiring:
    """The ledger is worthless if no agent reads or writes it."""

    def test_debugger_checks_ledger_before_diagnosing(self):
        text = (REPO / ".claude" / "agents" / "debugger.md").read_text(encoding="utf-8")
        assert "knowledge-ledger.py" in text
        assert "Phase 0" in text

    def test_verifier_records_on_pass(self):
        text = (REPO / ".claude" / "agents" / "verifier.md").read_text(encoding="utf-8")
        assert "knowledge-ledger.py" in text
        assert "--verified" in text

    def test_continuous_learning_owns_the_rubric_reference(self):
        text = (REPO / ".claude" / "skills" / "continuous-learning" / "SKILL.md").read_text(
            encoding="utf-8")
        assert ".claude/knowledge/issues/" in text
        assert "Verifier" in text

    def test_codex_skill_mirror_documents_the_ledger_too(self):
        """`.agents/skills/` is the Codex corpus mirror; substantive skill edits land in both."""
        text = (REPO / ".agents" / "skills" / "continuous-learning" / "SKILL.md").read_text(
            encoding="utf-8")
        assert ".Codex/knowledge/issues/" in text
        assert "knowledge-ledger.py" in text
