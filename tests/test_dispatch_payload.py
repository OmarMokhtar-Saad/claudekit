"""Behavioural coverage for the dispatcher's payload transport.

The regression under test: `dispatch.sh` passed the tool payload to its resolver
through the ENVIRONMENT, because a heredoc occupied stdin. Past `ARG_MAX`
(1048576) `execve` returns `E2BIG`, the resolver never starts, and a blocking
event exits 2 — so writing a >1 MB file was refused, with a message naming
neither the size nor the cause.

Everything here drives the real `dispatch.sh` with a real registry and asserts on
its exit code and stderr. Nothing inspects source text.
"""

import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DISPATCH = os.path.join(REPO_ROOT, '.claude', 'hooks', 'dispatch.sh')
RESOLVER = os.path.join(REPO_ROOT, '.claude', 'hooks', 'dispatch_resolve.py')
REGISTRY = os.path.join(REPO_ROOT, '.claude', 'hooks', 'dispatch-registry.json')


def _dispatch(event, payload, profile='standard', timeout=120):
    """Run the real dispatcher on a real payload. Returns CompletedProcess."""
    env = dict(os.environ, ECC_HOOK_PROFILE=profile)
    env.pop('CK_PAYLOAD', None)
    return subprocess.run(
        ['bash', DISPATCH, event],
        input=payload, capture_output=True, text=True,
        cwd=REPO_ROOT, env=env, timeout=timeout,
    )


def _write_payload(size_bytes):
    """A structurally valid `Write` payload whose content reaches `size_bytes`."""
    body = {
        'tool_name': 'Write',
        'tool_input': {'file_path': '/tmp/ck-payload-probe.txt', 'content': ''},
    }
    overhead = len(json.dumps(body))
    filler = 'x' * max(0, size_bytes - overhead)
    body['tool_input']['content'] = filler
    return json.dumps(body)


class TestLargePayloadIsNotRefused(unittest.TestCase):
    """The headline proof: a 2 MB payload must not be blocked by transport."""

    def test_a_two_megabyte_write_payload_returns_zero(self):
        payload = _write_payload(2 * 1024 * 1024)
        self.assertGreater(len(payload), 2 * 1024 * 1024 - 1024)
        proc = _dispatch('PreToolUse', payload)
        self.assertEqual(
            proc.returncode, 0,
            'a %d-byte payload was refused by the dispatcher:\n%s\n%s'
            % (len(payload), proc.stdout, proc.stderr))
        self.assertNotIn('could not resolve hook handlers', proc.stderr)

    def test_a_payload_just_over_the_old_arg_max_boundary_returns_zero(self):
        """1020 KB is the size the backlog measured failing at rc 2."""
        proc = _dispatch('PreToolUse', _write_payload(1020 * 1024))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_no_broken_pipe_leaks_onto_hook_stderr(self):
        """A handler exiting before draining stdin must not SIGPIPE the writer."""
        proc = _dispatch('PreToolUse', _write_payload(256 * 1024))
        self.assertNotIn('Broken pipe', proc.stderr)
        self.assertNotIn('write error', proc.stderr)

    def test_a_two_megabyte_write_to_a_guarded_path_is_still_blocked(self):
        """The fail-closed half. "Large payloads are allowed" must mean "transport no
        longer decides", NOT "size buys a pass". Without this, every assertion in this
        class is satisfied by a dispatcher that resolves no handlers at all, which is
        precisely the fail-open the ARG_MAX fix had to avoid re-introducing at the top
        of the pipe instead of the bottom. The guard's OWN reason must appear: a
        refusal naming the resolver would mean the block came from transport again.
        """
        payload = json.loads(_write_payload(2 * 1024 * 1024))
        payload['tool_input']['file_path'] = os.path.join(REPO_ROOT, 'src',
                                                          'claudekit', '__init__.py')
        proc = _dispatch('PreToolUse', json.dumps(payload))
        self.assertEqual(
            proc.returncode, 2,
            'a 2 MB direct write to a guarded source file was not blocked:\n%s\n%s'
            % (proc.stdout, proc.stderr))
        self.assertIn('OPS ENFORCEMENT', proc.stdout + proc.stderr,
                      'blocked, but not for the guard\'s own reason -- a transport '
                      'refusal would satisfy the exit code alone:\n%s\n%s'
                      % (proc.stdout, proc.stderr))
        self.assertNotIn('could not resolve hook handlers', proc.stderr)


