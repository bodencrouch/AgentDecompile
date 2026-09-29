# ProvenanceStamp

Where a figure or artifact came from and how fresh it is: reused or fresh, current or historical, measured or estimated, with basis and age; a link group to the receipt, the producing job, the basis and the witness.

**Consumer provides** the evidence origin (fresh, reused, historical, legacy), measured vs estimate, the basis digest, the observation time, and when recorded the receipt id, the producing job with its stage, and the tool or witness.

- The origin word sits in a small frame. **Fresh** is a 2px `ink-strong` frame, never the accent (the accent is not a status). Reused: a plain 1px `line-control` frame. Historical: dashed. Estimate: dotted. Digests and times in `type-code-small`.
- Label reused evidence as reused. Never backfill a fresh-run claim. A historical receipt is not fresh progress.
- Every figure shown in a pane carries a stamp or sits under one.
- **Snapshots are not stamped.** A worklist, a Recent entry or an Accessible View snapshot is view state, not evidence: it says "as of 14:02" (or "as read 14:02") beside its source link, never a stamp. A target that vanished "no longer resolves on build-b"; it is never called absent.
- **Link group**: receipt → receipt card · job → dock Jobs record · basis → basis detail · witness or tool as words (not a link). Receipt stamps also carry a StageChip ("7 Continuous parity") linking to the PipelineMap node, rendered only from the producing verb's `catalog_verbs` mapping; an unmapped verb reads "stage: unmapped", with no lane guess. Links appear only where the record names the target; nothing is correlated by timing.

**Linking**

- **Publishes:** nothing.
- **Follows:** the evidence it stamps. Not holdable itself; it stays with the held pane or Kept card that shows its evidence.
- **Targets rendered:** receipt id → the receipt card, which links back "Produced by job ‹id›" · job id → the dock Jobs record, focused · basis digest → the ProvenanceStamp detail and what changed since · StageChip → the pipeline node. The witness or tool is words. Link names read "Receipt 3e10, objdiff, fresh"; "Job c4e1, verify.objdiff, finished"; "Basis 9f3c, current".
- **Peek source:** the stored receipt header, the job record's three readouts, and the basis change summary; nothing is fetched.
- **Absent copy:** "job not recorded" · "basis unknown" · "legacy · no basis recorded" · "stage: unmapped". Never a link to a guessed job.
- **Target-size exception:** spacing: the group's short links are separated by `·` separators on one line.

**Keyboard**

- The group is a set of links in Tab order; each follows the linked-views grammar (Enter go, Shift+Enter open beside, Alt+↓ peek, Shift+F10 the one link menu).

**Accessibility**

- `role="group"` named by the origin and kind ("Provenance: fresh objdiff"). The origin word is text; frame style is a second cue. Identifiers carry `translate="no"`.

**Removes switching:** opening the dock and the receipt list to learn which job produced a figure and what its basis was (J02, J35).
