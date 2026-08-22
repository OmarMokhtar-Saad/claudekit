"""`ck mcp add` — behavioural proof that the profile's MCP budget binds.

An MCP server's tool schemas are always-on context: configured means paid for,
every session, whether or not a tool is called. These tests drive the real CLI
against the shipped `python` profile (max_servers=3, max_tools=40) and assert
the refusals quote current-vs-limit numbers and write nothing.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROFILES_SRC = os.path.join(REPO_ROOT, ".claude", "profiles")


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    (root / ".claude").mkdir(parents=True)
    shutil.copytree(PROFILES_SRC, root / ".claude" / "profiles")
    return root


def ck(root, *args, profile="python"):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "src"),
               ECC_HOOK_PROFILE=profile)
    return subprocess.run(
        [sys.executable, "-m", "claudekit.cli.main", *args],
        capture_output=True, text=True, cwd=str(root), env=env,
    )


def add(root, name, tools, **kw):
    return ck(root, "mcp", "add", name, "--tools", str(tools),
              "--", "npx", "-y", f"@example/{name}@1.0.0", **kw)


def config(root):
    path = root / ".mcp.json"
    return json.loads(path.read_text()) if path.exists() else {"mcpServers": {}}


def test_first_server_is_registered(project):
    result = add(project, "alpha", 5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert config(project)["mcpServers"]["alpha"] == {
        "command": "npx", "args": ["-y", "@example/alpha@1.0.0"]}
    ledger = json.loads((project / ".claude" / "state" / "mcp-servers.json").read_text())
    assert ledger["servers"]["alpha"]["tools"] == 5
    assert ledger["servers"]["alpha"]["source"] == "declared"


def test_max_servers_is_refused_with_numbers(project):
    """PROOF 3a: the fourth server under python (max_servers=3) is refused."""
    for name in ("alpha", "beta", "gamma"):
        assert add(project, name, 1).returncode == 0
    result = add(project, "delta", 1)
    assert result.returncode == 1, result.stdout
    assert "max_servers=3" in result.stderr
    assert "current 3" in result.stderr
    assert "delta" not in config(project)["mcpServers"]


def test_max_tools_is_refused_with_numbers(project):
    """PROOF 3b: crossing max_tools=40 is refused, current and projected quoted."""
    assert add(project, "alpha", 35).returncode == 0
    result = add(project, "beta", 10)
    assert result.returncode == 1, result.stdout
    assert "max_tools=40" in result.stderr
    assert "current total is 35" in result.stderr
    assert "projected 45" in result.stderr
    assert "beta" not in config(project)["mcpServers"]


def test_refusal_writes_nothing(project):
    assert add(project, "alpha", 35).returncode == 0
    before = (project / ".mcp.json").read_text()
    ledger_before = (project / ".claude" / "state" / "mcp-servers.json").read_text()
    assert add(project, "beta", 10).returncode == 1
    assert (project / ".mcp.json").read_text() == before
    assert (project / ".claude" / "state" / "mcp-servers.json").read_text() == ledger_before


def test_tool_count_is_required(project):
    """No default: a default of zero would make max_tools pass for free."""
    result = ck(project, "mcp", "add", "alpha", "--", "npx", "-y", "@example/a@1.0.0")
    assert result.returncode == 1
    assert "tool count is required" in result.stderr


def test_unlimited_when_the_profile_declares_no_budget(project):
    """standard declares no mcp keys, so the base layer's null (unlimited) wins."""
    for i in range(5):
        assert add(project, f"srv{i}", 50, profile="standard").returncode == 0


def test_a_server_already_in_the_ledger_is_refused(project):
    """A recorded server is not adoptable: there is nothing left to record."""
    assert add(project, "alpha", 1).returncode == 0
    result = add(project, "alpha", 1)
    assert result.returncode == 1
    assert "already registered" in result.stderr


def test_list_reports_usage_against_the_budget(project):
    assert add(project, "alpha", 12).returncode == 0
    result = ck(project, "mcp", "list")
    assert result.returncode == 0, result.stderr
    assert "servers 1/3" in result.stdout
    assert "tools 12/40" in result.stdout


def test_list_shows_the_config_only_servers_the_budget_counts(project):
    """The user's view must not disagree with the enforcer.

    `check_budget` counts servers that exist only in `.mcp.json`; listing only
    our ledger made them invisible, so its refusals looked arbitrary in the
    field. They are listed, with an unknown count -- which is the reason
    max_tools cannot be evaluated while they exist.
    """
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-a": {"command": "x"},
    }}, indent=2) + "\n")
    result = ck(project, "mcp", "list")
    assert result.returncode == 0, result.stderr
    assert "hand-a" in result.stdout
    assert "unknown tools" in result.stdout
    assert "config-only" in result.stdout
    assert "no recorded tool count" in result.stdout


