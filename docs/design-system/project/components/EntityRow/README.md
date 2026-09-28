# EntityRow

A dense row in the single Functions list: address, name with its provenance tier, logical identity hint and the compact seven-fact strip.

**Consumer provides** the concrete address in the inspected build, the display name and winning name tier, the logical id and counterpart count when accepted, the seven fact states, and selected/checked state.

- Address in `address`, `type-code-small`. The one primary item uses `row-selected-bg`; secondary text on it becomes `ink`.
- The fact strip is the FactBadge compact form: seven glyphs in fixed order, a tooltip naming each fact and state. It replaces the retired none/asm/C and none/obj/linked bars.
- A function without an accepted identity says "no identity"; never invent a counterpart.
- The batch column is a checkbox plus a count chip in the header, never a second fill.
