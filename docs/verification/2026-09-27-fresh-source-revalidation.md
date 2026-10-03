# Fresh source revalidation after process loss — 2026-09-27

Status: source independently approved; isolated `.13` wheel built and all 60
installed checks passed. Independent artifact review approved. Partial P0.4/RC-02;
no catalog, live-game or whole-image recovery acceptance.

## Delivered source route

`corpus.source_revalidation.revalidate` accepts a bounded untrusted candidate
recipe, explicit target/DB/binary context and a new private workspace. It verifies
current input digests and selected function rows, invokes the existing supported
compiler for each eligible candidate, and gives only newly produced opaque objects
to the existing reconstruction writer. It passes that live observation directly
into the existing matching-status consumer. Saved recipes request work; saved
audits never restore compiler or writer authority.

Candidates execute sequentially in stable ID order. A changed/rejected candidate
gets no contribution credit while a valid independent sibling can advance.
Explicitly discarded candidates stay excluded. The producer's actual source and
target digests must match the recipe after compilation, even when the source was
changed during compilation and later restored. Copied floor bytes may preserve
whole-file equality but never earn compiler-produced whole-image credit.

The initial route accepts at most 256 KiB of JSON, 32 candidates, 1 MiB per source,
a 128 MiB target, a 256 MiB corpus DB and 100,000 selected function rows. Unknown
schema/authority fields, duplicate keys and unsupported selection policies refuse.
Canonical DB paths containing SQLite URI metacharacters `?`, `#` or `%` are
unsupported because existing consumers interpolate URI paths differently.
All generated files stay in the exclusively created private workspace; existing
workspaces, output files and symlinks are refused.

## Source evidence

The decisive real-process fixture runs A, B and C separately using the supported
native compiler over a tiny synthetic PE target. A produces two candidates and
exits. B rejects old audit/lookalike objects, rejects changed source A, and freshly
compiles candidate B with a new invocation ID. Matching-status credits exactly
one selected function and six bytes, with an actual object write at offset 0x210.
C still gets zero from importing B's audit. Old outputs remain present and equal;
that equality cannot restore candidate A's contribution.

The final new-module snapshot passed **27 tests in 24.52 seconds**, including
source substitution/restoration and URI-path refusal. Earlier adjacent runs passed
39 cases in 49.43 seconds and 39 in 188.83 seconds; these selections overlap and
the latter began before final diagnostic/URI edits. They are not presented as one
final 60-case source run. The intended installed selection is all 60 cases across
revalidation, existing contribution, matching consumers and whole-image accounting.

Final reviewed-candidate hashes:

- `source_revalidation.py`: `5c622020257497a5f884f8f6a0548e4cf08d82f79416a4bfc20205ac17a0f349`.
- `test_source_revalidation.py`: `419cb3c9167f64c89fa7c725dff0f3581a330ba2eee01118db7996f7dedfbb7f`.

The implementation report, exact added-file diff and review are retained under
`/home/brunner56/Documents/AgentDecompile-fresh-revalidation-*.md` and `.diff`.
Raw source logs and the copied diagnostic three-process fixture are in
`/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-fresh-revalidation-source/`.
Copied fixture files do not carry acceptance authority.

## Installed artifact evidence

The genuine PEP 517 wheel is `2.0.1.dev0+autonomy20260927.13`, retained under
`/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-fresh-source-revalidation/`.
Wheel SHA-256: `9e8bb908be77b81a6d68d7b17b7ad99a320aebe8cce6661936fb5fab86ec58c9`.
Source/test reproduction archive SHA-256:
`68f2ec1d423a799a979f32fce23cf6577c0587db434ce979f0f3eff3cad9272b`.

The package explicitly reuses verified `.12`: 596 byte-equal members, one approved
new module and three generated metadata/version members, with zero removals. The
parent independently checked all 600 member hashes and the exact source overlay.
All 42 retained static/webui assets match the base and installed bytes; no frontend
rebuild or new runtime dependency download was needed.

The sole final installed selection passed **60 tests in 181.36 seconds** across
all four files, using a fresh isolated installation. All five process-origin
receipts—preflight, pytest and actual A/B/C children—resolve to installed bytes.
The actual native subprocess route retained changed-A rejection, fresh B production,
six-byte physical placement and exact consumer credit, then C's zero imported credit.
An initial dependency-path preflight failed before testing because an obsolete
user-site pathlib backport shadowed the standard library. Selecting the previously
verified dependency directory corrected it without installing packages or changing
product source; both attempts are retained in the report.

Final independent artifact review approved: it corroborated all 600 wheel members,
the approved source overlay, five process-origin receipts, the four unchanged staged
test files and the completed installed log. These checks establish the bounded
installed offline route and do not confer authority on copied diagnostic artifacts.

## Remaining boundaries

This is an explicitly invoked offline API, not an automatic restart scheduler or
a catalog-operated game-target workflow. Existing compiler/writer/evaluator path
rereads retain their prior scope; this increment does not provide a hostile-filesystem
sandbox or general toolchain support. Process loss still removes current authority.
A further process requires qualified fresh work; durable trust without reexecution
remains open. Full P0.4, RC-02 and M0 remain partial.

8080 had no listener; no service, provider, game or recovery operation was started.
The [original contribution receipt](2026-09-27-source-contribution.md) defines the
supported relocation-free object/exact-placement subset reused here.
