"""Quoted-heredoc bodies are stdin DATA, not shell (regression matrix).

The defect: validate() fed every newline-separated line to the shell parser, heredoc
bodies included. A quoted delimiter (`<<'EOF'`) means bash performs NO expansion on the
body - it is bytes on the command's stdin - so parsing it as shell refused commands that
are entirely legitimate. Two shapes were observed live in .claude/hooks/hooks.log:

  * any apostrophe in a body (`don't`, `it's`) opened a quote that never closed, giving
    `Malformed command (No closing quotation)`;
  * prose or code in a body that merely NAMED something the validator scans for.

The fix blanks quoted-heredoc bodies before the per-line split ONLY. Every whole-command
check still reads the original string, which is what keeps the guards below passing.

GUARDS vs DISCRIMINATORS - stated so guard coverage is never read as discrimination:

  DISCRIMINATORS (fail against the UNFIXED validator): every case in TestBodyIsData and
  TestTabStrippedAndMultiple.

  GUARDS (also pass against the unfixed validator; they exist to prove the fix did not
  trade a false refusal for a hole): all of TestUnquotedDelimiterStillExpands,
  TestWholeCommandChecksStillSeeTheOriginal, TestCodeAroundTheHeredoc, and the
  here-string and unterminated cases.

Run in BOTH modes: safe_mode=False skips the allowlist entirely, and that is the mode in
which a segmentation regression is invisible.
"""

import pytest

from claudekit.security.command_validator import (
    CommandValidator,
    _quoted_heredoc_delimiters,
    _strip_quoted_heredoc_bodies,
)

SAFE = CommandValidator()
UNSAFE = CommandValidator(safe_mode=False)


class TestBodyIsData:
    """A quoted body must not be parsed as shell. These fail before the fix."""

    @pytest.mark.parametrize("command", [
        # The exact shape logged as `Malformed command (No closing quotation)`.
        "cat <<'EOF'\ndon't parse this as shell\nEOF",
        "python3 <<'PY'\nprint(\"it's fine\")\nPY",
        # A lone double quote is the same hole with the other quote character.
        "cat <<'EOF'\nsay \"half a quote\nEOF",
        # An empty body, and a body that is only whitespace.
        "cat <<'EOF'\nEOF",
        "cat <<'EOF'\n   \nEOF",
        # Double-quoted delimiter: bash suppresses expansion for this spelling too.
        'cat <<"EOF"\ndon\'t\nEOF',
        # Whitespace between the operator and the delimiter is legal.
        "cat << 'EOF'\ndon't\nEOF",
    ])
    def test_accepted_in_both_modes(self, command):
        for validator, mode in ((SAFE, "safe"), (UNSAFE, "unsafe")):
            ok, reason = validator.validate(command)
            assert ok, (mode, command, reason)

    def test_blocklisted_name_in_a_quoted_body_is_text(self):
        """Documented behaviour change: bash runs nothing here, so neither do we.

        This is the same position the validator already took for a quoted ARGUMENT
        (`echo 'rm -rf /'` has always been allowed): the name is not in command
        position. Consistent with hard rule 6 - a denylist speed bump, not a sandbox.
        """
        ok, reason = SAFE.validate("cat <<'EOF'\nrm -rf /\nEOF")
        assert ok, reason


class TestTabStrippedAndMultiple:
    def test_dash_form_strips_leading_tabs_from_the_terminator(self):
        command = "cat <<-'EOF'\n\tdon't\n\tEOF"
        ok, reason = SAFE.validate(command)
        assert ok, reason

    def test_two_heredocs_on_one_line_consume_bodies_in_order(self):
        command = "cat <<'A' <<'B'\ndon't\nA\nwon't\nB"
        ok, reason = SAFE.validate(command)
        assert ok, reason
        assert _strip_quoted_heredoc_bodies(command) == "cat <<'A' <<'B'\n\n\n\n"


