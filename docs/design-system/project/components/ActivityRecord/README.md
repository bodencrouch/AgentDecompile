# ActivityRecord

One job in the activity dock: owner, operation, builds, measured progress and last observation.

**Consumer provides** the job id and catalog action, owner (process, PID, start time), source and target builds, step list with measured position when instrumented, last event time, and the log tail.

- A live job gets the `pane` fill; history stays on `chassis`. The dock tabs are Activity, Recovery, Logs, Jobs, Problems.
- Steps are measured units; the current one is outlined in `accent`. If progress is not instrumented, write "Not measured" and show the last event. Never a spinner, never an invented percentage or ETA.
- Log tails show the latest lines, truncated at the start, in `code-small`.
- Finished copy is factual: "Finished. Validate: not run." A finished job is not a match.
