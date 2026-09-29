# StarvationMeter

Starvation drawn beside the work: the age of the oldest unreviewed review row, the oldest waiting lane, and the longest-running job against its deadline. The age words are links to the row, lane or job each bar measures.

**Use it** in the dock's Events tab header, in the MatchReview queue header (oldest unreviewed row only), and in PipelineMap node Peeks.

**Consumer provides** the three ages, each deadline when one is set, and what each age measures: the review row (match id), the lane node id from `pipeline-model.json`, the job id.

- Each bar is `role="img"` with the age in words in its accessible name ("Oldest unreviewed review row: 2 hours 10 minutes, deadline 2 hours 45 minutes"). It is never a meter: a waiting lane with no deadline has no bounded maximum. The bar is a second cue; the words carry the value.
- The age is always written beside the bar ("2h 10m"), and **those words are the link**. The label before the bar is plain text; the bar itself is never a link.
- The deadline is a `fact-stale` tick. A job past its deadline fills `fact-failed` and becomes a named failover ("+18m over", words), never a spinner. With no deadline: "deadline not set" and no tick.
- A deferral from an urgent override stays visible and does not reset age.

**Linking**

- **Publishes:** the oldest-unreviewed age is a Go: it opens the review queue (`ws=compare&panel=review`), sets `page` to that match id, pushes one stop and focuses that row; the checked set is unchanged. The lane age goes to its node (`node=lane-E`); the job age opens its dock Jobs record (`dock=jobs&job=77c0`).
- **Follows:** `project`, re-read from the stored projection after the settle; not holdable. Ages are not live.
- **Targets rendered:** oldest unreviewed row → that match in the review queue, focused · oldest waiting lane → its PipelineMap node · longest job → its dock Jobs record, with its failover when past deadline. Link names read "Oldest unreviewed review row, match 18421, 2 hours 10 minutes".
- **Peek source:** Alt+↓ on an age link reads the stored review row, lane node counts or job record; nothing is fetched on hover.
- **Absent copy:** "No unreviewed rows." · "No lane waiting." · "No job past its deadline." · "deadline not set".
- **Target-size exception:** none; each age link is at least 24px tall, 44px below 700px. With a coarse pointer each age row carries one 44px row-menu button with the same link menu; there is no long-press.

**Accessibility**

- Each bar is `role="img"` named with its age in words; the adjacent age link carries the target. Ages are never live regions; the dock announces transitions once.

**Removes switching:** opening the review queue, the pipeline map and the Jobs dock to find what is starving (J28, credited to U181; counts in the plan ledger).
