# NameProvenance

Per-field name precedence: the winning name, its tier, its origin, and every rejected alternative and conflict.

**Consumer provides** the field, candidate names with tier, source build and witness, and the winner.

- Precedence: human annotation → debug info / STABS → authentic symbols → analysis names → placeholders. A placeholder never replaces a stronger name.
- Fusion is per field: the best donor may differ for every field. A human naming preference changes the display name, not physical-layout evidence.
- Rejected alternatives and conflicts stay visible; nothing authored is lost.
