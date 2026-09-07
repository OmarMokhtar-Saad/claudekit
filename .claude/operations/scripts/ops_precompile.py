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

WHOSE GRAMMAR. `ast.parse` uses the interpreter THIS GATE RUNS ON, not the target project's.
On a 3.9 floor a plan that adds a valid `match` statement is therefore refused as `invalid
syntax`, and there is no stdlib way to parse a grammar newer than the running interpreter
(`ast.parse(feature_version=...)` only lowers it, never raises it). A heuristic that guessed
"too new" would either fail open -- the silent pass this module exists to prevent -- or
misclassify a genuine break, so no guess is made: the `BREAK` line names the interpreter it
judged with, and `--no-parse-check` is the documented way past a refusal that is the gate's
age rather than the plan's defect.

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
import unicodedata


def _apply(src, edit, path, misses, spelling=None):
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
    def _miss(reason):
        # THE KEY GROUPS, THE SPELLING INFORMS. `check` builds the withheld-verdict set from
        # these paths, so the path must be the same `_canon` key the accumulator uses or the
        # withholding lands on nothing. But an author who wrote `./x.py` needs to find their
        # own line, so the spelling they used is stated in the reason when it differs.
        if spelling is not None and spelling != path:
            reason = 'written in this config as %s — %s' % (spelling, reason)
        misses.append((path, reason))

    find = edit.get('find')
    if not find:
        _miss('edit has no find pattern')
        return src
    seen = src.count(find)
    if seen == 0:
        _miss('anchor not found: %r' % (find[:60],))
        return src
    if seen > 1:
        _miss('anchor is ambiguous — it appears %d times, and the executor '
              'refuses an ambiguous match: %r' % (seen, find[:60]))
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
    if edit.get('delete') is True:
        return src.replace(find, '', 1)
    misses.append((path, 'edit names no action (replace/add_after/add_before/delete)'))
    return src


def _canon(path):
    """The executor's OWN path identity, so the gate and the writer agree on WHICH file.

    IT IS `os.path.relpath` AND NOTHING CLEVERER, deliberately. `execute_code_edit` keys its
    sim_state and its backup set on `os.path.relpath(str(file_path))`
    (execute-json-ops.py:684), so `x.py` and `./x.py` are ONE file there and used to be two
    here. Measured end to end: the gate read the alias fresh from disk, missed an anchor that
    an earlier operation would have written, withheld that file's verdict and exited 0 --
    "OK x.py still parses" -- while the executor applied both edits and left `A = (` on disk.

    A "better" canonicaliser is the wrong fix. `os.path.realpath` collapses a symlink alias
    too, but it stops being the executor's key, and a checker that models a DIFFERENT file
    identity than the writer is the divergence this function exists to close. Symlink
    aliasing is refused separately, by `_aliases`.
    """
    if not isinstance(path, str) or not path:
        return path
    return os.path.relpath(path)


_CASE_FOLD: dict = {}


