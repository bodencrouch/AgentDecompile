Read `entrypoint/RECOVERY_LOOP.md` from "What we export" to the end.

Produce the per-binary source bundle for `<build id>` and the separate exports the corpus
supports, through the existing catalog (`corpus.export-hookpack` and the advertised
siblings), into `<output directory>` on NVMe.

For each product, state its own validation result separately:

- Source bundle: compile under the identified toolchain; per-function objdiff; the
  function map with claim tier per function; correspondences with unresolved pairs kept.
- Hookpack: every site with its expected bytes, build instances and adapter key; list every
  site whose expected bytes are missing and call none of them safe.
- WASM-ready code and Lua interfaces: only where the corpus has them; report their own
  harness results.

Say explicitly that the bundle is not a verified whole-image build unless a fresh
whole-image compile plus objdiff zero-difference receipt exists for this build.
