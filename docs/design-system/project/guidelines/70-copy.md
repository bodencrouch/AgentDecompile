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
- Held and kept: toggle name "Hold this pane" (never changes); state words "Follows · as I move" / "Follows · on Enter" / "Held · ResourceRef::Resolve @ build-c · 4 min" / "Counterpart of ResourceRef::Resolve · derived"; "Held · read 14:02"; "◷ Basis changed since held · Refresh"; "◷ Basis changed since kept · Refresh"; "Basis at hold time not recorded"; "Kept", "Make primary", "Follow again", "Release". Limits: "Two center panes in use; kept as a card in Evidence"; "Three cards kept; release one".
- Following: "Follows · as I move" or "Follows · on Enter" in a following pane's header (the only follow words; never "Following" or "Follows selection"); a commit-on-Enter pane whose selection moved, "Shows ResourceRef::Resolve; selection is now Actor::LoadFromTemplate · Enter to load". An armed ActionStrip after the selection moved: "Bound to ResourceRef::Resolve · selection is now Actor::LoadFromTemplate · Rebind".
- Refused decision: "What changed since you looked". Row change words: "changed since you looked", "new since you looked", "left this page since you looked", "unchanged". After a reload: "Changes since the previous basis are not available; all rows need re-reading." The assertive refusal line: "Decision refused: basis changed. 2 rows changed and were unchecked; nothing was applied. F8 steps them after Step changed rows."
- Submitting and outcomes (words from the Job outcome vocabulary): "Submitted a3f9 for 0041b210 · pending"; "Already submitted a3f9 for this target · running"; "outcome in dock · job a3f9"; batch summary "4 runs: 1 running · 2 finished · 1 failed". Nothing is announced on pending. An inline edit ends with one terminal message: "Rename saved: local_8 is now itemCount on build-a, job a3f9."
- Worklists: "position 4 of 12 · 7 visited · 3 handled"; "visited ≠ reviewed"; "Handled is your checklist, not a review decision, and starts no work." Never "done", "complete", "reviewed" or "checked off" for worklist items. Snapshots say "as of 14:02" beside their source link. A target that vanished "no longer resolves on build-b"; it is never called absent.
- Navigation: "Open beside" (on 8080 without split panes, "Open beside (new window)"); "Update panes: As I move / On Enter"; panes and panels "Not loaded · Enter to load"; Peeks and cards, which have an Open button, "Not loaded. Open to read it."; "Not decompiled in this session · Enter to decompile"; "no earlier location in this tab"; Back's description before a program change, "Back · clears 12 checked rows on build-a"; copy confirmations, "Copied address 0041b210, build-b".
- Another project: "This link is for project corpus-beta. You are in corpus-alpha. Opening a project admits its eligible missing work and reuses its receipts." Buttons "Switch to corpus-beta" and "Stay". Never switch silently.
- Unresolved locations are words: "Event ‹id› is no longer retained", "Worklist not available here", "Address 0041b210 has no build; it exists in build-a, build-c", "contested · no winner".
- Operator mantra: "Selection is intent. Strip is command. Dock is truth. Palette is jump. Save is metadata. Finished ≠ match."

## Claim boundaries use ≠

candidate ≠ acceptance · compile admits candidate, not replacement · floor ≠ recovered C · local zero ≠ full-image or behavior proof · exported plan ≠ live detour permission · result exists ≠ independently accepted claim · deadline ≠ termination · byte journal rollback ≠ undo of executed side effects · liveness ≠ execution progress ≠ goal progress · Accuracy ≠ acceptance · Compiling C ≠ verified recovery · effective ≠ byte match · aligned ≠ equivalent · aligned by name ≠ same contents · joined by content ≠ same entity.

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
- "raw local observations": the only label for the canonical `rawLocalObservedC` count, always with its claim line "does not certify semantic identity, current toolchain, linked contribution or a full rebuilt image". The compatibility alias `byteExactRecoveredC` is never a label, and no total built from either reads as recovered C, verified recovery or whole-image acceptance.

## Editing, undo and scripts

Keep verbatim:

- "cannot be undone here": the EditHistory state word for a transaction that was checked in, is beyond the undo limit, or was recorded before the program was last closed. A job's row adds "its log, receipt and transcript cannot be undone".
- "byte journal rollback ≠ undo of executed side effects" under every undo list; "Undo applies to build-a only." for a propagated edit.
- "Patched bytes are not recovery evidence."
- "Propose to build-b, build-c": propagation is a separate step after the terminal result, never an "all builds" write.
- "Scripts are an advanced tool. Turn on Advanced in View settings to show Scripts."

## Search, results and listing views

Keep verbatim:

- "Stopped at 500 hits on build-a; more may exist." A count is never rounded or projected; a cut table counts "≥500".
- "not searched" is not 0: an unsearched build reads "build-d not loaded · not searched", never "0" or "no hits".
- "zero hits is not absence": zero pattern hits on a build never mean the function is absent there, because compile variance changes encodings.
- "hits are candidates; a pattern match is not identity".
- "aligned by name ≠ same contents" (program trees) and "aligned by name ≠ same role" (memory blocks).
- "Byte entropy" is a statistic of bytes; "entropy variance" is a variance class (build state differs). They are unrelated and never shortened together to "entropy".
- "Stay at this address on rebase" names Ghidra's pin symbol ("Keep" and "Kept" are reserved for cards). Never write "pin symbol" or "pinned" for it: ◎ pinned is a locator status.
- "Removed 3 rows from this table; nothing in the program changed."
- **Unavailable action:** "Not available on this server yet. ‹What still works›. · What this server offers", where the last part links to Help › What this server offers (the list read from `GET /api/v1/actions`). Example: "Not available on this server yet. Stored hashes still read. · What this server offers". Never "catalog action needed", "not in the catalog" or "not offered yet" in UI copy; design prose may say "catalog action".
- **Visible labels never show internal words.** A prepared action reads "Prepare: ‹catalog label›" (its accessible name adds "nothing runs until Run"), never "Arm: …" or "(catalog)"; Undo and Redo read "Undo…" and "Redo…". Docs keep the term "arm". A tool id such as `resolve-modification-conflict` is never UI copy; the button reads "Review changes", labelled from the catalog.
- The header control reads "Pause new work" ("Stops starting new jobs; jobs already started finish"), with the states "Starting new work", "Pausing · 1 job finishing" and "Paused". Docs may say admission.
- The checked-set recovery is "Restore" ("Checked set cleared (4) · Restore"). "Undo" is only the program transaction.
- Checkbox cells are named "Check ‹name›", never "Select ‹name›": checking is not selecting.
- "An address selection belongs to one build." Ghidra's selection is always "address selection"; "selection" alone is the one primary selection, a logical entity across builds.

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
