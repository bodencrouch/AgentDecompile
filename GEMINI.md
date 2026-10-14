# Gemini project guidance

Use the shared repository authorities; do not create a Gemini-specific product
definition or alternate pipeline:

- [AGENTS.md](AGENTS.md): repository operations, safety, and verification limits.
- [docs/USER_INTENT.md](docs/USER_INTENT.md): current product purpose, inputs,
  outputs, runtime scope, and authority order.
- [STRATEGY.md](STRATEGY.md): recovery sequence, matching, and acceptance proof.
- [METHODOLOGY.md](METHODOLOGY.md): durable engineering principles.

AgentDecompile is a higher-level reverse-engineering workbench built around
Ghidra. It relates concrete builds as one binary family, recovers C/C++ whose
compiled output can match each target, and exposes evidence-backed analysis and
supported runtime capabilities such as ABI, events, arguments, memory,
WASM/graphics, Lua/native shims, DLLs, hooks, code caves, and memory changes.
Keep each target and claim tied to its evidence: runtime behavior is not source
parity, and only the fresh full-image proof in STRATEGY.md establishes complete
recovery.

When instructions disagree, follow the authority order in
[docs/USER_INTENT.md](docs/USER_INTENT.md), subject to current-user instructions
and the operational safeguards in [AGENTS.md](AGENTS.md). Prefer these shared
contracts over duplicated Gemini-specific rules.
