Read `entrypoint/AGENT_BOOTSTRAP.md` first.

Triage `<path-to-binary>` and its sibling builds in `<directory>` at Tier 0 and Tier 1 only.
Do not open or analyze anything in Ghidra yet.

Report, with provenance for each fact:

1. Format, architecture, hashes, sections, imports, version strings and any debug metadata
   (STABS, DWARF, PDB paths) per build.
2. Which build looks like the debug donor and why.
3. Toolchain hypotheses, as named calibration profiles with the evidence for each, not a
   single guess.
4. What already exists for these binaries: `db/kotorxid.sqlite` rows, Ghidra projects and
   bindings, verified source, audit receipts. Label every reused item as reused.
5. The cheapest sufficient next tier and the single bounded action you recommend.

Say "insufficient evidence" wherever two readings fit the data.
