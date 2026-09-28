# Exchange rewrite consumption bridge

## Goal

Make completed exchange `rewrite` proposals useful without weakening the
existing compile/objdiff proof gate.

## Constraints

- A forwarded contribution is never verified or matched.
- Routing comes only from trusted producer records, never submitted artifacts.
- Identical content-addressed units may serve multiple local destinations.
- Queue transfer and acknowledgement must be durable and retry-safe.
- Every accepted rewrite must reach `attempt_candidate()` directly; source-shape
  search, compiler family, and built-in variants must not silently bypass it.

## Stages

1. Persist per-destination trusted routing records for rewrite offers.
2. Add durable, idempotent transfer from an awaiting proposal to a local queue,
   with a distinct forwarded acknowledgement.
3. Run forwarded rewrites through the normal candidate compile/objdiff path;
   preserve unresolved work on dry runs or exceptions.
4. Test failure, restart, multi-destination, and compiler-family paths.

## Deferred

`objdiff` lane economics remain blocked on a genuine retained PE/COFF
target/candidate pair; the current NDS/ARM output is not a valid measurement.
