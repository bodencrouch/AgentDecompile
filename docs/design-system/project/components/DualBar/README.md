# DualBar

Two three-step tracks that answer two different questions and are never merged.

1. **Decomp posture:** none · asm · c
2. **Validate posture:** none · obj · linked

**Consumer provides** both postures and a tooltip that names them in words ("Decomp: C · Validate: obj").

- Reached steps are `ink-muted`; the current step is `ink-strong`. The bars are neutral: posture is not pass/fail, so they never use `fact-passed`.
- Validate alone never implies byte identity. There is no third accuracy bar; whole-image identity is a FactBadge with its own receipt.
