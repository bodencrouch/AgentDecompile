# ArtifactCard

One output or result artifact in full. It says what the artifact proves and what it does not, and gives its identity (schema, hash, basis), the job and receipt that produced it, its members if it is a bundle, its coverage on each build, its determinism rule and its 8080 observation, with historical provenance labelled as historical.

**Use it** when an artifact name is opened from OutputsCatalog, a member list, a receipt, a job's Changed line or the PipelineMap export band (`ws=evidence&panel=outputs&artifact=‹id›`, a registered parameter). It sits in the Evidence workspace beside the catalog, or in the evidence rail. Alt+↓ on an artifact link shows its header and first two sections as a Peek. Keep keeps it (`keep=artifact:‹id›`, a registered kind).

**Consumer provides** the inventory row (name, kind, group, format or schema version, tier, the proves and does-not-prove sentences, and the determinism rule text with its source); the stored bytes hash and basis digest per build; the producing verb, job and receipt, with the provider requested and the provider served; per-build coverage with each measure kept separate (matched, linked, fuzzy) and the report state; for a bundle, its members with each member's status, hash and verify-gate outcome; the previous report per build, for changes; and the 8080 observation record, plus any historical observation with its port class.

- **Header.** A back-link when it was entered from a list ("← from Outputs · B · Parity"), never invented otherwise. Then the title in `type-pane-title`; **Copy path** and **Keep** (`aria-pressed`, with Shift+K only inside the card); and a sub-line with the status word and glyph (the OutputsCatalog set), the ClaimTier chip (for a produced artifact only), and the 8080 word. A historical observation adds a dashed ProvenanceStamp: "historical · 2026-09-08 · from a port outside 8080 that current operations forbid · not a current delivery receipt".
- **Sections, in fixed order**, each an h4 in `type-kicker`:
  1. **What it proves · what it does not**: two columns, **Proves** and **Does not prove**. The does-not-prove side leads with the bold ≠ sentence ("Local zero ≠ full-image or behavior proof", "A source ZIP ≠ full-image acceptance", "Packaging adds no claim").
  2. **Identity**: the format or schema version (mono), the bytes hash per build, and the basis digest as a link ("current for build-a and build-b; changed for build-c"). An artifact that was never produced reads "no hash · never produced".
  3. **Produced by**:
     - the verb from the job record (mono; the design names no action ids);
     - the StageChip (full form) from `catalog_verbs`, or "stage: unmapped";
     - the pipeline node;
     - the receipt and job as a ProvenanceStamp link group;
     - **Provider**: when the provider that served a run differed from the one requested, "⇄ build-c: requested profile vc8.0, served cl 19.51 · provider differed", linked to ToolchainEvidence for that build.
  4. **Members** (bundles only): one row each for the member's link, its status glyph and word, and its hash or verify-gate outcome. An optional member is on the chassis fill and says what its absence ships ("absent → not_in_scope receipt"). The section ends "Refused as a whole if any member fails its own verify gate."
  5. **Coverage by build**, one row per build. Measures stay in separate columns and are never summed:
     - Matched (objdiff 0): exact fractions, "1,142 of 1,188", with the percentage truncated to one decimal and never rounded up ("96.1%"). The word "done" appears only at exactly 1,188 of 1,188.
     - Linked, or "not measured".
     - Fuzzy, labelled with its tool and "truncated, never rounded up · not a claim".
     - The report link, or "∅ no report · run a61f recorded; its report file is missing".

     Under the table:
     - When builds differ: "◐ varies across builds", with the best build and the worst build named. Never an average.
     - A merge across source revisions is refused by name: "Merge refused for build-c: different source revision (recorded digest)."
  6. **Changes since the previous report**, per build, broken first. Each build is a `<details>` headed "1 broken · 2 new · 3 improved · 0 regressed · since basis 41c0". The broken table lists entity, before and after, and ends "…and N more".
     - A missing previous report says "previous report not found · changes not available". A stale report says "not computed · the report is stale".
     - Never "no changes" for a missing report.
  7. **Acceptance is separate**: for accuracy and parity reports, three FactBadge claims per build: byte exact · behaviour · toolchain origin. Then "This report is accuracy. 1,142 matched functions on build-a are not accepted.", with a link to Whole-image acceptance.
  8. **Determinism rule**: the rule in a mono well ("re-run under the same basis → byte-identical bundle"), with its source ("design text from the export-target node · not yet checked by any receipt") when no receipt has checked it.
  9. **On 8080**: ⊡ "Not observed on 8080", with the reason. Reused receipts are called reused ("from 3 days ago; they are not fresh progress"). A historical observation from a forbidden port stays historical and is never shown as fresh.
- Surfaces and fit: a `pane` card with a 1px `line` and square corners. It fits the evidence rail (260–480px) and the Evidence workspace; two cards sit side by side at 400px each or wider.
- Read-only by construction. The card never exports, verifies, downloads by itself or re-runs anything. Unstored evidence says "Not loaded. Open to read it."

**Linking**

- **Publishes:** nothing by itself. Keep publishes `keep=artifact:‹id›[~basis]` (replaceState). Opening a member or a related artifact is a Go that pushes `artifact=`.
- **Follows:** the `artifact` in the location, after the settle. A Kept copy is read-only, says "Kept", and reads "◷ Basis changed since kept · Refresh" when its basis changes.
- **Targets rendered:**
  - back-link → OutputsCatalog at that row;
  - basis digest → the ProvenanceStamp detail;
  - receipt id → receipt card;
  - job id → the dock Jobs record;
  - StageChip and node id → PipelineMap node;
  - member → its ArtifactCard;
  - entity in a change table → the Code Browser at that build and address (always with `build`);
  - provider line → ToolchainEvidence for that build (`panel=toolchain`).

  Link names read "Job a61f, corpus.objdiff-check, finished, no report".
- **Peek source:** stored receipt headers, the inventory row, the stored change summary. Nothing is fetched.
- **Absent copy:** "no receipt" · "job not recorded" · "no hash · never produced" · "stage: unmapped" · "∅ no report" · "previous report not found · changes not available" · "not measured" · "not observed on 8080".
- **Target-size exception:** none. Links in `<dl>` rows and member rows are at least 24px, and 44px below 700px.

**Keyboard**

- Tab moves through links, buttons and change disclosures in section order. Enter on a link is Go, Shift+Enter opens beside, Alt+↓ peeks, and Shift+F10 opens the link menu. Enter or Space toggles a change group.
- Shift+K (only while focus is inside the card, remappable) toggles Keep. Esc follows `keymap.json` `escapeOrder`. F6 leaves the rail, and returning restores the last-focused element.

**Accessibility**

- A `section` labelled by its h3, with h4 sections, so screen-reader users jump by heading. The coverage table has row headers per build. Status glyphs are `aria-hidden` beside their words.
- Disabled Copy path and Download are `aria-disabled` and name the reason through `aria-describedby`.
- Never color alone: the historical frame is dashed and the word "historical" is text. "Provider differed" is ⇄ plus words. "Varies" is ◐ plus words.

**Removes switching:** reading one artifact's proof boundary, provenance, per-build coverage and changes happens in one card, instead of opening the receipt list, the dock, the diff report and the docs separately.