def test_list_names_the_standing_overage_the_budget_will_not_block(project):
    """The budget binds on DELTAS, and `list` has to say so.

    Four config-only servers adopted at 20 tools each leave a project at 4/3
    servers and 80/40 tools with every command exiting 0 -- adoption cannot
    refuse (it adds no schema), `.mcp.json` is Claude Code's file, and `ck
    doctor` has no MCP check. Only the next ADDITION is refused. Printing the
    numbers while staying silent about that invites the reader to assume a
    standing overage is impossible.
    """
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-%s" % c: {"command": "x"} for c in "abcd"}}, indent=2) + "\n")
    for c in "abcd":
        adopted = ck(project, "mcp", "add", "hand-%s" % c, "--tools", "20")
        assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    result = ck(project, "mcp", "list")
    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    assert "servers 4/3" in out
    assert "tools 80/40" in out
    assert "OVER BUDGET" in out
    assert "the next new server is refused" in out
    assert "adopting one already in .mcp.json stays allowed" in out


def test_a_config_only_server_can_be_adopted_and_unblocks_the_budget(project):
    """THE ESCAPE PATH, end to end: refusal -> the printed remedy -> success.

    `.mcp.json` is Claude Code's file and `claude mcp add` is its primary
    writer, so a server with no ledger row is a normal state. Failing closed on
    it is correct; what was not correct is that the remedy the refusal printed
    then died with "already registered", leaving hand-editing the ledger as the
    only exit.
    """
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-a": {"command": "npx", "args": ["-y", "@example/hand-a@1.0.0"]},
    }}, indent=2) + "\n")

    blocked = ck(project, "mcp", "add", "second", "--tools", "1", "--", "echo", "hi")
    assert blocked.returncode == 1, blocked.stdout
    assert "cannot be evaluated" in blocked.stderr
    assert "ck mcp add" in blocked.stderr          # the remedy it prints...

    adopt = ck(project, "mcp", "add", "hand-a", "--tools", "4")   # ...actually works
    assert adopt.returncode == 0, adopt.stdout + adopt.stderr
    ledger = json.loads(
        (project / ".claude" / "state" / "mcp-servers.json").read_text())
    assert ledger["servers"]["hand-a"]["tools"] == 4
    assert ledger["servers"]["hand-a"]["source"] == "adopted"
    # Adoption records a fact; it must not touch Claude Code's file.
    assert config(project)["mcpServers"]["hand-a"] == {
        "command": "npx", "args": ["-y", "@example/hand-a@1.0.0"]}

    after = ck(project, "mcp", "add", "second", "--tools", "1", "--", "echo", "hi")
    assert after.returncode == 0, after.stdout + after.stderr
    assert config(project)["mcpServers"]["second"]["command"] == "echo"


def test_adopting_an_over_budget_server_is_recorded_with_a_warning(project):
    """Adoption adds no schema, so refusing it would only recreate the trap."""
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-a": {"command": "x"},
    }}, indent=2) + "\n")
    result = ck(project, "mcp", "add", "hand-a", "--tools", "99")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "max_tools=40" in result.stdout + result.stderr
    ledger = json.loads(
        (project / ".claude" / "state" / "mcp-servers.json").read_text())
    assert ledger["servers"]["hand-a"]["tools"] == 99
    # ...and the budget still binds for the next genuine addition
    nxt = ck(project, "mcp", "add", "second", "--tools", "1", "--", "echo", "hi")
    assert nxt.returncode == 1, nxt.stdout
    assert "projected 100" in nxt.stderr


def test_adopting_refuses_a_command_that_disagrees_with_the_config(project):
    """Adoption changes no configuration, so it will not silently accept a
    different argv than the one Claude Code has recorded."""
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-a": {"command": "npx", "args": ["-y", "@example/hand-a@1.0.0"]},
    }}, indent=2) + "\n")
    result = ck(project, "mcp", "add", "hand-a", "--tools", "4",
                "--", "echo", "hi")
    assert result.returncode == 1, result.stdout
    assert "changes no configuration" in result.stderr


def test_a_hand_added_server_in_mcp_json_still_counts(project):
    """REGRESSION: the budget must not fail OPEN on servers we did not add.

    `.mcp.json` is Claude Code's file and users edit it by hand. Counting only
    our own ledger made three hand-added servers count as zero and admitted
    three more under max_servers=3.
    """
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-a": {"command": "x"}, "hand-b": {"command": "y"},
        "hand-c": {"command": "z"},
    }}, indent=2) + "\n")
    result = ck(project, "mcp", "add", "fourth", "--tools", "1", "--", "echo", "hi")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "max_servers=3" in result.stderr
    assert "current 3" in result.stderr


def test_an_unbudgeted_server_makes_max_tools_unevaluable(project):
    """Unknown is not zero: refuse with the cause named."""
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "hand-a": {"command": "x"},
    }}, indent=2) + "\n")
    result = ck(project, "mcp", "add", "second", "--tools", "1", "--", "echo", "hi")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot be evaluated" in result.stderr
    assert "hand-a" in result.stderr
    assert "max_tools=40" in result.stderr
