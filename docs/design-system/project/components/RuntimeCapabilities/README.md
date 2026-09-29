# RuntimeCapabilities

Runtime binding evidence for one entity on one build: the three predicates (bytes, identity, operation) and the five independent capabilities.

**Consumer provides** presence, identity and operation predicate states with their receipts; each capability's state (on, unknown, refused with reason); the readiness chain position.

- Predicates are three rows, never a confidence score. Accepted binding = presence AND identity AND current dependencies. Each predicate names its receipt as a link, or says "no receipt".
- Capability chips L R C D W (located, readable, callable, detourable, writable) are independent: on (`lane-runtime-fill` with ink), dashed unknown, struck refused. Readable does not imply writable; callable does not imply detourable.
- There is no tooltip and no `title`. **The capability row is one button** (WCAG 2.5.8: five 20px chips join one target) whose accessible name lists every capability in words; it opens a Peek with each capability's state, each refusal's reason and the ladder member that refused it.
- Readiness chain states stay separate: discovered → identity-supported → resolved → installable/installed → call-observed → behavior-observed. The chain is an `<ol>` with `aria-current="step"`.
- Runtime calls never count as recovered source.

**Linking**

- **Publishes:** nothing.
- **Follows:** `entity` and `build`, after the settle; keepable as a card (`keep=runtime:88@build-b`).
- **Targets rendered:** predicate receipt → the receipt card · predicate name → its contract node (`?node=contract-bytes`, `contract-identity`, `contract-operation`) · a refusal (not_detourable, missing_adapter) → the ladder B evidence (`?node=ladder-B`) · the observed region → the Code Browser at that build and address · the readiness chain → `?node=lane-C`.
- **Peek source:** the stored runtime receipts and refusal records for that entity × build.
- **Absent copy:** "unknown · not observed" · "no receipt" · "refused: not_detourable" · "Not loaded. Open build-b to read its runtime evidence."
- **Target-size exception:** none; the capability row is one button at least 24px tall.

**Keyboard**

- The capability button: Enter, Space or Alt+↓ opens the Peek; Esc closes and returns focus. Links follow the grammar.

**Accessibility**

- The capability button carries `aria-haspopup="dialog"`, `aria-expanded` and a name in words ("Capabilities on build-b: located, readable, callable on; detourable refused, not_detourable; writable unknown"). Chips are `aria-hidden` inside it. Predicate states are words (BYTES passed), not only glyph color.

**Removes switching:** opening the runtime lane view and the ladder report to learn why an entity is not usable on a build (J33).
