"""`restore-backup.py --list` orders backups by time, and reports what the manifest holds.

`list_backups` sorted directory names in reverse under a comment asserting that a
lexicographic sort over `<plan>-<YYYYmmdd>-<HHMMSS>-<micros>` is a chronological one. It is
not -- that form sorts by PLAN SLUG first and only then by time, so name order is
chronological only within a single plan. On this repo's 101 real backups the first row
`--list` printed under the banner "most recent first" was over six hours older than the
newest backup. The cost is not cosmetic: `--list` is how a person finds the backup to
restore, and it was pointing at the alphabetically-last plan.

`test_newest_first_is_by_time_not_by_name` is the one that binds -- restore the
`sorted(backups, reverse=True)` body and it fails. The fixtures deliberately give the
OLDER backup the alphabetically-later slug, because a fixture whose name order and time
order agree cannot tell the two implementations apart.

Every case builds its own backup tree under `tmp_path`. Nothing here reads or writes the
repo's real `backups/`.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".claude" / "operations" / "scripts" / "restore-backup.py"


def _load_module():
    """Import the script by path; `restore-backup` is not a valid module name."""
    spec = importlib.util.spec_from_file_location("_restore_backup_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def restore():
    return _load_module()


def _backup(root, name, manifest):
    """Create one backup directory. `manifest` of None writes unparseable bytes."""
    directory = root / name
    directory.mkdir(parents=True)
    target = directory / "manifest.json"
    if manifest is None:
        target.write_text("{ not json", encoding="utf-8")
    else:
        target.write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def _manifest(plan, timestamp, files=("a.py",), created=(), post_state=True):
    return {
        "plan": plan,
        "timestamp": timestamp,
        "files": list(files),
        "created_files": list(created),
        "post_state": post_state,
    }


@pytest.fixture
def two_backups(tmp_path):
    """Name order and time order DISAGREE: the `zz-` slug is the older run.

    This is the real shape from the bug -- `reflection-...` sorted above a
    `claude-md-...` backup six hours newer -- reduced to two rows.
    """
    root = tmp_path / "backups"
    _backup(root, "zz-old-plan-20260101-090000-000001",
            _manifest("zz-old-plan", "2026-01-01T09:00:00+00:00"))
    _backup(root, "aa-new-plan-20260905-175126-628683",
            _manifest("aa-new-plan", "2026-09-05T17:51:26+00:00"))
    return root


def test_newest_first_is_by_time_not_by_name(restore, two_backups):
    """The binding test: name order would put `zz-old-plan` first."""
    ordered = [Path(p).name for p in restore.list_backups(str(two_backups))]

    assert ordered[0].startswith("aa-new-plan"), (
        "list_backups returned %r; the newest backup by manifest timestamp is the "
        "aa-new-plan row, and only a name sort puts zz-old-plan first" % (ordered,))
    assert ordered == sorted(ordered), (
        "vacuity guard: these two fixtures must disagree on name order vs time order, "
        "or this test cannot distinguish the two implementations")


def test_load_backups_pairs_each_path_with_its_manifest(restore, two_backups):
    rows = restore.load_backups(str(two_backups))

    assert [manifest["plan"] for _, manifest in rows] == ["aa-new-plan", "zz-old-plan"]


def test_an_unparseable_manifest_is_listed_not_dropped(restore, tmp_path):
    """A broken manifest is still a backup that exists, and hiding it hides the repair."""
    root = tmp_path / "backups"
    _backup(root, "good-20260905-120000-000000", _manifest("good", "2026-09-05T12:00:00+00:00"))
    _backup(root, "broken-20260905-130000-000000", None)

    rows = restore.load_backups(str(root))

    assert len(rows) == 2
    broken = [m for path, m in rows if Path(path).name.startswith("broken")]
    assert broken == [None]
    # Undatable sorts LAST: it must never be offered as "the latest backup".
    assert Path(rows[0][0]).name.startswith("good")


def test_a_directory_without_a_manifest_is_not_a_backup(restore, tmp_path):
    root = tmp_path / "backups"
    _backup(root, "real-20260905-120000-000000", _manifest("real", "2026-09-05T12:00:00+00:00"))
    (root / "stray-directory").mkdir()

    assert len(restore.load_backups(str(root))) == 1


def test_missing_backup_dir_is_empty_not_an_error(restore, tmp_path):
    assert restore.load_backups(str(tmp_path / "nope")) == []


def _run(args, cwd):
    return subprocess.run([sys.executable, str(SCRIPT)] + args,
                          cwd=str(cwd), capture_output=True, text=True, timeout=60)


def test_list_reports_plan_counts_and_completion(two_backups, tmp_path):
    result = _run(["--list", "--backup-dir", str(two_backups)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Plan:      aa-new-plan" in result.stdout
    assert "1 modified, 0 created" in result.stdout
    assert "Complete:  yes" in result.stdout
    assert result.stdout.index("aa-new-plan") < result.stdout.index("zz-old-plan")


def test_an_unstamped_post_state_reads_as_incomplete(tmp_path):
    """`post_state` is stamped only after the executor finishes; absent means it died."""
    root = tmp_path / "backups"
    _backup(root, "died-20260905-120000-000000",
            {"plan": "died", "timestamp": "2026-09-05T12:00:00+00:00", "files": ["a.py"]})

    result = _run(["--list", "--backup-dir", str(root)], cwd=tmp_path)

    assert "Complete:  no" in result.stdout


def test_list_json_is_parseable_and_carries_the_manifest_fields(two_backups, tmp_path):
    result = _run(["--list", "--json", "--backup-dir", str(two_backups)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)  # no banner may precede it, or this raises

    assert [row["plan"] for row in rows] == ["aa-new-plan", "zz-old-plan"]
    assert rows[0]["files"] == ["a.py"]
    assert rows[0]["created_files"] == []
    assert rows[0]["post_state"] is True
    assert rows[0]["readable"] is True
    assert rows[0]["backup"].startswith("aa-new-plan")


def test_list_json_marks_an_unreadable_row_rather_than_omitting_it(tmp_path):
    root = tmp_path / "backups"
    _backup(root, "broken-20260905-130000-000000", None)

    result = _run(["--list", "--json", "--backup-dir", str(root)], cwd=tmp_path)

    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["readable"] is False
    assert rows[0]["plan"] is None


def test_list_json_on_an_empty_tree_is_an_empty_array(tmp_path):
    result = _run(["--list", "--json", "--backup-dir", str(tmp_path / "nope")], cwd=tmp_path)

    assert json.loads(result.stdout) == []


def test_list_still_needs_no_backup_argument_and_restore_still_does(tmp_path):
    """The `--list` short-circuit must not have swallowed the `--backup` requirement."""
    result = _run([], cwd=tmp_path)

    assert result.returncode == 1
    assert "--backup required" in result.stdout
