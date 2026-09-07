#!/usr/bin/env python3
"""Prove an ops.json leaves every Python file it touches still parseable.

WHY THIS EXISTS. The ops pipeline gates on intent (a reviewer APPROVED it), on identity (this
is the exact ops.json that was approved) and on drift (the tree is still the one it was written
against). None of those is a gate on the RESULT. An ops.json that was validator-clean, dry-run
clean and APPROVED wrote a malformed f-string into a source file in the downstream QA repo this
gate was first built for, and the SyntaxError surfaced only when the next render crashed -- after
the write, after the backup, with nothing in the pipeline having objected.

`validate-config-json.py` proves each `find` anchor is present and unambiguous. This proves the
text that comes out the other side is text Python can still read. That is the one mechanical
claim human review does not reliably catch, because a reviewer reads the `replace` block and
not the splice of it into three thousand lines of surrounding source.

WHAT THIS IS NOT. Not a linter, not a test run, and not a judgement about whether the edit is
correct. A file that parses can still be wrong; that is what the reviewer and the pins are for.

    python3 .claude/operations/scripts/ops_precompile.py <ops.json>      # exit 0 = every touched .py still parses

The executor calls this itself, in dry-run as well as execute, and fails closed if it cannot.

CHANGING THIS FILE OBLIGES YOU TO RE-RUN ITS CHECKS:

    python3 -m pytest tests/test_ops_parse_gate.py -q

Those checks cover the four things this module refuses -- a result that does not parse, an
anchor that is missing or ambiguous, and a name this edit newly shadows at module level. They
are behavioural: each drives this module and asserts the verdict, so a mutation of the code
below turns one red. Unlike the upstream original they are NOT hand-run -- the suite and CI run
them, because a gate whose own behaviour goes unverified is the fragility this one exists to
prevent elsewhere.
"""
import argparse
import ast
import json
import os
import sys


def _apply(src, edit, path, misses):
    """One edit against the accumulated text, or a recorded miss.

    An anchor that is absent is NOT skipped quietly. If `find` is not there, the text this
    function returns is not the text the executor will write, and a checker that went on to
    parse it would be reporting on a file that never existed. The executor refuses such an
    ops.json outright; here it is recorded so the parse verdict can be withheld rather than
    guessed at.

    AMBIGUITY IS THE SAME KIND OF LIE. `execute_code_edit` counts occurrences and refuses at
    two or more (`execute-json-ops.py:759`), while `str.replace(..., 1)` would cheerfully
    splice the first one. A checker that modelled a result the executor will never write is
    worse than no checker: it would green-light a plan that then aborts, or -- far worse --
    describe the wrong splice as parsing. So the count is taken here on the SAME accumulated
    text the executor counts against, and disagreement is recorded rather than resolved.
    """
    find = edit.get('find')
    if not find:
        misses.append((path, 'edit has no find pattern'))
        return src
    seen = src.count(find)
    if seen == 0:
        misses.append((path, 'anchor not found: %r' % (find[:60],)))
        return src
    if seen > 1:
        misses.append((path, 'anchor is ambiguous — it appears %d times, and the executor '
                             'refuses an ambiguous match: %r' % (seen, find[:60])))
        return src
    # ORDER IS LOAD-BEARING AND IS NOT ALPHABETICAL. It mirrors the if/elif chain in
    # `execute_code_edit` (add_after, add_before, replace, delete) because an edit may carry
    # two action keys and `validate-config-json.py` accepts it -- it asks only that SOME
    # action is present. Whichever key the executor reaches first is the one that gets
    # written, so a checker that preferred a different key would model a result the executor
    # will never write and report OK on a file that does not compile. That is the exact lie
    # this module exists to refuse, so the chain below must stay byte-for-byte in the
    # executor's order.
    if 'add_after' in edit:
        return src.replace(find, find + edit['add_after'], 1)
    if 'add_before' in edit:
        return src.replace(find, edit['add_before'] + find, 1)
    if 'replace' in edit:
        return src.replace(find, edit['replace'], 1)
    if edit.get('delete'):
        return src.replace(find, '', 1)
    misses.append((path, 'edit names no action (replace/add_after/add_before/delete)'))
    return src


