"""`ExecutionLock` does not delete the lock file it may not own.

`release()` used to `os.unlink(self.lock_path)` unconditionally. That is what created the
race it appeared to prevent: process B opens the path and blocks on `flock`, A's
`release()` unlinks the file from under it, C creates a fresh path and acquires that --
and B and C now both believe they hold the lock while flocking two different inodes. Two
executors run concurrently against one tree.

The fix is to stop unlinking. Presence of the file means nothing; the `flock` means
everything. Test 3 below is the one that binds: reintroduce the `os.unlink` and it fails.

Windows is out of scope and stays honestly unprotected -- `_HAS_FCNTL` is False there and
the class docstring says so. No `msvcrt` shim was invented for a platform this project
cannot test, which is hard rule 6 applied to a lock.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXECUTOR = REPO / ".claude" / "operations" / "scripts" / "execute-json-ops.py"


def _load_executor():
    """Import the executor by path; its filename is not a valid module name."""
    sys.path.insert(0, str(EXECUTOR.parent))
    try:
        spec = importlib.util.spec_from_file_location("_exec_ops_under_test", EXECUTOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


@pytest.fixture(scope="module")
def executor():
    return _load_executor()


def test_a_second_acquire_fails_while_the_first_is_held(executor, tmp_path):
    if not executor._HAS_FCNTL:
        pytest.skip("no fcntl on this platform; the class documents that it is unprotected")
    path = str(tmp_path / "exec.lock")
    first, second = executor.ExecutionLock(path), executor.ExecutionLock(path)
    assert first.acquire()
    try:
        assert not second.acquire(), "two executors acquired the same lock"
    finally:
        first.release()


def test_the_lock_is_reacquirable_after_release(executor, tmp_path):
    """Not unlinking must not turn the lock into a permanent one."""
    path = str(tmp_path / "exec.lock")
    first, second = executor.ExecutionLock(path), executor.ExecutionLock(path)
    assert first.acquire()
    first.release()
    assert second.acquire(), "release() left the lock unusable"
    second.release()


def test_release_does_not_unlink_the_lock_file(executor, tmp_path):
    """THE mutation-sensitive assertion. Restore the os.unlink and this fails."""
    path = tmp_path / "exec.lock"
    lock = executor.ExecutionLock(str(path))
    assert lock.acquire()
    lock.release()
    assert path.exists(), (
        "release() unlinked the lock file -- that is the race: another process can be "
        "blocked on flock against this inode while a third creates a new one"
    )


def test_the_lock_file_records_the_holder_pid(executor, tmp_path):
    """The file that is no longer deleted has to be worth keeping."""
    path = tmp_path / "exec.lock"
    lock = executor.ExecutionLock(str(path))
    assert lock.acquire()
    lock.release()
    assert path.read_text().strip() == str(os.getpid())


def test_windows_limitation_is_documented_not_implied(executor):
    """Hard rule 6: the docstring must not promise protection that is absent."""
    doc = executor.ExecutionLock.__doc__ or ""
    assert "Windows" in doc and "fcntl" in doc
