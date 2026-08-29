"""Behavioral tests for review-record.py — binding a verdict to an ops.json.

Covers the drift gate that stops an edited-after-approval config inheriting its
score, the verdict-quality gate, ops.json resolution across naming conventions,
and the delta output that makes cheap re-review possible.
"""

import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts')
)
RECORD = os.path.join(SCRIPTS_DIR, 'review-record.py')

REVIEW_OK = """Some preamble the model wrote.
=== REVIEW ===
SCORE: 97
DECISION: APPROVED
CRITICAL_MAJOR_COUNT: 0
ISSUES:
- [MINOR] cosmetic wording — Location: x — Fix: y
=== END REVIEW ===
"""


def _run(cwd, *argv, stdin=None):
    return subprocess.run([sys.executable, RECORD] + list(argv), cwd=str(cwd),
                          input=stdin, capture_output=True, text=True, timeout=60)


def _fixture(tmp_path, ops_edits=1, ops_name='ops-demo.json'):
    plans = tmp_path / '.claude' / 'plans'
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / 'plan-demo.md'
    plan.write_text('# Plan: demo\n', encoding='utf-8')
    ops = plans / ops_name
    ops.write_text(json.dumps({
        'plan': 'demo',
        'operations': [{
            'type': 'code_edit', 'path': 'app.py',
            # non-ASCII exercises ensure_ascii normalization
            'reason': 'café — naïve',
            'edits': [{'find': f'a{i}', 'replace': f'b{i}'} for i in range(ops_edits)],
        }],
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    return plan, ops


def _approve(tmp_path, plan, ops, score=97, decision='APPROVED'):
    return _run(tmp_path, 'write', str(plan), str(ops),
                '--score', str(score), '--decision', decision)


class TestRoundHistory:
    """A re-review must not destroy the verdict it replaces.

    Before this, `write` overwrote the record, so a plan reviewed 80 REVISE then
    95 APPROVED left only the 95 on disk -- and the corpus consequently read as a
    100% approval rate in a 90-96 band, which is a strictly misleading summary of
    how review actually goes.
    """

    def _record(self, tmp_path, slug='demo'):  # ops_slug strips the 'ops-' prefix
        path = tmp_path / '.claude' / 'reports' / 'reviews' / f'{slug}.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def test_a_second_verdict_preserves_the_first(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops, 80, 'REVISE').returncode == 0
        assert _approve(tmp_path, plan, ops, 95, 'APPROVED').returncode == 0
        rec = self._record(tmp_path)
        assert rec['score'] == 95 and rec['decision'] == 'APPROVED'
        assert rec['round'] == 2
        assert len(rec['rounds']) == 1
        assert rec['rounds'][0]['score'] == 80
        assert rec['rounds'][0]['decision'] == 'REVISE'
        # The hash is what made the superseded verdict meaningful: it says which
        # artifact was judged, not merely that some earlier round happened.
        assert rec['rounds'][0]['ops_sha256'] == rec['ops_sha256']

    def test_history_accumulates_in_chronological_order(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        for score, decision in ((70, 'REJECTED'), (85, 'CONDITIONAL'), (93, 'APPROVED')):
            assert _approve(tmp_path, plan, ops, score, decision).returncode == 0
        rec = self._record(tmp_path)
        assert rec['round'] == 3
        assert [r['score'] for r in rec['rounds']] == [70, 85]
        assert [r['decision'] for r in rec['rounds']] == ['REJECTED', 'CONDITIONAL']

    def test_a_first_verdict_has_empty_history(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops).returncode == 0
        rec = self._record(tmp_path)
        assert rec['rounds'] == [] and rec['round'] == 1

    def test_a_superseded_round_keeps_its_findings(self, tmp_path):
        # findings is in ROUND_KEYS but was unpinned: dropping it from the tuple
        # left every test green while silently discarding what each superseded
        # verdict actually objected to.
        plan, ops = _fixture(tmp_path)
        r1 = _run(tmp_path, 'write', str(plan), str(ops), '--from-review', '-',
                  stdin="=== REVIEW ===\nSCORE: 80\nDECISION: REVISE\n"
                        "- [MAJOR] the thing is wrong\n=== END REVIEW ===\n")
        assert r1.returncode == 0, r1.stderr
        assert _approve(tmp_path, plan, ops, 95, 'APPROVED').returncode == 0
        prior = self._record(tmp_path)['rounds'][0]
        assert any('the thing is wrong' in f for f in prior['findings'])
        assert prior['recorded_utc']

    def test_the_trail_is_reported_to_the_operator(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops, 80, 'REVISE')
        res = _approve(tmp_path, plan, ops, 95, 'APPROVED')
        assert '80/REVISE' in res.stdout and 'round 2' in res.stdout

    def test_a_corrupt_prior_record_warns_and_still_records(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops, 80, 'REVISE').returncode == 0
        path = tmp_path / '.claude' / 'reports' / 'reviews' / 'demo.json'
        path.write_text('{ truncated', encoding='utf-8')
        res = _approve(tmp_path, plan, ops, 95, 'APPROVED')
        # A corrupt file must not brick approvals for this slug forever...
        assert res.returncode == 0
        # ...but losing history silently is how this defect class started.
        assert 'unreadable' in res.stderr
        assert self._record(tmp_path)['rounds'] == []

    def test_a_prior_record_with_invalid_utf8_does_not_brick_the_slug(self, tmp_path):
        """The corruption class, not the one member of it that came to mind.

        Invalid UTF-8 raises UnicodeDecodeError -- a ValueError, so neither
        JSONDecodeError nor OSError. Catching only those two crashes the write and
        blocks every future approval for this slug, which is the exact failure the
        fallback exists to prevent.
        """
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops, 80, 'REVISE').returncode == 0
        path = tmp_path / '.claude' / 'reports' / 'reviews' / 'demo.json'
        path.write_bytes(b'\xff\xfe{"score": 80}')
        res = _approve(tmp_path, plan, ops, 95, 'APPROVED')
        assert res.returncode == 0, res.stderr
        assert 'Traceback' not in res.stderr
        assert 'unreadable' in res.stderr
        assert self._record(tmp_path)['score'] == 95

    def test_history_is_capped_and_says_so(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        res = None
        for i in range(23):
            res = _approve(tmp_path, plan, ops, 90 + (i % 7), 'APPROVED')
            assert res.returncode == 0
        rec = self._record(tmp_path)
        assert len(rec['rounds']) == 20
        assert rec['round'] == 23
        # "Dropping is announced, never silent" -- asserted, not just claimed.
        assert 'MAX_ROUNDS=20' in res.stderr
        # And the survivors are the NEWEST 20: a `rounds[:MAX_ROUNDS]` slice keeps
        # the oldest instead and permanently discards the round immediately
        # preceding this one, which is the defect this whole change exists to fix.
        assert [r['score'] for r in rec['rounds']] == [90 + (i % 7) for i in range(2, 22)]


    def test_a_valid_json_record_of_the_wrong_shape_does_not_brick_the_slug(self, tmp_path):
        """Corruption is not only unparseable bytes.

        `"rounds": 5` is valid JSON and valid UTF-8, so it clears the parse and
        then fails on list(). If the structural walk sat outside the guard, one
        such file would block every future approval for this slug.
        """
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops, 80, 'REVISE').returncode == 0
        path = tmp_path / '.claude' / 'reports' / 'reviews' / 'demo.json'
        path.write_text(json.dumps({'score': 80, 'rounds': 5}), encoding='utf-8')
        res = _approve(tmp_path, plan, ops, 95, 'APPROVED')
        assert res.returncode == 0, res.stderr
        assert 'Traceback' not in res.stderr
        assert self._record(tmp_path)['score'] == 95

    def test_a_non_object_round_entry_cannot_fail_a_successful_write(self, tmp_path):
        """The trail printer runs AFTER the record is on disk.

        A round entry that is not an object used to reach it and raise, so the
        command exited 1 having already written an approval -- an exit code that
        contradicts the state on disk.
        """
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops, 80, 'REVISE').returncode == 0
        path = tmp_path / '.claude' / 'reports' / 'reviews' / 'demo.json'
        path.write_text(json.dumps({'score': 80, 'decision': 'REVISE',
                                    'rounds': 'APPROVED'}), encoding='utf-8')
        res = _approve(tmp_path, plan, ops, 95, 'APPROVED')
        assert res.returncode == 0, res.stdout + res.stderr
        assert 'Traceback' not in res.stderr

    def test_the_round_number_stays_true_past_the_cap(self, tmp_path):
        """Derived from the prior record's number, not from the capped list.

        Counting len(rounds)+1 makes the number saturate at MAX_ROUNDS+1, so
        review 30 reports itself as 21 -- and rounds-to-clean, the whole reason
        this history exists, quietly stops being a fact.
        """
        plan, ops = _fixture(tmp_path)
        for i in range(24):
            assert _approve(tmp_path, plan, ops, 90, 'APPROVED').returncode == 0
        assert self._record(tmp_path)['round'] == 24

class TestHistoryDoesNotWeakenTheGate:
    """The Safety claim, asserted rather than reasoned about.

    `rounds` is additive, but this file IS the approval machinery, so the gate's
    behaviour is pinned directly after a history-bearing write.
    """

    def test_an_approved_second_round_still_authorises_execution(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops, 80, 'REVISE')
        _approve(tmp_path, plan, ops, 95, 'APPROVED')
        assert _run(tmp_path, 'check', str(plan), str(ops)).returncode == 0

    def test_a_non_approving_latest_verdict_still_refuses(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops, 95, 'APPROVED')
        # An approval followed by a REVISE must NOT be rescued by the history.
        _approve(tmp_path, plan, ops, 60, 'REVISE')
        assert _run(tmp_path, 'check', str(plan), str(ops)).returncode == 4

    def test_drift_is_still_detected_after_a_second_round(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops, 80, 'REVISE')
        _approve(tmp_path, plan, ops, 95, 'APPROVED')
        ops.write_text(ops.read_text(encoding='utf-8').replace('b0', 'b9'),
                       encoding='utf-8')
        assert _run(tmp_path, 'check', str(plan), str(ops)).returncode == 2


class TestOpsResolution:
    def test_resolves_each_naming_convention(self, tmp_path):
        for name in ('ops-demo.json', 'demo.ops.json', 'demo.json'):
            d = tmp_path / name.replace('.', '_')
            plan, ops = _fixture(d, ops_name=name)
            res = _run(d, 'resolve', str(plan))
            assert res.returncode == 0, f"{name}: {res.stderr}"
            assert res.stdout.strip().endswith(name)

    def test_resolves_the_actual_plan_and_refine_naming_form(self, tmp_path):
        """Regression: /plan and /refine emit ${PLAN_FILE%.md}.ops.json -- the stem
        WITH the 'plan-' prefix retained, e.g. 'plan-demo.ops.json'. A resolver that
        strips the prefix before trying any candidate never finds this form, which
        bricks the mainline pipeline (the CRITICAL that motivated review round 2)."""
        plans = tmp_path / '.claude' / 'plans'
        plans.mkdir(parents=True)
        plan = plans / 'plan-demo.md'
        plan.write_text('# Plan: demo\n', encoding='utf-8')
        ops = plans / 'plan-demo.ops.json'
        ops.write_text(json.dumps({'plan': 'demo', 'operations': []}), encoding='utf-8')
        res = _run(tmp_path, 'resolve', str(plan))
        assert res.returncode == 0, res.stderr
        assert res.stdout.strip().endswith('plan-demo.ops.json')

    def test_ambiguous_candidates_are_reported_not_silently_picked(self, tmp_path):
        plans = tmp_path / '.claude' / 'plans'
        plans.mkdir(parents=True)
        plan = plans / 'plan-demo.md'
        plan.write_text('# Plan: demo\n', encoding='utf-8')
        (plans / 'plan-demo.ops.json').write_text('{}', encoding='utf-8')
        (plans / 'demo.json').write_text('{}', encoding='utf-8')
        res = _run(tmp_path, 'resolve', str(plan))
        assert res.returncode == 3
        assert 'AMBIGUOUS' in res.stderr

    def test_unresolvable_fails_loudly(self, tmp_path):
        plans = tmp_path / '.claude' / 'plans'
        plans.mkdir(parents=True)
        plan = plans / 'plan-orphan.md'
        plan.write_text('# Plan\n', encoding='utf-8')
        res = _run(tmp_path, 'resolve', str(plan))
        assert res.returncode == 3
        assert 'NO OPS' in res.stderr


class TestApprovalBinding:
    def test_check_without_record_reports_no_record(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        res = _run(tmp_path, 'check', str(plan), str(ops))
        assert res.returncode == 3 and 'NO RECORD' in res.stderr

    def test_check_passes_on_unmodified_approved_ops(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        assert _approve(tmp_path, plan, ops).returncode == 0
        res = _run(tmp_path, 'check', str(plan), str(ops))
        assert res.returncode == 0, res.stderr
        assert 'APPROVED' in res.stdout and '97' in res.stdout

    def test_drift_after_approval_is_blocking(self, tmp_path):
        """Regression: a config approved at N edits was executed at N+2 edits."""
        plan, ops = _fixture(tmp_path, ops_edits=2)
        _approve(tmp_path, plan, ops)
        cfg = json.loads(ops.read_text(encoding='utf-8'))
        cfg['operations'][0]['edits'].append({'find': 'late', 'replace': 'edit'})
        ops.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        res = _run(tmp_path, 'check', str(plan), str(ops))
        assert res.returncode == 2, 'post-approval drift must block'
        assert 'DRIFT' in res.stderr

    def test_matching_but_unapproved_verdict_is_refused(self, tmp_path):
        """Identity alone must not authorise execution — the score still gates."""
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops, score=45, decision='REVISE')
        res = _run(tmp_path, 'check', str(plan), str(ops))
        assert res.returncode == 4
        assert 'NOT APPROVED' in res.stderr

    def test_approved_but_below_threshold_is_refused(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops, score=88, decision='APPROVED')
        assert _run(tmp_path, 'check', str(plan), str(ops)).returncode == 4


class TestVerdictParsing:
    def test_parses_real_review_block(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        res = _run(tmp_path, 'write', str(plan), str(ops), '--from-review', '-',
                   stdin=REVIEW_OK)
        assert res.returncode == 0, res.stderr
        rec = json.loads((tmp_path / '.claude/reports/reviews/demo.json')
                         .read_text(encoding='utf-8'))
        assert rec['score'] == 97 and rec['decision'] == 'APPROVED'
        assert rec['findings'] and rec['findings'][0].startswith('[MINOR]')

    def test_echoed_template_is_not_a_verdict(self, tmp_path):
        """'SCORE: <integer 0-100>' must never parse as a score of 100."""
        plan, ops = _fixture(tmp_path)
        template = ("=== REVIEW ===\nSCORE: <integer 0-100>\n"
                    "DECISION: APPROVED | CONDITIONAL | REVISE | REJECTED\n"
                    "=== END REVIEW ===\n")
        res = _run(tmp_path, 'write', str(plan), str(ops), '--from-review', '-',
                   stdin=template)
        assert res.returncode == 1
        assert not (tmp_path / '.claude/reports/reviews/demo.json').exists()

    def test_last_block_wins_over_quoted_earlier_one(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        text = ("=== REVIEW ===\nSCORE: 10\nDECISION: REJECTED\n=== END REVIEW ===\n"
                "...revised...\n"
                "=== REVIEW ===\nSCORE: 95\nDECISION: APPROVED\n=== END REVIEW ===\n")
        assert _run(tmp_path, 'write', str(plan), str(ops),
                    '--from-review', '-', stdin=text).returncode == 0
        rec = json.loads((tmp_path / '.claude/reports/reviews/demo.json')
                         .read_text(encoding='utf-8'))
        assert rec['score'] == 95 and rec['decision'] == 'APPROVED'


class TestDeltaOutput:
    def test_diff_empty_when_unchanged(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        _approve(tmp_path, plan, ops)
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert res.returncode == 0 and 'no changes since approval' in res.stdout

    def test_delta_is_a_small_fraction_of_the_artifact(self, tmp_path):
        """The whole design rests on the delta being far cheaper than the file."""
        plan, ops = _fixture(tmp_path, ops_edits=200)
        _approve(tmp_path, plan, ops)
        cfg = json.loads(ops.read_text(encoding='utf-8'))
        cfg['operations'][0]['edits'].append({'find': 'NEW_ANCHOR', 'replace': 'x'})
        ops.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert res.returncode == 0 and 'NEW_ANCHOR' in res.stdout
        assert len(res.stdout) < 0.2 * len(ops.read_text(encoding='utf-8'))

    def test_formatting_only_change_is_not_a_delta(self, tmp_path):
        """Reformatting must not explode the diff, or delta review costs more
        than a full review and the mechanism defeats itself."""
        plan, ops = _fixture(tmp_path, ops_edits=3)
        _approve(tmp_path, plan, ops, score=95)
        cfg = json.loads(ops.read_text(encoding='utf-8'))
        # explicit reorder (top-level AND inside the operation dict) so sort_keys is
        # actually exercised — {'plan','operations'} sorted+reversed round-trips to
        # the original order and would pass vacuously
        op0 = cfg['operations'][0]
        reordered = {
            'operations': [{'edits': op0['edits'], 'path': op0['path'],
                           'reason': op0['reason'], 'type': op0['type']}],
            'plan': cfg['plan'],
        }
        # different indent, ascii escaping AND key order — all three normalizations
        ops.write_text(json.dumps(reordered, indent=8, ensure_ascii=True),
                       encoding='utf-8')
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert res.returncode == 0
        assert 'no changes since approval' in res.stdout
        assert 'formatting-only' in res.stdout
        # bytes still changed, so the gate must still block
        assert _run(tmp_path, 'check', str(plan), str(ops)).returncode == 2

    def test_sweeping_rewrite_demands_full_review(self, tmp_path):
        plan, ops = _fixture(tmp_path, ops_edits=4)
        _approve(tmp_path, plan, ops)
        ops.write_text(json.dumps({
            'plan': 'demo',
            'operations': [{'type': 'file_create', 'path': f'n{i}.py', 'content': 'x'}
                           for i in range(40)],
        }, indent=2), encoding='utf-8')
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert 'FULL REVIEW REQUIRED' in res.stdout

    def test_prior_findings_are_surfaced_without_the_prior_score(self, tmp_path):
        plan, ops = _fixture(tmp_path, ops_edits=3)
        _run(tmp_path, 'write', str(plan), str(ops), '--from-review', '-', stdin=REVIEW_OK)
        cfg = json.loads(ops.read_text(encoding='utf-8'))
        cfg['operations'][0]['edits'].append({'find': 'NEW', 'replace': 'x'})
        ops.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert 'cosmetic wording' in res.stdout, 'prior findings must be shown'
        assert '97' not in res.stdout.split('Delta since')[0], \
            'prior score must not anchor the reviewer'

    def test_small_plan_addition_still_gets_delta_review(self, tmp_path):
        """Regression: a pure ratio ceiling with no floor would force FULL REVIEW
        on exactly the small post-approval fixes this mechanism exists to make cheap."""
        plan, ops = _fixture(tmp_path, ops_edits=4)
        _approve(tmp_path, plan, ops)
        cfg = json.loads(ops.read_text(encoding='utf-8'))
        cfg['operations'][0]['edits'].append({'find': 'ONE_MORE', 'replace': 'x'})
        ops.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert 'FULL REVIEW REQUIRED' not in res.stdout
        assert 'ONE_MORE' in res.stdout

    def test_delta_mode_refused_when_prior_verdict_not_approved(self, tmp_path):
        """Delta review is only sound relative to an APPROVED baseline -- a
        REVISE-level plan's defects live in the very bulk 'do not re-derive' would skip."""
        plan, ops = _fixture(tmp_path, ops_edits=3)
        _approve(tmp_path, plan, ops, score=68, decision='REVISE')
        cfg = json.loads(ops.read_text(encoding='utf-8'))
        cfg['operations'][0]['edits'].append({'find': 'cosmetic', 'replace': 'x'})
        ops.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        res = _run(tmp_path, 'diff', str(plan), str(ops))
        assert 'FULL REVIEW REQUIRED' in res.stdout
        assert 'not approved' in res.stdout

    def test_diff_without_record_reports_no_record(self, tmp_path):
        plan, ops = _fixture(tmp_path)
        assert _run(tmp_path, 'diff', str(plan), str(ops)).returncode == 3


class TestWriteSafety:
    def test_hostile_plan_filename_cannot_make_dotfiles(self, tmp_path):
        """A plan named 'plan-...md' yields slug '..'; record filenames must be
        sanitized so no dot-file (or worse) lands in reports/reviews."""
        plans = tmp_path / '.claude' / 'plans'
        plans.mkdir(parents=True)
        plan = plans / 'plan-...md'
        plan.write_text('# Plan\n', encoding='utf-8')
        ops = plans / 'evil.json'
        ops.write_text(json.dumps({'plan': 'x', 'operations': []}), encoding='utf-8')
        res = _run(tmp_path, 'write', str(plan), str(ops),
                   '--score', '95', '--decision', 'APPROVED')
        assert res.returncode == 0, res.stderr
        reviews = tmp_path / '.claude' / 'reports' / 'reviews'
        names = sorted(p.name for p in reviews.iterdir())
        assert names, 'record must be written somewhere'
        assert all(not n.startswith('.') for n in names), names

    def test_symlinked_reports_dir_refused(self, tmp_path):
        """A symlink planted at .claude/reports must refuse the write — checking
        only the leaf + reviews/ leaves an arbitrary-write primitive one level up."""
        plan, ops = _fixture(tmp_path)
        outside = tmp_path / 'outside-target'
        outside.mkdir()
        (tmp_path / '.claude' / 'reports').symlink_to(outside)
        res = _run(tmp_path, 'write', str(plan), str(ops),
                   '--score', '95', '--decision', 'APPROVED')
        assert res.returncode == 1
        assert 'symlink' in res.stderr
        assert not any(outside.rglob('*.json')), 'nothing may land at the symlink target'

# --- the review loop that never terminates -------------------------------------------

def _record_round(tmp_path, score, decision, ops_name='ops-demo.json'):
    """Record one verdict against the demo fixture and return the completed process."""
    plan = str(tmp_path / '.claude' / 'plans' / 'plan-demo.md')
    ops = str(tmp_path / '.claude' / 'plans' / ops_name)
    return _run(tmp_path, 'write', plan, ops, '--score', str(score),
                '--decision', decision)


def _written_record(tmp_path):
    path = tmp_path / '.claude' / 'reports' / 'reviews' / 'demo.json'
    return json.loads(path.read_text(encoding='utf-8'))


class TestTheLoopTripwire:
    """Three consecutive rejections is the documented ceiling; now it is enforced."""

    def test_three_consecutive_rejections_fire_the_advisory(self, tmp_path):
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 78, 'REVISE')
        result = _record_round(tmp_path, 72, 'REVISE')
        assert 'LOOP TRIPWIRE' in result.stderr, result.stderr
        assert '3 consecutive' in result.stderr

    def test_the_advisory_never_blocks_the_write(self, tmp_path):
        """The load-bearing property: the verdict stays durable on the loop round.

        A tripwire that failed the write would destroy the history that makes loop
        detection possible, on exactly the round where it matters most.
        """
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 78, 'REVISE')
        result = _record_round(tmp_path, 72, 'REVISE')
        assert result.returncode == 0, result.stderr
        record = _written_record(tmp_path)
        assert record['score'] == 72 and record['decision'] == 'REVISE'

    def test_two_rejections_do_not_fire_it(self, tmp_path):
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        result = _record_round(tmp_path, 78, 'REVISE')
        assert 'LOOP TRIPWIRE' not in result.stderr, result.stderr

    def test_an_approval_resets_the_streak(self, tmp_path):
        """Consecutive, not cumulative -- the mutation this test exists to catch.

        Counting cumulatively would fire here on a plan that converged and was
        reopened, which trains people to ignore the message.
        """
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 78, 'REVISE')
        _record_round(tmp_path, 95, 'APPROVED')
        result = _record_round(tmp_path, 81, 'REVISE')
        assert 'LOOP TRIPWIRE' not in result.stderr, result.stderr

    def test_an_approved_below_threshold_does_not_reset_the_streak(self, tmp_path):
        """`write` records APPROVED/85, and `check` still refuses it (exit 4).

        A decision-word-only predicate would read that as an approval and silently
        undercount a live loop. `is_rejecting` is the one predicate for this file.
        """
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 85, 'APPROVED')
        result = _record_round(tmp_path, 81, 'REVISE')
        assert 'LOOP TRIPWIRE' in result.stderr, result.stderr

    def test_conditional_counts_as_non_approving(self, tmp_path):
        """cmd_check refuses execution on CONDITIONAL, so the loop counter must too."""
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 86, 'CONDITIONAL')
        result = _record_round(tmp_path, 84, 'REVISE')
        assert 'LOOP TRIPWIRE' in result.stderr, result.stderr

    def test_a_rising_trail_is_called_non_monotonic(self, tmp_path):
        _fixture(tmp_path)
        _record_round(tmp_path, 72, 'REVISE')
        _record_round(tmp_path, 86, 'CONDITIONAL')
        result = _record_round(tmp_path, 81, 'REVISE')
        assert 'NON-MONOTONIC' in result.stderr, result.stderr

    def test_a_plateau_then_a_fall_is_called_non_monotonic(self, tmp_path):
        """86 -> 86 -> 81: the exact shape the motivating retrospective names.

        `max(scores) > scores[0]` would be False here and suppress the notice, which
        is the bug this case exists to pin.
        """
        _fixture(tmp_path)
        _record_round(tmp_path, 86, 'CONDITIONAL')
        _record_round(tmp_path, 86, 'CONDITIONAL')
        result = _record_round(tmp_path, 81, 'REVISE')
        assert 'LOOP TRIPWIRE' in result.stderr
        assert 'NON-MONOTONIC' in result.stderr, result.stderr

    def test_a_monotonic_decline_is_not_called_non_monotonic(self, tmp_path):
        _fixture(tmp_path)
        _record_round(tmp_path, 86, 'REVISE')
        _record_round(tmp_path, 80, 'REVISE')
        result = _record_round(tmp_path, 72, 'REVISE')
        assert 'LOOP TRIPWIRE' in result.stderr
        assert 'NON-MONOTONIC' not in result.stderr, result.stderr

    def test_the_advisory_is_durable_in_the_record(self, tmp_path):
        """stderr is read by whoever is watching that second; the record outlives them."""
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 78, 'REVISE')
        _record_round(tmp_path, 72, 'REVISE')
        record = _written_record(tmp_path)
        assert 'loop_advisory' in record, sorted(record)
        assert any('LOOP TRIPWIRE' in line for line in record['loop_advisory'])

    def test_an_approving_write_carries_no_advisory(self, tmp_path):
        _fixture(tmp_path)
        _record_round(tmp_path, 79, 'REVISE')
        _record_round(tmp_path, 78, 'REVISE')
        _record_round(tmp_path, 95, 'APPROVED')
        assert 'loop_advisory' not in _written_record(tmp_path)

