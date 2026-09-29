# PropagationTransfer

Propagation drawn as the work: one exact field moving from its evidenced donor to each eligible recipient, with the compatibility gate and blocked recipients.

**Consumer provides** the field (name, type, comment, candidate source), the donor and its tier, and per recipient: counterpart address and edge state, gate result, before and after values, recipient validation state, and the transfer receipt.

- A field, never "everything": the best donor may differ per field.
- Blocked recipients keep their conflicting value and show why. The transfer is drawn only after its receipt exists.
- Compile success authorizes candidate distribution, not replacement; each recipient earns its own acceptance.
- Each row is a work-view event: it carries its WorkTimeline moment (`t=`); Enter on the event in the timeline goes to it, and Shift+Enter opens it beside as a Held pane (on 8080 without split panes, "Open beside (new window)").
- A recipient link is a counterpart link: it shows its identity-edge word (accepted or candidate) in its text and name. A recipient with no counterpart is the plain word "absent".

**Linking**

- **Publishes:** nothing.
- **Follows:** the primary entity and the field chosen in its host, after the settle. Holdable as a centre or secondary pane (`hold=receipt:d1f3@build-b`): a held transfer keeps its receipt and reads "Held · ResourceCache @ build-b · 4 min", with "◷ Basis changed since held · Refresh" when its basis moves.
- **Targets rendered:** recipient → the counterpart in the Code Browser for that build, with its edge word · donor → the donor counterpart · gate → its pipeline node (`?node=gate-5`) · before and after values → NameProvenance for that entity and build (the "Why this name" section) · transfer receipt → its receipt card · the event → its WorkTimeline moment (`t=38`) · the job → the dock Jobs record.
- **Peek source:** the stored transfer receipt rows and name-candidate rows.
- **Absent copy:** "absent" (no counterpart; plain word) · "blocked: layout differs" · "recipient verification: not run".
- **Target-size exception:** spacing: at most two short links per cell. With a coarse pointer each recipient row carries one 44px row-menu button with the same link menu; there is no long-press.

**Accessibility**

- A table with the recipient as row header; gate results are glyph plus words; "kept" and "blocked" are words.

**Removes switching:** opening each recipient build to see whether a field arrived and why it was blocked (J20).
