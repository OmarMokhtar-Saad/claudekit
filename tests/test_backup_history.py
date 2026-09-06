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

    assert [manifest["plan"] for _, manifest, _ in rows] == ["aa-new-plan", "zz-old-plan"]

def test_order_is_wrong_under_every_listdir_order(restore, tmp_path):
    """Three backups, so no enumeration order is accidentally correct.

    The two-fixture version of this could not do that job. Review mutation M8 removed the
    sort ENTIRELY and the two-backup ordering test still passed, because APFS happened to
    enumerate `aa-new-plan` before `zz-old-plan` -- it only reds a name sort because a name
    sort actively inverts two rows. With three backups whose time order is a rotation of
    both their name order and any stable enumeration order, no accident passes.
    """
    root = tmp_path / "backups"
    _backup(root, "zzz-middle-20260101-000000-000000",
            _manifest("zzz-middle", "2026-06-01T00:00:00+00:00"))
    _backup(root, "aaa-newest-20260101-000000-000001",
            _manifest("aaa-newest", "2026-09-01T00:00:00+00:00"))
    _backup(root, "mmm-oldest-20260101-000000-000002",
            _manifest("mmm-oldest", "2026-01-01T00:00:00+00:00"))

    plans = [manifest["plan"] for _, manifest, _ in restore.load_backups(str(root))]

    assert plans == ["aaa-newest", "zzz-middle", "mmm-oldest"], plans
    assert plans != sorted(plans, reverse=True), "vacuity: name order must differ from time order"


def test_the_name_tiebreak_orders_a_same_timestamp_pair(restore, tmp_path):
    """The documented tie-break, which no test covered: the mutant dropping `row[0]` from
    the sort key survived all 11 original tests."""
    root = tmp_path / "backups"
    same = "2026-05-05T05:05:05+00:00"
    _backup(root, "aaa-plan-20260505-050505-000000", _manifest("aaa-plan", same))
    _backup(root, "zzz-plan-20260505-050505-000001", _manifest("zzz-plan", same))

    plans = [manifest["plan"] for _, manifest, _ in restore.load_backups(str(root))]

    assert plans == ["zzz-plan", "aaa-plan"], (
        "equal timestamps must fall back to reverse name order, got %r" % (plans,))


def test_a_west_of_utc_offset_is_ordered_by_the_instant_not_the_string(restore, tmp_path):
    """`02:00-08:00` is 10:00Z -- an hour NEWER than `09:00+00:00`, and a string compare
    puts it older. The producer only ever writes `+00:00`, so this is the coupling the
    change exists to remove rather than a live defect; parsing is what removes it."""
    root = tmp_path / "backups"
    _backup(root, "west-20260101-020000-000000",
            _manifest("west", "2026-01-01T02:00:00-08:00"))
    _backup(root, "utc-20260101-090000-000000",
            _manifest("utc", "2026-01-01T09:00:00+00:00"))

    plans = [manifest["plan"] for _, manifest, _ in restore.load_backups(str(root))]

    assert plans == ["west", "utc"], plans


def test_a_naive_timestamp_is_read_as_utc_and_still_orders(restore, tmp_path):
    """A naive stamp must not raise on comparison against an aware one."""
    root = tmp_path / "backups"
    _backup(root, "naive-20260101-120000-000000", _manifest("naive", "2026-01-01T12:00:00"))
    _backup(root, "aware-20260101-090000-000000",
            _manifest("aware", "2026-01-01T09:00:00+00:00"))

    plans = [manifest["plan"] for _, manifest, _ in restore.load_backups(str(root))]

    assert plans == ["naive", "aware"], plans


@pytest.mark.parametrize("timestamp", [None, 1234567890, "not-a-date", ""])
def test_an_unusable_timestamp_sorts_last_without_raising(restore, tmp_path, timestamp):
    root = tmp_path / "backups"
    _backup(root, "dated-20260101-090000-000000",
            _manifest("dated", "2026-01-01T09:00:00+00:00"))
    _backup(root, "zzz-undated-20260101-120000-000000",
            {"plan": "zzz-undated", "timestamp": timestamp, "files": []})

    plans = [manifest["plan"] for _, manifest, _ in restore.load_backups(str(root))]

    assert plans == ["dated", "zzz-undated"], plans


