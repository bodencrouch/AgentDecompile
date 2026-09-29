# ImageDeltaMap

Whole-image rebuild drawn as the work: the image's regions in file order, with the remaining deltas marked where they are and every value repeated in a text key.

**Use it** in the Recovery workspace's report (`ws=recovery&panel=report`) and from a VariantLedger cell's differing byte count.

**Consumer provides** the section and region map of the fresh rebuild, per-region equality, each differing range with its start address and byte count, and the rebuild receipt.

- Regions in file order, scaled to size. Equal regions are `chassis` and labelled "=". Differing regions are hatched (top and bottom bands over `lane-fault-fill`, so the label sits on a solid fill) and labelled "✕ ‹n› bytes". A differing region is never narrower than its label; if the regions cannot fit, the map scrolls in its own container.
- **A text key with values** sits under the map and is tied to it with `aria-describedby`: every differing region with its name, range and byte count ("✕ .text 00401000–00401137 · 312 bytes differ"), then the equal regions by name. Labels are at least 11px. Fill and hatching are never the only carrier.
- **Forced colors.** The map uses `forced-color-adjust: none` only because the key carries every value; the key itself follows the system colors.
- Each differing region is a link. Deltas localize to headers, layout, imports, relocations, resources or function and data regions. The whole-file hash is the only terminal fact.

**Linking**

- **Publishes:** nothing by itself; a region link is a Go.
- **Follows:** the inspected `build` and its latest rebuild receipt, after the settle; holdable (a held map keeps its receipt and says so).
- **Targets rendered:** a differing region → the Listing at the range start in that build (`build`, `addr`), with the ObjectDiff pair as the secondary pane (35 typed links) · the rebuild receipt → its receipt card · the shipped hash → the build's identity receipt. Link names read "Region .text, differs, 312 bytes; Listing at 00401000, build-a".
- **Peek source:** the stored region summaries of the rebuild receipt; nothing is rebuilt.
- **Absent copy:** "no fresh rebuild for build-a" · "=" and "equal" (plain, not a link) · "range start unknown · opens the region list".
- **Target-size exception:** none; region links are at least 32px tall and at least as wide as their label, and every region is also reachable through the key.

**Keyboard**

- The regions are an ordered list; Tab moves between the differing-region links in file order. Enter goes to the Listing at the range start; Shift+Enter opens it beside; Alt+↓ peeks the region summary; Shift+F10 opens the one link menu.

**Accessibility**

- The map is an ordered list of regions in file order; each region's name and state ("header, equal"; "Region .text, differs, 312 bytes") are in its accessible name, and clipped labels are complete there and in the key.
- The key is plain text with values, so the map is readable without color, hatching or the drawing.

**Removes switching:** it serves J34 (from a whole-image delta to the offending region and its object diff, 4 → 1), credited to typed links (U171) in the plan ledger.
