# Copy

Calm engineer. Plain, operational English from the operator's side. Say what happened and what it means, and nothing more.

## Keep verbatim

- "A finished job is not a match."
- "Real C and a complete executable are separate facts."
- "Select a function to decompile, rename, and match siblings." (empty inspector)
- "Missing evidence blocks its claim. An unhealthy resource blocks its dependents. Ready independent work continues."
- "Recover from the best evidence, reuse only what transfers, and verify each result at the level where it will be used."
- "Provider paused for this input revision" · "Checking whether the operation completed"
- "diverged — counterpart structurally different, possibly inlined/split"
- "root unresolved on this build; members tried: …" · "Refuse, never zero."
- Match review confirm: "Move 3 rows to verification? This cannot be undone here." Single row: "Accept split for match 18421? This cannot be undone here."
- Held and kept: toggle name "Hold this pane" (never changes); state words "Following · sync A" / "Held · ResourceRef::Resolve @ build-c · 4 min"; "Held · read 14:02"; "◷ Basis changed since held · Refresh"; "◷ Basis changed since kept · Refresh"; "Basis at hold time not recorded"; "Kept", "Make primary", "Follow again", "Release". Limits: "Two center panes in use; kept as a card in Evidence"; "Three cards kept; release one".
- Following: "Follows · on Enter" in a following pane's header; a commit-on-Enter pane whose selection moved, "Shows ResourceRef::Resolve; selection is now Actor::LoadFromTemplate · Enter to load". An armed ActionStrip after the selection moved: "Bound to ResourceRef::Resolve · selection is now Actor::LoadFromTemplate · Rebind".
- Refused decision: "What changed since you looked". Row change words: "changed since you looked", "new since you looked", "left this page since you looked", "unchanged". After a reload: "Changes since the previous basis are not available; all rows need re-reading." The assertive refusal line: "Decision refused: basis changed. 2 rows changed and were unchecked; nothing was applied. F8 steps them after Step changed rows."
- Submitting and outcomes (words from the Job outcome vocabulary): "Submitted a3f9 for 0041b210 · pending"; "Already submitted a3f9 for this target · running"; "outcome in dock · job a3f9"; batch summary "4 runs: 1 running · 2 finished · 1 failed". Nothing is announced on pending. An inline edit ends with one terminal message: "Rename saved: local_8 is now itemCount on build-a, job a3f9."
- Worklists: "position 4 of 12 · 7 visited · 3 handled"; "visited ≠ reviewed"; "Handled is your checklist, not a review decision, and starts no work." Never "done", "complete", "reviewed" or "checked off" for worklist items. Snapshots say "as of 14:02" beside their source link. A target that vanished "no longer resolves on build-b"; it is never called absent.
- Navigation: "Open beside" (on 8080 without split panes, "Open beside (new window)"); "Update panes: As I move / On Enter"; "Not loaded. Open to read it."; "Not decompiled in this session · Enter to decompile"; "no earlier location in this tab"; Back's description before a program change, "Back · clears 12 checked rows on build-a"; copy confirmations, "Copied address 0041b210, build-b".
- Another project: "This link is for project corpus-beta. You are in corpus-alpha. Opening a project admits its eligible missing work and reuses its receipts." Buttons "Switch to corpus-beta" and "Stay". Never switch silently.
- Unresolved locations are words: "Event ‹id› is no longer retained", "Worklist not available here", "Address 0041b210 has no build; it exists in build-a, build-c", "contested · no winner".
- Operator mantra: "Selection is intent. Strip is command. Dock is truth. Palette is jump. Save is metadata. Finished ≠ match."

## Claim boundaries use ≠

candidate ≠ acceptance · compile admits candidate, not replacement · floor ≠ recovered C · local zero ≠ full-image or behavior proof · exported plan ≠ live detour permission · result exists ≠ independently accepted claim · deadline ≠ termination · byte journal rollback ≠ undo of executed side effects · liveness ≠ execution progress ≠ goal progress · Accuracy ≠ acceptance · Compiling C ≠ verified recovery · effective ≠ byte match · aligned ≠ equivalent.

## Outputs, reports and compiler-aware views

Keep verbatim:

- "Accuracy ≠ acceptance." An accuracy or parity report's numbers never appear as acceptance: "This report is accuracy. 1,142 matched functions on build-a are not accepted."
- "Compiling C ≠ verified recovery."
- "no report": a run is recorded but its report file is missing ("∅ no report · run a61f recorded; its report file is missing").
- "previous report not found · changes not available". Never "no changes" for a missing or stale previous report; a stale one reads "not computed · the report is stale".
- "varies across builds · not averaged", with the best and worst build named. Builds are never averaged, and reports from different source revisions are never merged ("Merge refused for build-d: different source revision").
- "provider differed": "⇄ build-c: requested ‹profile›, served ‹compiler› · provider differed".
- "done" only at exactly 100%: "1,188 of 1,188". Fractions are exact ("1,142 of 1,188"), and percentages are truncated, never rounded up (96.1%, not 96.2% and never 100%).
- "Scores from different tools are never compared or averaged." Each score names its own tool ("0.81 BSim similarity", "38 bytes differ objdiff").
- "Reconstructed explanation, not observed compiler passes." This is the first line of every transformation timeline, followed by "Order is the conventional stage order, not an observed sequence".
- Evidence words: "witness", "record", "hypothesis (heuristic)" with "basis: …", and "unknown". "absence is not proof". A hypothesis never reads as a witness.
- "Delivered means a receipt records bounded evidence for that scope; it does not mean the artifact is live, current or accepted." · "not observed on 8080".

## Coverage phrasing

"resolvable on {build-a, build-b, build-c}, ambiguous on build-d, absent on build-e". "entity X: resolved on {…}, member used; unresolved on {…}". Always name the scope: "byte-identical in build-b (max-C variant)", never "matched".

## Confirms

Title is verb + object ("Remove build-c from corpus-alpha"). One sentence of consequence. The primary button is the verb ("Remove"); Cancel is always visible. A mutating confirm names its exact target. Never a naked "Are you sure?".

## Errors

Name the field from the catalog and where to fix it: "`kb` is required. Enter it in Fields…". Never show model names or internal class names. "No recovered C on disk" is not "Decompile failed". Transient read errors keep the last content and say how old it is: "Reconnecting. Showing data from 14:02."

## Forbidden

"Success!", "All done!", "Matched!", "Completed with flying colors" · "decompile updated" after an edit (the terminal message names the change and its job) · green celebration or confetti · "≥90% recovered" · "100% confidence" · "40–60% instantly" · "works on all builds" · invented percentages, ETAs or "unmeasured" where a measurement could exist · "Project data combined." · an application-wide "Working…" · a lease countdown presented as a release time · toast spam on poll · "contested" outside the locator set · "no changes" when the previous report is missing · a percentage rounded up, or "done" below exactly 100% · an average across builds or across tools' scores · "observed" or "live" for an artifact with only a receipt · product, game, binary or company names in design artifacts.

## Terms

logical entity / implementation variant / physical instance · recovery unit ≠ compilation unit ≠ comparison unit · byte-accurate C+assembly-floor vs max-C · reconstruction vs original-style rebuild · project → folders → programs (reserve "repository" for Ghidra Server) · reused vs fresh evidence · accepted vs candidate source.
