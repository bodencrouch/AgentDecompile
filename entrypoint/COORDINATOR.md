# The evidence and validation coordinator

Status: **proposed design**. Nothing on this page is implemented yet unless the row says so.
It is the smallest architectural addition that closes the five gaps in
[README.md](README.md#the-five-gaps) without introducing another general-purpose RE agent.
Everything it does not list is delegated to an existing project.

```mermaid
flowchart TD
  subgraph in[Inputs]
    agents[Agent proposals]
    engines[Engine results: BSim, FIN, VeriBin, CounterTV, AFL++, PANDA]
  end
  in --> contract[Evidence contract]
  contract --> graph[Identity graph]
  graph --> gate[Validation gate]
  gate -->|PASS| arbiter[Conflict arbiter]
  gate -->|FAIL or UNKNOWN| graph
  arbiter -->|serialized| ghidra[Guarded Ghidra commit]
  arbiter -->|contested| graph
  router[Capability router] --> engines
  graph --> router
```

## The five pieces

### 1. Identity graph

Represents one-to-one and many-to-many function relationships with confidence, provenance
and competing hypotheses, instead of a flat `address -> name` table.

- Nodes: logical entity, implementation variant, physical instance (standalone, inline,
  thunk, split, folded), per the vocabulary in [CONCEPTS.md](../CONCEPTS.md).
- Edges: `implements`, `instance_of`, `inlined_into`, `split_from`, `matches` (with
  evidence layers and score), `contradicts`.
- Every edge carries the evidence contract id that produced it and a status: proposed,
  validated, contested, withdrawn.
- Storage: Dolt branches per agent or campaign, merged through the arbiter. Today's
  `db/kotorxid.sqlite` (`identity`, `recovered_function`, `reuse_candidate`) is the
  authoritative store and the migration source; the graph is a superset of it, not a
  replacement until qualified.

### 2. Evidence contract

Every finding carries immutable references to what produced it.

```json
{
  "finding_id": "f_01J...",
  "claim": {"kind": "match", "subject": "k1_steam_103:0x5a1b20", "object": "k1_gog_100:0x59f0c0", "tier": "advisory"},
  "inputs": {"binaries": ["sha256:..."], "traces": ["dvc:..."], "source": ["git:...:path@rev"]},
  "tools": [{"name": "bsim", "version": "11.3", "config_hash": "..."}],
  "validation": [{"check": "objdiff", "result": "UNKNOWN", "conditions": "not attempted: no compile"}],
  "lineage": "openlineage:run/...",
  "attestation": "cosign:sha256:..."
}
```

- References are content-addressed (hashes, DVC paths, git revisions, tool versions).
- `tier` uses the claim vocabulary from [METHODOLOGY.md](../METHODOLOGY.md) §4 and never
  exceeds what `validation` supports.
- Lineage is emitted as OpenLineage events with custom facets; integrity comes from
  in-toto layouts and Cosign signatures where the environment is configured for them. A
  signed wrong conclusion stays wrong; the signature only proves who said it and that it
  was not altered.

### 3. Validation gate

A hypothesis becomes a verified finding only after the configured checks run. The gate
records **PASS**, **FAIL** or **UNKNOWN** per check plus the exact conditions of any proof.

| Claim kind | Required checks (configurable per corpus) |
|---|---|
| Function source | Compile under identified toolchain; objdiff 0; optional ReAgent/reccmp scoped evidence |
| Binary-level equivalence | VeriBin or CounterTV where their scope applies; AFL++ differential run; angr path comparison on bounded regions |
| Match | Agreement across at least the configured evidence layers; BinKit-calibrated threshold for the architecture and compiler family; no open contradiction |
| Runtime capability | Independent target identity; live ABI, layout, lifetime, ownership and policy checks |
| Whole image | Fresh compile and link; objdiff zero difference on the whole file |

UNKNOWN is a first-class result: the check could not run or does not cover the case. It
never rounds up to PASS. The gate's job includes making "insufficient evidence" easy to
emit and hard to hide.

### 4. Conflict arbiter

Compares every proposed change against the database revision it originated from, preserves
competing edits and prohibits silent overwrites.

- Optimistic concurrency: a proposal names its base revision; a stale base is a conflict,
  never a last-writer-wins.
- Dolt row and schema conflicts surface as `contested` edges in the identity graph with
  both sides and their evidence contracts intact.
- Authoritative Ghidra writes are serialized through one writer per program. This is
  required because Ghidra's transaction model is not fully isolated: concurrent
  transactions may join an existing one as sub-transactions and share rollback behavior.
- Arbitration policy is explicit and recorded: prefer the proposal with more validated
  checks; on a tie, keep both and emit insufficient evidence. The arbiter never decides
  which interpretation is correct by itself.

### 5. Capability router

Chooses the engine for a question from binary format, architecture, the question asked,
cost and the evidence the gate will need, using [stack.json](stack.json) and the live
`doctor.py` report as its inventory.

| Question | Candidates, in order | Skip when |
|---|---|---|
| Which function is this across builds? | debug metadata, exact bytes, BSim, VexIR2Vec, BinDiff, FIN | an authoritative donor already answers it |
| Did inlining happen here? | FIN (debug info present), SBridge or the inlining dataset method (source present) | stripped and no source |
| Is this candidate equivalent? | objdiff, then CounterTV (x86 vs IR), VeriBin (binary vs binary), Alive2 (IR vs IR), AFL++ differential | no compilable candidate |
| What does the device do? | existing traces, Renode, avatar², PANDA, real hardware | unmodeled peripheral: emit UNKNOWN |
| Who else is writing? | Ghidra Server checkouts, Temporal history, Dolt branches | single-writer corpus |

The router prefers the cheapest tier that can answer, per `tiered-re-analysis`, and
records why each candidate was chosen or skipped.

## Orchestration and durability

Temporal workflows wrap long campaigns: one workflow per corpus campaign, one activity per
bounded task with a measured resource budget. Activities are idempotent on the evidence
contract id because Temporal may run a retried activity more than once. Execution history
is itself provenance and is exported as OpenLineage runs.

## Mapping onto what exists

| Coordinator piece | Exists today | Gap |
|---|---|---|
| Identity graph | `kotorxid.sqlite` identity, implementation variant and instance rows; `logical_id` | Many-to-many edges, contested status, branching |
| Evidence contract | Compile, objdiff and audit receipts under work dirs; `corpus.export-hookpack` provenance fields | One schema, content addressing, lineage emission, signatures |
| Validation gate | objdiff-gated promotion in reconstruct and corpus stages; PASS/FAIL receipts | UNKNOWN as a recorded result; pluggable checks; binary-level equivalence engines |
| Conflict arbiter | One-writer rule in AGENTS.md; program binding | Revision-aware proposals, preserved competing edits |
| Capability router | `tiered-re-analysis` skill; action catalog | Automated engine selection from inventory and cost |

## Non-goals

- Replacing Ghidra, BSim, objdiff or the 8080 catalog.
- Deciding truth. The coordinator records evidence and runs checks; it cannot make missing
  evidence appear.
- Running before qualification. The coordinator is adopted the same way everything else
  is: a local publish, work, verify, materialize cycle first, then wider use.
