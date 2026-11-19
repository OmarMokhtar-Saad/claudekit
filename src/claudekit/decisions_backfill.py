"""Read-only candidate extractor for the decision ledger (`ck decide backfill --scan`).

Scans the owner messages the task-brief hook logged (``<acct>/task-brief/<hash>.json``)
for rule-like sentences and ranks them. It never writes a rule: the owner approves
batches through ``/decide``. Pasted blocks are not the owner's own words, so they
are dropped before scanning.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from claudekit import decisions as dec

# (pattern, weight): stronger commitments score higher.
_SIGNALS = [
    (re.compile(r"\bfrom now on\b", re.I), 5),
    (re.compile(r"\brule\s*:", re.I), 5),
    (re.compile(r"\b(?:must|should)\s+never\b|\bnever\b", re.I), 4),
    (re.compile(r"\balways\b", re.I), 3),
    (re.compile(r"\b(?:do not|don't|dont|stop)\s+\w+", re.I), 3),
    (re.compile(r"\b(?:must|only)\b", re.I), 2),
    (re.compile(r"\bgoing forward\b|\bin future\b|\bremember to\b", re.I), 3),
]
_PASTE = re.compile(r"<pasted_content\b[^>]*>.*?</pasted_content[^>]*>", re.S)
_TAGS = re.compile(r"<(system-reminder|task-notification|bash-input|bash-stdout|"
                   r"fork-boilerplate)\b.*?</\1>", re.S)
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_PATHISH = re.compile(r"[\w./~-]+/[\w./-]+\.\w+")
_MIN, _MAX = 12, 300


def default_logs() -> List[str]:
    """Every account's task-brief dir on this machine."""
    return sorted(glob.glob(str(Path.home() / ".claude*" / "task-brief")))


def owner_sentences(text: str) -> Iterable[str]:
    """Sentences the owner typed: pasted and injected blocks are removed first."""
    text = _TAGS.sub(" ", _PASTE.sub(" ", text or ""))
    for part in _SPLIT.split(text):
        s = part.strip().strip("-*>• ").strip()
        if _MIN <= len(s) <= _MAX:
            yield s


def score(sentence: str) -> int:
    pts = sum(w for rx, w in _SIGNALS if rx.search(sentence))
    if sentence.rstrip().endswith("?"):
        return 0          # a question is not a commitment
    return pts


def guess_scope(sentence: str) -> str:
    """Scope hint only; the owner always answers global-or-project."""
    if _PATHISH.search(sentence) or re.search(r"\b(this|the) (repo|project|branch)\b", sentence, re.I):
        return "project"
    return "global" if re.search(r"\b(always|never|everywhere|all projects|every)\b", sentence, re.I) \
        else "unknown"


def _existing_text(stores: List[Path]) -> List[str]:
    out: List[str] = []
    for st in stores:
        for r in dec.load_store(st):
            body = r.get("body", "")
            out.append(dec._norm(r.get("title", "") + " " + dec._rule_line(r) + " " + body))
    return out


def scan(logs: Optional[List[str]] = None, stores: Optional[List[Path]] = None,
         min_score: int = 3, limit: int = 50) -> List[Dict]:
    """Ranked candidates. Duplicates (within the scan or already stored) are dropped."""
    known = _existing_text(stores or [])
    seen = set()
    found: List[Dict] = []
    for d in (logs if logs is not None else default_logs()):
        for f in sorted(glob.glob(str(Path(d) / "*.json"))):
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
                msgs = data.get("msgs", [])
            except (OSError, ValueError, AttributeError):
                continue
            for m in msgs:
                for s in owner_sentences(m.get("text", "") if isinstance(m, dict) else ""):
                    pts = score(s)
                    key = dec._norm(s)
                    if pts < min_score or not key or key in seen:
                        continue
                    seen.add(key)
                    if any(key in k for k in known):
                        continue
                    found.append({"score": pts, "quote": s, "source": Path(f).stem,
                                  "ts": m.get("ts", 0), "scope_guess": guess_scope(s)})
    found.sort(key=lambda c: (-c["score"], -float(c["ts"] or 0)))
    return found[:limit]