class TestFailClosedIsPreserved(unittest.TestCase):
    """Moving the payload off the environment must not weaken any refusal.

    The registry path is deliberately NOT overridable by an environment variable:
    a caller who could point the dispatcher at an empty registry could make it
    resolve zero handlers and allow everything. So the failure paths are exercised
    by copying the hooks tree and corrupting the copy, which is what a real broken
    install looks like anyway.
    """

    def _hooks_copy(self, mutate):
        """A working copy of .claude/hooks with `mutate(dir)` applied."""
        tmp = tempfile.mkdtemp(prefix='ck-hooks-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        dest = os.path.join(tmp, 'hooks')
        shutil.copytree(os.path.join(REPO_ROOT, '.claude', 'hooks'), dest)
        mutate(dest)
        return dest

    def _run_copy(self, hooks_dir, payload, event='PreToolUse'):
        env = dict(os.environ, ECC_HOOK_PROFILE='standard')
        env.pop('CK_PAYLOAD', None)
        return subprocess.run(
            ['bash', os.path.join(hooks_dir, 'dispatch.sh'), event],
            input=payload, capture_output=True, text=True,
            cwd=REPO_ROOT, env=env, timeout=120)

    def test_a_malformed_payload_still_fails_closed_on_a_blocking_event(self):
        """Blocking, not merely "0 or 2".

        An earlier revision asserted `returncode in (0, 2)`, which cannot detect a
        fail-OPEN — the exact thing the test name claims to prove. On PreToolUse
        under the standard profile, ops-enforcement refuses an unparseable payload,
        so the answer is 2 and the test says 2.
        """
        proc = _dispatch('PreToolUse', 'not json at all')
        self.assertEqual(proc.returncode, 2,
                         'a malformed payload did not BLOCK on a blocking event '
                         '(rc=%s):\n%s' % (proc.returncode, proc.stderr))
        self.assertTrue(proc.stderr.strip(), 'a block must carry a reason on stderr')

    def test_an_unresolvable_registry_blocks_and_does_not_leak_a_broken_pipe(self):
        """The resolver's exit-3 path, with a payload big enough to fill the pipe.

        This is what proves stdin is drained BEFORE the registry is opened: if it
        were not, the writing printf would take SIGPIPE here.
        """
        def corrupt(d):
            with open(os.path.join(d, 'dispatch-registry.json'), 'w') as fh:
                fh.write('{ not valid json')
        hooks = self._hooks_copy(corrupt)
        proc = self._run_copy(hooks, _write_payload(512 * 1024))
        self.assertEqual(proc.returncode, 2,
                         'an unreadable registry did not fail closed:\n' + proc.stderr)
        self.assertNotIn('Broken pipe', proc.stderr)
        self.assertNotIn('write error', proc.stderr)

    def test_the_refusal_names_the_size_and_the_resolver_exit_code(self):
        """A refusal an operator cannot diagnose is most of why this sat unfixed."""
        def corrupt(d):
            with open(os.path.join(d, 'dispatch-registry.json'), 'w') as fh:
                fh.write('{ not valid json')
        hooks = self._hooks_copy(corrupt)
        payload = _write_payload(4096)
        proc = self._run_copy(hooks, payload)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn(str(len(payload)), proc.stderr,
                      'the refusal does not name the payload size:\n' + proc.stderr)
        self.assertIn('rc=3', proc.stderr,
                      'the refusal does not name the resolver exit code:\n'
                      + proc.stderr)

    def test_a_missing_resolver_fails_closed_rather_than_allowing(self):
        """The catastrophe install.sh's own comment is about: `python3 <missing>`."""
        def remove(d):
            os.remove(os.path.join(d, 'dispatch_resolve.py'))
        hooks = self._hooks_copy(remove)
        # >= 256 KB deliberately: the pipe buffer is ~64 KB, so a 4096-byte payload
        # (what an earlier revision used) fits entirely and the writer never blocks,
        # which made this structurally unable to see the Broken pipe leak it now
        # guards. The resolver dies before reading here, so this is the path where
        # draining stdin first does NOT help and the writer's stderr must be redirected.
        proc = self._run_copy(hooks, _write_payload(256 * 1024))
        self.assertEqual(proc.returncode, 2,
                         'a missing resolver did not fail closed:\n' + proc.stderr)
        self.assertNotIn('Broken pipe', proc.stderr,
                         'the writer leaked SIGPIPE noise above the BLOCKED line:\n'
                         + proc.stderr)
        self.assertNotIn('write error', proc.stderr, proc.stderr)


class TestResolverIsAHelperNotAHook(unittest.TestCase):
    """The resolver must ship, and must not inflate the published hook count."""

    def test_the_resolver_ships_beside_the_dispatcher(self):
        self.assertTrue(os.path.exists(RESOLVER), RESOLVER)

    def test_the_published_hook_count_does_not_count_the_resolver(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'gen_docs', os.path.join(REPO_ROOT, 'scripts', 'gen-docs.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        files = module._hook_files()
        names = [p.name for p in files]
        self.assertIn('dispatch_resolve.py', names,
                      'the resolver is not even seen by the counter, so this test '
                      'would pass for the wrong reason')
        self.assertTrue(
            module._is_helper_module(
                next(p for p in files if p.name == 'dispatch_resolve.py'), files),
            'the resolver is counted as a HOOK, which inflates the published count '
            'and reddens gen-docs --check; a shell-invoked .py is a helper')


class TestAdvisoryHooksCannotSilentlyGainABlock(unittest.TestCase):
    """The clamp and the artifacts must not drift apart.

    This class DOES inspect source text, unlike the rest of the module: the property
    is "no exit-2 path exists", and a hook with no such path cannot be driven into
    demonstrating its absence. The grep is anchored to a statement rather than the
    bare string, so a comment mentioning `exit 2` is not a false red and
    `exit "$RC"` is not a false green.

    Four PreToolUse handlers are `tier: "advisory"` in dispatch-registry.json, so
    any `exit 2` they grow would be silently clamped to ADVISE. None has one
    today; this asserts that stays true, so the clamp cannot quietly disarm a
    guard whose author believed it blocks.
    """

    ADVISORY = ('file-guard-gate', 'security-reminder', 'pre-commit', 'pre-push')

    def test_the_advisory_pretooluse_handlers_have_no_exit_2_path(self):
        with open(REGISTRY, encoding='utf-8') as handle:
            registry = json.load(handle)
        rows = {r['id']: r for r in registry.get('events', {}).get('PreToolUse', [])}
        checked = 0
        for hook_id in self.ADVISORY:
            row = rows.get(hook_id)
            if row is None:
                continue
            self.assertEqual(row.get('tier'), 'advisory', hook_id)
            path = os.path.join(REPO_ROOT, '.claude', 'hooks', row['file'])
            if not os.path.exists(path):
                continue
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
            self.assertIsNone(
                re.search(r'^\s*exit\s+2\b', text, re.M),
                '%s is clamped to ADVISE but now has an `exit 2` statement, so it '
                'believes it blocks and silently does not. Either promote its tier '
                'or remove the exit.' % hook_id)
            checked += 1
        self.assertEqual(checked, len(self.ADVISORY),
                         'only %d of %d advisory handlers were checked; a renamed or '
                         'removed registry row would silently shrink this test'
                         % (checked, len(self.ADVISORY)))


class TestUndecodablePayloadDoesNotDisarmTheDispatcher(unittest.TestCase):
    """F1: an invalid-UTF-8 payload must not silently skip every handler.

    The transport this replaced read `os.environ`, which decodes with
    `surrogateescape` and cannot raise. Text-mode stdin decodes with
    `errors='strict'` under a normal user locale, so one bad byte raised
    UnicodeDecodeError, the resolver exited 1, and handler resolution produced
    NOTHING -- measured 10 handlers to 0 on a non-blocking event, with no test able
    to see it because the suite never sets a locale.
    """

    @staticmethod
    def _run(event, payload_bytes, locale='en_US.UTF-8'):
        env = dict(os.environ, ECC_HOOK_PROFILE='standard',
                   LC_ALL=locale, LANG=locale)
        env.pop('CK_PAYLOAD', None)
        return subprocess.run(
            ['bash', DISPATCH, event],
            input=payload_bytes, capture_output=True,
            cwd=REPO_ROOT, env=env, timeout=120)

    @staticmethod
    def _payload_with_an_invalid_byte():
        body = json.dumps({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/tmp/ck-locale-probe.txt', 'content': 'X'},
        })
        return body.encode('utf-8').replace(b'X', b'\xff')

    def test_a_non_blocking_event_still_resolves_its_handlers(self):
        payload = self._payload_with_an_invalid_byte()
        proc = self._run('PostToolUse', payload)
        self.assertEqual(proc.returncode, 0,
                         proc.stdout.decode('utf-8', 'replace')
                         + proc.stderr.decode('utf-8', 'replace'))
        err = proc.stderr.decode('utf-8', 'replace')
        self.assertNotIn('UnicodeDecodeError', err)
        self.assertNotIn('could not resolve hook handlers', err,
                         'an undecodable payload disarmed handler resolution:\n' + err)

    def test_a_blocking_event_is_not_refused_for_a_transport_reason(self):
        payload = self._payload_with_an_invalid_byte()
        proc = self._run('PreToolUse', payload)
        err = proc.stderr.decode('utf-8', 'replace')
        self.assertNotIn('UnicodeDecodeError', err)
        self.assertNotIn('could not resolve hook handlers', err,
                         'the resolver failed to START on an undecodable payload, so '
                         'the refusal is a transport artefact rather than a verdict:\n'
                         + err)


class TestReflectionGateBlocksOnAnUnparseablePayload(unittest.TestCase):
    """The hard-rule-2 half of the stdin change, bound to the EXIT CODE.

    Unpatched, `read_event` decoded stdin in text mode, so one invalid UTF-8 byte
    raised out of it, nothing caught it, and the hook died with a traceback and
    `rc 1` -- neither 0 nor 2, which CLAUDE.md hard rule 2 forbids and the host reads
    as NON-blocking.

    This asserts `rc == 2` and the gate's own reason. The only test that reddened
    under the text-mode mutant asserted the ABSENCE of a traceback, which a later
    refactor to `return {}` on decode failure would satisfy while restoring the
    fail-open -- a blocking contract with no test on its exit code.
    """

    GATE = os.path.join(REPO_ROOT, '.claude', 'hooks', 'reflection-gate.py')
    REASON = 'could not parse the tool payload'

    @staticmethod
    def _run(payload_bytes, profile='standard'):
        env = dict(os.environ, ECC_HOOK_PROFILE=profile,
                   LC_ALL='en_US.UTF-8', LANG='en_US.UTF-8')
        env.pop('CK_PAYLOAD', None)
        return subprocess.run(
            [sys.executable,
             os.path.join(REPO_ROOT, '.claude', 'hooks', 'reflection-gate.py'),
             '--event', 'PreToolUse'],
            input=payload_bytes, capture_output=True,
            cwd=REPO_ROOT, env=env, timeout=120)

    def test_an_invalid_utf8_payload_exits_two_with_a_reason(self):
        proc = self._run(b'{"tool_name": "Write", "x": "\xff\xfe"')
        err = proc.stderr.decode('utf-8', 'replace')
        self.assertEqual(proc.returncode, 2,
                         'a payload the gate cannot parse must block, not pass: '
                         'rc=%s\n%s' % (proc.returncode, err))
        self.assertIn(self.REASON, err, err)
        self.assertNotIn('UnicodeDecodeError', err, err)
        self.assertNotIn('Traceback', err, err)

    def test_an_undecodable_byte_alone_does_not_change_the_verdict(self):
        """A payload that is valid JSON apart from one undecodable byte must be
        JUDGED, not refused for a transport reason -- the same invariant the
        dispatcher preserves. surrogateescape keeps it parseable, so the gate reaches
        its normal path and returns 0 with nothing pending."""
        body = json.dumps({'tool_name': 'Read',
                           'tool_input': {'file_path': '/tmp/ck-probe.txt'},
                           'pad': 'X'}).encode('utf-8').replace(b'X', b'\xff')
        proc = self._run(body)
        err = proc.stderr.decode('utf-8', 'replace')
        self.assertNotIn(self.REASON, err,
                         'an undecodable byte made a parseable payload unparseable, '
                         'so the gate blocked on transport rather than on merit:\n'
                         + err)
        self.assertNotIn('Traceback', err, err)


class TestRegisteredHooksAreNotMisclassifiedAsHelpers(unittest.TestCase):
    """F5's converse. Narrowing helper-detection must not swallow a real hook.

    Two false-positive shapes were measured, both silently taking the published
    count 22 -> 21 with every test green: matching the filename anywhere (a real
    hook is discussed in another hook's comments), and requiring only an
    interpreter on the same line (prose in a comment or docstring still matched).
    Asserting only that the resolver IS a helper is one-directional and would have
    passed for both.
    """

    @staticmethod
    def _gen_docs():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'gen_docs', os.path.join(REPO_ROOT, 'scripts', 'gen-docs.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_registered_handler_classifies_as_a_hook(self):
        module = self._gen_docs()
        files = module._hook_files()
        by_name = {p.name: p for p in files}
        with open(REGISTRY, encoding='utf-8') as handle:
            registry = json.load(handle)
        registered = {row['file']
                      for rows in registry.get('events', {}).values()
                      for row in rows if isinstance(row, dict) and row.get('file')}
        self.assertTrue(registered, 'no registered handlers found to check')
        checked = 0
        for name in sorted(registered):
            path = by_name.get(name)
            if path is None:
                continue
            self.assertFalse(
                module._is_helper_module(path, files),
                '%s is a REGISTERED handler but classifies as a helper, so it is '
                'missing from the published hook count' % name)
            checked += 1
        expected = len(registered & {p.name for p in files})
        self.assertEqual(checked, expected,
                         'only %d of %d registered handlers were checked; a registry '
                         'rename would leave this green on almost nothing'
                         % (checked, expected))
        self.assertGreater(checked, 0, 'no registered handler was actually checked')
        # dispatch.sh and post-implement.sh are counted hooks that no registry row
        # names, so the loop above never reaches them. Assert them explicitly rather
        # than leaving two of the 22 uncovered.
        for name in ('dispatch.sh', 'post-implement.sh'):
            path = by_name.get(name)
            if path is not None:
                self.assertFalse(
                    module._is_helper_module(path, files),
                    '%s is a hook but classifies as a helper' % name)


class TestExportedMergeIsCovered(unittest.TestCase):
    """`decisions.merge` is re-exported public API and had zero coverage.

    Mutating `worst = ALLOW` -> `worst = DENY` (making every merge return DENY) left
    the full suite green at 1951 passed. It has no caller in this repo, but
    `claudekit.enforcement` re-exports it, so it is API someone can depend on — which
    is why it is tested rather than deleted. The merge that actually RUNS is the bash
    arithmetic in dispatch.sh, mutation-proven separately by test_dispatch_merge.py.

    These tests were once written straight into the ops config's embedded content and
    then lost when that content was refreshed from its source file. That is why they
    live here, in the file the config reads.
    """

    @staticmethod
    def _decisions():
        src = os.path.join(REPO_ROOT, 'src')
        if src not in sys.path:
            sys.path.insert(0, src)
        from claudekit.enforcement import decisions
        return decisions

    def test_merge_returns_the_most_restrictive_of_every_pair_and_triple(self):
        d = self._decisions()
        order = [d.ALLOW, d.ADVISE, d.ERROR, d.DENY]
        for n in (1, 2, 3):
            for combo in itertools.product(order, repeat=n):
                self.assertEqual(
                    int(d.merge(combo)), int(max(combo)),
                    'merge%r disagreed with most-restrictive-wins' % (combo,))

    def test_merge_of_nothing_is_allow(self):
        d = self._decisions()
        self.assertEqual(int(d.merge([])), int(d.ALLOW))

    def test_merge_rejects_a_value_that_is_not_a_decision(self):
        d = self._decisions()
        with self.assertRaises(d.DecisionError):
            d.merge([0, 9])

    def test_merge_is_reachable_through_the_package_export(self):
        """The reason it is kept rather than deleted: it is public API."""
        src = os.path.join(REPO_ROOT, 'src')
        if src not in sys.path:
            sys.path.insert(0, src)
        from claudekit import enforcement
        self.assertIn('merge', getattr(enforcement, '__all__', ()),
                      'merge left __all__; if it is no longer public API it can be '
                      'deleted, and this test should go with it')
        self.assertTrue(callable(getattr(enforcement, 'merge', None)),
                        'merge is exported but not importable — the export and the '
                        'module have drifted')


if __name__ == '__main__':
    unittest.main()