def _case_insensitive(existing, st):
    """Does THIS device fold case? Probed once per `st_dev`, and it writes nothing.

    Case sensitivity is a property of the MOUNT, not of the operating system: APFS folds by
    default, ext4 does not, and one checkout can span both through a mounted subtree. So it
    cannot be a constant and it cannot be `sys.platform`.

    THE PROBE LEAVES NOTHING BEHIND. It takes an ancestor that already exists, swaps the case
    of that ancestor's OWN name, and stats it: the same `(st_dev, st_ino)` back means the
    kernel folded the two spellings. The obvious alternative -- `mkstemp` a two-cased name and
    look for its twin -- answers the same question but needs the directory to be writable and
    drops a file into the author's tree in the middle of a read-only check.

    UNDECIDABLE FOLDS TOWARD COLLAPSING. When no ancestor name carries a cased letter (`/`, a
    numeric-only path) or the walk cannot stat, the answer given is True. The two errors are
    NOT symmetric. Collapsing wrongly costs a FALSE REFUSAL -- loud, in the report, and fixed
    by naming the file once. Staying distinct wrongly reopens exactly the hole this exists to
    close: gate exit 0, `Errors: 0`, unparseable Python on disk. The quiet error is the unsafe
    one, so the probe fails toward the loud one.
    """
    if st.st_dev in _CASE_FOLD:
        return _CASE_FOLD[st.st_dev]
    result, cur, cur_st = True, existing, st
    while True:
        parent, base = os.path.dirname(cur), os.path.basename(cur)
        # NEVER ANSWER FROM ANOTHER DEVICE. The verdict is cached under `st.st_dev`, and
        # swapping a component's case looks that NAME up in its PARENT directory -- so the
        # device that decides the answer is the parent's, not `cur`'s. When `existing` is
        # itself a mount point, its name lives in the parent mount: a case-insensitive volume
        # mounted inside a case-sensitive tree would be probed against the case-sensitive
        # parent, cached as sensitive, and its aliases would then stay distinct -- the silent
        # exit-0 hole this module exists to close. Refusing the probe leaves `result` True,
        # which collapses: loud, not silent.
        #
        # An earlier version of this guard compared `cur_st.st_dev` with `st.st_dev`, which on
        # the first iteration compares a value with itself and can never differ. The test
        # caught it; reasoning about it had not.
        try:
            if os.stat(parent).st_dev != st.st_dev:
                break
        except OSError:
            break
        swapped = base.swapcase()
        if swapped != base:
            try:
                other = os.stat(os.path.join(parent, swapped))
                result = (other.st_dev, other.st_ino) == (cur_st.st_dev, cur_st.st_ino)
            except OSError:
                result = False          # the swapped name is absent: this device is sensitive
            break
        if parent == cur:
            break                       # nothing cased anywhere up the path: collapse
        cur = parent
        try:
            cur_st = os.stat(cur)
        except OSError:
            break                       # cannot probe: collapse
    _CASE_FOLD[st.st_dev] = result
    return result


def _fold(component, case_insensitive):
    """One path component as the FILESYSTEM would compare it.

    RESIDUAL, STATED BECAUSE IT IS THE SAME CLASS: Apple's on-disk normalisation is not strict
    Unicode NFD -- it diverges for codepoints added after Unicode 3.2 -- so for those
    codepoints `normalize('NFC', ...)` can disagree with what the filesystem itself folds.
    That residual is confined to paths that DO NOT EXIST YET, because an existing path is
    keyed by `(st_dev, st_ino)`, which is the kernel's own answer and cannot be wrong. A
    plan naming a not-yet-created file twice, in two normalisations, using such a codepoint,
    is the one shape still unmodelled here.

    NFC ALWAYS. macOS normalises the names it stores, so `café.py` written NFD is read back
    NFC and the two spellings are one file -- and a plan carrying both escaped every earlier
    fix. A filesystem that does not normalise makes them two files, and folding them there is
    a false refusal, which is the loud direction (see `_case_insensitive`). Probing
    normalisation the way case is probed is not possible without writing, because it needs a
    name whose own spelling is decomposable.

    Lowercasing ONLY where the device was measured to fold case.
    """
    component = unicodedata.normalize('NFC', component)
    return component.lower() if case_insensitive else component


