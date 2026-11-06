# Input normalization

AgentDecompile uses one spelling-normalization algorithm at its input boundaries:
`normalize_identifier` lowercases a name and removes every non-ASCII-letter
character. For example, `programPath`, `program_path`, and `PROGRAM-PATH` share
the normalized core `programpath`.

The boundaries intentionally have different jobs and precedence:

- The Click boundary accepts varied command and long-option spellings. Exact
  registered commands win before normalized command matches and semantic tool
  aliases. Opaque passthrough commands disable token normalization.
- The registry resolves canonical tool and parameter names, then applies
  explicit semantic aliases. Canonical parameter values win alias fallbacks.
- The provider boundary normalizes incoming top-level argument keys. If multiple
  top-level spellings collide, the later dictionary item wins, preserving the
  existing provider contract. Provider getters list only genuinely different
  semantic aliases because spelling variants already share one normalized core.

Normalization is not recursive. Nested dictionary keys, argument values, and
output/schema field names remain unchanged.

## Defaults and convenience commands

The `symbols`, `strings`, `list-functions`, `references`, `datatypes`,
`structures`, `comments`, `bookmarks`, `callgraph`, `constants`, and `vtables`
convenience commands derive their options and selector choices from each
family's owning `run` command. The shorter commands therefore retain Click's
declared types, choices, tuple handling, and validation instead of maintaining
a second option schema. Their intentionally omitted run-only inputs remain
unavailable. The shortcut choice surface is also preserved: for example,
`bookmarks removeAll` remains available through `bookmarks run --action
removeAll`, not as a convenience subcommand.

Normal use leaves backend-owned defaults implicit. In this bounded surface,
`symbols --filter-default-names` and
`strings --include-referencing-functions` are omitted from the payload when the
user supplies neither form of the paired flag. Their positive and negative forms
send explicit `true` and `false` overrides. Other CLI policy and mutation-safety
defaults remain explicit because they are not proven redundant with provider
behavior. Missing run-only options are suppressed when a shortcut invokes its
owning command, so a shortcut does not acquire hidden workflow defaults.

Ordinary explicit empty strings are preserved. Program selection is narrower:
an empty or whitespace-only `--binary` remains absent rather than selecting a
target. This selector policy does not recursively normalize or trim arbitrary
payload values.

## Inline compatibility check

This check uses only the pure registry normalizer; it does not import providers
or start the JVM or server:

```sh
PYTHONPATH=src python -B - <<'PY'
from agentdecompile_cli.registry import normalize_identifier

spellings = ("programPath", "program_path", "PROGRAM-PATH")
assert {normalize_identifier(value) for value in spellings} == {"programpath"}

nested = {"Nested_Key": "A-B"}
normalized = {normalize_identifier(key): value for key, value in {"program_path": nested}.items()}
assert normalized == {"programpath": nested}
assert next(iter(normalized.values())) == {"Nested_Key": "A-B"}
print("normalizer: spelling variants converge; nested keys and values remain opaque")
PY
```
