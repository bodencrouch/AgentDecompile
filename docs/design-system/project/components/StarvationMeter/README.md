# StarvationMeter

Starvation drawn beside the work: the oldest unreviewed review row, the oldest waiting lane, and the longest-running job against its deadline. Each bar links to the row, lane or job it measures.

**Use it** at the top of the dock's Activity tab, in the MatchReview queue header (oldest unreviewed row only), and in PipelineMap node Peeks.

**Consumer provides** the three ages, the deadline, and what each age measures: the review row (match id), the lane node, the job id.

- Bars show age; the deadline is a `fact-stale` tick. A job past its deadline fills `fact-failed` and becomes a named failover, never a spinner.
- The age is always written as words beside the bar ("2h 10m"); the bar is a second cue. "+18m over" is words.
- A deferral from an urgent override stays visible and does not reset age.

**Linking**

- **Publishes:** nothing.
- **Follows:** `project`, re-read from the stored projection; not holdable.
- **Targets rendered:** oldest unreviewed row → that match in the review queue (`ws=compare&panel=review&page=18419`), focused · oldest waiting lane → its pipeline node (`?node=lane-E`) · longest job → its dock Jobs record, with its failover when past deadline. Link names read "Oldest unreviewed review row, match 18421, 2 hours 10 minutes".
- **Peek source:** Alt+↓ on a label reads the stored row, lane or job record.
- **Absent copy:** "No unreviewed rows." · "No lane waiting." · "No job past its deadline." · "deadline not set".
- **Target-size exception:** none; each label link is a 24px row.

**Accessibility**

- Each bar is `role="meter"` with `aria-valuetext` in words ("oldest unreviewed row 2h 10m, deadline 2h 45m"); the label link carries the target. Ages are not live regions.

**Removes switching:** opening the review queue, the pipeline map and the Jobs dock to find what is starving (J28).
