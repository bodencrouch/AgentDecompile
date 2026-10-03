# Task 4.1 review

**Spec compliance: APPROVED for the bounded source slice.**

**Code quality: APPROVED for source acceptance.** No Critical, Important or
Minor findings were identified. This is not live approval, positive recovery
acceptance, or U4/U33 closure.

## Scope and evidence

Reviewed the supplied owned-path diff once, from
`bb41404123636d456862aac7c0850427b4a111af` to
`1c74b9c5f3098bf84639c07d92decf22023b58fd`, against `task-4-brief.md` and the
adopted `next-linked-contribution-contract.md`. Read `task-4-report.md` as
claims to check, AGENTS.md, src/CLAUDE.md, and the SDD
`task-reviewer-prompt.md` template. The installation has one combined reviewer
template, rather than separate spec and quality templates.

The diff includes all three required production paths and the new regression
source. No unrelated parity, matrix, generic compilation, terminal dashboard
consumer, or ownership-policy changes occur in this review package.

## Spec compliance

- `src/agentdecompile_recovery/corpus/verify_direct_full_image.py:104–120`
  constructs the unavailable contribution internally, with exact unsupported
  status, refusal reason and six missing bindings in the specified order.
  The reason is appended to errors and `verified` is unconditionally false.
- `src/agentdecompile_recovery/corpus/verify_direct_full_image.py:99–103,128–141`
  preserves independently measured size/hash equality, adds accurate claim
  wording, sets `compilerProducedWholeImage` false, retains receipt persistence
  and summary output, and returns nonzero. Generic link output and local
  diagnostics cannot override the refusal. No imported-proof input, callback,
  trust flag or bounded reconstruction observation was introduced.
- `src/agentdecompile_recovery/corpus/cli.py:720–721` sets precisely the
  existing direct action's mutating and long-running attributes. Its public
  argument list and exact action name remain intact.
- `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py:2127–2159`
  handles the exact `work-dir` key for incoming and stored direct-action jobs,
  canonicalizes incoming paths against the current execution root and stored
  paths against their recorded root, and retains the legacy branches for other
  actions. Active-status filtering and exact canonical duplicate comparison
  remain intact.
- `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py:2172–2191`
  applies the same action-specific canonicalization to the external exclusion
  hint. The diff adds no external-contract allowlist entry, resource release
  authority, reconciliation authority, Ghidra-writer classification or new
  admission path. The unchanged process-text lookup remains an exclusion hint,
  not a proof of ownership or safe admission.
- `tests/test_direct_full_image_boundary.py:77–223` authors the required
  refusal, retained equality/diagnostics, forged input, freshness, pre-existing
  work, metadata, duplicate-alias and unrelated-action cases. The full set is
  source evidence only; none was executed for this review.

## Code quality and strengths

- The terminal correction is local and explicit. The receipt distinguishes
  measured equality from unavailable contribution proof without adding a
  speculative trust framework
  (`verify_direct_full_image.py:104–132`).
- Canonical path handling reuses the existing helper rather than introducing a
  competing normalization policy. The direct-action condition keeps other
  callers' key precedence and resolution behavior unchanged
  (`dashboard/actions/jobs.py:2127–2159,2172–2191`).
- Regression source exercises the real direct runner with only its expensive
  producer calls replaced; it asserts the receipt, diagnostic build payload,
  summary, exit status and fresh-work behavior. Mock output is explicitly
  framed as refusal evidence, not successful recovery
  (`tests/test_direct_full_image_boundary.py:27–149`).
- Lookup regressions exercise the existing helper logic with stored records,
  a different cwd, relative/absolute/symlink aliases, all three active statuses,
  completed jobs and unrelated legacy keys. The synthetic proc fixture
  preserves the Path type needed by canonicalization
  (`tests/test_direct_full_image_boundary.py:166–223`).

## Findings

- **Critical:** None.
- **Important:** None.
- **Minor:** None.

## Focused context checks and limits

The following named risks justified narrow source reads beyond the diff:

1. **Fixture validity and retained diagnostics:** the direct runner's
   preflight/build block was omitted between diff hunks. Read only
   `verify_direct_full_image.py:32–94` to check fixture prerequisites, owned
   work creation, preserved compiler/local-verifier calls and freshness errors.
   Checked `verify_full_image_receipt.py:35–57` to confirm the synthetic local
   receipt satisfies the existing loader and the asserted unmatched error is
   the actual loader message. This source tracing supports the intended cases;
   it does not establish that the tests execute successfully.
2. **Path resolution versus actual execution root:** checked
   `dashboard/actions/jobs.py:411–440,1000–1019,1064–1077`. The canonical helper
   resolves relative paths against its supplied base; job creation captures the
   same current root, and execution consumes the recorded root.
3. **Metadata accidentally granting ownership authority:** checked
   `dashboard/actions/introspect.py:120–161` and
   `dashboard/actions/jobs.py:442–459`, plus a targeted search for the direct
   action in jobs.py. Parser attributes feed the corpus action metadata, the
   corpus backend does not trigger the MCP-mutating Ghidra condition, and the
   only direct-action mentions in jobs.py are the two lookup branches. No
   direct-action allowlist membership was introduced.

Cannot verify from source review: executable regression results, actual
compiler/linker behavior, safe compiler/Wine/source/output admission, complete
child/writer lifetime closure, loaded consumer activation, real same-build
replacement ownership/fixups, variant binding, fresh whole-image recovery or
original-game launch. These remain separate open gates. The report's prior
AST/JSON/whitespace checks were not rerun and are not independently reproduced
evidence here.

Checks performed were read-only source, diff and document inspection. No
tests, builds, typechecking, project imports, DB queries or creation, proof
scripts, runtime/catalog/process/service operations, Git mutations, source
fixes or subagents were used. Only this review report was written.

Memory was used solely to retain the established source/live evidence
distinction (MEMORY.md:274,282); current supplied source and contract determine
the verdict.

**Assessment: ready for source acceptance of Task 4.1 only.** The refusal-only
truth correction and exact action metadata/work-key correction meet their
bounded contract. Positive producer and safe live admission work remain open.
