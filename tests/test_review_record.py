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
