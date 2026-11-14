"""Behavioural tests for the decision ledger (claudekit.decisions / `ck decide`)."""

import pytest

from claudekit import decisions as dec


def _add(store, title="Keep Redis", rule="Cache stays on Redis", scope="project", **kw):
    return dec.add(store, scope, title, rule, "we agreed: Redis only", today="2026-11-01", **kw)


def test_add_and_load(tmp_path):
    p = _add(tmp_path, guard_paths=["src/cache/**"], guard_keywords=["memcached"])
    assert p.name == "D-001-keep-redis.md"
    r = dec.load_store(tmp_path)[0]
    assert r["status"] == "active" and r["guard_paths"] == ["src/cache/**"]
    assert dec.next_id(tmp_path, "project") == "D-002"


def test_global_prefix(tmp_path):
    assert _add(tmp_path, scope="global").name.startswith("G-001-")


def test_scope_required_and_quote_required(tmp_path):
    with pytest.raises(dec.DecisionError, match="global or this project"):
        dec.add(tmp_path, "", "t", "r", "q")
    with pytest.raises(dec.DecisionError, match="owner quote"):
        dec.add(tmp_path, "project", "t", "r", "  ")


def test_duplicate_refused(tmp_path):
    _add(tmp_path)
    with pytest.raises(dec.DecisionError, match="duplicate of D-001"):
        _add(tmp_path, title="Other title", rule="cache stays on redis!")


def test_supersede_chain_links_both_ways(tmp_path):
    _add(tmp_path)
    new = dec.supersede(tmp_path, "D-001", "Use Valkey", "Cache moves to Valkey",
                        "owner: switch to Valkey", "licence change", today="2026-11-05")
    rules = {r["id"]: r for r in dec.load_store(tmp_path)}
    assert rules["D-001"]["status"] == "superseded" and rules["D-001"]["superseded_by"] == "D-002"
    assert rules["D-002"]["supersedes"] == ["D-001"] and new.name.startswith("D-002")
    assert "superseded by D-002: licence change" in rules["D-001"]["body"]
    dec.write_index(tmp_path)
    assert dec.check(tmp_path)["errors"] == []


def test_supersede_needs_reason(tmp_path):
    _add(tmp_path)
    with pytest.raises(dec.DecisionError, match="reason"):
        dec.supersede(tmp_path, "D-001", "t", "r", "q", " ")


def test_match_order_and_filters(tmp_path):
    proj, glob = tmp_path / "p", tmp_path / "g"
    dec.add(proj, "project", "Kw rule", "kw", "q", guard_keywords=["redis"], today="2026-11-03")
    dec.add(proj, "project", "Path rule", "path", "q", guard_paths=["src/**/cache.py"],
            today="2026-11-01")
    dec.add(glob, "global", "Global kw", "gk", "q", guard_keywords=["Redis"], today="2026-11-04")
    dec.add(proj, "project", "Dropped", "d", "q", guard_keywords=["redis"], today="2026-11-05")
    dec.drop(proj, "D-003", "obsolete")
    hits = dec.match(dec.load_store(proj), dec.load_store(glob),
                     path="src/a/b/cache.py", text="should we use REDIS here")
    assert [h["id"] for h in hits] == ["D-002", "D-001", "G-001"]
    assert dec.match(dec.load_store(proj), [], text="redisx") == []  # whole word only
    assert len(dec.match(dec.load_store(proj), dec.load_store(glob),
                         text="redis", max_n=1)) == 1


def test_glob_double_star(tmp_path):
    r = {"guard_paths": ["a/**/c.py", "docs/**"]}
    assert dec.path_hit(r, "a/c.py") and dec.path_hit(r, "a/b/x/c.py")
    assert dec.path_hit(r, "docs/x/y.md") and not dec.path_hit(r, "b/c.py")


def test_check_credential_fails_directive_only_warns(tmp_path):
    _add(tmp_path, rule="Never touch /Users/omar/secret dir")
    dec.write_index(tmp_path)
    res = dec.check(tmp_path)
    assert res["errors"] == []
    bad = tmp_path / "D-002-leak.md"
    bad.write_text(bad_text("D-002", "token sk-ant-api03-AbCdEf0123456789xyzXYZ0123456789abcd"))
    dec.write_index(tmp_path)
    assert any("credential" in e for e in dec.check(tmp_path)["errors"])


def bad_text(rid, body):
    return (f"---\nid: {rid}\ntitle: leak\nscope: project\nstatus: active\nagreed: 2026-11-01\n"
            f"supersedes: []\nsuperseded_by:\napplies: [plan]\nguard_paths: []\n"
            f"guard_keywords: []\n---\n## Rule\n{body}\n\n## Owner words\n> q\n")


def test_check_broken_links_and_stale_index(tmp_path):
    _add(tmp_path)
    dec.write_index(tmp_path)
    p = next(tmp_path.glob("D-001-*.md"))
    p.write_text(p.read_text().replace("supersedes: []", "supersedes: [D-009]"))
    errs = dec.check(tmp_path)["errors"]
    assert any("unknown D-009" in e for e in errs)
    _add(tmp_path, title="Second", rule="Another rule")
    assert any("INDEX.md" in e for e in dec.check(tmp_path)["errors"])


def test_cli_round_trip(tmp_path, capsys, monkeypatch):
    from claudekit.cli import main as m

    store, g = str(tmp_path / "p"), str(tmp_path / "g")
    base = ["decide", "--store", store, "--global-store", g]
    monkeypatch.setattr("sys.argv", ["ck", *base, "add", "--scope", "project", "--title",
                                     "Keep Redis", "--rule", "Redis only", "--quote", "q",
                                     "--keywords", "redis"])
    assert m.main() == 0
    monkeypatch.setattr("sys.argv", ["ck", *base, "index"])
    assert m.main() == 0
    monkeypatch.setattr("sys.argv", ["ck", *base, "check"])
    assert m.main() == 0
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["ck", *base, "match", "--text", "use redis", "--json"])
    assert m.main() == 0
    assert '"D-001"' in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["ck", *base, "add", "--title", "x", "--rule", "y",
                                     "--quote", "q"])
    assert m.main() == 1  # no scope -> refused
