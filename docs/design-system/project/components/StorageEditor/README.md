# StorageEditor

A genuine editor for custom parameter and return storage: ordered register and stack pieces validated against the selected program.

**Consumer provides** the function, its parameters with datatype and current storage, the registers and stack model from the program's language and compiler spec, and the draft.

- Each piece is a row: kind (register or stack), register or stack offset, size. Invalid sizes, unknown registers, overlapping pieces or non-integer offsets block submission with the reason inline.
- Submission reviews the catalog action before mutation and shows conflicts explicitly; a button never resubmits unchanged values.
- Conventions and registers come from the selected program; never hardcode guide-example ABI sizes or register assignments.
