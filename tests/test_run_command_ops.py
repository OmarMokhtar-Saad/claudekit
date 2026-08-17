"""Behavioral tests for the run_command operation type (GUARDs 30-34).

Runs the REAL validator and executor via subprocess against throwaway
projects — nothing is asserted about source structure, only outcomes:
what gets APPROVED/REJECTED, what actually executes, what is refused.
"""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCRIPTS = os.path.join(REPO_ROOT, '.claude', 'operations', 'scripts')
VALIDATOR = os.path.join(SCRIPTS, 'validate-config-json.py')
EXECUTOR = os.path.join(SCRIPTS, 'execute-json-ops.py')


def write_config(tmp_path, operations, plan='run-command-test'):
    config_path = tmp_path / 'ops.json'
    config_path.write_text(json.dumps({'plan': plan, 'operations': operations}))
    return str(config_path)


def run_script(script, config_path, cwd, extra_allow=None, args=()):
    env = dict(os.environ)
    env.pop('CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW', None)
    if extra_allow:
        env['CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW'] = extra_allow
    return subprocess.run(
        [sys.executable, script, config_path, *args],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )


def run_op(command, reason='regenerate derived artifact', **extra):
    op = {'type': 'run_command', 'command': command, 'reason': reason}
    op.update(extra)
    return op


# ---------------------------------------------------------------- validator

def test_validator_accepts_allowlisted_command(tmp_path):
    cfg = write_config(tmp_path, [run_op(['pip-compile', 'requirements.in'])])
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 0, result.stdout
    assert 'APPROVED' in result.stdout


def test_validator_rejects_non_allowlisted_command(tmp_path):
    cfg = write_config(tmp_path, [run_op(['echo', 'hi'])])
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 1
    assert 'not an allowlisted command' in result.stdout


def test_validator_rejects_path_executable(tmp_path):
    cfg = write_config(tmp_path, [run_op(['/usr/bin/black', '.'])])
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 1
    assert 'bare basename' in result.stdout


def test_validator_rejects_escaping_arguments(tmp_path):
    for bad_arg in ['../outside.txt', '/etc/passwd']:
        cfg = write_config(tmp_path, [run_op(['black', bad_arg])])
        result = run_script(VALIDATOR, cfg, tmp_path)
        assert result.returncode == 1, bad_arg
        assert 'escapes the project root' in result.stdout


def test_validator_rejects_shell_string_command(tmp_path):
    cfg = write_config(tmp_path, [run_op('black . && rm -rf /')])
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 1


def test_validator_rejects_short_reason(tmp_path):
    cfg = write_config(tmp_path, [run_op(['black', '.'], reason='short')])
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 1
    # Rejected by the schema layer (minLength 10) when jsonschema is installed,
    # by GUARD text otherwise — either way the config must be REJECTED.
    assert 'Reason too short' in result.stdout or 'REJECTED' in result.stdout


def test_validator_caps_run_command_count(tmp_path):
    ops = [run_op(['black', f'file{i}.py']) for i in range(6)]
    cfg = write_config(tmp_path, ops)
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 1
    assert 'Too many run_command operations' in result.stdout


def test_validator_rejects_run_command_before_file_ops(tmp_path):
    target = tmp_path / 'a.txt'
    target.write_text('hello anchor\n')
    ops = [
        run_op(['black', 'a.txt']),
        {'type': 'code_edit', 'path': 'a.txt',
         'edits': [{'find': 'hello anchor', 'replace': 'hi anchor'}]},
    ]
    cfg = write_config(tmp_path, ops)
    result = run_script(VALIDATOR, cfg, tmp_path)
    assert result.returncode == 1
    assert 'GUARD 33' in result.stdout


