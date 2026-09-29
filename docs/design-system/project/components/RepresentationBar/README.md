# RepresentationBar

The exhaustive, disjoint accounting of an inventory: accepted source, candidate source, preserved region, unclassified, excluded with reason.

**Consumer provides** the counts per bucket for one build or corpus, and the inventory denominator.

- Every inventory member appears exactly once; totals are disjoint. Facts and capabilities overlap and are never summed into this bar.
- `rep-accepted`, `rep-candidate`, `rep-preserved`, `rep-unclassified` (dashed), `rep-excluded` (hatched). A key with counts always accompanies the bar.
- **Non-color cues**: adjacent segments are separated by 2px `chassis` gaps; candidate is striped, unclassified has a dashed edge, excluded is hatched; the key states every bucket as a word and a count. The bar is `role="img"` described by the key (`aria-describedby`); the key carries the values.
- The two recovery variants get separate bars; floor bytes never count toward recovered C.

**Linking**

- **Publishes:** nothing; its key links set a filter (`f=rep:…`) owned by the Functions grid.
- **Follows:** `project` and `build`, after the settle; not holdable.
- **Targets rendered:** each key count → the Functions grid filtered to that bucket on that build · the build → the Code Browser for that build · the variant → the VariantLedger (`ws=recovery&panel=report`). Link names read "Candidate source, 1,090 functions, build-a, max-C".
- **Peek source:** none; the key already carries every value.
- **Absent copy:** "not measured" · "inventory not observed"; never a percentage in its place.
- **Target-size exception:** none; key items are 24px.

**Accessibility**

- Key links are 24px targets; counts use tabular numerals. In forced colors the bar keeps its patterns and the key carries the values.

**Removes switching:** opening the Functions list and setting a filter by hand to see which functions sit in one bucket (J22).
