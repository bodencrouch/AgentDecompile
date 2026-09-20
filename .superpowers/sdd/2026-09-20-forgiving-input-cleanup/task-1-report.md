# Task 1 report: normalize Click tokens at the CLI boundary

## Status

Implemented in the isolated `refactor/forgiving-inputs-20260920` worktree based
on `c1e45e0869befd31f03051ed4269b1cc486ee8da`.

## Changes

- Added `_normalize_cli_token`, backed by `registry.normalize_identifier` for
  command and long-option tokens while preserving every one-character token.
- Configured the root Click context with native `token_normalize_func`.
- Added `ForgivingCliGroup` resolution precedence:
  1. exact registered command;
  2. one unambiguous normalized registered command;
  3. registry semantic alias, only when its canonical command is registered.
- Distinct registered commands with the same normalized spelling now fail closed.
  Multiple names for the same `click.Command` object remain unambiguous.
- Reused `normalize_identifier` in `_is_cli_result_limit_param`.
- Removed normalized-equivalent long-option declarations. Primary displayed/help
  spellings, explicit Click destination names, short flags, and semantic aliases
  remain. Native token normalization accepts the removed spellings.
- Removed the obsolete comment claiming snake-case commands are separately
  registered.

No registry, executor, backend, provider, recovery, or runtime files were changed.

## Inline verification

All checks were pure Python/Click parser-object checks run with `python -B`. They
imported the edited CLI module but did not invoke `main`, application callbacks,
the filesystem test runner, a CLI subprocess, a JVM, a backend, or a server.

### Source compile

Command:

```sh
python -B - <<'PY'
from pathlib import Path
path = Path('src/agentdecompile_cli/cli.py')
compile(path.read_text(encoding='utf-8'), str(path), 'exec')
print('compile: ok')
PY
```

Output:

```text
compile: ok
```

### Command, option, value, passthrough, and ambiguity checks

The inline script inserted this worktree's `src` at the front of `sys.path`,
then used `click.Context`, `Group.get_command`, `Group.resolve_command`, and
`Command.make_context` directly. It asserted:

- canonical, camel, Pascal, snake, kebab, spaced, and uppercase command forms;
- exact curated command precedence over semantic forwarding;
- `rename_function` semantic alias resolution;
- unknown command rejection;
- canonical, camel, Pascal, snake, kebab, and uppercase long flags;
- boolean flags and preservation of false, zero, and empty values;
- case-sensitive `-p` and `-P` behavior;
- unchanged path and JSON argument values, including nested JSON keys;
- unchanged unknown option-like/raw tokens for `recover` passthrough;
- actual generated `manage-symbols` and curated `open` parser objects;
- rejection of two distinct commands whose names normalize identically.

Output:

```text
commands: canonical/camel/Pascal/snake/kebab/uppercase resolve; exact curated wins; semantic alias resolves; unknown fails
options: native long variants parse; short case and opaque path/JSON/empty/false/0 preserved
actual-main-parser: generated and curated normalized flags parse with stable destinations; callbacks not invoked
passthrough: unknown option-like and opaque argument tokens unchanged
ambiguity: distinct normalized command collisions fail closed
```

### Static duplicate and whitespace checks

Commands:

```sh
python -B - <<'PY'
# AST scan of each click.option decorator for alpha-core-equivalent long names,
# followed by compile(source, ...).
PY
git diff --check
```

Output:

```text
static: source compiles; no normalized-equivalent long-option declarations remain
```

`git diff --check` produced no output and exited successfully.

## Boundaries and concerns

- Click also applies `token_normalize_func` to `click.Choice` tokens. This is
  consistent with forgiving CLI control-token spelling; free-form arguments,
  option values, paths, JSON strings, and passthrough tokens remain untouched.
- Public canonical command and primary option help spellings are unchanged.
- This task intentionally leaves registry/executor normalization consolidation
  to later tasks.
- Repository test suites and filesystem fixtures were not run under the global
  mission constraint. Runtime/backend behavior was not exercised.
- `docs/plans/2026-09-20-forgiving-input-cleanup.md` was already modified by
  another concurrent owner and is excluded from this task's commit.
