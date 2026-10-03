# Task 8.1 review

## Spec compliance

**Verdict: compliant for the bounded explicit-input/source-snapshot packaging slice.** No actionable missing, extra, or misunderstood requirements found. This is not completion of U8 or U21.

Reviewed the owned-path package from base `d966fefcaeef5cc185de4ac6bdaa371a5ab28301` to head `2590e25a5926d195f34e88b0675095cf1891e6c2`, following the task-reviewer prompt and Task 8 brief. Unrelated commits are excluded by the supplied package.

## Strengths and requirement evidence

- Explicit input contract and layout are implemented at `src/agentdecompile_recovery/corpus/package_authoritative.py:118` and `:289`: required workspace/recovered/coverage inputs, optional output/config, workspace-relative output and assembler paths, and forwarding of the optional configuration. The missing-basis and existing-output checks precede output creation (`:126`, `:132`, `:203`). There is no installation-relative input fallback.
- The package opens an existing database with `mode=ro`, checks the consumed schema columns, and closes it on success and refusal (`package_authoritative.py:51`, `:140`). The package no longer invokes the creating/migrating shared database helper. Each listed non-DRM assembler tree is checked before output mutation (`:149`).
- One deep-copied coverage index supplies parser admission and retained observation provenance (`package_authoritative.py:157`). The optional parser keyword preserves old callers and explicitly distinguishes `None` from an empty supplied dictionary (`src/agentdecompile_recovery/corpus/ingest_recovered.py:245`, `:263`). The corresponding unrun regression distinguishes pinned, absent, and empty snapshots (`tests/test_ingest_target_binding.py:62`).
- `_source_snapshot` checks candidate/observation source and target digests, checked region address, offset, size and comparison bytes before reading and hashing the candidate's exact current bytes (`package_authoritative.py:81`). It checks the shared real-C classifier against those bytes and refuses conflicting header or symbol hints. Selection uses the checked address exclusively; the legacy unique-byte fallback is removed.
- Retained source bytes are written directly at `package_authoritative.py:214`, while metadata preserves the producer source digest and original coverage observation (`:191`). No later source-file reread can substitute different exported bytes. The unrun mutation fixtures separately cover edits after parsing and after package snapshot capture (`tests/test_package_authoritative_binding.py:219`), and ledger replacement after observation capture (`:242`).
- Parser refusals survive and gain the pinned observation where available (`package_authoritative.py:161`); package refusals retain source/target provenance (`:169`, `:188`). Tests specify legacy, stale, withdrawn and changed-target refusals, including an available legacy byte extraction that cannot rescue them (`tests/test_package_authoritative_binding.py:169`).
- Selection excludes binaries outside the canonical non-DRM export set (`package_authoritative.py:175`), refuses duplicate selected addresses (`:185`), exports the selected set (`:205`), and derives manifest/return counts from that same set (`:229`, `:256`). The positive fixture specifies exact byte/digest/provenance and count-to-export checks (`tests/test_package_authoritative_binding.py:69`).
- Metadata and README qualify `verified_c` compatibility names as local readable-C selection, retain canonical placement and assembler representation separately, and explicitly mark independent acceptance unavailable (`package_authoritative.py:198`, `:239`, `:275`). Direct output writes and external assembler symlinks remain openly unqualified for the broader atomic/portable bundle contract (`:244`, `:280`). No source or ASM recovery promotion is introduced.

## Issues

- Critical: **0**.
- Important: **0**.
- Minor: **0**.
- Actionable finding IDs: **none**.

## Quality assessment

**Verdict: Approved for the bounded source-review gate.** The source-snapshot helper separates admission from publication, and the minimal parser keyword avoids duplicating ledger loading or changing existing parser consumers. The fixture sources exercise meaningful positive, refusal, provenance and mutation boundaries; they are not passing acceptance receipts.

## Checks and evidence limits

- Read the task-reviewer prompt, Task 8 brief, implementer report and supplied diff. The initial combined tool output truncated the package implementation; recovered only that missing diff section with bounded `sed` reads. No Git commands or AST checks were rerun. A subsequent text-only `awk` locator pass over the same package supplied current-file line numbers without rereading changed files in full.
- Named risk: parser field normalization could make the new candidate/observation equality gate reject valid admitted observations or incorrectly attach metadata. Read the parser continuation cut off by the diff hunk (`ingest_recovered.py:265–325`) and its source/target binding helpers (`src/agentdecompile_recovery/corpus/coverage_evidence.py:19–28`, `:55–116`). The parser preserves digest/region values and lowercases `originalBytes`; the new package comparison matches that contract. Existing target checks remain explicitly limited to recorded target bytes.
- Named risk: slug-keyed selection/export could alias two admitted canonical DB binaries. Checked only the defining inventory schema (`src/agentdecompile_recovery/corpus/db.py:19–22`); both canonical `repo_path` and `slug` are unique. This supports the ordinary admitted-database count/set argument; this review is not an independent inventory audit.
- Named risk: the new readable-C gate could reference a different classifier API. Checked the shared classifier definition (`src/agentdecompile_recovery/corpus/source_claims.py:117–121`), which delegates to the existing C readable-source validator. No classifier execution was performed.
- **Not verified:** test execution, package execution, installed consumer behavior, filesystem immutability under an executed package, runtime/platform behavior, live 8080 activation, independent source acceptance, whole-image proof, full atomic bundle behavior, or clean-host portability. The implementer's AST and whitespace checks remain reported evidence; they were not rerun. `tests/test_package_authoritative_binding.py:69–283` and `tests/test_ingest_target_binding.py:62–75` are unrun fixture specifications.
- No tests, builds, proofs, source imports, databases, runtime/process/service tools, recovery operations, commits or subagents were used. Only this review report was written.
