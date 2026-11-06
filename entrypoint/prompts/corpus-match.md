Read `entrypoint/AGENT_BOOTSTRAP.md` and `entrypoint/RECOVERY_LOOP.md` sections 1 to 5.

Treat the builds in `<directory>` as one corpus. Through the existing 8080 catalog
(`GET /api/v1/actions`), not a direct CLI:

1. Register every build. Mark the STABS/DWARF build as the donor. Reuse existing Ghidra
   analysis; do not re-run `analyze-program` where analysis exists.
2. Run identity matching in STRATEGY's layer order. For each proposed pair record which
   evidence layers agreed, which disagreed and which were unavailable.
3. Leave ambiguous, absent, inline, split and folded cases visible and unresolved.
4. Report identity coverage (functions bound to a `logical_id`), auto-accept precision as
   far as it can be measured against the donor, and the unresolved and ambiguous counts.

A match is a transfer channel, not proof. Do not promote any pair by score or by vote.
