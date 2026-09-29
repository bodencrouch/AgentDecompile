# RegisterValuesEditor

The register manager for one explicit build. Its register tree comes from that build's language. It shows register and context-register values over address ranges, and lets you set, edit, clear and delete ranges. Before Save it states the consequence: "re-disassembly requires admission". Other builds' values are shown side by side through anchors and never merged or proposed.

**Use it** from the palette ("Register values"), the build crumb's Peek, the Listing link menu on a selection (Set register values…, Clear register values…), and from a StateNotice that names a context-register cause. It replaces Ghidra's Register Manager window and its Set Register Values dialog. It opens as a secondary surface in the Code Browser; below 700px it is its own NarrowFlow pane.

**Consumer provides**

- **Registers:** the build's registers from its own language, grouped as the language groups them, with sub-registers (EAX → AX → AL/AH), bit widths, context registers and their defined values, and the language default values.
- **Stored ranges:** each register's explicit ranges on this build (start, end, value, source: user, analysis or import).
- **Writer and counterparts:** the writer state. For every other build, that build's ranges for the same register as last read, mapped through recorded anchor pairs, or "not loaded".
- **Evidence:** any recorded variance witness (for example the language id).
- **Actions:** the catalog actions from `GET /api/v1/actions` for setting, clearing and deleting register values, and for re-disassembly (admitted as a job, never run here). The verbs are "catalog action needed". No action id is named here.

**Anatomy**

1. **Header and target bar.** The framed target build chip, "registers from build-a's language · x86 32-bit" and the writer line. Changing the build opens a new editor bound to that build; it never re-targets this one.
2. **Register tree** (left). An APG Tree with groups (Flags, General, Context, …) and expandable parent registers. Each row's meta shows its range count, "default" or "none". A filter field sits above it. Registers are never listed from another build's language.
3. **Ranges grid** (right). A "Track cursor" toggle (per viewer, like Ghidra's) selects the row whose range contains the Listing cursor; it never moves the cursor. It is for the selected register on the target build, with columns Start (an address link with its build), End, Value, Source and a Delete… button per row. A "Show language defaults" checkbox adds default-value rows, marked "language default" and read-only.
4. **Range editor.** Start, End and Value, validated against the register's width and, for context registers, its defined values.
5. **Consequence block**, always shown before Save. It states the register, the value, the range, the build, and what the value changes, which depends on the register kind: a context register changes how that range disassembles the next time it is disassembled; any register value changes the next decompile of that range. It always says "existing instructions are not re-disassembled, and re-disassembly requires admission as a job" and "Other builds are unchanged".
6. **Footer.** Save on ‹build›…, Set over selection…, Clear values in selection… and Cancel. Each opens ConfirmDialog.
7. **Across builds.** A comparison grid, program-local and side by side. It has one row per range on the target build and a column per build. Values come through recorded anchors ("via anchor 0041b2c0"), and between anchors the row names the anchor it used. It also has a context row that states which context registers each build's language has. The language itself is a solid record ("build-d language is x86 64-bit"); the variance class for the difference is a dashed "hypothesis (heuristic)" unless source, toolchain and flag identity are recorded for both builds. A build where the anchor's function is unresolved reads "◌ unresolved" and names the missing anchor. Register values are never proposed to other builds.

**Confirm tier** (P07: CAT, CF-dlg, 1W, NA)

- **ConfirmDialog:** setting a value over a range, editing a range, deleting a range, and clearing values in a selection. The dialog names the register, the range size and the build.
- **Save stays enabled.** An unchanged draft posts nothing and says "No register change to submit".
- **Validation before anything posts:** a value wider than the register, an undefined context value, End before Start, or a range outside this build's memory. Each is reported inline with ✕ and the fix.
- **No analysis (NA).** After the terminal result, affected Listing and Decompile ranges read "◷ predates job ‹id›". The catalog's re-disassembly action is armed in the ActionStrip for that range and build, never run, and it waits for admission. Valid receipts are reused.
- **Modification conflict (MC):** both range sets are shown side by side. None is pre-picked.

**States**

- editing;
- invalid;
- no change to submit;
- awaiting ConfirmDialog;
- pending, admitted, running, then finished or failed, shown as an OutcomeCell on the range row with its job link;
- ambiguous outcome ("Checking whether the operation completed");
- conflict (⇄);
- "predates job ‹id›";
- waiting at gate;
- no values ("No explicit values for ECX on build-a");
- not loaded, for a comparison build.

**Linking**

- **Publishes:** nothing. Selecting a register is local view state, not location. A range start link is Go.
- **Follows:** the inspected build is chosen at open, not after it. With the editor open, a selection in the Listing prefills Start and End when Set over selection… is chosen. The editor can be kept as a card (read-only, registered kind `registers`), but it cannot be held.
- **Targets rendered:**
  - range start → the Code Browser at that build and address;
  - a counterpart value → that build's address through its anchor;
  - the job → the dock Jobs record;
  - the armed re-disassembly → the ActionStrip.
- **Peek source:** Alt+↓ on a range start reads the cached listing there. On a counterpart cell, it reads that build's stored ranges.
- **Absent copy:** "no value" · "not loaded" · "language default" · "No explicit values for ‹reg› on ‹build›" · "No register change to submit" · "no anchor before ‹addr› on ‹build›".
- **Target-size exception:** none. Tree rows and controls are 24px or more, and 44px below 700px.

**Keyboard**

- The register tree is an APG Tree: ↑/↓, → opens, ← closes or goes to the parent, `*` expands siblings, and typeahead works without a prefix (no letter commands are bound there). The ranges grid is an APG Grid. F6 moves between regions, and Tab moves between tree, grid and editor.
- Keymap ids (registered): `registers.open` (no default key; palette "Register values"); `registers.setOverSelection` and `registers.clearInSelection` (link menu and palette only; keys only arm).

**Accessibility**

- The tree is named "Registers of ‹build›". The grid is named "Value ranges of ‹register› on ‹build›", and each Delete… button is named by its range.
- The consequence block is visible text before Save, and ConfirmDialog repeats it (WCAG 3.3.4). The "predates" notice is `role="status"` only when the operator's own Save caused it.
- The comparison grid reads "build-b, 0x0, via anchor 0041b2c0".

**Parity rows covered**

- P07 Register Manager: register and context values over ranges; set, edit, clear and delete ranges; default values.

**Prior art**

- Ghidra's Register Manager and Set Register Values: the register tree, value ranges and default values.
- IDA segment register values (Alt+G).
- What changes here: one explicit build, per-language registers, the consequence stated before Save, re-disassembly only by admission, and cross-build comparison only through anchors.
