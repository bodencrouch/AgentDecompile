# RuntimeCapabilities

Runtime binding evidence for one entity on one build: the three predicates (bytes, identity, operation) and the five independent capabilities.

**Consumer provides** presence, identity and operation predicate states with receipts; each capability's state (on, unknown, refused with reason); the readiness chain position.

- Predicates are three rows, never a confidence score. Accepted binding = presence AND identity AND current dependencies.
- Capability chips L R C D W (located, readable, callable, detourable, writable) are independent: on (`lane-runtime-fill` with ink), dashed unknown, struck refused. Readable does not imply writable; callable does not imply detourable.
- Readiness chain states stay separate: discovered → identity-supported → resolved → installable/installed → call-observed → behavior-observed.
- Runtime calls never count as recovered source.
