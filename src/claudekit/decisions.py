"""Decision ledger: owner-agreed rules stored as small markdown files.

One rule = one file ``D-NNN-slug.md`` (project store) or ``G-NNN-slug.md`` (global
store). Accepted rules are never rewritten: a change is a new file plus
``status: superseded`` on the old one; wording fixes are a History line only.

Matching is deterministic (no embeddings, no model call):
  * paths use ``fnmatch``-style globs with ``**`` against a repo-relative path;
  * keywords are case-insensitive whole words;
  * order: path hits, then keyword hits; project before global; newest ``agreed``
    first; then id. Only ``status: active`` rules match; ``max`` defaults to 5.

The same spec is implemented by the stdlib-only hook library
``agent-config/accounts/personal/hooks/_decisions_lib.py``; a parity test keeps the
two in step. Frontmatter is a flat ``key: value`` subset with inline ``[a, b]``
lists (no YAML dependency), so both implementations parse it identically.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Dict, List, Optional

STATUSES = ("active", "superseded", "dropped")
SCOPES = ("global", "project")
APPLIES = ("plan", "debug", "websearch", "edit")
DEFAULT_MAX = 5

_FM = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
_ID = re.compile(r"^([DG])-(\d{3,})-")
_SECTIONS = ("Rule", "Owner words", "Why", "Not allowed", "History")


class DecisionError(Exception):
    """Raised for any ledger problem the caller should show verbatim."""


# --------------------------------------------------------------------- parse

def _parse_list(raw: str) -> List[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [p.strip().strip("'\"") for p in raw.split(",") if p.strip()]


def parse_rule(text: str, path: Optional[Path] = None) -> Dict:
    m = _FM.match(text)
    if not m:
        raise DecisionError(f"{path or 'rule'}: missing --- frontmatter ---")
    meta: Dict = {}
    for line in m.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        meta[k] = _parse_list(v) if v.startswith("[") else v
    for key in ("supersedes", "applies", "guard_paths", "guard_keywords"):
        meta.setdefault(key, [])
    meta.setdefault("status", "active")
    meta.setdefault("superseded_by", "")
    meta["body"] = m.group(2)
    if path is not None:
        meta["file"] = path.name
    return meta


def _rule_line(rule: Dict) -> str:
    body = rule.get("body", "")
    m = re.search(r"^## Rule[ \t]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return (m.group(1) if m else "").strip().splitlines()[0] if m and m.group(1).strip() else ""


def load_store(store: Path) -> List[Dict]:
    out: List[Dict] = []
    if not store.is_dir():
        return out
    for p in sorted(store.glob("[DG]-*.md")):
        if _ID.match(p.name):
            out.append(parse_rule(p.read_text(encoding="utf-8"), p))
    return out


# --------------------------------------------------------------------- match

def glob_to_regex(glob: str) -> "re.Pattern[str]":
    i, n, out = 0, len(glob), ""
    while i < n:
        c = glob[i]
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(out + r"\Z")


def path_hit(rule: Dict, path: str) -> bool:
    path = path.lstrip("./") if path.startswith("./") else path
    return any(glob_to_regex(g).match(path) for g in rule.get("guard_paths", []))


def keyword_hit(rule: Dict, text: str) -> bool:
    return any(re.search(r"\b" + re.escape(k) + r"\b", text, re.I)
               for k in rule.get("guard_keywords", []) if k)


def match(project: List[Dict], glob_rules: List[Dict], path: str = "", text: str = "",
          max_n: int = DEFAULT_MAX) -> List[Dict]:
    hits = []
    for origin, rules in ((0, project), (1, glob_rules)):
        for r in rules:
            if r.get("status") != "active":
                continue
            ph = bool(path) and path_hit(r, path)
            kh = bool(text) and keyword_hit(r, text)
            if ph or kh:
                hits.append((0 if ph else 1, origin, _neg_date(r), r["id"], r))
    hits.sort(key=lambda t: t[:4])
    return [h[4] for h in hits[:max_n]]


def _neg_date(rule: Dict) -> int:
    d = rule.get("agreed", "")
    try:
        return -_dt.date.fromisoformat(d).toordinal()
    except ValueError:
        return 0


# --------------------------------------------------------------------- write

def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:48] or "rule"


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def next_id(store: Path, scope: str) -> str:
    prefix = "G" if scope == "global" else "D"
    nums = [int(m.group(2)) for p in store.glob(f"{prefix}-*.md")
            if (m := _ID.match(p.name))] if store.is_dir() else []
    return f"{prefix}-{(max(nums) if nums else 0) + 1:03d}"


def _render(meta: Dict, rule: str, quote: str, why: str, not_allowed: str,
            history: List[str]) -> str:
    def lst(v):
        return "[" + ", ".join(v) + "]"
    fm = [
        "---", f"id: {meta['id']}", f"title: {meta['title']}", f"scope: {meta['scope']}",
        f"status: {meta['status']}", f"agreed: {meta['agreed']}",
        f"supersedes: {lst(meta['supersedes'])}", f"superseded_by: {meta['superseded_by']}",
        f"applies: {lst(meta['applies'])}", f"guard_paths: {lst(meta['guard_paths'])}",
        f"guard_keywords: {lst(meta['guard_keywords'])}", "---", "",
    ]
    body = [
        "## Rule", rule, "", "## Owner words", "> " + quote.replace("\n", "\n> "), "",
        "## Why", why, "", "## Not allowed", not_allowed, "", "## History",
        *[f"- {h}" for h in history], "",
    ]
    return "\n".join(fm + body)


def add(store: Path, scope: str, title: str, rule: str, quote: str, why: str = "",
        not_allowed: str = "", applies: Optional[List[str]] = None,
        guard_paths: Optional[List[str]] = None,
        guard_keywords: Optional[List[str]] = None, supersedes: Optional[List[str]] = None,
        today: Optional[str] = None) -> Path:
    if scope not in SCOPES:
        raise DecisionError(f"scope must be one of {SCOPES}; ask the owner: global or this project")
    if not quote.strip():
        raise DecisionError("an owner quote is required (the rule must trace to the owner's words)")
    if not rule.strip():
        raise DecisionError("rule text is required")
    applies = applies or list(APPLIES)
    bad = [a for a in applies if a not in APPLIES]
    if bad:
        raise DecisionError(f"unknown applies value(s) {bad}; allowed {APPLIES}")
    for g in guard_paths or []:
        try:
            glob_to_regex(g)
        except re.error as exc:
            raise DecisionError(f"bad glob {g!r}: {exc}") from exc
    store.mkdir(parents=True, exist_ok=True)
    existing = load_store(store)
    for r in existing:
        if r["status"] == "active" and not (supersedes and r["id"] in supersedes):
            if _norm(r["title"]) == _norm(title) or (_rule_line(r) and
                                                     _norm(_rule_line(r)) == _norm(rule)):
                raise DecisionError(
                    f"duplicate of {r['id']} ({r['title']}); use supersede or add a History line")
    today = today or _dt.date.today().isoformat()
    rid = next_id(store, scope)
    meta = {"id": rid, "title": title, "scope": scope, "status": "active", "agreed": today,
            "supersedes": supersedes or [], "superseded_by": "", "applies": applies,
            "guard_paths": guard_paths or [], "guard_keywords": guard_keywords or []}
    hist = [f"{today} added" + (f" (supersedes {', '.join(supersedes)})" if supersedes else "")]
    text = _render(meta, rule.strip(), quote.strip(), why.strip(), not_allowed.strip(), hist)
    path = store / f"{rid}-{_slug(title)}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _find(store: Path, rid: str) -> Path:
    for p in store.glob(f"{rid}-*.md"):
        return p
    raise DecisionError(f"no rule {rid} in {store}")


def _edit_status(path: Path, status: str, superseded_by: str, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^status: .*$", f"status: {status}", text, count=1)
    text = re.sub(r"(?m)^superseded_by:.*$", f"superseded_by: {superseded_by}", text, count=1)
    if "## History" not in text:
        text = text.rstrip("\n") + "\n\n## History\n"
    path.write_text(text.rstrip("\n") + f"\n- {line}\n", encoding="utf-8")


def supersede(store: Path, old_id: str, title: str, rule: str, quote: str, reason: str,
              **kw) -> Path:
    if not reason.strip():
        raise DecisionError("a reason is required to supersede a rule")
    old = _find(store, old_id)
    meta = parse_rule(old.read_text(encoding="utf-8"), old)
    if meta["status"] != "active":
        raise DecisionError(f"{old_id} is {meta['status']}, not active")
    kw.setdefault("scope", meta.get("scope", "project"))
    today = kw.get("today") or _dt.date.today().isoformat()
    new = add(store, title=title, rule=rule, quote=quote, supersedes=[old_id], **kw)
    m = _ID.match(new.name)
    assert m is not None
    nid = m.group(0)[:-1]
    _edit_status(old, "superseded", nid, f"{today} superseded by {nid}: {reason.strip()}")
    return new


def drop(store: Path, rid: str, reason: str, today: Optional[str] = None) -> None:
    if not reason.strip():
        raise DecisionError("a reason is required to drop a rule")
    p = _find(store, rid)
    today = today or _dt.date.today().isoformat()
    _edit_status(p, "dropped", "", f"{today} dropped: {reason.strip()}")


def note(store: Path, rid: str, line: str, today: Optional[str] = None) -> None:
    """Append a History line only (wording fix); never touches the rule text."""
    p = _find(store, rid)
    today = today or _dt.date.today().isoformat()
    text = p.read_text(encoding="utf-8").rstrip("\n")
    p.write_text(text + f"\n- {today} {line.strip()}\n", encoding="utf-8")


# --------------------------------------------------------------- index/check

def render_index(store: Path) -> str:
    lines = ["# Decision index (generated by `ck decide index`; do not edit)", ""]
    for r in load_store(store):
        if r["status"] == "active":
            guard = ",".join(r["guard_paths"] + r["guard_keywords"])
            lines.append(f"- {r['id']} {r['title']}: {_rule_line(r)}"
                         + (f" [{guard}]" if guard else ""))
    return "\n".join(lines) + "\n"


def write_index(store: Path) -> Path:
    store.mkdir(parents=True, exist_ok=True)
    p = store / "INDEX.md"
    p.write_text(render_index(store), encoding="utf-8")
    return p


def check(store: Path) -> Dict[str, List[str]]:
    """Return {'errors': [...], 'warnings': [...]}; errors mean a non-zero exit."""
    from claudekit import memory as mem

    errors: List[str] = []
    warnings: List[str] = []
    rules = load_store(store)
    by_id: Dict[str, Dict] = {}
    for r in rules:
        rid = r.get("id", "")
        if rid in by_id:
            errors.append(f"{rid}: duplicate id ({by_id[rid]['file']} and {r['file']})")
        by_id[rid] = r
        if not r["file"].startswith(rid + "-"):
            errors.append(f"{r['file']}: id {rid!r} does not match the file name")
        if r["status"] not in STATUSES:
            errors.append(f"{rid}: bad status {r['status']!r}")
        for g in r["guard_paths"]:
            try:
                glob_to_regex(g)
            except re.error:
                errors.append(f"{rid}: glob does not parse: {g}")
        if mem.looks_like_credential(r["body"]):
            errors.append(f"{rid}: body looks like it carries a credential")
        if "## Owner words" not in r["body"]:
            errors.append(f"{rid}: no Owner words section")
        for d in mem.directives(r["body"]):
            warnings.append(f"{rid}: directive shape ({d['kind']}): advisory only")
            break
    for r in rules:
        for s in r["supersedes"]:
            o = by_id.get(s)
            if o is None:
                errors.append(f"{r['id']}: supersedes unknown {s}")
            elif o["superseded_by"] != r["id"]:
                errors.append(f"{r['id']}: {s} does not point back (superseded_by)")
        sb = r["superseded_by"]
        if sb:
            n = by_id.get(sb)
            if n is None or r["id"] not in n["supersedes"]:
                errors.append(f"{r['id']}: superseded_by {sb} does not point back")
    idx = store / "INDEX.md"
    if rules and (not idx.is_file() or idx.read_text(encoding="utf-8") != render_index(store)):
        errors.append("INDEX.md is missing or out of date; run `ck decide index`")
    return {"errors": errors, "warnings": warnings}
