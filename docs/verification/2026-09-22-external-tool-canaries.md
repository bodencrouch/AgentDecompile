# Real external-tool canaries — 2026-09-22

**Observed:** real pinned ReAgent and reccmp CLIs consumed original tiny fixtures.
Positive and negative expectations passed, including report-content assertions.
This is provider interoperability evidence, **not a delivered production adapter,
full binary comparison, recovered-source acceptance or live-game proof**.

## Scope and environment

The user authorized external integration/testing. These checks use no proprietary
binary, second Ghidra analysis, live server or model provider. `pyghidra`, JPype and
model SDKs were installed as upstream dependencies; none was used to start those
services. No global or repository virtual-environment packages were changed.

Interpreter identity was checked before use: `/usr/bin/python3` resolves to
`/usr/bin/python3.14`. The new isolated environment is
`/tmp/agentdecompile-external-canaries-20260922`; its `bin/python` resolves to the
same system executable. It does not use the historical offloaded NVMe virtualenv.
Installation compiled upstream's JPype dependency and completed successfully.

| Provider | Inspected and installed revision | Installed version | Download archive SHA-256 |
|---|---|---|---|
| ReAgent | `d12cea338c61898b06a86fe8adb25275fa9d5615` | `auto-re-agent 0.4.0` | `65c22a9de6fc63bed302152e7e20bc548970594131ededef00f01fc6c2baec3f` |
| reccmp | `e91a51bfadfbb600adfdc750589ac40ae9742883` | `reccmp 0.1.7` | `6801afde929b3fb847a482a9c8aff0f674a133ec72594a426bc4ef3c81e36aaa` |

[Resolved dependency versions](../../tests/fixtures/external_validation/observed-2026-09-22/resolved-requirements.txt)
and [pip install report with distribution hashes](../../tests/fixtures/external_validation/observed-2026-09-22/install-report.json)
record what was installed. This is a resolved observation, not a complete offline
wheelhouse or a promise that dependency resolution will remain unchanged.

## Commands and observed behavior

Installation used `/usr/bin/python3 -m venv` at the scratch path above, followed by
that environment's `python -m pip install` with the two revision archive URLs in
the table, `--report <environment>/install-report.json`, and a retained install log.
No `--system-site-packages` option was used.

The [runner](../../tests/fixtures/external_validation/run_canaries.py) copied
[original fixtures](../../tests/fixtures/external_validation/README.md) into a new
private scratch directory. The final checked invocation was:

```text
/usr/bin/python3 tests/fixtures/external_validation/run_canaries.py /tmp/agentdecompile-external-canaries-20260922/bin /tmp/agentdecompile-external-canary-verified-20260922
```

All provider commands below used that scratch directory as cwd and the isolated
`bin/` executables. Exact absolute argv/cwd and exit expectations are retained in
[receipt.json](../../tests/fixtures/external_validation/observed-2026-09-22/receipt.json).

| Real command | Observed result | What this establishes |
|---|---|---|
| `re-agent --version` | Exit 0, version 0.4.0 | Installed CLI identity |
| `reccmp-decomplint --version` | Exit 0, version 0.1.7 | Installed CLI identity |
| `re-agent benchmark --manifest benchmark.json --output benchmark-report.json` | Exit 0; 2/2 expectations met | Real JSON-in/JSON-out harness execution and report contract |
| `re-agent --config re-agent.yaml plan --address 0x401000 --max-depth 0 --max-functions 1 --output plan-report.json` | Exit 0; one selected function, exact supplied decompile retained | `ghidra-json` snapshot consumption, no live bridge |
| `reccmp-decomplint --target CANARY --warnfail source-positive` | Exit 0 | Valid annotation fixture consumed |
| `reccmp-decomplint --target CANARY --warnfail source-negative` | Exit 1; `duplicate_offset` at line 8, address `0x00401000` | Deliberate duplicate annotation rejected by warnings-as-failure policy |

The matching arithmetic candidate passed all three inputs: 0, 7 and -9. The wrong
candidate was detected at input 0: reference result 1 versus candidate result 2.
Its `matched:false` and `expected_match:false` made this a successful **negative
canary**; benchmark exit zero does not accept the incorrect candidate.

The final runner also asserted the actual positive/negative benchmark fields,
positive case count, negative first-case detection, exact selected decompile text,
selection bounds, and duplicate-offset diagnostic. All five content assertions
were true. The initial execution already matched all exit expectations; a second
execution verified the added report-content assertions. No fixture correction or
provider workaround was required.

## Evidence retained

- [Raw benchmark report](../../tests/fixtures/external_validation/observed-2026-09-22/benchmark-report.json)
- [Raw bounded plan report](../../tests/fixtures/external_validation/observed-2026-09-22/plan-report.json)
- [Negative lint diagnostic](../../tests/fixtures/external_validation/observed-2026-09-22/lint-negative.stdout)
- [Command receipt and raw report hashes](../../tests/fixtures/external_validation/observed-2026-09-22/receipt.json)
- [Fixture hashes](../../tests/fixtures/external_validation/observed-2026-09-22/fixture-sha256.json)

The same directory retains each command's stdout/stderr. Scratch paths inside the
raw plan are honest origin metadata; copying a receipt does not turn them into
portable execution paths. The checked-in fixture package can be copied to new
scratch; its arithmetic commands currently declare Linux `/usr/bin/python3`.

## Limits and next integration gate

The snapshot is explicitly synthetic, with known empty cross-reference lists and
no assembly/CFG/P-code claim. ReAgent's plan reports no gaps for the fields it
checks; this does not imply complete binary evidence. A real AgentDecompile export
must preserve missing-field gaps, input provenance and snapshot identity.

ReAgent benchmark compares only the declared observable JSON cases. It is not
formal equivalence, binary parity or full-domain correctness. reccmp lint validates
annotations, not executable instructions. `reccmp-reccmp` PE/PDB comparison,
ReAgent model-assisted reversal, actual AgentDecompile cached-snapshot export,
production catalog dispatch, candidate acceptance and native execution were
**not exercised here**. A production integration must pass these same raw outputs
through its normalizer and existing job/catalog path, then separately qualify a
supported original PE/PDB fixture and meaningful candidate-consuming gates.

The upstream contracts were read at the installed revisions:
[ReAgent benchmark](https://github.com/Dryxio/reagent/blob/d12cea338c61898b06a86fe8adb25275fa9d5615/src/re_agent/cli/cmd_benchmark.py),
[differential harness](https://github.com/Dryxio/reagent/blob/d12cea338c61898b06a86fe8adb25275fa9d5615/src/re_agent/verification/differential.py),
[JSON snapshot backend](https://github.com/Dryxio/reagent/blob/d12cea338c61898b06a86fe8adb25275fa9d5615/src/re_agent/backend/exports.py),
and [reccmp linter](https://github.com/isledecomp/reccmp/blob/e91a51bfadfbb600adfdc750589ac40ae9742883/reccmp/tools/decomplint.py).
