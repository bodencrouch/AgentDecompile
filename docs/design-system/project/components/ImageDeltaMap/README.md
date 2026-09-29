# ImageDeltaMap

Whole-image rebuild drawn as the work: the image's regions in file order, with remaining deltas marked where they are.

**Consumer provides** the section/region map of the fresh rebuild, per-region equality, each differing range with its start address and byte count, and the rebuild receipt.

- Regions in file order scaled to size; equal regions `chassis`, differing regions `lane-fault-fill` with the byte count.
- **Non-color cue**: a differing region carries ≠, its name and its byte count; the text key under the map lists every differing region with its range and count in words. Fill is never the only carrier; in forced colors the key carries the values.
- Each differing region is a link. Deltas localize to headers, layout, imports, relocations, resources or function and data regions. The whole-file hash is the only terminal fact.

**Linking**

- **Publishes:** nothing.
- **Follows:** the inspected `build` and its latest rebuild receipt, after the settle; holdable (a held map keeps its receipt and says so).
- **Targets rendered:** a differing region → the Listing at the range start in that build (`build`, `addr`), with the ObjectDiff pair opened beside it · the rebuild receipt → its receipt card · the shipped hash → the build's identity receipt. Link names read "Region .text, differs, 312 bytes; Listing at 00401000, build-a".
- **Peek source:** the stored region summaries of the rebuild receipt; nothing is rebuilt.
- **Absent copy:** "no fresh rebuild for build-a" · "region equal" (plain, not a link) · "range start unknown · opens the region list".
- **Target-size exception:** none; region links are at least 32px tall, and narrow regions are also reachable through the key.

**Accessibility**

- The map is an ordered list of regions in file order; clipped labels are complete in each link's accessible name and in the key.

**Removes switching:** opening the rebuild report, then the Listing, then the object diff to reach the bytes behind a whole-image delta (J34).
