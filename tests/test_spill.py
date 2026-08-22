"""Proof 5: spill returns a bounded preview plus a locator that really retrieves,
and the pruner is deterministic and model-free.

"Bounded" and "retrievable" are asserted against real bytes on disk, not against
the shape of the returned dict.
"""
from __future__ import annotations

import ast
import os
import stat
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from claudekit.enforcement import spill as spillmod  # noqa: E402  (module, not the fn)

BIG = "line-%04d: " % 0 + ("x" * 40) + "\n"
PAYLOAD = "".join("line-%04d: %s\n" % (i, "x" * 40) for i in range(500))


def test_under_threshold_is_left_alone(tmp_path):
    """Short output is not spilled: a file read would cost more than the string."""
    result = spillmod.spill("short", str(tmp_path), "s1", threshold=1024)
    assert result["spilled"] is False
    assert result["preview"] == "short"
    assert result["locator"] is None
    assert os.listdir(str(tmp_path)) == []


def test_over_threshold_gives_a_bounded_preview_and_a_working_locator(tmp_path):
    """PROOF 5, the whole contract in one test."""
    directory = str(tmp_path)
    result = spillmod.spill(PAYLOAD, directory, "s1", threshold=1024, preview_bytes=256)

    assert result["spilled"] is True
    # Bounded: preview is the 256-byte head plus a short annotation, nowhere near
    # the ~24 KB original. The +512 is headroom for the annotation, not the body.
    assert len(result["preview"].encode("utf-8")) < 256 + 512
    assert len(result["preview"]) < len(PAYLOAD)
    # Honest: the preview says content was withheld, and how much.
    assert "withheld" in result["preview"]
    assert str(result["bytes"]) in result["preview"]
    assert result["locator"] in result["preview"]
    # Retrievable: the locator returns the ORIGINAL text, byte for byte.
    assert spillmod.retrieve(result["locator"], directory) == PAYLOAD


def test_preview_never_splits_a_codepoint(tmp_path):
    """A truncation that emits half a UTF-8 sequence corrupts the transcript."""
    text = "é" * 5000  # 2 bytes each; every odd cut lands mid-codepoint
    result = spillmod.spill(text, str(tmp_path), "s1", threshold=100, preview_bytes=101)
    result["preview"].encode("utf-8").decode("utf-8")  # must not raise


def test_locator_cannot_escape_the_spill_directory(tmp_path):
    """The locator round-trips through a model, so it is parsed, never interpolated."""
    for bad in ("ck-spill://s1/../../etc/passwd",
                "ck-spill://../s1/" + "a" * 64,
                "file:///etc/passwd",
                "ck-spill://s1/nothex",
                ""):
        with pytest.raises(spillmod.SpillError):
            spillmod.retrieve(bad, str(tmp_path))


def test_tampered_spill_file_is_refused(tmp_path):
    """A spill file edited on disk is a corrupted record, not a cheaper answer."""
    directory = str(tmp_path)
    result = spillmod.spill(PAYLOAD, directory, "s1", threshold=1024)
    with open(result["path"], "a", encoding="utf-8") as fh:
        fh.write("injected\n")
    with pytest.raises(spillmod.SpillError) as excinfo:
        spillmod.retrieve(result["locator"], directory)
    assert "digest" in str(excinfo.value)


def test_missing_spill_file_raises_rather_than_returning_empty(tmp_path):
    directory = str(tmp_path)
    result = spillmod.spill(PAYLOAD, directory, "s1", threshold=1024)
    os.remove(result["path"])
    with pytest.raises(spillmod.SpillError):
        spillmod.retrieve(result["locator"], directory)


# ------------------------------------------------------------------ pruning --

def _rec(rid, size, used, **extra):
    row = {"id": rid, "bytes": size, "last_used": used}
    row.update(extra)
    return row


def test_prune_drops_the_stalest_first():
    records = [_rec("a", 100, 1), _rec("b", 100, 5), _rec("c", 100, 3)]
    kept, dropped = spillmod.prune(records, budget_bytes=200)
    assert [r["id"] for r in kept] == ["b", "c"]
    assert [r["id"] for r in dropped] == ["a"]


def test_prune_is_a_pure_function_of_its_input():
    """Same records in any order -> same result. The id tie-break is what buys this."""
    records = [_rec("a", 100, 1), _rec("b", 100, 1), _rec("c", 100, 1)]
    first = spillmod.prune(list(records), budget_bytes=200)
    second = spillmod.prune(list(reversed(records)), budget_bytes=200)
    assert [r["id"] for r in first[0]] == [r["id"] for r in second[0]]
    assert [r["id"] for r in first[1]] == [r["id"] for r in second[1]]