def simulate(ops):
    """({path: final text}, [(path, reason) misses], {paths this plan CREATES}).

    A MISS IS A PAIR, NOT A SENTENCE. The path travels as its own value because `check`
    needs it back to decide which file's parse verdict to withhold, and recovering it from
    a rendered line cannot be done safely: a colon is legal in a filename on macOS and on
    Linux, so `mod.py:v1: anchor not found` splits into the WRONG key. Rendering happens
    once, at the point of output.

    The third value exists so the verdict can say which claim it is making. "This file was
    edited and still parses" and "this file is new and parses" are different statements about
    different risks, and a checker that printed them identically would be committing the
    reporting sin this repo pins against everywhere else.

    Edits are threaded through a per-file accumulator IN ORDER, because a later `find` may
    exist only in the text an earlier `replace` produced. That is how the executor threads its
    own state, and a checker that disagreed with the executor about the resulting text would be
    worse than no checker at all.
    """
    files: dict = {}
    misses: list = []
    created: set = set()
    deleted: set = set()
    # Both schemas. LEGACY is `files: [{path, edits}]`; MODERN is `operations: [...]` carrying
    # file_create, code_edit, file_delete and run_command. A file_create of a .py file is
    # checked too -- a new file that does not parse is the same defect one step earlier.
    for f in ops.get('files') or []:
        path = f.get('path')
        src = files.get(path)
        if src is None:
            if not os.path.exists(path):
                misses.append((path, 'no such file to edit'))
                continue
            with open(path, encoding='utf-8-sig') as fh:
                src = fh.read()
        for edit in f.get('edits') or []:
            src = _apply(src, edit, path, misses)
        files[path] = src
    for op in ops.get('operations') or []:
        kind, path = op.get('type'), op.get('path')
        if kind == 'file_create':
            # `execute_file_create` indexes operation['content'] directly, so an absent key is
            # a KeyError there, not an empty file. Modelling it as '' would green-light a plan
            # that cannot run.
            if 'content' not in op:
                misses.append((path, 'file_create has no content key (the executor '
                                     'would KeyError on it)'))
                continue
            files[path] = op.get('content') or ''
            created.add(path)
            deleted.discard(path)
        elif kind == 'file_delete':
            files.pop(path, None)
            created.discard(path)
            deleted.add(path)
        elif kind == 'code_edit':
            src = files.get(path)
            if src is None:
                if path in deleted:
                    # The file is still on disk -- this plan has not run yet -- so a naive
                    # re-read would model an edit the executor cannot perform.
                    misses.append((path, 'edited after this same plan deletes it'))
                    continue
                if not os.path.exists(path):
                    misses.append((path, 'no such file to edit'))
                    continue
                with open(path, encoding='utf-8-sig') as fh:
                    src = fh.read()
            for edit in op.get('edits') or []:
                src = _apply(src, edit, path, misses)
            files[path] = src
    return files, misses, created


