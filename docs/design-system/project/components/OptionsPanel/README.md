# OptionsPanel

The per-viewer tool options for each code viewer (the decompiler, the byte viewer, the structure editor and search, with links to ListingFieldLayout for Listing display and cross-reference hints) beside a read-only, per-build view of the program options that shape analysis and decompilation (the decompiler program options, such as Prototype evaluation, and specification extensions), which change only through the catalog.

**Use it** as **Tool options…** in the View menu and the palette ("Options", "Tool options", or an option's name), and from a viewer's pane-header menu, which opens it at that viewer's section. It replaces Ghidra's Tool Options dialog and the decompiler, byte viewer and structure editor option pages. It sits beside two existing homes and does not repeat them: **View settings** (Density, Increase contrast, Reduce motion, Screen-reader verbosity, the pointer options and Advanced) and **KeymapSettings** (keys). Listing columns and field layout belong to ListingFieldLayout. The header links all three as buttons.

**Consumer provides** the option schema per viewer section (name, kind, allowed values, default, whether it is a decompile request option that enters the basis), the viewer's override diff from durable workspace state, the views currently showing content produced under other request options, and per build the stored program options (the decompiler program options, prototype and call-fixup extensions with kind and the compiler spec they apply to) with read time, the writer lock as reported, and the catalog actions that set program options or import and remove extensions (read from `GET /api/v1/actions`; no action id is named here).

**Anatomy**

- **Header.** "Tool options", the override count ("6 overrides by you, stored beside View settings and keys · never in a link or browser storage"), the three sibling buttons (View settings…, Keyboard…, Listing fields…) and a Find field that filters every section by option name.
- **Section tree** (APG Tree) in two groups. **Viewers · per viewer:** Listing display and Cross-reference hints are link rows only: ListingFieldLayout owns the operand display options (row L04), the XREF field options (row L09) and the EOL comment options (row L08), and these rows open its Field settings group at Operands, XREF field or EOL comments. They hold no values here, so there is one store and one set of words; their counts are ListingFieldLayout's changes. Decompiler (display options, and the analysis options as request options), Byte viewer (bytes per line, group size, alignment offset, charset, char width, and which formats the HexStrip offers), Structure editor (offsets and sizes in hex or decimal, show undefined bytes), Search (default scope this build or all builds, highlight hits, result limit). **Program · per build:** Decompiler program options, Specification extensions. Each section shows its override count.
- **Option rows.** Name, a short description with the kind ("display", "analysis · request option · part of the basis") and "changed by you, default X" or "default X", then the control (segmented buttons, a select or a short field) and **Reset** for an overridden value. Changes apply to the viewer at once, post nothing and start no job.
- **Request options.** Ghidra keeps the decompiler's analysis options (Eliminate unreachable code, Respect read-only flags, Simplify predication, Alias blocking and the rest) as tool options, not program options. Here they are per viewer and enter the decompile basis; the two that DecompileView toggles (D05) are listed first. Changing one never re-decompiles: views decompiled under other options show "decompiled with ‹option› ‹value› · Enter to decompile", and the panel counts them in a notice.
- **Program options, per build, read-only.** Ghidra's Options for ‹program› › Decompiler, today Prototype evaluation (the convention used where a function's convention is unknown, from that build's own compiler spec). A table with one column per build and "differs" (±) where builds disagree, "not read" where a build was not read. **Set on ‹build› (catalog)…** arms the ActionStrip for one build, with ConfirmDialog because it changes every later decompile of that build; today it is disabled with "catalog action needed · not offered yet".
- **Specification extensions, per build.** A table of the build's prototype and call-fixup extensions, each with the other builds where an extension of the same name is present ("build-b · compared, not shared; same compiler spec", "build-a only"). Extensions are program-local: that column compares, it does not share. **Import extension (catalog)…** and **Remove…** confirm through ConfirmDialog and need that build's writer; today both are `aria-disabled` with "catalog action needed · not offered yet" (D31). An extension applies only to builds whose language and compiler spec match; others are named and excluded.
- **Restore defaults** per section removes that section's overrides and shows an inline Undo (per-viewer state is not program data, so no dialog). **Reset all overrides…** at the bottom confirms and names the count, as KeymapSettings does.
- **Server settings.** Tool and program caching are server settings and are shown as such, not as options.

**States**

- **Views under other options:** the caution notice names the views and says nothing re-decompiles by itself.
- **Program options not read:** "not read" per build; reading them is a read and never opens or analyzes a program.
- **No catalog action:** program rows are read-only with the reason.
- **Writer owned:** an extension import waits and names the owner as reported.
- **Find with no match:** "No option matches ‹text›. View settings and Keyboard have their own find."

**Multi-variant rules**

- Viewer options apply to every build alike and are never propagated (PV). Program options belong to one build: compared across builds, never merged, and recorded in each decompile's basis so that builds compared on different options are flagged in the ProvenanceStamp.

**Linking**

- **Publishes:** nothing. Options are a per-viewer diff in durable workspace state; the open section is remembered there too. It never navigates or changes the selection.
- **Follows:** opened from a viewer's pane-header menu, it opens at that viewer's section; otherwise nothing. Not holdable.
- **Targets rendered:** views decompiled under other options → those decompile views at their build · program option rows → AnalyzerPanel for analysis options (`panel=analysis`) · Listing display and Cross-reference hints → ListingFieldLayout's Field settings group (Operands, XREF field, EOL comments), which owns those options · sibling homes as buttons, not links.
- **Peek source:** none.
- **Absent copy:** "not read" · "catalog action needed · not offered yet" · "build-a only" · "Program caching is a server setting".
- **Target-size exception:** none; controls are 24px, 44px below 700px and with a coarse pointer.

**Keyboard**

- The section tree is an APG Tree (typeahead needs no prefix); option rows are in Tab order; segmented controls move with ←/→. Ctrl/Cmd+F is not bound here; the Find field is the first control after the header buttons.
- Keymap id `options.open` (no keys · menu and palette only; Cmd+, is taken by the browser on macOS).

**Accessibility**

- Each option's control is labelled by the option name and described by its kind and default ("Eliminate unreachable code, analysis request option, part of the basis, changed by you, default on").
- A restore or a reset is announced once in the polite region; nothing is announced per change.
- The program table has a name and column headers; "differs" is a word, the ± glyph is `aria-hidden`.

**Parity rows covered**

Rows from the [Ghidra Code Browser parity specification](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md), section "New components needed".

- **I06** Tool Options dialog: restore defaults, per-section options; caching shown as a server setting.
- **D30** decompiler options: display and analysis options are per-viewer request options; the one program option (Prototype evaluation) is per build, read-only, catalog to change.
- **D31** specification extensions: import and remove prototype and call-fixup extensions, per build, ConfirmDialog, one writer.
- **D05** Eliminate Unreachable Code and Respect Read-only Flags as request options in the basis (DecompileView shows their state; this panel sets them).
- **N11** Byte Viewer options: bytes per line, alignment offset, group size, charset, char width (HexStrip reads them).
- **T19** structure editor options such as hex display.
- Links to **L04**, **L08** and **L09** display options, which ListingFieldLayout owns (Listing and XrefPanel read them).

**Prior art**

Ghidra Tool Options (`Tool/ToolOptions_Dialog.htm`), Decompiler Options, Byte Viewer Options and the structure editor's options. VS Code's settings editor (one searchable tree, "modified" per row, reset per row) for the row form.
