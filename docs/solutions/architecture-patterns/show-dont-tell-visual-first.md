---
title: "Show, don't tell: pictures carry meaning, words live in tooltips"
date: 2026-09-29
category: architecture-patterns
module: docs/design-system
problem_type: architecture_pattern
component: ui-copy
severity: high
applies_when:
  - Designing or reviewing any view, panel, dialog or preview
  - Writing labels, empty states, disclaimers or status lines
  - Tempted to explain a result in a sentence next to it
tags: [visual-first, tooltips, design-system, ui-copy, text-off-test]
---

# Show, don't tell: pictures carry meaning, words live in tooltips

## Problem

Previews read as documents. Every label that was an instruction, statement or sentence sat on screen: disclaimers, consequences, scope notes, empty-state explanations. The user rejected them: "Too much text." Then clarified: "the text is fine but they should almost exclusively only be tooltips for explanation of what the user is seeing. Which should be predominantly provided as visual ui. Image says a thousand words."

## Solution

A picture says a thousand words only when each word it replaces has one home and each mark means one thing.

- Draw every fact once in the layout. Name each drawn form once in the Key.
- This instance's exact values and one reading go in its tip or readout. Evidence, links and actions go in Peek. Behavior and procedure go in Help.
- A tip explains what the user is looking at, never what the product does or refuses to do.
- A sentence recast as a glyph plus words ("≠ arrows bind") is still telling.
- Numerals are data, so compared values stay visible.
- Encodings already taken (2px frame, double, dotted, ○) keep their meaning; see guideline 20.
- Gate every view with the text-off test: hide all words; the view must still say what state it is in and what changed.

Budgets and the full sentence-to-shape table: [guideline 25](../../design-system/project/guidelines/25-show-dont-tell.md). Visual vocabulary: the `adv-*` classes in `components/bundle.css`. Exemplar: `components/FunctionStartPatterns/preview.html`.

## Prevention

Before adding a sentence to a view, name the shape that replaces it (fraction bar, small multiples, histogram, stacked bar, share line, chip, target map, key-value chips, empty or n/a mark). If none fits, the sentence belongs in a tip, Peek or Help, not on the surface.