def _module_bound(node, out):
    """Names bound at MODULE level -- not inside a def or class body.

    Scope is the whole point. A function-local `html = ...` shadows nothing outside that
    function and is common and harmless; flagging it would be noise. What matters is a binding
    that replaces the import for the WHOLE FILE, which is what report_selfcheck.py:193 does --
    `html = report_render.PromptRows().row(p, 1)`, at module level, inside an `if`.

    So this descends through if / for / while / with / try bodies, and stops at def and class,
    whose bodies are a different scope. The def or class NAME still counts: that binding is
    module level.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(child.name)
            # A body is another scope -- EXCEPT for `global`, which reaches back into this
            # one. `global html` followed by an assignment rebinds the module name exactly as
            # a top-level statement would, so those names are collected and the rest of the
            # body is still skipped. Measured: without this, a rebind through `global` was
            # the one hazard of six probed that slipped through.
            #
            # Declared AND assigned, because `global x` on its own rebinds nothing.
            _declared = {n for g in ast.walk(child) if isinstance(g, ast.Global)
                         for n in g.names}
            if _declared:
                _assigned = set()
                for sub in ast.walk(child):
                    _tg = []
                    if isinstance(sub, ast.Assign):
                        _tg = sub.targets
                    elif isinstance(sub, (ast.AugAssign, ast.AnnAssign, ast.For)):
                        _tg = [sub.target]
                    for _t in _tg:
                        for _nm in ast.walk(_t):
                            if isinstance(_nm, ast.Name):
                                _assigned.add(_nm.id)
                out |= _declared & _assigned
            continue
        targets = []
        if isinstance(child, ast.Assign):
            targets = child.targets
        elif isinstance(child, (ast.AugAssign, ast.AnnAssign)):
            targets = [child.target]
        elif isinstance(child, ast.For):
            targets = [child.target]
        elif isinstance(child, ast.withitem) and child.optional_vars is not None:
            targets = [child.optional_vars]
        elif isinstance(child, ast.ExceptHandler) and child.name:
            out.add(child.name)
        for t in targets:
            for name in ast.walk(t):
                if isinstance(name, ast.Name):
                    out.add(name.id)
        _module_bound(child, out)


def shadowed(src, tree=None):
    """Imported names this file also rebinds at module level, so the import is not what runs.

    `import html` in report_selfcheck.py validated, parsed, placed correctly and was approved,
    then died on every capture with "'str' object has no attribute 'unescape'" -- the file had
    already bound the bare name to a rendered string. That is a runtime name binding, invisible
    to ast.parse, which is right to accept it.

    `tree` lets a caller that has ALREADY parsed this text hand the tree over instead of paying
    for a second parse; `check` does exactly that for the post-edit side. The baseline read has
    no such tree and parses its own.
    """
    tree = ast.parse(src) if tree is None else tree
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
    bound: set = set()
    _module_bound(tree, bound)
    return imported & bound


def _new_shadows(path, after, created, tree=None):
    """Names this edit NEWLY shadows -- diffed, never absolute.

    DIFF-AWARE ON PURPOSE. An absolute check fires on two aliases report_selfcheck.py already
    shadows (`_dc`, `_dcs`), and a gate that is noisy on day one gets muted, which is worse
    than not having it. Cleaning those up is a separate deliberate change, not something this
    should force as a side effect of an unrelated edit.

    A created file has no baseline, so everything it shadows is new -- correct, since a new
    file shadowing its own import is the same defect one step earlier.
    """
    before = set()
    if path not in created and os.path.exists(path):
        try:
            with open(path, encoding='utf-8-sig') as fh:
                before = shadowed(fh.read())
        except (OSError, SyntaxError):
            before = set()          # unreadable or already broken: report everything after
    return sorted(shadowed(after, tree) - before)


def _parsed_before(path, created):
    """Did `path` parse BEFORE this plan touched it?

    THE GATE IS DIFFERENTIAL, like `_new_shadows` beside it. It answers "did this plan
    break something", not "is this file perfect". Those differ whenever the file was
    already broken, and the absolute reading has two failure modes that the differential
    one does not:

      * it makes an already-unparseable .py UNEDITABLE through the engine unless a single
        plan happens to make the whole file parse -- so the Iron Law path cannot be used to
        repair a syntax error, which is precisely when it is most wanted;
      * it charges this plan for damage it did not do, and the report names the splice, so
        the author is sent to look at an edit that is innocent.

    A file this plan CREATES has no "before", and is judged absolutely: there is no
    pre-existing state to be innocent of.
    """
    if path in created:
        return True
    try:
        with open(path, encoding='utf-8-sig') as fh:
            ast.parse(fh.read(), filename=path)
    except SyntaxError:
        return False
    except OSError:
        # Unreadable now: no baseline can be established, so judge absolutely rather than
        # grant an exemption on the strength of a file we could not read. Fails closed.
        return True
    return True


def check(config_path, quiet=False):
    """(ok, [lines]) -- whether every touched .py parses, and what to print about it."""
    out, bad, unparsed = [], 0, 0
    try:
        with open(config_path, encoding='utf-8') as fh:
            ops = json.load(fh)
    except (OSError, ValueError) as exc:
        return False, ['CANNOT READ %s: %s' % (config_path, exc)]
    files, misses, created = simulate(ops)
    # WHOSE REFUSAL IS THIS? A missing or ambiguous anchor is NOT this module's to refuse, and
    # the port originally made it one. `execute_code_edit` already fails closed on both --
    # 'pattern-not-found' and 'ambiguous-pattern' -- and RESULT-JSON then names WHICH operation
    # failed, which is exactly what the implementer reads to know where to look. A gate that
    # refused first would turn every such plan into `operations: []` with a generic parse-gate
    # reason, destroying more diagnostic information than it added, and `tests/
    # test_ops_hardening.py::test_failed_run_reports_failed_status_in_result_json` pins that
    # contract.
    #
    # ORDERING INVARIANT (pinned by tests/test_ops_parse_gate.py): the AMBIGUITY verdict wins
    # over the parse verdict. It is expressed here, not by moving the gate's call site -- the
    # gate must still run before any write -- and it works by this module declining to refuse
    # what `execute_code_edit` diagnoses more precisely a moment later.
    #
    # So a miss is REPORTED, and it withholds the parse verdict for the file it touched
    # (below), but it does not fail this gate. Nothing is waved through by that: the executor
    # refuses the same plan a moment later, with a better message. This module refuses only
    # what it is the sole authority on -- Python that would not parse.
    for miss_path, miss_reason in misses:
        out.append('MISS  %s: %s' % (miss_path, miss_reason))
    # A file whose anchors did not all land is NOT reported as parsing. It would parse -- the
    # edit that was going to break it never got applied -- and printing "OK" there would be
    # the checker telling a true sentence that means the opposite of what a reader takes from
    # it. The verdict is withheld and said to be withheld.
    # THE PATH IS CARRIED, NOT RE-PARSED. This set was once rebuilt by splitting each
    # rendered miss on its first colon -- and a colon is legal in a filename on both macOS
    # and Linux. `mod.py:v1: anchor not found ...` then yielded the key `mod.py`, so a
    # DIFFERENT file named `mod.py` that this same plan genuinely broke matched here and was
    # printed as "not checked" instead of BREAK. Measured: that turned a refusal (ok=False)
    # into a pass (ok=True) on a plan whose result does not compile -- the exact silent pass
    # this module exists to prevent. A formatted string is a lossy channel for structured
    # data, so `misses` carries (path, reason) and the rendering happens above, at the
    # output. The other direction was a false claim rather than a hole: the colon-bearing
    # file itself fell OUT of this set and was reported "still parses" though its anchor
    # never landed.
    unresolved = {miss_path for miss_path, _ in misses}
    for path in sorted(files):
        if path in unresolved:
            out.append('?     %s not checked — an anchor above did not land, so the text '
                       'this would parse is not the text the executor would write' % path)
            continue
        # "Checked and it parses" and "not a Python file" must not print the same. The
        # project's standing rule -- "not captured" and "captured, and empty" are different
        # claims -- applies to a checker's own verdicts too.
        if not path.endswith(('.py', '.pyi')):
            out.append('skip  %s (not Python — this check has nothing to say about it)' % path)
            continue
        try:
            _tree = ast.parse(files[path], filename=path)
            # BOTH CLAIMS, ALWAYS. That the file parses and that it shadows nothing are
            # independent facts, and this module's own rule is to state distinct claims
            # distinctly rather than let one imply the other -- so the parse line is printed
            # even when the shadow check then refuses.
            out.append('OK    %s %s' % (path, 'is new and parses' if path in created
                                        else 'still parses after the edits in this plan'))
            # Parsing is not enough, and this is where that was learned. See `shadowed`.
            # The tree is handed over rather than re-derived: `shadowed` would otherwise pay
            # for a second parse of text just parsed on the line above.
            _shadows = _new_shadows(path, files[path], created, _tree)
            if _shadows:
                bad += 1
                out.append('SHADOW %s: %s' % (path, ', '.join(_shadows)))
                out.append('       imported here and also rebound at module level, so by the '
                           'time it is used the name is the assigned value, not the module. '
                           'Alias the import (the file already uses _dc, _dcv, _dcs, _dg).')
        except SyntaxError as exc:
            # PRE-EXISTING BREAKAGE IS NOT THIS PLAN'S. See `_parsed_before`. Reported either
            # way -- a withheld refusal that printed nothing would be a silent pass -- but
            # only NEW breakage refuses the run.
            if not _parsed_before(path, created):
                # NOT counted in `bad` -- it does not refuse the run -- but counted, because
                # --quiet promises silence when every touched file PARSES, and this one did
                # not. A suppressed PRE line would be exactly the silent pass this module
                # exists to prevent, one category over.
                unparsed += 1
                out.append('PRE   %s: %s at line %s — this file ALREADY did not parse before '
                           'the plan, so this gate does not refuse it. The edits here are not '
                           'the cause; fix the file, or land the repair in this same plan.'
                           % (path, exc.msg, exc.lineno))
                continue
            bad += 1
            out.append('BREAK %s: %s at line %s' % (path, exc.msg, exc.lineno))
            lines = files[path].splitlines()
            lo = max(0, (exc.lineno or 1) - 3)
            for n, line in enumerate(lines[lo:(exc.lineno or 1) + 1], lo + 1):
                out.append('   %5d | %s' % (n, line))
    if not files:
        out.append('note  this ops.json writes no files — nothing to parse')
    return bad == 0, ([] if quiet and bad == 0 and unparsed == 0 else out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('config', help='path to the ops.json')
    ap.add_argument('--quiet', action='store_true',
                    help='print nothing when every touched file parses')
    args = ap.parse_args()
    ok, lines = check(args.config, quiet=args.quiet)
    for line in lines:
        print(line)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