def _identity(path):
    """What the KERNEL would call this path -- for a file that exists AND one that does not.

    THIS IS THE SECOND OF TWO KEYS, AND THE SPLIT IS DELIBERATE. `_canon` is
    `os.path.relpath` because it must equal the EXECUTOR's own accumulator key
    (execute-json-ops.py:684); a checker that modelled a different file identity than the
    writer is the divergence that key exists to close. This one answers a different question
    -- "do two of the plan's keys name one file?" -- and is used only by `_aliases`.

    FOUR ROUNDS OF REVIEW SAY LEXICAL IDENTITY CANNOT ANSWER IT. `os.path.relpath` missed
    `./x.py`; `os.path.realpath` missed `X.py` on a case-insensitive filesystem;
    `(st_dev, st_ino)` closed both and hardlinks with them, but an inode can only be read for
    a path ALREADY ON DISK -- so every `file_create` target fell back to a lexical realpath,
    which is precisely what the first two rounds disproved. Reproduced end to end three ways
    (`file_create new.py` + `code_edit New.py`; create through a symlinked directory and edit
    through the real one; `sub/n.py` and `SUB/n.py`): `ok=True`, executor exit 0, `Errors: 0`,
    unparseable file on disk.

    SO THE KEY IS AN INODE PLUS FOLDED COMPONENTS. Resolve the symlinks, walk up to the
    nearest ancestor that EXISTS, key that ancestor by `(st_dev, st_ino)` -- the kernel's own
    answer -- and append the components that do not exist yet, each folded by that device's
    measured rules. A path already on disk yields a bare inode key exactly as before; a path
    that does not exist yet is anchored to a real inode instead of to a string.

    `os.path.realpath` FIRST, NOT INSTEAD. It resolves a symlinked directory in the middle of
    the path, and it resolves a DANGLING link to the target it points at -- so a plan that
    creates `pkg/m.py` and edits a broken `sym.py` aimed there is still one file. Dropping it
    in favour of the ancestor walk alone regressed that pair to two keys.

    OUTSIDE THE PROJECT ROOT IS STILL ONE FILE. The key is absolute, so `../other/x.py` gets
    a real identity rather than an escape-shaped string; whether the plan is ALLOWED to write
    there is a different gate's question and the executor's path guard answers it.
    """
    try:
        cur = os.path.realpath(os.path.abspath(path))
    except OSError:
        cur = os.path.abspath(path)
    tail = []
    while True:
        try:
            st = os.stat(cur)
            break
        except OSError:
            parent = os.path.dirname(cur)
            if parent == cur:
                # NO ANCESTOR EXISTS AT ALL -- an absolute path on a device that is not
                # mounted, or a root that cannot be stat'd. There is no inode to anchor to,
                # so this degrades to a lexical key, but a FOLDED one: the case and
                # normalisation aliases still collapse instead of reopening the hole. Nothing
                # can be written there either, so the executor fails on the same path a
                # moment later.
                return ('lex',) + tuple(
                    _fold(c, True) for c in os.path.abspath(path).split(os.sep))
            tail.append(os.path.basename(cur))
            cur = parent
    if not tail:
        return ('ino', st.st_dev, st.st_ino)
    folds = _case_insensitive(cur, st)
    return ('ino', st.st_dev, st.st_ino) + tuple(
        _fold(c, folds) for c in reversed(tail))


def _aliases(paths):
    """Distinct keys in one plan that name ONE file: {identity: [keys]}.

    `pkg/m.py` plus a symlink `sym.py` pointing at it are two `os.path.relpath` keys and one
    file, and NEITHER side models it: this gate reads `sym.py` before the executor's earlier
    write to `pkg/m.py` has happened, and the executor writes through `os.replace`, which
    REPLACES the symlink with a regular file rather than following it. Measured: gate exit 0,
    `sym.py` unparseable afterwards. A gate that cannot model a plan must fail closed rather
    than withhold, so this is a refusal.

    IDENTITY COMES FROM `_identity`, WHICH ASKS THE FILESYSTEM, NOT FROM A STRING. Every
    lexical canonicaliser tried here was measurably defeated by the next spelling -- see
    `_identity` for the four rounds and the reproductions. The invariant, and not any one
    spelling, is what
    tests/test_ops_parse_gate.py::test_the_identity_is_invariant_under_every_alias_spelling
    pins; the folds that this machine's filesystem does not perform SKIP there with a reason
    rather than passing for the wrong reason.

    OVER-REFUSAL IS THE FAILURE DIRECTION THAT WOULD BLOCK EVERY FUTURE CHANGE, so it is
    measured, not asserted: all 601 archived ops configs in `.claude/plans/archive` were swept
    through this function and NONE was flagged, before the change and after it.
    """
    groups: dict = {}
    for p in paths:
        if not isinstance(p, str) or not p:
            continue
        try:
            key = _identity(p)
        except (OSError, ValueError):
            # A path the OS refuses to even look at (an embedded NUL). The validator refuses
            # such a config outright; dropping it here is not a hole, it is a shape that
            # never reaches the writer.
            continue
        groups.setdefault(key, []).append(p)
    return {k: sorted(ks) for k, ks in groups.items() if len(ks) > 1}


