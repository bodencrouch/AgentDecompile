# PropagationTransfer

Propagation drawn as the work: one exact field moving from its evidenced donor to each eligible recipient, with the compatibility gate and blocked recipients.

**Consumer provides** the field (name, type, comment, candidate source), the donor and its tier, and per recipient: counterpart address and edge state, gate result, before and after values, recipient validation state, and the transfer receipt.

- A field, never "everything": the best donor may differ per field.
- Blocked recipients keep their conflicting value and show why. The transfer is drawn only after its receipt exists.
- Compile success authorizes candidate distribution, not replacement; each recipient earns its own acceptance.
- Each row is a work-view event: it carries its WorkTimeline moment (`t=`); Enter on the event in the timeline goes to it, and Shift+Enter opens it beside as a Held pane (on 8080 without split panes, "Open beside (new window)").
- A recipient link is a counterpart link: it shows its identity-edge word (accepted or candidate) in its text and name. A recipient with no counterpart is the plain word "absent".

**Apply settings per category (X03)** ([spec](../../../../dashboard-design/2026-09-29-ghidra-code-browser-parity.md): X03, following Ghidra's Program Diff apply settings)

When a propagation spans more than one field, the operator chooses, per category, whether differences are replaced, merged or ignored. The settings are per viewer; applying them is a proposal to one recipient build at a time.

- **Anatomy.** An **Apply settings** band above the recipient table: one row per category, each with an APG radio group of only the values that category allows, a one-line note, and the count of differences in it for the chosen recipient.

  | Category | Covers | Values (default first) | Note |
  |---|---|---|---|
  | Bytes | byte values | Ignore · Replace | Replace is offered only inside anchor-aligned ranges of equal length and the same toolchain family; never to build-d (x86-64 from build-a's x86-32). "Patched bytes are not recovery evidence." |
  | Code units | instructions, data and equates | Ignore · Replace | Replacing code units needs the layout check to pass for data types. |
  | References | memory, external and stack references | Ignore · Replace | Each target is re-resolved through anchors; a target with no anchor is blocked "no anchor", never carried by address. |
  | Comments | plate, pre, EOL, post and repeatable, each its own row | Merge · Replace · Ignore | Merge appends the donor text under the recipient's, with a separator line. Annotations re-resolve on the recipient (see Listing, A09). |
  | Symbols | labels | Merge · Merge and set primary · Replace · Ignore | Merge adds labels and keeps the recipient's primary. A stronger-tier name on the recipient is never replaced ("blocked: build-c has a debug-info name"). |
  | Functions | functions with their frames, and function tags | Replace · Ignore; tags Merge · Replace · Ignore | Functions go only to accepted counterparts; the frame goes only where the layout check passes. |
  | Bookmarks | all bookmark categories | Ignore · Replace | |
  | Properties | program properties, including stored colors | Ignore · Replace | Only at anchor-mapped ranges. |
  | Context | program context register values | Ignore · Replace | Needs the same language on both builds; otherwise "not offered: build-d has another language". |

  Source maps stay Ignore and are not offered: a source map describes one build.
- **Set all.** **Set all to Ignore**, **Set all to Replace**, and **Set all to Merge** (Merge where allowed, otherwise Replace; labels become Merge and set primary). **Save as my default** stores the current settings as this viewer's default; a new proposal starts from it. All of it is per-viewer state in durable workspace state, never the URL, never program data.
- **Ignore a difference.** In the recipient preview, **Ignore** on a row hides that difference in this proposal for this viewer and moves it to "Ignored (3) · Show". Unlike Ghidra's Ignore Selection, it is reversible and changes nothing in either program.
- **Propose, one recipient at a time.** The band's primary button names one recipient: **Propose to build-b…**. The recipient chooser lists only builds with an accepted counterpart; candidates are listed and blocked. The button opens ConfirmDialog with the per-category counts and every overwritten custom value: "Propose 13 changes to build-b: 6 labels merged, 3 EOL comments merged, 1 plate comment replaced (overwrites your comment at 0041b2c0), 3 references; 1 reference blocked: no anchor. Ignored: bytes, code units, context." Each recipient is its own catalog proposal with its own outcome, and the next recipient is proposed separately; "all builds" is never one write.
- **States.** No differences in a category: "none for build-b". Category not offered: its reason in words. Blocked rows keep the recipient's value and say why, as elsewhere in this component. After the terminal result, each row shows its transfer receipt.
- **Keyboard.** The band is a group of APG radio groups: Tab moves between categories, arrows change the value. The Ignore button on a preview row is reached by Tab. Keymap id `propagate.setAll` (no default key) opens the Set all menu.
- **Accessibility.** Each radio group is named with its category and count ("Comments, EOL, 3 differences for build-b"). A value that is not allowed is not rendered (not disabled), and the note says which values the category has.

**Linking**

- **Publishes:** nothing.
- **Follows:** the primary entity and the field chosen in its host, after the settle. Holdable as a centre or secondary pane (`hold=receipt:d1f3@build-b`): a held transfer keeps its receipt and reads "Held · CacheEntry @ build-b · 4 min", with "◷ Basis changed since held · Refresh" when its basis moves.
- **Targets rendered:** recipient → the counterpart in the Code Browser for that build, with its edge word · donor → the donor counterpart · gate → its pipeline node (`?node=gate-5`) · before and after values → NameProvenance for that entity and build (the "Why this name" section) · transfer receipt → its receipt card · the event → its WorkTimeline moment (`t=38`) · the job → the dock Jobs record.
- **Peek source:** the stored transfer receipt rows and name-candidate rows.
- **Absent copy:** "absent" (no counterpart; plain word) · "blocked: layout differs" · "recipient verification: not run".
- **Target-size exception:** spacing: at most two short links per cell. With a coarse pointer each recipient row carries one 44px row-menu button with the same link menu; there is no long-press.

**Accessibility**

- A table with the recipient as row header; gate results are glyph plus words; "kept" and "blocked" are words.

**Removes switching:** opening each recipient build to see whether a field arrived and why it was blocked (J20).

## Behavior

Moved from the preview's tips and chips (Guideline 25).

- Key (moved text): "Target map: the one recipient a proposal writes; struck builds are proposed separately."
- shift: the dashed chip drops ≈ (≈ is reserved for compile variance).
- Bytes conditions (anchor-aligned, = length, = toolchain) are key-value chips, not dashed hypothesis chips: "Anchor-aligned, equal-length ranges, same toolchain family only."
- Merge preview: "Merge appends the donor text under yours with a separator line."
- ≠ stronger tier (chip removed): "A stronger-tier name on build-b is never replaced."
- = x86-32 · x86-32: "Offered only between builds with the same language; build-a and build-b are both x86-32."
- ⊘ source maps: "Source maps are not offered."
