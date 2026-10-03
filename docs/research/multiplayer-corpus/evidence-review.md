# Scoped evidence re-review

Reviewed `/tmp/corpus-evidence-fix.md`, revised documentation, and the five new retained disassembly exports. No tests repeated, no binary hash checks repeated, no live MCP, and no repository edits.

1. **ADDRESSED — receiver/privilege raw evidence.** Five new exports retain the receiver, getter, wrappers and server internal handler instructions, with input SHA256 and commands. They substantiate the earlier instruction-level conclusions. Independent receipt/hash validation remains with the parent.
2. **ADDRESSED — universal fourth-argument zero claim.** README and engine evidence now restrict the directly supported zero value to a named call and explicitly disclose missing reaching definitions for other register pushes. The four-stack-argument ABI conclusion is preserved.
3. **ADDRESSED — existing versus proposed transport.** Comparison-engine evidence now clearly distinguishes the original in-process queue from the proposed remote transport.
4. **ADDRESSED — both-mode acceptance wording.** Separate co-op and persistent-world ledger rows exist and remain unpassed. Final scoped check confirmed README.md:109 now says 'then implement both required gameplay modes', closing the remaining ambiguity.

New breakage caused by these fixes: none found. This review does not certify any source-built executable or multiplayer implementation.
