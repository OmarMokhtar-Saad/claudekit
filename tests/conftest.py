"""Shared pytest fixtures.

`reflection_env` is the isolation primitive the reflection tests need. Two properties,
both load-bearing:

  * REDIRECTION - `CLAUDEKIT_REFLECTION_DIR` / `CLAUDEKIT_REFLECTION_INBOX` point at a
    per-test directory, so no test can read or write the developer's real ledger under
    the OS temp dir (`reflection.ledger_dir()` falls back there when the variable is
    unset, and that fallback is shared by every session on the host).
  * RESTORATION - the caller's previous values are put back on teardown. Popping them
    instead, as these fixtures used to, mutates process-global state: any test that ran
    later in the same process with an ambient `CLAUDEKIT_REFLECTION_DIR` exported would
    silently retarget the real temp dir, and its result would then depend on whether a
    reflection test happened to run first. That is an order dependence, not a test.

`ECC_HOOK_PROFILE` is forced here too (project convention: a hook result must never
depend on the developer's own session profile).
"""

import os
from contextlib import contextmanager

import pytest


@contextmanager
def scoped_env(**overrides):
    """Set environment variables for the duration of the block, then restore exactly
    what was there before - including absence."""
    previous = {name: os.environ.get(name) for name in overrides}
    try:
        for name, value in overrides.items():
            os.environ[name] = value
        yield dict(overrides)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture()
def reflection_env(tmp_path):
    """Per-test ledger and inbox directories, restored on teardown."""
    overrides = {
        "CLAUDEKIT_REFLECTION_DIR": str(tmp_path / "ledger"),
        "CLAUDEKIT_REFLECTION_INBOX": str(tmp_path / "inbox"),
        "ECC_HOOK_PROFILE": "minimal",
    }
    with scoped_env(**overrides) as active:
        yield active