def test_validator_env_extends_allowlist(tmp_path):
    cfg = write_config(tmp_path, [run_op(['mytool', 'generate'])])
    rejected = run_script(VALIDATOR, cfg, tmp_path)
    assert rejected.returncode == 1
    allowed = run_script(VALIDATOR, cfg, tmp_path, extra_allow='mytool')
    assert allowed.returncode == 0, allowed.stdout


# ----------------------------------------------------------------- executor

def test_executor_dry_run_does_not_execute(tmp_path):
    marker = tmp_path / 'marker.txt'
    cfg = write_config(tmp_path, [run_op(['touch', 'marker.txt'])])
    result = run_script(EXECUTOR, cfg, tmp_path, extra_allow='touch', args=('--dry-run',))
    assert result.returncode == 0, result.stdout
    assert 'DRY RUN' in result.stdout
    assert not marker.exists(), 'dry-run must not execute the command'


def test_executor_runs_allowlisted_command(tmp_path):
    marker = tmp_path / 'marker.txt'
    cfg = write_config(tmp_path, [run_op(['touch', 'marker.txt'])])
    result = run_script(EXECUTOR, cfg, tmp_path, extra_allow='touch')
    assert result.returncode == 0, result.stdout
    assert marker.exists(), 'command should have executed in the project cwd'
    assert '"status": "success"' in result.stdout


def test_executor_blocks_non_allowlisted_by_default(tmp_path):
    cfg = write_config(tmp_path, [run_op(['touch', 'marker.txt'])])
    result = run_script(EXECUTOR, cfg, tmp_path)  # no extra allow
    assert result.returncode == 1
    assert 'not an allowlisted command' in result.stdout
    assert not (tmp_path / 'marker.txt').exists()


def test_executor_propagates_command_failure(tmp_path):
    cfg = write_config(tmp_path, [run_op(['false'])])
    result = run_script(EXECUTOR, cfg, tmp_path, extra_allow='false')
    assert result.returncode == 1
    assert 'exited 1' in result.stdout


def test_executor_blocks_run_command_before_file_ops(tmp_path):
    target = tmp_path / 'a.txt'
    target.write_text('hello anchor\n')
    marker = tmp_path / 'marker.txt'
    ops = [
        run_op(['touch', 'marker.txt']),
        {'type': 'code_edit', 'path': 'a.txt',
         'edits': [{'find': 'hello anchor', 'replace': 'hi anchor'}]},
    ]
    cfg = write_config(tmp_path, ops)
    result = run_script(EXECUTOR, cfg, tmp_path, extra_allow='touch')
    assert result.returncode == 1
    assert 'after all file operations' in result.stdout
    assert not marker.exists(), 'nothing may execute when ordering is violated'
    assert target.read_text() == 'hello anchor\n'


def test_executor_reports_missing_executable(tmp_path):
    cfg = write_config(tmp_path, [run_op(['definitely-not-a-real-tool-xyz'])])
    result = run_script(EXECUTOR, cfg, tmp_path,
                        extra_allow='definitely-not-a-real-tool-xyz')
    assert result.returncode == 1
    assert 'not found on PATH' in result.stdout


def test_mixed_plan_file_ops_then_command(tmp_path):
    """The intended real-world shape: edit source, then regenerate."""
    target = tmp_path / 'requirements.in'
    target.write_text('requests\n')
    ops = [
        {'type': 'code_edit', 'path': 'requirements.in',
         'edits': [{'find': 'requests', 'replace': 'requests>=2.31'}]},
        run_op(['touch', 'requirements.txt'],
               reason='stand-in for pip-compile regeneration'),
    ]
    cfg = write_config(tmp_path, ops)
    valid = run_script(VALIDATOR, cfg, tmp_path, extra_allow='touch')
    assert valid.returncode == 0, valid.stdout
    result = run_script(EXECUTOR, cfg, tmp_path, extra_allow='touch')
    assert result.returncode == 0, result.stdout
    assert target.read_text() == 'requests>=2.31\n'
    assert (tmp_path / 'requirements.txt').exists()
