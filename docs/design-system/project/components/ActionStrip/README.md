# ActionStrip

The typed command line for one catalog verb: what will run, on which target, with which fields, before anything is posted.

**Consumer provides** the action title and id, the bound target (program, build, address or checked set), the optional fields from the catalog schema, and the checked-set count.

- Sits under the session tabs when an action is armed. Palette picks and toolbar quick actions share this one execute path.
- Buttons: "Run with defaults" (`.primary`), "Fields…" to edit catalog parameters, and "Run N" when a checked set is bound, with an "N selected" count chip.
- A mutating action confirms once through ConfirmDialog, naming its exact target.
- Field errors name the catalog field: "`kb` is required. Enter it in Fields…".
