#!/usr/bin/env python3
"""Flag *compound* silent failures: a MUTATING operation whose failure is swallowed while
the caller goes on to report success.

Scope is deliberately narrow. The corpus has 192 `2>/dev/null` and 14 `|| true`; a rule that
flags those is noise and gets disabled, which is strictly worse than no lint.

SHELL rule -- report only when BOTH hold:
  1. a failure path is ignored: `|| true`, `|| :`, `|| echo`, `|| print_warn`, or the
     `cmd && ok || fallback` shape; and
  2. the command mutates state: a write-mode `git` subcommand, one of
     rm/mv/cp/mkdir/chmod/chown/ln/touch/tee/dd/install/sed -i/truncate/mkfifo, a `>`/`>>`
     redirection into a variable path, or an inline `python3 -c` whose script writes.

PYTHON rule -- report an `except` handler whose body is exactly `pass` when:
  1. the guarded `try` body performs a mutating call on PERSISTENT state (a write to
     sys.stdout/sys.stderr is a diagnostic, not a mutation, and does not count); and
  2. no ancestor handler has a TOP-LEVEL `raise` in its body (the canonical temp-file cleanup
     idiom propagates its failure one frame out); and
  3. no SIBLING handler on the same `try` both propagates (top-level `raise`/`return`) AND
     catches a SUPERSET of this handler's exception types -- the `except FileExistsError:
     pass` / `except OSError: return None` pair is the idiomatic `exist_ok` emulation, but an
     unrelated `except ValueError: return None` beside an `except OSError: pass` proves
     nothing about the OSError swallow; and
  4. the handler is NOT inside a teardown method (release/close/cleanup/__exit__/__del__),
     where best-effort is the documented contract.

============================================================================
WHAT THIS SCANNER CANNOT SEE  (read this before trusting a clean run)
============================================================================
Recall is bounded, deliberately, and the bounds are enumerated rather than implied. Two
successive revisions of this check shipped a wrong corpus count because the *measuring
instrument* had a blind spot -- first a missing verb (`rmdir`), then a missing root
(`.claude/hooks/`). So:

  * VERBS. `git` uses a DENYLIST of read-only subcommands, so an unknown git subcommand is
    treated as mutating and fails loud. Every other shell verb is an ALLOWLIST, so unlisted
    mutators (`curl -o`, `rsync`, `python3 some_script.py`, project shell functions) are
    SILENT MISSES. Python mutators are likewise an allowlist (PY_MUTATORS).
  * ROOTS. Both halves now scan every file under the given paths, with no language-specific
    root filter. There is no `PY_ROOTS`: an asymmetry there is what hid 10 sites in
    `.claude/hooks/` behind a published count of 13.
  * SHELL SYNTAX. `$'...'` ANSI-C quoting and backticks are not modelled; they degrade to a
    SILENT SKIP (no finding, no diagnostic), not to a crash. `<<<WORD` here-strings ARE
    handled -- HEREDOC carries a lookbehind and a lookahead so a here-string is not
    mis-read as a heredoc opener (without both, the regex matches from the second `<` of
    `<<<`, sets a bogus delimiter, and trips the cap with a spurious DIAGNOSTIC).
  * DATAFLOW. "The failure sets a flag that nothing ever reads" is not detectable here.
  * CONDITIONAL RAISE. Clause 2 looks for a top-level `raise` in an ancestor handler's body.
    A `raise` nested inside an `if` in that handler does NOT exempt the inner handler.
  * SIBLING HANDLERS. Clause 3 exempts only when a propagating sibling catches a provable
    SUPERSET of this handler's types, resolved against the builtin exception hierarchy. A
    project-defined exception class cannot be resolved, so a genuine subset relation
    expressed with custom classes is NOT recognised and the site is reported (a possible
    false positive, chosen over a silent miss).

Read a clean run as "no *known* shape present", never as "no silent failures present".

Exempt an intentional site with an inline pragma whose reason is at least 10 characters, on
the offending line or the line above it:

    # silent-ok: optional asset dir; absence is not an error
    cp "$SRC"/*.md "$DEST/" 2>/dev/null || true

The 10-character floor is a TYPO FILTER, not enforcement: `# silent-ok: aaaaaaaaaa` passes.
Substance is a review obligation, not a machine check. A pragma is preferred over a path
skip-list because a skip-list goes stale silently -- the very class this script lints.

Exit codes:
    0  files were scanned, no findings, no diagnostics
    1  findings
    2  usage error, unreadable path, or ZERO files scanned
    3  the scan was INCOMPLETE (a file would not parse, or a join/heredoc cap tripped).
       Exit 3 outranks 1: an incomplete scan cannot support a clean or a complete verdict.

A zero-finding run, a zero-file run and an incomplete run are never conflated; that would
make this script an instance of the class it lints.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, List, NamedTuple, Optional, Sequence, Set, Tuple

EXCLUDED_PARTS = {
    "backups", ".git", "node_modules", ".venv", "__pycache__", ".pytest_cache",
    ".tmp-test-fixtures",  # this repo's pytest sandbox; planted fixtures must never be scanned
}

MAX_JOIN_LINES = 80  # bounds both the quote-join and the heredoc skip; see logical_lines()

# --- shell rule vocabulary -------------------------------------------------
IGNORES_FAILURE = re.compile(
    r"\|\|\s*(?:true\b|:\s*(?:$|[;&])|echo\b|print_warn\b|print_info\b|warn\b)"
)
AND_OR_FALLBACK = re.compile(r"&&.*\|\|")
READONLY_GIT = (
    r"rev-parse|status|log|diff|show|describe|ls-files|ls-tree|ls-remote|cat-file|"
    r"symbolic-ref|check-ignore|merge-base|name-rev|rev-list|var|"
    r"stash\s+list|branch\s+--show-current|config\s+--get"
)
MUTATING_CMD = re.compile(
    r"(?<![\w./-])(?:git\s+(?!(?:%s))[a-z-]+|rm|rmdir|mv|cp|mkdir|chmod|chown|ln|touch|"
    r"tee|dd|install|truncate|mkfifo|sed\s+-i\S*)\s" % READONLY_GIT
)
REDIRECT_WRITE = re.compile(r">>?\s*\"?\$")
INLINE_PYTHON = re.compile(r"python3?\s+-c")
PYTHON_WRITES = re.compile(
    r"open\([^)]*['\"][wax]|\.write\b|json\.dump|os\.replace|os\.rename|os\.remove|"
    r"shutil\.|write_text|write_bytes"
)
# The lookbehind AND lookahead together keep a `<<<WORD` here-string from being mis-read as
# a heredoc opener. `(?!<)` alone is not enough: the engine simply matches from the SECOND
# `<` of `<<<`, which is how this shipped wrong the first time.
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")
PRAGMA = re.compile(r"#\s*silent-ok:\s*(?P<reason>.+)")
MIN_REASON = 10
SHEBANG = re.compile(r"^#!.*\b(?:ba|da|k|z)?sh\b")

# --- python rule vocabulary ------------------------------------------------
# NOTE: `close` and `flock` are deliberately ABSENT. Neither mutates persistent state by
# this script's own definition, and including them made every `f.close()` in a try body a
# latent false positive that only the teardown/re-raise exclusions happened to mask.
PY_MUTATORS = {
    "write", "write_text", "write_bytes", "writelines", "dump", "unlink", "rmtree", "rmdir",
    "copy", "copy2", "copytree", "move", "rename", "replace", "mkdir", "makedirs", "remove",
    "chmod", "chown", "truncate", "symlink", "link",
}
PY_TEARDOWN = {"release", "close", "cleanup", "_cleanup", "teardown", "__exit__", "__del__"}


class Finding(NamedTuple):
    path: Path
    line: int
    text: str
    why: str


class Diagnostic(NamedTuple):
    path: Path
    line: int
    message: str


# --------------------------------------------------------------------------
# shell scanning
# --------------------------------------------------------------------------
def split_code_and_comment(line: str, in_squote: bool, in_dquote: bool) -> Tuple[str, bool, bool]:
    """Return (code_without_trailing_comment, in_squote, in_dquote) after this line.

    Quote parity is tracked with a real state machine so a `#` inside quotes is not mistaken
    for a comment and a quote inside a comment does not corrupt parity. Both mistakes let one
    stray quote in a comment swallow 100+ following lines.
    """
    out: List[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and (in_dquote or not in_squote):
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch == "'" and not in_dquote:
            in_squote = not in_squote
        elif ch == '"' and not in_squote:
            in_dquote = not in_dquote
        elif ch == "#" and not in_squote and not in_dquote:
            if i == 0 or line[i - 1].isspace():
                break
        out.append(ch)
        i += 1
    return "".join(out), in_squote, in_dquote


def logical_lines(text: str) -> Tuple[List[Tuple[int, str, str]], List[Tuple[int, str]]]:
    """Yield (start_lineno, code, raw_block) plus diagnostics.

    Joins backslash continuations and unterminated double-quoted blocks, because the
    install.sh case opens `python3 -c "` and swallows the failure 17 lines later.

    BOTH unbounded loops are capped and diagnosed. An uncapped heredoc skip is the same hole
    MAX_JOIN_LINES closes on the quote branch: a terminator that never matches (`<<\\EOF`,
    trailing whitespace, an arithmetic `<<`) would silently swallow the rest of the file.
    """
    blocks: List[Tuple[int, str, str]] = []
    diags: List[Tuple[int, str]] = []
    lines = text.splitlines()
    raw_buf: List[str] = []
    code_buf: List[str] = []
    start: Optional[int] = None
    in_sq = in_dq = False
    heredoc_end: Optional[str] = None
    heredoc_start = 0
    heredoc_len = 0
    i = 0
    while i < len(lines):
        raw = lines[i]
        lineno = i + 1
        if heredoc_end is not None:
            if raw.strip() == heredoc_end:
                heredoc_end = None
            else:
                heredoc_len += 1
                if heredoc_len >= MAX_JOIN_LINES:
                    diags.append((heredoc_start,
                                  "heredoc terminator %r not found within %d lines; skip "
                                  "abandoned (scan may be incomplete)"
                                  % (heredoc_end, MAX_JOIN_LINES)))
                    heredoc_end = None
            i += 1
            continue
        if start is None:
            start = lineno
            in_sq = in_dq = False
        code, in_sq, in_dq = split_code_and_comment(raw, in_sq, in_dq)
        raw_buf.append(raw)
        code_buf.append(code)

        hd = HEREDOC.search(code)
        continues = raw.rstrip().endswith("\\") or in_dq or in_sq
        if hd and not in_dq and not in_sq:
            heredoc_end = hd.group(1)
            heredoc_start = lineno
            heredoc_len = 0
            continues = False
        if continues and len(raw_buf) >= MAX_JOIN_LINES:
            diags.append((start, "unterminated quote joined %d lines and hit the cap; block "
                                 "truncated (scan may be incomplete)" % len(raw_buf)))
            continues = False
            in_sq = in_dq = False
        if continues:
            i += 1
            continue
        blocks.append((start, "\n".join(code_buf), "\n".join(raw_buf)))
        raw_buf, code_buf, start = [], [], None
        i += 1
    if raw_buf and start is not None:
        blocks.append((start, "\n".join(code_buf), "\n".join(raw_buf)))
    if heredoc_end is not None:
        diags.append((heredoc_start, "file ended inside heredoc %r; trailing lines were "
                                     "never scanned" % heredoc_end))
    return blocks, diags


def has_pragma(*texts: str) -> bool:
    for text in texts:
        match = PRAGMA.search(text)
        if match and len(match.group("reason").strip()) >= MIN_REASON:
            return True
    return False


def shell_mutation(code: str) -> str:
    match = MUTATING_CMD.search(code)
    if match:
        return "mutating command %r" % match.group(0).strip()
    if REDIRECT_WRITE.search(code):
        return "redirection writing to a variable path"
    if INLINE_PYTHON.search(code) and PYTHON_WRITES.search(code):
        return "inline python3 -c that writes"
    return ""


def scan_shell(path: Path, text: str) -> Tuple[List[Finding], List[Diagnostic]]:
    raw_lines = text.splitlines()
    blocks, diag_raw = logical_lines(text)
    diags = [Diagnostic(path, ln, msg) for ln, msg in diag_raw]
    findings: List[Finding] = []
    for lineno, code, raw_block in blocks:
        if not code.strip():
            continue
        if not (IGNORES_FAILURE.search(code) or AND_OR_FALLBACK.search(code)):
            continue
        why = shell_mutation(code)
        if not why:
            continue
        preceding = raw_lines[lineno - 2] if lineno >= 2 else ""
        if has_pragma(raw_block, preceding):
            continue
        first = next((ln for ln in code.split("\n") if ln.strip()), "").strip()
        findings.append(Finding(path, lineno, first, why))
    return findings, diags


# --------------------------------------------------------------------------
# python scanning
# --------------------------------------------------------------------------
def _handler_exc_names(handler: ast.ExceptHandler) -> Optional[List[str]]:
    """Exception type names caught by a handler; None for a bare `except:` (catches all)."""
    node = handler.type
    if node is None:
        return None
    parts = node.elts if isinstance(node, ast.Tuple) else [node]
    names: List[str] = []
    for part in parts:
        if isinstance(part, ast.Name):
            names.append(part.id)
        elif isinstance(part, ast.Attribute):
            names.append(part.attr)
        else:
            return []  # unparseable form: claim nothing
    return names


def _catches_superset_of(sibling: ast.ExceptHandler, inner: ast.ExceptHandler) -> bool:
    """True when `sibling` catches every exception type `inner` does.

    Resolved against the real builtin hierarchy via issubclass, so
    FileExistsError -> OSError is recognised without a hand-maintained map. A name that is
    not a builtin exception (a project-defined class) resolves to nothing, and an
    unprovable relation returns False -- the recall-safe direction for a lint.
    """
    sibling_names = _handler_exc_names(sibling)
    if sibling_names is None:
        return True  # bare `except:` catches everything
    inner_names = _handler_exc_names(inner)
    if inner_names is None or not inner_names or not sibling_names:
        return False  # a bare `except: pass` cannot be a subset of a typed sibling

    def resolve(name: str) -> Optional[type]:
        obj = getattr(builtins, name, None)
        return obj if isinstance(obj, type) and issubclass(obj, BaseException) else None

    sibling_types = [resolve(n) for n in sibling_names]
    if any(t is None for t in sibling_types):
        return False
    for name in inner_names:
        inner_type = resolve(name)
        if inner_type is None:
            return False
        if not any(issubclass(inner_type, s) for s in sibling_types if s is not None):
            return False
    return True


def _py_mutators(node: ast.AST) -> Set[str]:
    found: Set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else "")
        if name in PY_MUTATORS:
            # A write to sys.stdout/sys.stderr is a diagnostic, not persistent state.
            target = func.value if isinstance(func, ast.Attribute) else None
            if name in ("write", "writelines") and isinstance(target, ast.Attribute) \
                    and isinstance(target.value, ast.Name) and target.value.id == "sys" \
                    and target.attr in ("stdout", "stderr"):
                continue
            found.add(name)
        if name == "open":
            candidates = list(sub.args[1:]) + [k.value for k in sub.keywords if k.arg == "mode"]
            for arg in candidates:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and arg.value[:1] in ("w", "a", "x"):
                    found.add("open(write)")
    return found


def scan_python(path: Path, text: str) -> Tuple[List[Finding], List[Diagnostic]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], [Diagnostic(path, exc.lineno or 0,
                               "could not parse (file NOT scanned): %s" % exc.msg)]
    raw_lines = text.splitlines()
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def ancestors(node: ast.AST) -> Iterator[ast.AST]:
        while node in parents:
            node = parents[node]
            yield node

    findings: List[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)):
                continue
            mutators = _py_mutators(ast.Module(body=node.body, type_ignores=[]))
            if not mutators:
                continue
            chain = list(ancestors(handler))
            # Top-level `raise` only: a raise nested in an `if` inside an ancestor handler
            # does not prove this failure is propagated.
            if any(isinstance(a, ast.ExceptHandler)
                   and any(isinstance(s, ast.Raise) for s in a.body) for a in chain):
                continue
            # A sibling handler makes this `pass` a deliberate carve-out only when it
            # both propagates AND catches a SUPERSET of what this handler catches.
            if any(h is not handler
                   and any(isinstance(s, (ast.Raise, ast.Return)) for s in h.body)
                   and _catches_superset_of(h, handler)
                   for h in node.handlers):
                continue
            func = next((a for a in chain
                         if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
            if func is not None and func.name in PY_TEARDOWN:
                continue
            lo = max(0, handler.lineno - 2)
            hi = min(len(raw_lines), handler.body[0].lineno)
            if has_pragma(*raw_lines[lo:hi]):
                continue
            findings.append(Finding(
                path, handler.lineno,
                raw_lines[handler.lineno - 1].strip() if handler.lineno <= len(raw_lines) else "",
                "swallowed failure of %s; caller continues as if it succeeded"
                % ", ".join(sorted(mutators)),
            ))
    return findings, []


# --------------------------------------------------------------------------
def is_shell(path: Path) -> bool:
    if path.suffix == ".sh":
        return True
    if path.suffix:
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return bool(SHEBANG.match(handle.readline()))
    except OSError:
        return False


def collect(roots: Iterable[Path]) -> Tuple[List[Path], List[Path]]:
    """Collect shell and python files. No language-specific root filter, by design:
    an asymmetry here (shell unfiltered, python restricted) hid 10 sites behind a
    published count."""
    shell: List[Path] = []
    python: List[Path] = []
    candidates: Sequence[Tuple[Path, Tuple[str, ...]]]
    for root in roots:
        if root.is_file():
            # An explicitly named file always wins over the exclusion list, exactly as
            # other linters behave. Without this, a path *inside* an excluded directory
            # could never be scanned even when asked for by name.
            candidates = [(root, ())]
        else:
            candidates = [(p, p.relative_to(root).parts) for p in sorted(root.rglob("*"))]
        for path, rel_parts in candidates:
            if not path.is_file():
                continue
            # Match on parts RELATIVE to the scan root. Matching absolute parts made the
            # result depend on where the repo happened to be checked out.
            if EXCLUDED_PARTS & set(rel_parts):
                continue
            if path.suffix == ".py":
                python.append(path)
            elif is_shell(path):
                shell.append(path)
    return shell, python


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("paths", nargs="*", help="files or directories (default: repo root)")
    parser.add_argument("--check", action="store_true",
                        help="accepted for symmetry with the other gate scripts")
    args = parser.parse_args(argv)

    roots: List[Path] = []
    for candidate in (args.paths or [str(Path(__file__).resolve().parent.parent)]):
        path = Path(candidate)
        if not path.exists():
            print("ERROR: path does not exist: %s" % candidate, file=sys.stderr)
            return 2
        roots.append(path)

    shell_files, python_files = collect(roots)
    findings: List[Finding] = []
    diagnostics: List[Diagnostic] = []
    for path, scanner in ([(p, scan_shell) for p in shell_files]
                          + [(p, scan_python) for p in python_files]):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print("ERROR: cannot read %s: %s" % (path, exc), file=sys.stderr)
            return 2
        found, diags = scanner(path, text)
        findings.extend(found)
        diagnostics.extend(diags)

    total = len(shell_files) + len(python_files)
    if not total:
        print("ERROR: scanned 0 files under %s — nothing was checked"
              % ", ".join(str(r) for r in roots), file=sys.stderr)
        return 2

    for diag in sorted(diagnostics):
        print("%s:%d: DIAGNOSTIC: %s" % (diag.path, diag.line, diag.message), file=sys.stderr)
    for finding in sorted(findings):
        print("%s:%d: silent failure: %s | %s"
              % (finding.path, finding.line, finding.why, finding.text), file=sys.stderr)

    if diagnostics:
        print("\nINCOMPLETE: %d file region(s) could not be scanned; %d silent-failure "
              "site(s) found in what WAS scanned. Neither a clean nor a complete verdict "
              "is available." % (len(diagnostics), len(findings)), file=sys.stderr)
        return 3
    if findings:
        print("\nFAIL: %d silent-failure site(s) across %d file(s) (%d shell, %d python). "
              "Fix the failure path, or annotate with `# silent-ok: <reason>`."
              % (len(findings), total, len(shell_files), len(python_files)), file=sys.stderr)
        return 1

    print("OK: %d file(s) scanned (%d shell, %d python), 0 silent-failure sites."
          % (total, len(shell_files), len(python_files)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
