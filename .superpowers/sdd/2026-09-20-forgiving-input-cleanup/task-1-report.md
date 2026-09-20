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

Command:

```sh
python -B - <<'PY'
import sys
sys.path.insert(0, 'src')
import click
from agentdecompile_cli.cli import ForgivingCliGroup, _normalize_cli_token, main
from agentdecompile_cli.registry import Tool

root = click.Context(main, info_name='agentdecompile-cli', token_normalize_func=_normalize_cli_token)
spellings = ('manage-symbols', 'ManageSymbols', 'Manage_Symbols', 'MANAGE SYMBOLS', 'MANAGE-SYMBOLS')
resolved = [main.get_command(root, spelling) for spelling in spellings]
assert resolved[0] is not None and all(command is resolved[0] for command in resolved)
assert main.get_command(root, 'rename_function') is main.get_command(root, Tool.MANAGE_FUNCTION.value)
assert main.get_command(root, 'search-code') is main.commands['search-code']
assert main.get_command(root, 'definitely_unknown') is None
print('commands: canonical/camel/Pascal/snake/kebab/uppercase resolve; exact curated wins; semantic alias resolves; unknown fails')

@click.command(context_settings={'token_normalize_func': _normalize_cli_token})
@click.option('--program-path')
@click.option('--dry-run/--no-dry-run', default=False)
@click.option('--count', type=int)
@click.option('-p', 'lower', is_flag=True)
@click.option('-P', 'upper', is_flag=True)
@click.argument('payload')
def probe(**kwargs):
    pass

for option in ('--program-path', '--programPath', '--ProgramPath', '--program_path', '--PROGRAM-PATH'):
    parsed = probe.make_context('probe', [option, '/Tmp/A_B-C.json', '--dryRun', '--count', '0', '{"Nested_Key":"A-B"}']).params
    assert parsed == {'program_path': '/Tmp/A_B-C.json', 'dry_run': True, 'count': 0, 'payload': '{"Nested_Key":"A-B"}', 'lower': False, 'upper': False}
for flag, expected in (('-p', (True, False)), ('-P', (False, True))):
    parsed = probe.make_context('probe', [flag, 'x']).params
    assert (parsed['lower'], parsed['upper']) == expected
empty = probe.make_context('probe', ['--programPath', '', '']).params
assert empty['program_path'] == '' and empty['payload'] == '' and empty['dry_run'] is False
print('options: native long variants parse; short case and opaque path/JSON/empty/false/0 preserved')

command = main.commands['manage-symbols']
actual = command.make_context('ManageSymbols', ['--programPath', '/Tmp/A_B.exe', '--MODE', 'list'], parent=root).params
assert actual['program_path'] == '/Tmp/A_B.exe' and actual['mode'] == 'list'
open_cmd = main.commands['open']
for option in ('--destination_folder', '--destination-folder', '--DestinationFolder'):
    parsed = open_cmd.make_context('open', [option, '/Repo/A_B', '--no-analyze-after-import', '--enableVersionControl'], parent=root).params
    assert parsed['destination_folder'] == '/Repo/A_B' and parsed['analyze_after_import'] is False and parsed['enable_version_control'] is True
print('actual-main-parser: generated and curated normalized flags parse with stable destinations; callbacks not invoked')

recover = main.commands['recover']
recover_ctx = recover.make_context('recover', ['--Weird_Flag', 'A_B-C', '{"Nested_Key":0}'], parent=root)
assert recover_ctx.params['args'] == ('--Weird_Flag', 'A_B-C', '{"Nested_Key":0}')
print('passthrough: unknown option-like and opaque argument tokens unchanged')

ambiguous = ForgivingCliGroup('probe', context_settings={'token_normalize_func': _normalize_cli_token})
ambiguous.add_command(click.Command('one'), 'a-b')
ambiguous.add_command(click.Command('two'), 'a_b')
try:
    ambiguous.get_command(click.Context(ambiguous), 'AB')
except click.UsageError:
    pass
else:
    raise AssertionError('ambiguous normalized commands were accepted')
print('ambiguity: distinct normalized command collisions fail closed')
PY
```

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
import ast, re
source=open('src/agentdecompile_cli/cli.py',encoding='utf-8').read(); tree=ast.parse(source)
remaining=[]
for node in ast.walk(tree):
    if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
    for decorator in node.decorator_list:
        if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Attribute) or decorator.func.attr!='option': continue
        opts=[a.value for a in decorator.args if isinstance(a,ast.Constant) and isinstance(a.value,str) and a.value.startswith('--') and '/' not in a.value]
        groups={}
        for opt in opts: groups.setdefault(re.sub('[^a-z]','',opt.lower()),[]).append(opt)
        remaining.extend((node.name,names) for names in groups.values() if len(names)>1)
assert not remaining, remaining
compile(source, 'src/agentdecompile_cli/cli.py', 'exec')
print('static: source compiles; no normalized-equivalent long-option declarations remain')
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
