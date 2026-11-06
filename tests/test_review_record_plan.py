"""Behavioral tests for review-record.py plan-keyed records (plan-write / plan-check)."""

import json
import os
import subprocess
import sys

RECORD = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '.claude', 'operations', 'scripts', 'review-record.py'))

REVIEW_OK = """=== REVIEW ===
SCORE: 97
DECISION: APPROVED
CRITICAL_MAJOR_COUNT: 0
ISSUES:
- [MINOR] cosmetic wording — Location: x — Fix: y
=== END REVIEW ===
"""

PLAN_BODY = "# Plan: demo\n- **Files:** `app.py`, `src/pkg/*.py`\n- **Tier:** 3\n"


def _run(cwd, *argv, stdin=None):
    return subprocess.run([sys.executable, RECORD, *argv], cwd=str(cwd), input=stdin,
                          capture_output=True, text=True, timeout=60)


def _plan(root, body=PLAN_BODY):
    plans = root / '.claude' / 'plans'
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / 'plan-demo.md'
    plan.write_text(body, encoding='utf-8')
    return plan


def _approve(root, plan, score=95):
    return _run(root, 'plan-write', str(plan), '--score', str(score),
                '--decision', 'APPROVED', '--owner-approved')


def test_record_and_check(tmp_path):
    plan = _plan(tmp_path)
    assert _approve(tmp_path, plan).returncode == 0
    r = _run(tmp_path, 'plan-check', str(plan), '--path', 'app.py')
    assert r.returncode == 0, r.stderr
    rec = json.loads(next((tmp_path / '.claude/reports/reviews').glob('*.plan.json'))
                     .read_text())
    assert rec['files'] == ['app.py', 'src/pkg/*.py'] and rec['decision'] == 'APPROVED'


def test_glob_match_and_miss(tmp_path):
    plan = _plan(tmp_path)
    _approve(tmp_path, plan)
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'src/pkg/mod.py').returncode == 0
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'other.py').returncode == 4


def test_drift_blocks(tmp_path):
    plan = _plan(tmp_path)
    _approve(tmp_path, plan)
    plan.write_text(PLAN_BODY + "extra\n", encoding='utf-8')
    assert _run(tmp_path, 'plan-check', str(plan)).returncode == 2


def test_missing_record(tmp_path):
    plan = _plan(tmp_path)
    assert _run(tmp_path, 'plan-check', str(plan)).returncode == 3


def test_non_authorising_verdicts(tmp_path):
    plan = _plan(tmp_path)
    r = _run(tmp_path, 'plan-write', str(plan), '--score', '70', '--decision', 'REVISE')
    assert r.returncode == 0
    assert _run(tmp_path, 'plan-check', str(plan)).returncode == 4
    _approve(tmp_path, plan, score=80)
    assert _run(tmp_path, 'plan-check', str(plan)).returncode == 4


def test_bare_approval_refused(tmp_path):
    plan = _plan(tmp_path)
    r = _run(tmp_path, 'plan-write', str(plan), '--score', '95', '--decision', 'APPROVED')
    assert r.returncode == 7


def test_bare_glob_rejected(tmp_path):
    for glob in ('*', '**', '**/*'):
        plan = _plan(tmp_path, "# P\n- **Files:** `%s`\n" % glob)
        assert _approve(tmp_path, plan).returncode == 8


def test_from_review_binds_parsed_block(tmp_path):
    plan = _plan(tmp_path)
    r = _run(tmp_path, 'plan-write', str(plan), '--from-review', '-', stdin=REVIEW_OK)
    assert r.returncode == 0, r.stderr
    assert _run(tmp_path, 'plan-check', str(plan)).returncode == 0


def test_worktree_uses_main_records(tmp_path):
    main = tmp_path / 'main'
    main.mkdir()

    def git(*a, cwd=main):
        return subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                              cwd=str(cwd), capture_output=True, text=True, check=True)

    git('init', '-q')
    (main / '.claude').mkdir()
    (main / 'f').write_text('x')
    git('add', 'f')
    git('commit', '-qm', 'i')
    wt = tmp_path / 'wt'
    git('worktree', 'add', '-q', str(wt))
    plan = _plan(wt)
    assert _approve(wt, plan).returncode == 0
    assert list((main / '.claude/reports/reviews').glob('*.plan.json'))
    assert _run(wt, 'plan-check', str(plan)).returncode == 0


def test_reviewer_role_is_recorded_and_rounds_accumulate(tmp_path):
    plan = _plan(tmp_path)
    assert _run(tmp_path, 'plan-write', str(plan), '--score', '60', '--decision', 'REVISE',
                '--reviewer-role', 'reviewer', '--owner-approved').returncode == 0
    assert _approve(tmp_path, plan).returncode == 0
    rec = json.loads((tmp_path / '.claude' / 'reports' / 'reviews'
                      / 'demo.plan.json').read_text(encoding='utf-8'))
    assert rec['round'] == 2 and rec['rounds'][0]['decision'] == 'REVISE'



def _dplan(root, files):
    return _plan(root, "# P\n- **Files:** %s\n- **Tier:** 3\n" % files)


def _load_recorder():
    import importlib.util
    spec = importlib.util.spec_from_file_location('review_record_mod', RECORD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_delete_marker_parsing():
    rr = _load_recorder()
    text = "Files:\n  `a.py` (delete)\n  `b.py`\n  c.py (DELETE), d.py\n"
    assert rr.parse_plan_files(text) == ['a.py', 'b.py', 'c.py', 'd.py']
    assert rr.parse_plan_deletions(text) == ['a.py', 'c.py']


def test_delete_cap_and_glob_refused(tmp_path):
    four = ' '.join('`f%d.py` (delete)' % i for i in range(4))
    assert _approve(tmp_path, _dplan(tmp_path, four)).returncode == 8
    three = ' '.join('`f%d.py` (delete)' % i for i in range(3))
    assert _approve(tmp_path, _dplan(tmp_path, three)).returncode == 0
    assert _approve(tmp_path, _dplan(tmp_path, '`src/*.py` (delete)')).returncode == 8


def test_plan_check_delete(tmp_path):
    plan = _dplan(tmp_path, '`gone.py` (delete) `keep.py`')
    assert _approve(tmp_path, plan).returncode == 0
    ok = _run(tmp_path, 'plan-check', str(plan), '--path', 'gone.py', '--delete')
    assert ok.returncode == 0, ok.stderr
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'keep.py', '--delete').returncode == 4
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'other.py', '--delete').returncode == 4
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'keep.py').returncode == 0
    plan.write_text(plan.read_text() + '\nedit\n')
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'gone.py', '--delete').returncode == 2


def test_unmarked_record_still_authorises_path(tmp_path):
    plan = _plan(tmp_path)
    assert _approve(tmp_path, plan).returncode == 0
    assert _run(tmp_path, 'plan-check', str(plan), '--path', 'app.py').returncode == 0
