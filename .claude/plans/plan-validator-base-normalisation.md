# Implementation Plan: close the two deferred base-command bypasses

> Findings **M1** and **M2** of round 1 of the adversarial review of `plan-validator-segmentation`,
> deferred there by name because they are pre-existing and deserve their own behaviour matrix.
> Round 3 added a third form (`$''`) to the same class. This plan closes all of them.

## The defect: `BLOCKLIST`'s docstring is false

`command_validator.py` documents `BLOCKLIST` as *"Commands that are NEVER allowed, even in unsafe
mode."* Two token shapes falsify that, both measured with a bash oracle (a shadowed `rm` marker
function plus one real file deletion):

**M1 — a leading file-descriptor digit becomes the base command.** `_split_segments` drops a
redirect operator and its target, but a *preceding* fd number is an ordinary token, so it lands in
command position:

```
2>/dev/null rm -rf /     segments -> [['2', 'rm', '-rf', '/']]     base = '2'
  safe   : REJECT, but for the WRONG REASON - "Command not in allowlist: 2"
  unsafe : ALLOW          <-- bash deletes the file
```
Same for `2>&1 sudo rm -rf /`, `3>&1 rm -rf /`, `0<in rm -rf /`, and
`2>/dev/null eval rm -rf /` — which also slips past `_SHELL_BUILTIN_DENY`.

**M2 — an empty expansion glued to the command name defeats matching.** Bash removes it before
resolving the command; the validator matches the literal token:

```
``rm -rf /   -> base '``rm'      $()rm -rf /  -> base '$'
rm`` -rf /   -> base 'rm``'      rm$() -rf /  -> base 'rm$'
$''rm -rf /  -> base '$rm'       $""rm -rf /  -> base '$rm'
  all: unsafe ALLOW; bash runs `rm`
```
The `$''` and `$""` forms were added by round 3 and are why the fix is written against a character
class rather than a list of literal sequences: an enumeration of empty-expansion spellings is the
same losing game as an env-name denylist.

## Fix, and the one design decision that matters

1. **M1:** strip the file-descriptor number from the raw string before tokenizing, in
   `_strip_adjacent_fds()`. Three constraints, and the first two were each a **rejected
   design caught in review**:
   * **Adjacency.** Bash treats a digit as an fd only when it touches the operator; `2 > log`
     runs a command *named* `2`. The unguarded version dropped the digit there, so `2 > f; ls`
     and `ls; 2 > f` ran a digit-named executable unchecked in the default mode.
   * **Position, not value.** The second attempt collected "digit strings that appear adjacent
     somewhere" into a set and tested tokens by value — so a quoted `'x 2>y'` anywhere in the
     line poisoned it and silently erased a genuine `2 > f` segment. Working on the raw string
     binds each occurrence to its own position.
   * **Quotes.** `echo "a 2>b"` is an argument, not a redirect.
   `2 files` keeps `2` as its base command, and `2>/dev/null` alone fails closed as
   `Empty command after parsing` rather than validating its redirect target.
2. **M2:** derive a second base by stripping the expansion punctuation `` ` ``, `$`, `(`, `)` from
   each token and taking the first that survives non-empty.

**The stripped base feeds the deny checks ONLY — never the allowlist.** This is the whole design.
Measured on the first attempt, which used the stripped base everywhere: **5,118 REJECT→ALLOW
transitions** over a 168,400-payload fuzz, because `$ls` and `` `ls` `` normalised to the
allowlisted `ls` and were let through. Command substitution in command position is not `ls`; it is
"run whatever this prints". Normalisation is a fail-closed tool: it may add rejections, never
remove them. With the deny-only split, the same fuzz gives **0 undisclosed widenings**.

## Measured behaviour change

| input | before (safe / unsafe) | after (safe / unsafe) |
|---|---|---|
| `2>/dev/null rm -rf /` | not-in-allowlist / **ALLOW** | `Blocked command: rm` / `Blocked command: rm` |
| `2>&1 sudo rm -rf /`, `3>&1 rm -rf /`, `0<in rm -rf /` | not-in-allowlist / **ALLOW** | blocked / blocked |
| `2>/dev/null eval rm -rf /` | not-in-allowlist / **ALLOW** | `Dangerous pattern (eval)` / same |
| ``` ``rm -rf / ```, `rm`` -rf /`, `rm$() -rf /`, `$()rm -rf /`, `$''rm -rf /`, `$""rm -rf /` | reject / **ALLOW** | `Blocked command: rm` / same |
| `$ls` | not-in-allowlist / ALLOW | **unchanged** — the allowlist still sees `$ls` |
| `ls`, `npm run build`, `make test 2> err.log`, `echo hi > out.txt`, `bundle exec rspec`, `2 files` | unchanged | unchanged |

**Differential fuzz, 204,183 payloads** over `` {`, $, (, ), #, ', ", \, \n, ;, |, &&, >, 2>,
`2 >`, ls, rm -rf /, sudo -s, x, echo} ``, both modes, prototype vs the currently-applied
module: **8,396 ALLOW→REJECT** (the tightening) and **204 REJECT→ALLOW — every one of them the
disclosed fd shape**, 194 safe-mode `Command not in allowlist: 2` cases that were an accident of
the digit landing in command position (`2>x echo` now validates `echo`, which is what bash runs)
and 10 that now fail closed differently. Zero undisclosed widenings; none loses a blocklist
rejection, and in unsafe mode all of them were already ALLOW.

## Out of scope, named

A bare `$VAR` or `${x}foo` in command position is still unresolvable and still validated
literally. It cannot be resolved statically at all, and treating it as its stripped spelling would
be the allowlist-widening mistake above. Unchanged in both directions by this plan.

## Implementation Steps

1. `src/claudekit/security/command_validator.py` — `_FD_RE` + the digit skip in `_split_segments`;
   `_EXPANSION_PUNCT` + `_expansion_stripped_base()`; the deny-only second check in
   `_validate_segment`, placed before the existing checks so `blocklist_only` (the
   command-substitution path) is covered too.
2. `tests/test_validator_segmentation.py` — `FD_PREFIXED` and `EMPTY_EXPANSION` lists, in BOTH
   `MUST_REJECT` and `UNSAFE_MUST_REJECT` (round 3's `unsafe-mode-matrix-gap` ratchet: unsafe mode
   is where these were exploitable, so asserting them in safe mode only would repeat the exact
   mistake that ratchet exists to stop), plus a test that the allowlist is NOT normalised.
3. `CHANGELOG.md` — the fix and the 382-payload widening, disclosed together.

## Testing Strategy

Mutants: delete the digit skip → the five `FD_PREFIXED` unsafe-mode cases fail. Delete
`_expansion_stripped_base` → the six `EMPTY_EXPANSION` unsafe-mode cases fail. Feed the stripped
base to the allowlist as well → `test_the_allowlist_is_not_normalised` fails. Plus the full suite,
`ruff`, `mypy`, and the security coverage floor.

## Rollback

`git revert` — one module, one test file, one CHANGELOG entry. Reverting restores both bypasses.
