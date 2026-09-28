# RepresentationBar

The exhaustive, disjoint accounting of an inventory: accepted source, candidate source, preserved region, unclassified, excluded with reason.

**Consumer provides** the counts per bucket for one build or corpus, and the inventory denominator.

- Every inventory member appears exactly once; totals are disjoint. Facts and capabilities overlap and are never summed into this bar.
- `rep-accepted`, `rep-candidate`, `rep-preserved`, `rep-unclassified` (dashed), `rep-excluded` (hatched). A key with counts always accompanies the bar.
- The two recovery variants get separate bars; floor bytes never count toward recovered C.
