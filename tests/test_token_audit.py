"""scripts/token-audit.py: the reproducible token-spend measurement.

Pins the two rules the 2026-09-19 audit was built on: a request id that appears on several
transcript lines is billed ONCE (a naive sum overstated by ~42%), and billed = input +
cache_read + cache_creation + output per unique request.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "token-audit.py"


def assistant(request_id, uuid, inp, cache_read, cache_create, out):
    return {
        "type": "assistant", "requestId": request_id, "uuid": uuid, "isSidechain": False,
        "sessionId": "sess-1", "timestamp": "2026-09-19T10:00:00.000Z",
        "message": {
            "role": "assistant", "model": "test",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {
                "input_tokens": inp, "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create, "output_tokens": out,
            },
        },
    }


def transcript(tmp_path):
    lines = [
        {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "go"}},
        assistant("req_1", "a1", 1000, 100000, 5000, 500),
        assistant("req_1", "a2", 1000, 100000, 5000, 500),  # same request, second line
        {"type": "system", "subtype": "compact_boundary",
         "compactMetadata": {"trigger": "auto", "preTokens": 250000}},
        assistant("req_2", "a3", 2000, 150000, 0, 1000),
    ]
    p = tmp_path / "sess-1.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return p


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          timeout=60)


def test_duplicate_request_ids_are_billed_once(tmp_path):
    result = run(str(transcript(tmp_path)))
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "unique_requests=2" in out, out
    assert "dup_lines=1" in out, out
    digits = out.replace(",", "")
    # req_1: 1000 + 100000 + 5000 + 500 = 106500; req_2: 2000 + 150000 + 0 + 1000 = 153000
    assert "259500" in digits, out
    # the naive sum counts req_1 twice
    assert "366000" in digits, out
    assert "compact" in out.lower(), "compactions are part of the picture"


def test_json_output_is_machine_readable(tmp_path):
    out = tmp_path / "audit.json"
    result = run(str(transcript(tmp_path)), "--json", str(out))
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    sessions = data["sessions"]
    assert len(sessions) == 1 and sessions[0]["unique_requests"] == 2, sessions
    assert sessions[0]["billed"] == 259500 and sessions[0]["dup_lines"] == 1, sessions[0]


def test_the_script_is_executable_and_documents_its_rules():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "requestId" in text and "cache_read" in text.lower()
    assert SCRIPT.stat().st_mode & 0o111, "scripts/token-audit.py must be executable"