def _normalize(ops):
    """LEGACY `files` -> MODERN `operations`, in the EXECUTOR's precedence.

    `normalize_config` (execute-json-ops.py:313) returns the config UNCHANGED whenever
    `operations` is present, discarding `files` entirely. This module used to process both
    keys always, so a config carrying both was simulated as a plan the executor would never
    run. Reproduced in both directions -- a silent pass to an unparseable tree, and a refusal
    of a config that runs cleanly -- and reachable on a default install, where without
    `jsonschema` the validator skips the schema check and reports APPROVED on such a config.

    THE PIN COVERS THE CONFIGS THE EXECUTOR ACCEPTS, and says so rather than claiming more:
    differential fuzzing found six malformed shapes where this and `normalize_config`
    disagree (`files: null` raises there and returns [] here, and five shapes where it
    returns None and this converts anyway). Every one of those aborts the run before any
    write, so the divergence is in the permissive-but-harmless direction -- but the pin is
    three well-formed configs, not a proof of total agreement.

    ON THE EXECUTOR'S PATH THIS IS A NO-OP. `check_parses` hands `check` the dict
    `normalize_config` already produced, so there is exactly ONE normaliser in production.
    This branch serves the standalone CLI, and its agreement with the executor's is pinned
    by tests/test_ops_parse_gate.py::test_the_gate_normaliser_agrees_with_the_executors.
    """
    if not isinstance(ops, dict):
        return {'operations': []}
    if 'operations' in ops:
        return ops
    converted = []
    for f in ops.get('files') or []:
        if not isinstance(f, dict):
            continue
        converted.append({'type': 'code_edit', 'path': f.get('path'),
                          'edits': f.get('edits')})
    return dict(ops, operations=converted)