def test_protected_and_pinned_records_are_never_dropped():
    records = [_rec("keep", 300, 0, pinned=True), _rec("fresh", 100, 9)]
    kept, dropped = spillmod.prune(records, budget_bytes=200)
    assert [r["id"] for r in kept] == ["keep"]
    assert [r["id"] for r in dropped] == ["fresh"]

    kept, dropped = spillmod.prune(
        [_rec("named", 300, 0), _rec("fresh", 100, 9)],
        budget_bytes=200, protect=["named"])
    assert "named" in [r["id"] for r in kept]


def test_prune_rejects_a_malformed_record():
    with pytest.raises(spillmod.SpillError):
        spillmod.prune([{"id": "a", "bytes": 1}], budget_bytes=10)
    with pytest.raises(spillmod.SpillError):
        spillmod.prune([_rec("a", -1, 0)], budget_bytes=10)


def test_pruner_is_model_free_by_construction():
    """The pruner must not be able to make a network or model call.

    Asserted on the module's import list rather than by mocking: the guarantee is
    "no paid call is possible here", and an import list is the checkable form of
    that. ClaudeKit is not a harness and this module is one place that could
    quietly turn it into one.
    """
    source = os.path.join(REPO_ROOT, "src", "claudekit", "enforcement", "spill.py")
    tree = ast.parse(open(source, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    allowed = {"hashlib", "os", "re", "tempfile", "typing", "__future__"}
    assert imported <= allowed, (
        "spill.py imports %s -- outside the model-free stdlib set %s"
        % (sorted(imported - allowed), sorted(allowed)))


def test_measurement_is_separate_from_policy():
    """size_of reads no policy constant; policy is passed in, not baked in.

    Otherwise every future budget change lands as a diff on the counter and the
    two stop being independently reviewable.
    """
    assert spillmod.size_of("abc") == 3
    assert spillmod.size_of("é") == 2
    small = spillmod.spill("x" * 50, "/nonexistent-dir", "s", threshold=1000)
    assert small["spilled"] is False  # no filesystem touched below threshold


def test_a_spill_file_is_readable_only_by_its_owner(tmp_path):
    """0600 on the file, 0700 on the directory -- and the UMASK is forced,
    because the umask is the real mutant.

    Spilled text is the oversized tool output that could not stay inline, so it
    is precisely where a secret ends up; that is the whole reason spilling
    exists. `spill()` used plain `open()`, which takes the process umask, so on
    an ordinary 022 box every spill file was 0644 -- a world-readable copy of
    tool output, created by an optimisation, while `eventlog.append` next door
    already used `os.open(..., 0o600)`. Round-4 review found the asymmetry.

    The umask is forced to 0o022 for the duration and restored after. Without
    that, a developer running with umask 0o077 would get 0600 from the OLD
    `open()` form too, and this test would pass against the exact defect it
    exists to catch -- a vacuous assertion, dressed as a security test.
    """
    old = os.umask(0o022)
    try:
        result = spillmod.spill("s" * 5000, str(tmp_path), "sess",
                                threshold=10, preview_bytes=20)
    finally:
        os.umask(old)
    assert result["spilled"] is True
    mode = stat.S_IMODE(os.stat(result["path"]).st_mode)
    assert mode == 0o600, (
        "spill file %s is mode %o, not 0600 -- spilled tool output is group- or "
        "world-readable on disk" % (result["path"], mode))
    leftovers = [name for name in os.listdir(os.path.dirname(result["path"]))
                 if name.endswith(".tmp")]
    assert not leftovers, (
        "a temp file survived the write: %r. A stale temp is not just litter -- "
        "with a fixed temp name it can make every later spill of the same digest "
        "fail" % leftovers)
    # L2-R5: the DIRECTORY mode was correct but asserted nowhere. The round-5
    # reviewer's mutant dropped BOTH `mode=0o700` from os.makedirs and the file
    # mode, and only the file assertion above flipped -- so under umask 022 the
    # spill directory would silently become 0755 with nothing catching it. The
    # directory asserted here is the one spill() creates itself
    # (<spill_dir>/<session>), so makedirs' mode really applies to it; asserting
    # on tmp_path instead would be vacuous, because makedirs(exist_ok=True)
    # leaves an existing directory's mode untouched.
    spill_directory = os.path.dirname(result["path"])
    dir_mode = stat.S_IMODE(os.stat(spill_directory).st_mode)
    assert dir_mode == 0o700, (
        "spill dir %s is mode %o, not 0700 -- the session directory holding "
        "spilled tool output is group- or world-traversable"
        % (spill_directory, dir_mode))
