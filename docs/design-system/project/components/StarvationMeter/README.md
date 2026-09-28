# StarvationMeter

Starvation drawn beside the work: the oldest unreviewed review row, the oldest waiting lane, and the longest-running job against its deadline.

**Consumer provides** the three ages and the deadline.

- Bars show age; the deadline is a `fact-stale` tick. A job past its deadline fills `fact-failed` and becomes a named failover, never a spinner.
- A deferral from an urgent override stays visible and does not reset age.
