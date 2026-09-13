"""Agent-memory scaffold: installer behaviour and `knowledge-ledger.py distill`.

Behavioural, per CLAUDE.md: these run the real installer and the real script and
assert outcomes, rather than asserting that source text contains a string.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
LEDGER = REPO / ".claude" / "operations" / "scripts" / "knowledge-ledger.py"
# Pin the profile: a result must never depend on a developer's settings.local.json.
ENV = dict(os.environ, ECC_HOOK_PROFILE="minimal")


def _install(dest, mode="--full"):
    """Install into `dest`. `--yes` because install.sh refuses to overwrite an
    existing .claude/ without it, and the idempotence test installs twice."""
    subprocess.run(["git", "init", "-q", "."], cwd=str(dest), check=True)
    proc = subprocess.run(["bash", str(INSTALL), mode, "--yes", "."], cwd=str(dest),
                          capture_output=True, text=True, timeout=300, env=ENV)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Path(dest) / ".claude"


def _declaring(claude):
    out = []
    for f in sorted((claude / "agents").glob("*.md")):
        if any(line.strip() == "memory: project"
               for line in f.read_text(encoding="utf-8").splitlines()[:40]):
            out.append(f.stem)
    return out


def _ledger(cwd, *args):
    return subprocess.run([sys.executable, str(LEDGER), *args], cwd=str(cwd),
                          capture_output=True, text=True, timeout=120,
                          env=dict(ENV, CLAUDEKIT_PROJECT_ROOT=str(cwd)))


def _receipt(root, slug, signature, origin="workflow", status="open"):
    d = root / ".claude" / "knowledge" / "issues"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(
        f'---\nsignature: "{signature}"\nroot_cause: ""\nfix: ""\nfiles: []\n'
        f"date: 2026-09-13\nstatus: {status}\norigin: {origin}\nverified: false\n---\n\n"
        f"# {slug}\n", encoding="utf-8")


class TestInstallerScaffold:
    def test_full_install_creates_a_directory_per_declaring_agent(self, tmp_path):
        claude = _install(tmp_path)
        declaring = _declaring(claude)
        assert declaring, "fixture invalid: no agent declares memory: project"
        for agent in declaring:
            assert (claude / "agent-memory" / agent / "MEMORY.md").is_file(), agent

    def test_reinstall_leaves_an_existing_memory_byte_identical(self, tmp_path):
        """The regression that matters: a project's accumulated memory is not
        clobbered by re-running the installer."""
        claude = _install(tmp_path)
        agent = _declaring(claude)[0]
        memory = claude / "agent-memory" / agent / "MEMORY.md"
        memory.write_text("# real\n\n- [Lesson](x.md) - keep me\n", encoding="utf-8")
        before = hashlib.sha256(memory.read_bytes()).hexdigest()
        _install(tmp_path)
        assert hashlib.sha256(memory.read_bytes()).hexdigest() == before

    def test_the_agent_list_is_derived_not_hardcoded(self, tmp_path):
        """A newly declaring agent must get a directory without touching install.sh.
        A hardcoded list is how the hook allowlist went stale and shipped a project
        where every Edit and Write was blocked."""
        claude = _install(tmp_path)
        (claude / "agents" / "brand-new.md").write_text(
            "---\nname: brand-new\nmemory: project\n---\nbody\n", encoding="utf-8")
        _install(tmp_path)
        assert (claude / "agent-memory" / "brand-new" / "MEMORY.md").is_file()


class TestMemorySurvivesReinstall:
    """The data-loss regression, pinned in both shapes it appeared in.

    Phase 1 originally wrote its stub BEFORE preserve_assets.py ran, so the stub
    occupied the path preservation restores into and a project's real MEMORY.md was
    replaced by an empty one. Moving the block after preservation fixed the plain
    case but NOT the transition case: a manifest written by the buggy build lists
    MEMORY.md as kit-owned, so preservation declined to restore it. Both are pinned
    here because a hand-run proof is what failed to catch this twice.
    """

    REAL = "# planner memory\n\n- [Irreplaceable](x.md) - months of knowledge\n"

    def _seed(self, claude):
        agent = _declaring(claude)[0]
        memory = claude / "agent-memory" / agent / "MEMORY.md"
        memory.write_text(self.REAL, encoding="utf-8")
        return memory

    def test_a_reinstall_does_not_replace_real_memory_with_a_stub(self, tmp_path):
        claude = _install(tmp_path)
        memory = self._seed(claude)
        _install(tmp_path)
        assert memory.read_text(encoding="utf-8") == self.REAL, memory.read_text()

    def test_memory_survives_even_when_the_manifest_calls_it_kit_owned(self, tmp_path):
        """The transition case: simulate a manifest written by the buggy build, which
        recorded the stub as a kit asset. Preservation must still restore the real
        file -- ownership of accumulated memory is decided by path, never by a
        manifest that a previous build got wrong."""
        claude = _install(tmp_path)
        memory = self._seed(claude)
        rel = str(memory.relative_to(claude))
        manifest = claude / ".claudekit-manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        files = data["files"] if isinstance(data, dict) and "files" in data else data
        if isinstance(files, dict):
            files[rel] = files.get(rel, "")
        else:
            files.append(rel)
        manifest.write_text(json.dumps(data), encoding="utf-8")
        _install(tmp_path)
        assert memory.read_text(encoding="utf-8") == self.REAL, memory.read_text()

    def test_the_kit_owned_readme_is_still_installed(self, tmp_path):
        claude = _install(tmp_path)
        assert (claude / "agent-memory" / "README.md").is_file()


class TestDistillRefusals:
    """Every refusal below protects a file that is auto-injected into a system prompt."""

    def _root(self, tmp_path):
        (tmp_path / ".claude" / "hooks").mkdir(parents=True)
        (tmp_path / ".claude" / "hooks" / "reflection.py").write_text(
            (REPO / ".claude" / "hooks" / "reflection.py").read_text(encoding="utf-8"),
            encoding="utf-8")
        return tmp_path

    def test_a_draft_is_written_and_memory_is_untouched(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", "assumed the shell splits words")
        mem = root / ".claude" / "agent-memory" / "planner"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("# planner memory\n", encoding="utf-8")
        before = (mem / "MEMORY.md").read_text(encoding="utf-8")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (mem / "MEMORY.md.draft").is_file()
        assert (mem / "MEMORY.md").read_text(encoding="utf-8") == before

    def test_receipts_are_not_closed_by_distilling(self, tmp_path):
        """Closing at draft time would destroy the source for a discarded draft."""
        root = self._root(tmp_path)
        _receipt(root, "r1", "assumed the shell splits words")
        _ledger(root, "distill", "--agent", "planner")
        text = (root / ".claude" / "knowledge" / "issues" / "r1.md").read_text()
        assert "status: open" in text

    def test_identical_signatures_group_and_differing_ones_do_not(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", "assumed the shell splits words")
        _receipt(root, "r2", "assumed  the shell   splits words")
        # NB: not "tokens" -- reflection.py's _SECRET matches that word literally,
        # so the receipt would be refused (correctly) and this test would not be
        # measuring grouping at all.
        _receipt(root, "r3", "assumed the shell splits arguments")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        draft = (root / ".claude" / "agent-memory" / "planner" / "MEMORY.md.draft"
                 ).read_text(encoding="utf-8")
        assert "2 receipts" in draft, draft
        assert "1 receipt:" in draft, draft

    def test_an_absolute_path_is_refused(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", "failed under /Users/someone/secret/tree")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 4, proc.stdout + proc.stderr
        assert "REFUSED" in proc.stderr

    def test_a_credential_shaped_string_is_refused(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", "token was sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 4, proc.stdout + proc.stderr

    def test_it_fails_closed_when_the_sanitizer_cannot_load(self, tmp_path):
        """An unloadable sanitizer must never read as 'nothing to redact'."""
        root = tmp_path
        (root / ".claude" / "hooks").mkdir(parents=True)
        (root / ".claude" / "hooks" / "reflection.py").write_text(
            "raise SystemExit(1)\n", encoding="utf-8")
        _receipt(root, "r1", "anything at all")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 3, proc.stdout + proc.stderr
        assert "REFUSED" in proc.stderr

    def test_the_sanitizer_import_is_live_not_copied(self, tmp_path):
        """Mutation proof. Tighten reflection.py's rule to match a benign sentinel;
        distill must then refuse it. A COPIED regex passes every other test here."""
        root = self._root(tmp_path)
        refl = root / ".claude" / "hooks" / "reflection.py"
        text = refl.read_text(encoding="utf-8")
        text += "\n_SECRET = __import__('re').compile(r'ZZBENIGNSENTINELZZ')\n"
        refl.write_text(text, encoding="utf-8")
        _receipt(root, "r1", "harmless ZZBENIGNSENTINELZZ marker")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 4, proc.stdout + proc.stderr

    def test_it_routes_to_any_declaring_agent_not_just_the_origin_table(self, tmp_path):
        """`origin` has three values and cannot address seven agents. debugger and
        verifier declare memory but no origin maps to them, so --agent must reach
        them or their memory can never be written."""
        root = self._root(tmp_path)
        (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        for name in ("debugger", "verifier"):
            (root / ".claude" / "agents" / f"{name}.md").write_text(
                f"---\nname: {name}\nmemory: project\n---\nbody\n", encoding="utf-8")
        _receipt(root, "r1", "a lesson for the debugger")
        proc = _ledger(root, "distill", "--agent", "debugger")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (root / ".claude" / "agent-memory" / "debugger"
                / "MEMORY.md.draft").is_file()

    def test_an_agent_that_declares_no_memory_is_refused(self, tmp_path):
        """A typo silently created a directory nothing would ever read."""
        root = self._root(tmp_path)
        (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "agents" / "planner.md").write_text(
            "---\nname: planner\nmemory: project\n---\nbody\n", encoding="utf-8")
        _receipt(root, "r1", "a lesson")
        proc = _ledger(root, "distill", "--agent", "plannr")
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "does not declare" in proc.stderr
        assert not (root / ".claude" / "agent-memory" / "plannr").exists()

    def test_list_agents_reports_the_declaring_set(self, tmp_path):
        root = self._root(tmp_path)
        (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        for name in ("planner", "debugger"):
            (root / ".claude" / "agents" / f"{name}.md").write_text(
                f"---\nname: {name}\nmemory: project\n---\nbody\n", encoding="utf-8")
        (root / ".claude" / "agents" / "nomem.md").write_text(
            "---\nname: nomem\n---\nbody\n", encoding="utf-8")
        out = _ledger(root, "distill", "--list-agents").stdout.split()
        assert sorted(out) == ["debugger", "planner"], out

    # --- clustering (opt-in; affects the DRAFT only) ---

    A = "alpha beta gamma delta"
    B = "beta gamma delta epsilon"
    C = "gamma delta epsilon zeta"

    def test_omitting_similarity_groups_literally(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", "tests mock the database")
        _receipt(root, "r2", "the database tests mock")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        draft = (root / ".claude" / "agent-memory" / "planner"
                 / "MEMORY.md.draft").read_text(encoding="utf-8")
        assert draft.count("1 receipt:") == 2, draft

    def test_reordered_words_are_one_group_when_fuzzing(self, tmp_path):
        """The exact fixture that falsified the retracted claim that
        `--similarity 100` equals literal grouping. These two strings are two
        literal groups and score Jaccard 1.0, so they merge under ANY threshold.
        Pinned with these literal strings on purpose: the divergence depends on the
        tokenizer regex and stop-list, so drift there must re-break this test rather
        than silently resurrect the equivalence."""
        root = self._root(tmp_path)
        _receipt(root, "r1", "tests mock the database")
        _receipt(root, "r2", "the database tests mock")
        proc = _ledger(root, "distill", "--agent", "planner", "--similarity", "99")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        draft = (root / ".claude" / "agent-memory" / "planner"
                 / "MEMORY.md.draft").read_text(encoding="utf-8")
        assert "2 receipts:" in draft, draft

    def test_similarity_100_is_refused(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", "a lesson")
        proc = _ledger(root, "distill", "--agent", "planner", "--similarity", "100")
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "token-set equality is not string equality" in proc.stderr

    def test_chaining_is_bounded_by_complete_linkage(self, tmp_path):
        """A~B and B~C clear the threshold, A~C does not. Under single linkage B
        would drag A and C together. Asserts NON-MEMBERSHIP only -- which of
        {A,B}+{C} or {B,C}+{A} forms is comparison-order dependent and deliberately
        not claimed. Do not tighten this."""
        root = self._root(tmp_path)
        _receipt(root, "r1", self.A)
        _receipt(root, "r2", self.B)
        _receipt(root, "r3", self.C)
        proc = _ledger(root, "distill", "--agent", "planner", "--similarity", "55")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        draft = (root / ".claude" / "agent-memory" / "planner"
                 / "MEMORY.md.draft").read_text(encoding="utf-8")
        for line in draft.splitlines():
            assert not ("alpha" in line and "zeta" in line), (
                "A and C were merged despite A~C below threshold:\n" + draft)
        assert "2 receipts:" in draft, draft

    def test_an_unrelated_signature_is_not_merged(self, tmp_path):
        root = self._root(tmp_path)
        _receipt(root, "r1", self.A)
        _receipt(root, "r2", self.B)
        _receipt(root, "r3", "entirely unrelated wording about printers")
        _ledger(root, "distill", "--agent", "planner", "--similarity", "55")
        draft = (root / ".claude" / "agent-memory" / "planner"
                 / "MEMORY.md.draft").read_text(encoding="utf-8")
        assert "1 receipt:" in draft, draft

    def test_a_merged_group_lists_every_receipt_it_consumed(self, tmp_path):
        """The draft must show its work: a human verifies the grouping rather than
        trusting it, which is half of why fuzzing is acceptable here at all."""
        root = self._root(tmp_path)
        _receipt(root, "r1", self.A)
        _receipt(root, "r2", self.B)
        _ledger(root, "distill", "--agent", "planner", "--similarity", "55")
        draft = (root / ".claude" / "agent-memory" / "planner"
                 / "MEMORY.md.draft").read_text(encoding="utf-8")
        assert "r1" in draft and "r2" in draft, draft

    def test_the_sanitiser_still_refuses_inside_a_fuzzy_group(self, tmp_path):
        """Clustering must not become a way around the refusal."""
        root = self._root(tmp_path)
        _receipt(root, "r1", self.A)
        _receipt(root, "r2", self.B + " under /Users/someone/secret")
        proc = _ledger(root, "distill", "--agent", "planner", "--similarity", "55")
        assert proc.returncode == 4, proc.stdout + proc.stderr

    # --- staleness (lists only) ---

    def test_stale_lists_an_old_unfixed_entry_and_changes_nothing(self, tmp_path):
        root = self._root(tmp_path)
        d = root / ".claude" / "knowledge" / "issues"
        d.mkdir(parents=True, exist_ok=True)
        (d / "old.md").write_text(
            '---\nsignature: "an old one"\ndate: 2020-01-01\nstatus: open\n'
            'origin: workflow\nverified: false\n---\n\n# old\n', encoding="utf-8")
        before = (d / "old.md").read_text(encoding="utf-8")
        proc = _ledger(root, "distill", "--stale", "1")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "old" in proc.stdout, proc.stdout
        assert "Nothing was closed" in proc.stdout
        assert (d / "old.md").read_text(encoding="utf-8") == before

    def test_crossing_the_200_line_cliff_is_refused(self, tmp_path):
        root = self._root(tmp_path)
        mem = root / ".claude" / "agent-memory" / "planner"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("# x\n" * 200, encoding="utf-8")
        _receipt(root, "r1", "one more lesson")
        proc = _ledger(root, "distill", "--agent", "planner")
        assert proc.returncode == 5, proc.stdout + proc.stderr
        assert "truncation cliff" in proc.stderr
