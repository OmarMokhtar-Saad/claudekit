import json
from pathlib import Path

from claudekit import decisions as dec
from claudekit import decisions_backfill as bf


def _log(d: Path, name: str, texts):
    d.mkdir(exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(
        {"msgs": [{"ts": i + 1, "text": t} for i, t in enumerate(texts)],
         "seen": [], "deny_streak": 0}))


def test_ranks_rule_like_sentences_and_drops_questions(tmp_path):
    _log(tmp_path, "aaa", ["From now on never push main yourself. ok?",
                           "Can you always do this?", "please look at foo"])
    out = bf.scan([str(tmp_path)], [])
    assert [c["quote"] for c in out] == ["From now on never push main yourself."]
    assert out[0]["source"] == "aaa" and out[0]["score"] >= 9


def test_pasted_and_injected_text_is_not_owner_words(tmp_path):
    _log(tmp_path, "b", ['<pasted_content id="x">Never delete the vault always.</pasted_content>',
                         "<system-reminder>Never do X, always do Y here.</system-reminder>"])
    assert bf.scan([str(tmp_path)], []) == []


def test_dedups_against_store_and_within_scan(tmp_path):
    store = tmp_path / "store"
    dec.add(store, "project", "No main push", "Never push main yourself.",
            "Never push main yourself.", guard_keywords=["push"])
    _log(tmp_path, "c", ["Never push main yourself.", "Always use the venv python here.",
                         "Always use the venv python here."])
    out = bf.scan([str(tmp_path)], [store])
    assert [c["quote"] for c in out] == ["Always use the venv python here."]


def test_scope_guess_and_bad_files(tmp_path):
    _log(tmp_path, "d", ["Never edit src/app/main.py without a plan."])
    (tmp_path / "bad.json").write_text("{nope")
    out = bf.scan([str(tmp_path)], [])
    assert out[0]["scope_guess"] == "project"


def test_cli_scan_is_read_only(tmp_path, monkeypatch, capsys):
    from claudekit.cli import main as m
    _log(tmp_path, "e", ["Never skip the tests, always run them."])
    store = tmp_path / "s"
    monkeypatch.setattr("sys.argv", ["ck", "decide", "backfill", "--scan", "--logs",
                                     str(tmp_path), "--store", str(store),
                                     "--global-store", str(tmp_path / "g"), "--json"])
    assert m.main() == 0
    assert json.loads(capsys.readouterr().out)[0]["quote"].startswith("Never skip")
    assert not store.exists()
    monkeypatch.setattr("sys.argv", ["ck", "decide", "backfill"])
    assert m.main() == 1