@pytest.mark.parametrize("files_value", [None, 3, "a.py", {"a": 1}])
def test_a_non_list_files_field_does_not_crash_the_listing(tmp_path, files_value):
    """Regression: `{"files": null}` is valid JSON in a valid object, and `.get('files', [])`
    returns None because the key IS present. The first version of this change called len()
    on it, raised TypeError, exited 1, and printed only the rows sorting ABOVE it -- worse
    than the implementation it replaced, which printed all three as one-line errors."""
    root = tmp_path / "backups"
    _backup(root, "bad-20260101-120000-000000",
            {"plan": "bad", "timestamp": "2026-01-01T12:00:00+00:00", "files": files_value})
    _backup(root, "aaa-good-20260101-110000-000000",
            _manifest("aaa-good", "2026-01-01T11:00:00+00:00"))

    result = _run(["--list", "--backup-dir", str(root)], cwd=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    # The row sorting BELOW the malformed one must still be reachable.
    assert "aaa-good" in result.stdout, result.stdout
    assert "0 modified" in result.stdout


def test_the_concrete_error_reaches_the_text_listing(tmp_path):
    """A generic sentence keeps the row and throws away what makes it actionable."""
    root = tmp_path / "backups"
    _backup(root, "broken-20260101-120000-000000", None)

    result = _run(["--list", "--backup-dir", str(root)], cwd=tmp_path)

    assert "Error reading manifest: JSONDecodeError" in result.stdout, result.stdout
    assert "line 1 column 3" in result.stdout, (
        "the parser's own position must survive: %s" % result.stdout)


def test_a_manifest_that_is_a_json_list_names_its_type(tmp_path):
    root = tmp_path / "backups"
    directory = root / "listy-20260101-120000-000000"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text("[1, 2]", encoding="utf-8")

    result = _run(["--list", "--backup-dir", str(root)], cwd=tmp_path)

    assert "manifest is list, not an object" in result.stdout, result.stdout


def test_json_carries_the_error_string_for_an_unreadable_row(tmp_path):
    root = tmp_path / "backups"
    _backup(root, "broken-20260101-120000-000000", None)

    result = _run(["--list", "--json", "--backup-dir", str(root)], cwd=tmp_path)

    rows = json.loads(result.stdout)
    assert rows[0]["readable"] is False
    assert "JSONDecodeError" in rows[0]["error"]


def test_json_without_list_is_refused_rather_than_silently_inert(tmp_path):
    """It used to fall through to `--backup required`, which names the wrong flag."""
    result = _run(["--json"], cwd=tmp_path)

    assert result.returncode == 1
    assert "--json applies to --list" in result.stdout, result.stdout



def test_an_unparseable_manifest_is_listed_not_dropped(restore, tmp_path):
    """A broken manifest is still a backup that exists, and hiding it hides the repair."""
    root = tmp_path / "backups"
    _backup(root, "good-20260905-120000-000000", _manifest("good", "2026-09-05T12:00:00+00:00"))
    _backup(root, "broken-20260905-130000-000000", None)

    rows = restore.load_backups(str(root))

    assert len(rows) == 2
    broken = [(m, e) for path, m, e in rows if Path(path).name.startswith("broken")]
    assert broken[0][0] is None
    assert "JSONDecodeError" in broken[0][1], (
        "the concrete exception must survive to the caller: %r" % (broken[0][1],))
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


@pytest.mark.parametrize("files_value", [None, 3, "a.py", {"a": 1}])
def test_json_never_hands_a_consumer_a_non_list_file_field(tmp_path, files_value):
    """`--json` exists for machine consumers, which is where a wrong TYPE does the most
    damage. The text branch was hardened for this and the JSON branch was not: it emitted
    the raw value with `readable: true, error: null`, so `len()` raised the same TypeError
    the text fix was filed for -- and `"files": "a.py"` did not raise at all, it reported
    four files."""
    root = tmp_path / "backups"
    _backup(root, "bad-20260101-120000-000000",
            {"plan": "bad", "timestamp": "2026-01-01T12:00:00+00:00",
             "files": files_value, "created_files": files_value})

    result = _run(["--list", "--json", "--backup-dir", str(root)], cwd=tmp_path)

    row = json.loads(result.stdout)[0]
    assert isinstance(row["files"], list), row
    assert isinstance(row["created_files"], list), row
    assert row["files"] == [] and row["created_files"] == []
    # Silently substituting [] would be its own lie; the row must say what it dropped.
    assert row["error"] and "not a list" in row["error"], row


def test_a_well_formed_manifest_still_reports_no_error(tmp_path):
    """Vacuity guard for the above: `error` must stay None in the ordinary case."""
    root = tmp_path / "backups"
    _backup(root, "good-20260101-120000-000000",
            _manifest("good", "2026-01-01T12:00:00+00:00", files=["a.py"], created=["b.py"]))

    result = _run(["--list", "--json", "--backup-dir", str(root)], cwd=tmp_path)

    row = json.loads(result.stdout)[0]
    assert row["error"] is None, row
    assert row["files"] == ["a.py"] and row["created_files"] == ["b.py"]


def test_list_still_needs_no_backup_argument_and_restore_still_does(tmp_path):
    """The `--list` short-circuit must not have swallowed the `--backup` requirement."""
    result = _run([], cwd=tmp_path)

    assert result.returncode == 1
    assert "--backup required" in result.stdout
