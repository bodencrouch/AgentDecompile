# Independent Vite reference workbench review — 2026-10-09

Scope: bounded CompareView.tsx / compare.css source slice described in vite-reference-workbench-2026-10-09.md. This is not acceptance of the complete project-wide workbench. No builds, tests, browser sessions, servers, native applications, commits, or implementation edits were performed for this review.

## Verdicts

Spec: the bounded source slice substantially follows its brief: observed source sits beside recorded target/candidate alignment; source visibility is local; difference inspection no longer immediately changes shared selection; explicit address navigation retains a return-function breadcrumb. Both existing function-list response shapes are supported. Complete project-wide visual comparison remains explicitly open in the implementation report and is not a regression finding against this slice.

Quality: changes requested for one Important stale-navigation issue. No Critical findings. Source-only acceptance cannot establish rendered responsiveness, keyboard focus behavior, packaged activation, or visual fidelity. Cockpit API unreachable and existing bundle errors are reported baseline runtime gaps, not evidence that this unbuilt source introduced them.

## Important finding: inspected address outlives its recorded evidence

CompareView.tsx stores inspectedAddress in ComparePanel and clears it only by remounting for a changed selection query. useFunctionEvidence polls every five seconds. A successful refresh can replace the alignment/mismatch receipt or remove its addresses while leaving the same selection query; the old inspectedAddress and its Navigate to address button remain. InstructionDiff separately resets its selected row whenever rows change, so the visible highlight can disappear while navigation still targets the previous receipt's location.

Concrete case: inspect target address A in receipt R1; a refreshed response R2 contains only address B or no aligned rows/mismatches. The interface still offers navigation to A as an inspected target address beneath R2. This weakens the relationship between visible evidence and the address action. Revalidate the inspected address against current alignment/mismatch addresses on evidence replacement, or clear it when its supporting evidence changes. Retaining it during loading with the same saved evidence is reasonable. This finding was sent to the implementing worker and root for routing; this review does not authorize implementation.

## Source review evidence and limits

- useData keys responses by URL, suppresses old-selection data immediately, aborts replaced reads, and retains the same selection's saved data on refresh errors. Combined with ComparePanel's selection key, this prevents the prior function's source/receipt being displayed under a new selected function.
- SourceEditor receives allowDraft=false and observed sourceWitness/sourceExtent output. The adjacent observation/candidate receipt warning preserves the distinction between decompiler/source observations and byte proof; existing matchingPhase verification and receipt parsers are reused. No new mutation endpoint or scheduler was introduced in the reviewed change.
- Navigation through previous/next difference and mismatch buttons stays local until the explicit native button is activated. Workstation mergeSelection clears changed function/logical identity on an address change. lastFunctionAddr supports the existing Last function return action; it is a breadcrumb, not a guarantee that an interior-address request continues to fetch at the entry address.
- Native source-toggle/navigation buttons, aria-pressed, labeled sections, the existing labeled source editor, and the focusable instruction-table scroll area provide reasonable source-level accessibility. The inspected-address update has no dedicated live announcement; rendered screen-reader behavior remains unverified.
- The new container query uses actual document width and minmax(0, …) constraints, and existing global media rules stack the symbol rail. New narrow rules make the workspace scroll and permit toolbar wrapping. The existing duplicate compare selectors in InstructionDiff.css and workstation.css make real cascade/layout verification necessary before responsive acceptance. No confirmed new CSS failure was established from source inspection.
- The report accurately distinguishes syntax parsing/diff checks from typechecking/build/runtime proof and does not claim that the existing packaged bundle contains the change. Reference citations are attributed with their inspection limits; this review did not independently browse the reference sites.

Review artifacts examined: the bounded implementation report and embedded incremental diff; current CompareView.tsx and compare.css; useData/useFunctionEvidence; SourceEditor; InstructionDiff/DiffEvidence; selection query/merge contracts; relevant existing workstation/editor styles.

## Fix round 1 re-review

Previous Important finding: ADDRESSED in current CompareView.tsx source. The rendered navigation uses currentInspectedAddress, derived synchronously by checking the selected address against current alignment rows or memoized mismatches. Therefore an address removed by refreshed evidence is absent from the rendered navigation before the effect runs. The effect clears invalid stored state, preventing a removed address from reappearing automatically on a later receipt. Addresses still supported by current recorded evidence remain inspectable, including during same-evidence loading.

Bounded spec verdict: PASS for the stated source slice. Quality verdict: PASS at source-review scope, with no remaining Important or Critical findings in the reviewed fix. The change adds no conditional hooks, API contracts, proof claims, mutation behavior, or selection-scope changes. Existing runtime, build, responsive, and accessibility acceptance limits above remain. No tests, builds, browser actions, backend/static inspection, or implementation edits were performed in this re-review.
