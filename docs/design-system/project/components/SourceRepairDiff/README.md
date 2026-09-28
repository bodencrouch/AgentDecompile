# SourceRepairDiff

Source recovery drawn as the work: the actual source change beside the compiler diagnostic or semantic evidence it addresses.

**Consumer provides** the candidate revision pair, the diagnostic, the exact compiler, flags and ABI, and the retry history.

- Diff well: removed lines on `lane-fault-fill` with −, added lines on `rep-candidate` with +. The diagnostic sits above in mono.
- Repairs explain preserved machine behavior. A cleaner decompile is hypothesis refinement, not validation.
- Retry history lists deterministic helpers first, then one bounded LLM cleanup, with each exact proposal recorded.