def simulate(ops):
    """({path: final text}, [(path, reason) misses], {CREATES}, {DELETES}, {NAMES}).

    THE FIFTH VALUE IS EVERY PATH THE CONFIG NAMES, and it is separate from the four
    above because those are what this module could MODEL. A `code_edit` of a path that is
    not on disk yet is recorded as a miss and skipped -- so it entered none of the other
    sets, and the alias check in `check` never saw it. Measured: `file_create new.py` plus
    `code_edit New.py` on a case-folding filesystem, gate exit 0, executor `Errors: 0`,
    unparseable file on disk. Alias detection is a question about the paths the plan NAMES,
    not about the subset the checker managed to simulate.

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
    ops = _normalize(ops)
    files: dict = {}
    misses: list = []
    created: set = set()
    deleted: set = set()
    named: set = set()
    # ONE SCHEMA, ONE IDENTITY. `_normalize` above has already applied the executor's
    # `operations`-wins precedence, so the LEGACY `files` key is no longer read here; and
    # every accumulator below is keyed on `_canon(path)`, which is the executor's own key.
    # Both of those were divergences, and both were reachable past a clean validator.
    for op in ops.get('operations') or []:
        kind, spelling = op.get('type'), op.get('path')
        path = _canon(spelling)
        if kind == 'run_command':
            # No path and no modelled writes. Reported once, in `check`, so the verdict says
            # what it does not cover instead of implying it covered everything.
            continue
        if not isinstance(path, str) or not path:
            misses.append(('<no path>', 'operation of type %r names no path, and the '
                                        'executor refuses such a config' % (kind,)))
            continue
        # NAMED BEFORE MODELLED. Every branch below can decline to model this path -- a
        # missing file to edit, an anchor that did not land -- and the alias check must
        # still see it, because two spellings of ONE file is exactly the case where one
        # of them cannot be modelled.
        named.add(path)
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
                src = _apply(src, edit, path, misses, spelling)
            files[path] = src
    return files, misses, created, deleted, named


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


def check(config, quiet=False):
    """(ok, [lines]) -- whether every touched .py parses, and what to print about it.

    `config` is EITHER an already-normalised config dict OR a path to an ops.json. The
    executor passes the dict `normalize_config` produced, so the gate simulates the same
    plan the writer will run instead of re-deriving it from the file and disagreeing about
    which schema key wins. See `_normalize`; the path form serves the standalone CLI.
    """
    out, bad, unparsed = [], 0, 0
    if isinstance(config, dict):
        ops = config
    else:
        try:
            with open(config, encoding='utf-8') as fh:
                ops = json.load(fh)
        except (OSError, ValueError) as exc:
            return False, ['CANNOT READ %s: %s' % (config, exc)]
    files, misses, created, deleted, named = simulate(ops)
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
    # ONE FILE UNDER TWO NAMES. See `_aliases`. REFUSED, not withheld: a withheld verdict
    # exits 0, and the measured consequence of exiting 0 here was an unparseable file on
    # disk. This is the one case where the gate refuses something that is not itself a
    # SyntaxError, because it is not deferring to a better diagnosis later -- the executor
    # has none for this, it simply writes both.
    # The union, not just `files`: a plan that DELETES pkg/m.py and edits a symlink to it is
    # the same unmodellable shape, and checking only `files` pronounced `OK sym.py still
    # parses` on it. `created` is in `files` already, but naming it here keeps the set honest
    # if that ever changes.
    # `named` FIRST, and it is the set that matters: the others are only what could be
    # modelled, and an unmodellable spelling is the whole hazard. They stay in the union so
    # the set cannot shrink if `named` is ever narrowed.
    for _ident, _keys in sorted(
            _aliases(named | set(files) | deleted | created).items(), key=repr):
        bad += 1
        # Name a PATH, never the identity. The group key is an inode tuple, possibly with
        # folded components appended for a path that does not exist yet (see `_identity`),
        # so printing the key put a bare inode number where the reader needs something
        # they can open.
        try:
            _one = os.path.realpath(_keys[0])
        except OSError:
            _one = _keys[0]
        out.append('ALIAS %s: this plan names one file (%s) %d ways. Neither this gate nor '
                   'the executor models that -- the writes go through os.replace, which '
                   'REPLACES a symlink instead of following it. Name the file once, by one '
                   'path.' % (', '.join(_keys), _one, len(_keys)))
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
                           'the plan, so this gate does not refuse it. Whether the edits in '
                           'this plan also break it cannot be told apart from the '
                           'pre-existing error, because only the final text is parsed; fix '
                           'the file, or land the repair in this same plan.'
                           % (path, exc.msg, exc.lineno))
                continue
            bad += 1
            out.append('BREAK %s: %s at line %s (as CPython %d.%d reads it -- this gate '
                       'parses with the interpreter it runs on, so syntax newer than that '
                       'is reported as invalid; see WHOSE GRAMMAR above)'
                       % (path, exc.msg, exc.lineno,
                          sys.version_info[0], sys.version_info[1]))
            lines = files[path].splitlines()
            lo = max(0, (exc.lineno or 1) - 3)
            for n, line in enumerate(lines[lo:(exc.lineno or 1) + 1], lo + 1):
                out.append('   %5d | %s' % (n, line))
    if not files:
        out.append('note  this ops.json writes no files — nothing to parse')
    # WHAT THIS VERDICT DOES NOT COVER, said rather than implied. A run_command may rewrite
    # any file in the tree after this gate has pronounced on it, and nothing here models
    # that. The project's standing rule -- distinct claims stated distinctly -- applies to
    # the boundaries of a claim too.
    if any(isinstance(op, dict) and op.get('type') == 'run_command'
           for op in (_normalize(ops).get('operations') or [])):
        out.append('note  this ops.json also runs run_command operations, whose writes are '
                   'not modelled here — a file this gate calls parseable can still be '
                   'rewritten by a command afterwards')
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
