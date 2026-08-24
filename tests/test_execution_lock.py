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


def test_a_refused_acquire_does_not_destroy_the_holders_pid(executor, tmp_path):
    """`O_TRUNC` truncated on OPEN, i.e. before the flock that decides ownership.

    So a contender that went on to be REFUSED still emptied the file first, destroying
    the pid in the one situation it exists for. Measured before the fix: A holds and the
    file reads a pid; B is refused; the file reads "". The earlier tests could not see it
    because none of them had a contender.
    """
    if not executor._HAS_FCNTL:
        pytest.skip("no fcntl on this platform; the class documents that it is unprotected")
    path = tmp_path / "exec.lock"
    holder, contender = executor.ExecutionLock(str(path)), executor.ExecutionLock(str(path))
    assert holder.acquire()
    try:
        recorded = path.read_text().strip()
        assert recorded == str(os.getpid())
        assert not contender.acquire()
        assert path.read_text().strip() == recorded, (
            "a refused acquire truncated the lock file and destroyed the holder's pid"
        )
    finally:
        holder.release()


def test_the_lock_file_is_not_world_readable(executor, tmp_path):
    """It persists now, so its mode matters. `os.open` without a mode argument takes
    0o666 & ~umask, which on a permissive umask is world-readable."""
    path = tmp_path / "exec.lock"
    lock = executor.ExecutionLock(str(path))
    assert lock.acquire()
    lock.release()
    assert (path.stat().st_mode & 0o077) == 0, oct(path.stat().st_mode & 0o777)


def test_the_refusal_message_does_not_tell_the_operator_to_delete_the_lock(executor, tmp_path):
    """The shipped message said "remove the lock file if stale". Following it while a
    holder is live lets a third process acquire a FRESH path -- two executors, one tree.
    A leftover file is now the normal post-run state, so an operator sees that advice
    routinely."""
    path = tmp_path / "exec.lock"
    holder = executor.ExecutionLock(str(path))
    assert holder.acquire()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            with executor.ExecutionLock(str(path)):
                pass
        message = str(excinfo.value)
        assert "remove the lock file if stale" not in message
        assert "DO NOT delete the lock file" in message
        assert str(os.getpid()) in message, "the message must name the holding pid"
    finally:
        holder.release()
