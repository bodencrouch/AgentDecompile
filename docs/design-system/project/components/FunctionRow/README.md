# FunctionRow

A dense row in the single Functions surface: address, name, logical identity hint and the two posture bars.

**Consumer provides** the concrete address (for the inspected build), the resolved name and its raw name, the logical id when one is accepted, both postures, and selected/checked state.

- Address column is `code-small` in `address`; the list is a working set, not a report.
- The one primary item uses `selection`; secondary text on it is promoted to `ink`. Batch selection is a checkbox column plus a count chip, never a second fill.
- A function without an accepted identity shows "no identity" in muted text; never invent a counterpart.
- There is exactly one Functions surface in the workstation.