class TestUnquotedDelimiterStillExpands:
    """`<<EOF` without quotes: bash expands the body, so it stays live code."""

    @pytest.mark.parametrize("command", [
        "cat <<EOF\n$(rm -rf /)\nEOF",
        "cat <<EOF\n`rm -rf /`\nEOF",
    ])
    def test_substitution_in_an_unquoted_body_is_still_checked(self, command):
        for validator, mode in ((SAFE, "safe"), (UNSAFE, "unsafe")):
            ok, reason = validator.validate(command)
            assert not ok, (mode, command, reason)

    def test_unquoted_bodies_are_not_stripped(self):
        command = "cat <<EOF\nrm -rf /\nEOF"
        assert _strip_quoted_heredoc_bodies(command) == command


class TestWholeCommandChecksStillSeeTheOriginal:
    """Only the per-line split reads the stripped string."""

    @pytest.mark.parametrize("command,label", [
        ("python3 <<'PY'\nimport subprocess\nsubprocess.run(['ls'])\nPY", "python subprocess"),
        ("python3 <<'PY'\nos.system('ls')\nPY", "python os.system()"),
        ("python3 <<'PY'\n__import__('os')\nPY", "python __import__()"),
        ("cat <<'EOF' > /etc/passwd\nroot\nEOF", "redirect into /etc"),
    ])
    def test_dangerous_patterns_still_fire_through_a_quoted_body(self, command, label):
        for validator, mode in ((SAFE, "safe"), (UNSAFE, "unsafe")):
            ok, reason = validator.validate(command)
            assert not ok and label in reason, (mode, command, reason)


class TestCodeAroundTheHeredoc:
    def test_the_opener_line_is_still_validated(self):
        ok, reason = SAFE.validate("rm -rf / <<'EOF'\ndata\nEOF")
        assert not ok, reason

    def test_code_after_the_terminator_is_still_validated(self):
        for validator, mode in ((SAFE, "safe"), (UNSAFE, "unsafe")):
            ok, reason = validator.validate("cat <<'EOF'\ndata\nEOF\nrm -rf /")
            assert not ok, (mode, reason)

    def test_an_unterminated_heredoc_is_handed_back_untouched(self):
        """No terminator means the command is malformed; the existing parser fails it."""
        command = "cat <<'EOF'\nrm -rf /"
        assert _strip_quoted_heredoc_bodies(command) == command
        ok, reason = SAFE.validate(command)
        assert not ok, reason

    def test_here_string_is_not_read_as_a_heredoc(self):
        """`<<<` has no body: consuming the following lines as one would hide them."""
        assert _quoted_heredoc_delimiters("grep x <<<'literal'") == []
        for validator, mode in ((SAFE, "safe"), (UNSAFE, "unsafe")):
            ok, reason = validator.validate("grep x <<<'a'\nrm -rf /")
            assert not ok, (mode, reason)


class TestDelimiterScanner:
    @pytest.mark.parametrize("line,expected", [
        ("cat <<'EOF'", [("EOF", False)]),
        ('cat <<"EOF"', [("EOF", False)]),
        ("cat <<-'EOF'", [("EOF", True)]),
        ("cat << 'EOF'", [("EOF", False)]),
        ("diff <<'A' <<'B'", [("A", False), ("B", False)]),
        # Unquoted delimiter: not ours to strip.
        ("cat <<EOF", []),
        # Inside quotes it is text, not an operator.
        ("echo \"a <<'EOF'\"", []),
        ("echo 'a <<\"EOF\"'", []),
        # After an unquoted `#` the rest of the line is inert, matching the
        # over-approximation _split_unquoted_newlines already makes.
        ("ls # cat <<'EOF'", []),
        ("grep x <<<'y'", []),
    ])
    def test_scanner(self, line, expected):
        assert _quoted_heredoc_delimiters(line) == expected

    def test_stripping_preserves_the_line_count(self):
        command = "cat <<'EOF'\na\nb\nc\nEOF\nls"
        assert len(_strip_quoted_heredoc_bodies(command).split("\n")) == 6

    def test_command_without_the_operator_is_returned_unchanged(self):
        assert _strip_quoted_heredoc_bodies("ls -la") == "ls -la"
