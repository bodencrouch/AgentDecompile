---
title: "Agents drifted into governance; anchor every plan to the north star"
date: 2026-09-29
category: architecture-patterns
module: docs
problem_type: architecture_pattern
component: product-direction
severity: high
applies_when:
  - Starting any plan, design, brainstorm or roadmap document
  - Deciding what to build next or how to rank work
  - Writing UI copy, status panels or verification sections
  - Tempted to add an audit, receipt ledger, claim tier or parity matrix
tags: [north-star, product-direction, drift, visual-first, status-words, planning]
---

# Agents drifted into governance; anchor every plan to the north star

## Problem

For a month, sessions produced plans instead of products. Between 2026-08-29 and 2026-09-29 the repo gained 398 Markdown files. Across them, "receipt" appears 1,386 times, "verif…" 1,368, "claim" 682 and "audit" 275. The browser build appears 53 times and modding 40. Each gate, ledger and disclaimer was defensible alone. Together they replaced the product. The user asked why nothing was moving, and said the planning agents were misreading their intent.

## Symptoms

- Every panel carries a disclaimer paragraph; every plan ends in an audit.
- New plans re-derive intent from a partial read of the pile, then add to it.
- A full round went into 224 features of a manual disassembler and 113 proposed contracts.
- Named deliverables (the runtime scripting bridge, the browser build, portable signatures) stay future while documentation reads "substantially complete".

## The misreadings

1. **Honesty was read as the product.** It is a property of the product. It was meant to make outputs trustworthy, and became paperwork, gates and UI copy.
2. **Ghidra parity was read as the core.** The user said Ghidra-level analysis is "mid". The Code Browser is the drill-down floor. The core is the machine that does what the human would have done in it.
3. **Planning was read as progress.** A plan that moves no product on a real corpus is not progress, however careful.

## What the user considers too obvious to say

- You upload anything; it does the rest. There is no Start button.
- The program is the unit, not the function. Every build of it is one program.
- Every output falls out of understanding: byte-identical source, a Lua API over every function and event, address-free signatures, the whole program in a browser tab, headers, the editor, multiplayer and ports.
- Addresses are a cache. Scripts never hold a literal address.
- The machine is the reverse engineer: pointers, call graphs, similarity, structs, vtables, diffs, live tracing and compiler identity, all automatic.
- Byte identity is the judge.
- It is visual. Pictures carry the meaning; text is tooltips.

## Solution

Read [`NORTH_STAR.md`](../../NORTH_STAR.md) before any other plan. It ranks above every plan, ledger and design note. `AGENTS.md` still governs operations.

Judge every plan by the five questions. A plan that fails any of them is not ready.

1. Which product moves, and which clock shortens, on a real corpus?
2. Does it reuse what exists, or re-plan it?
3. Can the user see the result as a picture within one click?
4. Does it run without anyone pressing a button?
5. Is its claim checkable against bytes or a hash, and stated in one status word?

## Rules

- **Visual-first.** Visible text is names, numbers and labels of three words or fewer. Explanations are tooltips. Solid, dashed and double encodings, stamps and hash rows carry the truth.
- **One-word status.** done, partial, next or future. Never call a future or partial deliverable done. Never write a disclaimer where a word, glyph or frame will do.
- **No governance as progress.** No new audits, receipt ledgers, claim tiers or parity matrices unless a product showcase needs them.
- **Build on what exists.** The outputs, units and component specs are on paper already. Build them in product order. Parity features are drill-down work.
- **Names.** Use fixture ids (corpus-alpha, build-a…build-d) and role names ("the runtime scripting bridge", "the injection host"). Never use product, game or binary names.

## Prevention

When a session starts to write more than it builds, stop. Re-read section 4 of [`NORTH_STAR.md`](../../NORTH_STAR.md) and pick the next product step in its build order.
