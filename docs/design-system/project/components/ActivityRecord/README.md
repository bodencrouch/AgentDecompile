# ActivityRecord

One job in the activity dock with its three separate readouts: liveness, execution progress and goal progress.

**Consumer provides** job id and catalog action, owner (managed or external, with process identity), source and target builds, measured units with the current one, accepted outcomes, blocking prerequisites, last event time and the log tail.

- Liveness, execution progress and goal progress are three labelled readouts; never one bar. PID churn increments nothing.
- Units are measured durable units: done `progress-unit-done`, current outlined `progress-unit-now`. Uninstrumented work says "Progress unknown" and the last event.
- A live job is on `pane`; history on `chassis`. An external job stays visible and non-cancellable, and blocks duplicate admission.
- Derive/backfill rows show row → derived column → receipt. Log tails show the latest lines. Finished copy: "Finished. Recipient verification: not run."
