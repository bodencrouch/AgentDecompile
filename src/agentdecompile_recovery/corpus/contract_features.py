"""Calling-contract features for x86-32 function listings, and a pair check.

The v1 scorer (``match_engine.score_features``) sees block counts and the
mnemonic histogram. It cannot see how a body forms its receiver, what it
returns, or which field offsets it touches. Two bodies that differ only there
can score 0.99. This module extracts those facts from the cached instruction
listing and says whether two bodies can share one calling contract.

Input is the listing the corpus already stores: ``func_knowledge.asm``
(schema ``ingest_ghidra_knowledge.py:15-28``), one ``ADDR: HH HH ..  TEXT`` line
per instruction. ``LISTING_LINE`` is the pattern of ``asm_extent.LINE``
(``asm_extent.py:23``) and ``parse_cache_listing`` returns the same
``{va: (bytes, text)}`` shape as ``asm_extent.listing`` (``asm_extent.py:33``),
so either parser's output can be passed to ``extract_contract``. The module is
stdlib-only on purpose; it does not import ``asm_extent``.

Branch, call and ``ret`` operands are read from the instruction bytes, not
from the ``LAB_``/``; ->`` annotations. Other operands come from the text, in
Ghidra (``MOV EDI,ECX``) or Capstone/Intel (``mov edi, ecx``) syntax.

The analysis is a forward dataflow over the listing with symbolic register
values (entry ECX = receiver, stack arguments, loads through them, call
results). Calls clobber EAX, ECX and EDX only (MSVC x86-32 ABI). An
instruction it does not model makes every register unknown; it is never a
no-op.

``contract_compatibility`` returns ``compatible`` only when both listings
are complete and every hard axis is determined on both sides. A determined
hard-axis difference yields ``incompatible`` with named reasons. Everything
else is ``unknown``. Compatibility is necessary for identity, not evidence of
it.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Mapping

__all__ = [
    "LISTING_LINE",
    "HARD_AXES",
    "parse_cache_listing",
    "listing_from_rows",
    "extract_contract",
    "contract_compatibility",
]

# Same pattern as asm_extent.LINE (asm_extent.py:23) and capture.py:76.
LISTING_LINE = re.compile(r"^\s*([0-9a-fA-F]+):\s+((?:[0-9a-fA-F]{2}\s+)+)(.*)$")
MAX_LISTING_CHARS = 256 * 1024
MAX_VALUES = 8
HARD_AXES = ("receiver", "return", "ret_cleanup", "callees")

REGS = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi")
SUBREGS = {
    "al": "eax", "ah": "eax", "ax": "eax", "cl": "ecx", "ch": "ecx", "cx": "ecx",
    "dl": "edx", "dh": "edx", "dx": "edx", "bl": "ebx", "bh": "ebx", "bx": "ebx",
    "si": "esi", "di": "edi", "bp": "ebp", "sp": "esp",
}
CLOBBERED = ("eax", "ecx", "edx")
TRACKED = ("eax", "ecx", "edx", "ebx", "ebp", "esi", "edi")

UNKNOWN = ("unknown",)
OPAQUE = ("opaque",)
LOCAL = ("local",)

# Provenance markers carried only inside stack slots created by ``push reg``.
# ("pushfresh", P): the value pushed at P is still in the slot (not overwritten).
# ("pushslot", P):  the slot was created by the push at P.
# ("pushesc", P):   the slot's address escaped (lea) while the pushed value was fresh.
# They are stripped before a slot value reaches a register and never count as values.
FRESH, SLOTOF, ESCAPED = "pushfresh", "pushslot", "pushesc"
_MARKERS = frozenset((FRESH, SLOTOF, ESCAPED))
MAX_PUSH_SLOT_PASSES = 4

_NO_EFFECT = frozenset("nop test cmp bt clc stc cld std fwait wait".split())
_DEST_OPAQUE = frozenset(
    "and or adc sbb shl shr sar sal rol ror rcl rcr neg not bsf bsr bswap".split()
)
_JCC = frozenset(
    "ja jae jb jbe jc je jg jge jl jle jna jnae jnb jnbe jnc jne jng jnge jnl jnle "
    "jno jnp jns jnz jo jp jpe jpo js jz jecxz jcxz loop loope loopne loopz loopnz".split()
)
_TERMINAL = frozenset("int3 hlt ud2".split())
_NUMBER = re.compile(r"^(-)?\s*(0x[0-9a-f]+|[0-9]+)$")
_SIZE_PREFIX = re.compile(r"^(?:byte|word|dword|qword|tword|fword|xmmword)\s+ptr\s+")
_SEGMENT = re.compile(r"^(?:[cdefgs]s):")


# --------------------------------------------------------------------------
# Listing input


def parse_cache_listing(text: str) -> dict[int, tuple[bytes, str]]:
    """Parse a ``func_knowledge.asm`` text; mirrors ``asm_extent.listing``."""
    if not isinstance(text, str) or len(text) > MAX_LISTING_CHARS:
        raise ValueError("instruction_listing_unavailable_or_unbounded")
    rows: dict[int, tuple[bytes, str]] = {}
    for line in text.splitlines():
        match = LISTING_LINE.match(line)
        if not match:
            continue
        address = int(match[1], 16)
        if address in rows:
            raise ValueError("duplicate_instruction_address")
        raw = bytes.fromhex(match[2])
        if not 1 <= len(raw) <= 15:
            raise ValueError("invalid_instruction_length")
        rows[address] = (raw, match[3].strip())
    if not rows:
        raise ValueError("instruction_coverage_unavailable")
    return rows


def listing_from_rows(rows: Iterable[Mapping[str, Any]]) -> dict[int, tuple[bytes, str]]:
    """``[{va, hex, text}]`` rows (evidence packets) to the listing shape."""
    out: dict[int, tuple[bytes, str]] = {}
    for row in rows:
        va = int(row["va"])
        if va in out:
            raise ValueError("duplicate_instruction_address")
        out[va] = (bytes.fromhex(str(row["hex"])), str(row["text"]))
    return out


# --------------------------------------------------------------------------
# Operand parsing


def _number(token: str) -> int | None:
    match = _NUMBER.match(token.strip())
    if not match:
        return None
    value = int(match[2], 16) if match[2].startswith("0x") else int(match[2])
    return -value if match[1] else value


def _split_operands(text: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _parse_mem(inner: str) -> dict[str, Any]:
    mem: dict[str, Any] = {"base": None, "index": None, "disp": 0, "param": None,
                           "local": False, "local_off": None, "symbol": False, "bad": False}
    expr = inner.replace(" ", "").replace("-", "+-")
    for term in filter(None, expr.split("+")):
        if "*" in term:
            reg, _, scale = term.partition("*")
            if reg in REGS and _number(scale) is not None and mem["index"] is None:
                mem["index"] = reg
            else:
                mem["bad"] = True
        elif term in REGS:
            if mem["base"] is None:
                mem["base"] = term
            elif mem["index"] is None:
                mem["index"] = term
            else:
                mem["bad"] = True
        elif _number(term) is not None:
            mem["disp"] += _number(term)
        elif re.fullmatch(r"param_(\d+)", term):
            mem["param"] = int(term.split("_")[1])
        elif re.fullmatch(r"-?local_[0-9a-f_]+", term):
            named = re.fullmatch(r"local_([0-9a-f]+)", term)
            # Ghidra names a stack local by its offset below entry ESP: local_8 is entry_esp - 8.
            mem["local_off"] = int(named[1], 16) if named and not mem["local"] else None
            mem["local"] = True
        else:
            mem["symbol"] = True
    return mem


def _operand(token: str) -> tuple:
    text = token.strip().lower()
    text = _SIZE_PREFIX.sub("", text)
    text = _SEGMENT.sub("", text)
    if text.startswith("[") and text.endswith("]"):
        return ("mem", _parse_mem(text[1:-1]))
    if text in REGS:
        return ("reg", text)
    if text in SUBREGS:
        return ("sub", SUBREGS[text])
    value = _number(text)
    if value is not None:
        return ("imm", value & 0xFFFFFFFF)
    return ("sym", text)


def _decode(va: int, raw: bytes, text: str) -> dict[str, Any]:
    body = text.split(";", 1)[0].strip()
    parts = body.split(None, 1)
    mnem = parts[0].lower() if parts else ""
    ops = [_operand(o) for o in _split_operands(parts[1])] if len(parts) > 1 else []
    insn: dict[str, Any] = {"va": va, "raw": raw, "len": len(raw), "text": body,
                            "mnem": mnem, "ops": ops, "target": None, "indirect": False}
    b0 = raw[0]
    if mnem == "call" or mnem == "jmp" or mnem in _JCC:
        if b0 in (0xE8, 0xE9) and len(raw) == 5:
            insn["target"] = (va + 5 + int.from_bytes(raw[1:5], "little", signed=True)) & 0xFFFFFFFF
        elif (b0 == 0xEB or 0x70 <= b0 <= 0x7F or 0xE0 <= b0 <= 0xE3) and len(raw) == 2:
            insn["target"] = (va + 2 + int.from_bytes(raw[1:2], "little", signed=True)) & 0xFFFFFFFF
        elif b0 == 0x0F and len(raw) == 6 and 0x80 <= raw[1] <= 0x8F:
            insn["target"] = (va + 6 + int.from_bytes(raw[2:6], "little", signed=True)) & 0xFFFFFFFF
        elif b0 == 0xFF and mnem in ("call", "jmp"):
            insn["indirect"] = True
        else:
            insn["undecoded_branch"] = True
        if mnem == "call" and b0 == 0xE9 or mnem != "call" and b0 == 0xE8:
            insn["undecoded_branch"] = True
    if mnem in ("ret", "retn"):
        if raw == b"\xc3":
            insn["ret_imm"] = 0
        elif b0 == 0xC2 and len(raw) == 3:
            insn["ret_imm"] = int.from_bytes(raw[1:3], "little")
        else:
            insn["undecoded_branch"] = True
    return insn


# --------------------------------------------------------------------------
# Symbolic values. Each register holds a frozenset of possible values.
#   ('rcv', k)          entry ECX + k (k None: widened)
#   ('arg', n, k)       stack argument n (1-based) + k
#   ('entry', reg)      the register's value at entry
#   ('sp', k)           entry ESP - k
#   ('const', v)        constant
#   ('deref', root, k)  load from root ('rcv+0x0', 'arg1+0x8') + k
#   ('clobber',)        value left by a call
#   OPAQUE              written with something untracked
#   UNKNOWN             tracking lost


def _add_value(value: tuple, delta: int) -> tuple:
    kind = value[0]
    if kind == "rcv":
        return ("rcv", None if value[1] is None else value[1] + delta)
    if kind == "arg":
        return ("arg", value[1], None if value[2] is None else value[2] + delta)
    if kind == "sp":
        return ("sp", value[1] - delta)
    if kind == "const":
        return ("const", (value[1] + delta) & 0xFFFFFFFF)
    if kind == "deref":
        return ("deref", value[1], value[2] + delta)
    if kind == "unknown":
        return UNKNOWN
    return OPAQUE


def _add(values: frozenset, delta: int) -> frozenset:
    return frozenset(_add_value(v, delta) for v in values)


def _opaque_from(values: frozenset) -> frozenset:
    return frozenset({UNKNOWN}) if UNKNOWN in values else frozenset({OPAQUE})


def _strip(values: frozenset) -> frozenset:
    """Slot values without push-site provenance markers."""
    return frozenset(v for v in values if v[0] not in _MARKERS)


def _marks(values: frozenset, kind: str) -> set:
    return {v[1] for v in values if v[0] == kind}


def _root(value: tuple) -> tuple[str, int] | None:
    if value[0] == "rcv" and value[1] is not None:
        return ("rcv", value[1])
    if value[0] == "arg" and value[2] is not None:
        return (f"arg{value[1]}", value[2])
    return None


def _render(value: tuple) -> str:
    kind = value[0]
    if kind == "rcv":
        return "rcv+?" if value[1] is None else f"rcv{value[1]:+#x}"
    if kind == "arg":
        return f"arg{value[1]}+?" if value[2] is None else f"arg{value[1]}{value[2]:+#x}"
    if kind == "deref":
        return f"[{value[1]}]{value[2]:+#x}"
    if kind == "entry":
        return f"entry_{value[1]}"
    if kind == "clobber":
        return "call_result"
    if kind == "const":
        return f"const:{value[1]:#x}"
    return kind


class _Flow:
    """Mutable analysis context for one listing."""

    def __init__(self) -> None:
        self.lost: list[str] = []
        self.stack_faults: list[str] = []

    def widen(self, values: frozenset, va: int) -> frozenset:
        core = _strip(values)
        if len(core) <= MAX_VALUES:
            return values
        markers = values - core
        widened = set()
        for v in core:
            if v[0] == "rcv":
                widened.add(("rcv", None))
            elif v[0] == "arg":
                widened.add(("arg", v[1], None))
            elif v[0] in ("deref", "const", "clobber", "opaque"):
                widened.add(OPAQUE)
            else:
                widened.add(v)
        if len(widened) > MAX_VALUES:
            self.lost.append(f"{va:#x}:value_set_overflow")
            return frozenset({UNKNOWN}) | markers
        return frozenset(widened) | markers


def _entry_state() -> tuple[dict[str, frozenset], tuple]:
    regs = {r: frozenset({("entry", r)}) for r in TRACKED}
    regs["ecx"] = frozenset({("rcv", 0)})
    return regs, ()


def _merge(flow: _Flow, va: int, old, new):
    if old is None:
        return new, True
    old_regs, old_stack = old
    new_regs, new_stack = new
    if old_stack is None or new_stack is None:
        merged_stack = None
    elif len(old_stack) != len(new_stack):
        flow.stack_faults.append(f"{va:#x}:stack_depth_disagrees_at_join")
        merged_stack = None
    else:
        merged_stack = tuple(flow.widen(a | b, va) for a, b in zip(old_stack, new_stack))
    regs = {r: flow.widen(old_regs[r] | new_regs[r], va) for r in TRACKED}
    changed = regs != old_regs or merged_stack != old_stack
    return (regs, merged_stack), changed


# --------------------------------------------------------------------------
# Transfer


class _Recorder:
    def __init__(self) -> None:
        self.accesses: dict[int, list[tuple[str, int]]] = {}
        self.uses: dict[int, set] = {}
        self.derivations: dict[int, set] = {}
        self.calls: dict[int, dict[str, Any]] = {}
        self.rets: dict[int, dict[str, Any]] = {}
        # push reg of a receiver value: {va: set of k}; judged after the flow, not counted as a use here.
        self.push_rcv: dict[int, set] = {}
        # ("read"|"maybe"|"addr", P) events about the slot pushed at P.
        self.slot_events: dict[int, set] = {}

    def reset(self, va: int) -> None:
        self.accesses[va] = []
        self.uses[va] = set()
        self.derivations[va] = set()
        self.push_rcv.pop(va, None)
        self.slot_events[va] = set()


def _use_rcv(rec: _Recorder, va: int, values: frozenset) -> None:
    for v in values:
        if v[0] == "rcv":
            rec.uses[va].add(v[1])


def _mem_location(mem: dict, regs, stack) -> tuple:
    """Classify a memory operand: stack slot, stack argument, field, or other."""
    base = mem["base"]
    if mem["param"] is not None and base in ("esp", "ebp"):
        return ("arg", mem["param"])
    if mem["local"] and base in ("esp", "ebp"):
        off = mem.get("local_off")
        if off is not None and stack is not None and mem["index"] is None and not mem["bad"] \
                and not mem["symbol"] and mem["disp"] == 0 and off % 4 == 0 and 1 <= off // 4 <= len(stack):
            return ("slot", off // 4 - 1, True)  # named local: addressed as a local
        return ("local",)
    if mem["bad"] or mem["symbol"]:
        return ("other",)
    if base == "esp" and mem["index"] is None:
        if stack is None:
            return ("lost",)
        depth = 4 * len(stack)
        off = mem["disp"]
        if off % 4:
            return ("local",)
        if 0 <= off < depth:
            return ("slot", len(stack) - 1 - off // 4, False)
        if off - depth >= 4:
            return ("arg", (off - depth) // 4)
        return ("local",)
    if base == "ebp" and mem["index"] is None and regs["ebp"] and all(v[0] == "sp" for v in regs["ebp"]) \
            and len(regs["ebp"]) == 1:
        (_, k), = regs["ebp"]
        entry_off = mem["disp"] - k
        if entry_off >= 4 and entry_off % 4 == 0:
            return ("arg", entry_off // 4)
        below = -entry_off
        if stack is not None and below >= 4 and below % 4 == 0 and below // 4 - 1 < len(stack):
            return ("slot", below // 4 - 1, True)  # frame-pointer relative: addressed as a local
        return ("local",)
    index_values = regs.get(mem["index"], frozenset({UNKNOWN})) if mem["index"] not in (None, "esp") else frozenset()
    if base is None:
        return ("other", index_values)
    return ("field", regs.get(base, frozenset({UNKNOWN})) if base != "esp" else frozenset({OPAQUE}), index_values)


def _record_access(rec: _Recorder, va: int, mem: dict, loc: tuple) -> None:
    if loc[0] == "other" and len(loc) > 1:
        _use_rcv(rec, va, loc[1])  # receiver as the index of an absolute address
        return
    if loc[0] != "field":
        return
    base_values = loc[1]
    _use_rcv(rec, va, base_values)
    # [base + index]: base and index are interchangeable; a receiver in either is a use.
    _use_rcv(rec, va, loc[2])
    if mem["index"] is not None:
        return
    for v in base_values:
        root = _root(v)
        if root is not None:
            rec.accesses[va].append((root[0], root[1] + mem["disp"]))


def _load(mem: dict, loc: tuple, stack) -> frozenset:
    kind = loc[0]
    if kind == "arg":
        return frozenset({("arg", loc[1], 0)})
    if kind == "slot":
        return _strip(stack[loc[1]])
    if kind == "lost":
        return frozenset({UNKNOWN})
    if kind == "field":
        if mem["index"] is not None:
            return _opaque_from(loc[1])
        out = set()
        for v in loc[1]:
            root = _root(v)
            if root is not None:
                out.add(("deref", f"{root[0]}{root[1] + mem['disp']:+#x}", 0))
            elif v == UNKNOWN:
                out.add(UNKNOWN)
            else:
                out.add(OPAQUE)
        return frozenset(out)
    return frozenset({OPAQUE})


def _lea(mem: dict, regs, stack) -> frozenset:
    off = mem.get("local_off")
    if mem["local"] and off is not None and mem["base"] in ("esp", "ebp") and mem["index"] is None \
            and not mem["bad"] and not mem["symbol"] and mem["disp"] == 0 and mem["param"] is None:
        return frozenset({("sp", off)})  # Ghidra local_N is entry ESP - N, like [ebp - (N - 4)]
    if mem["bad"] or mem["symbol"] or mem["param"] is not None or mem["local"]:
        return frozenset({OPAQUE})
    base = mem["base"]
    if base is None:
        return frozenset({("const", mem["disp"] & 0xFFFFFFFF)})
    if base == "esp":
        if stack is None:
            return frozenset({UNKNOWN})
        values = frozenset({("sp", 4 * len(stack))})
    else:
        values = regs[base]
    if mem["index"] is not None:
        return _opaque_from(values | regs.get(mem["index"], frozenset()))
    return _add(values, mem["disp"])


def _step(flow: _Flow, rec: _Recorder, insn: dict, nxt: dict | None, state,
          local_slots: frozenset = frozenset()):
    """Apply one instruction; return the new state (or None when terminal).

    ``local_slots`` holds push sites whose slot an earlier pass saw addressed
    as a local (frame-pointer relative, a Ghidra ``local_N`` name, or its
    address taken). The call-arity walk stops at those slots.
    """
    regs, stack = dict(state[0]), state[1]
    va, mnem, ops = insn["va"], insn["mnem"], insn["ops"]
    rec.reset(va)
    if mnem in _TERMINAL:
        return None

    def slot_event(kind: str, sites) -> None:
        for site in sites:
            rec.slot_events[va].add((kind, site))

    def fresh_escaped() -> set:
        if stack is None:
            return set()
        return {p for slot in stack for p in _marks(slot, FRESH) & _marks(slot, ESCAPED)}

    def note_slot(loc: tuple, reading: bool) -> None:
        """Record what an access does to push-reg slots."""
        if loc[0] == "slot" and stack is not None:
            slot = stack[loc[1]]
            if reading:
                slot_event("read", _marks(slot, FRESH))
            if len(loc) > 2 and loc[2]:
                slot_event("addr", _marks(slot, SLOTOF))
        elif loc[0] in ("local", "lost"):
            # A stack access that cannot be tied to a slot may touch a pushed value.
            if stack is not None:
                slot_event("maybe", {p for slot in stack for p in _marks(slot, FRESH)})
        elif loc[0] == "field" and any(v[0] == "sp" for v in loc[1] | loc[2]):
            slot_event("maybe", fresh_escaped())  # access through a pointer into the stack

    def value_of(op: tuple) -> frozenset:
        kind = op[0]
        if kind == "reg":
            if op[1] == "esp":
                return frozenset({UNKNOWN}) if stack is None else frozenset({("sp", 4 * len(stack))})
            return regs[op[1]]
        if kind == "imm":
            return frozenset({("const", op[1])})
        if kind == "mem":
            loc = _mem_location(op[1], regs, stack)
            _record_access(rec, va, op[1], loc)
            note_slot(loc, reading=True)
            return _load(op[1], loc, stack)
        if kind == "sub":
            return _opaque_from(regs.get(op[1], frozenset()))
        return frozenset({OPAQUE})

    def touch(op: tuple) -> None:
        if op[0] == "mem":
            loc = _mem_location(op[1], regs, stack)
            _record_access(rec, va, op[1], loc)
            note_slot(loc, reading=True)

    def lose(reason: str) -> None:
        flow.lost.append(f"{va:#x}:{reason}")
        for r in TRACKED:
            regs[r] = frozenset({UNKNOWN})

    def write(op: tuple, values: frozenset) -> None:
        nonlocal stack
        kind = op[0]
        if kind == "reg":
            if op[1] == "esp":
                flow.stack_faults.append(f"{va:#x}:untracked_esp_write")
                stack = None
                return
            for v in values:
                if v[0] == "rcv" and op[1] != "ecx" or v[0] == "rcv" and v[1] != 0:
                    rec.derivations[va].add(v[1])
            regs[op[1]] = values
        elif kind == "sub":
            if op[1] == "esp":
                stack = None
                flow.stack_faults.append(f"{va:#x}:untracked_esp_write")
            else:
                regs[op[1]] = _opaque_from(regs[op[1]] | values)
        elif kind == "mem":
            loc = _mem_location(op[1], regs, stack)
            _record_access(rec, va, op[1], loc)
            note_slot(loc, reading=False)
            _use_rcv(rec, va, values)
            if loc[0] == "slot" and stack is not None:
                # A store overwrites the pushed value; the slot keeps only its push site.
                kept = frozenset(v for v in stack[loc[1]] if v[0] in (SLOTOF, ESCAPED))
                stack = stack[:loc[1]] + (values | kept,) + stack[loc[1] + 1:]

    def push(values: frozenset) -> None:
        nonlocal stack
        if stack is not None:
            stack = stack + (values,)

    def pop(count: int) -> tuple | None:
        nonlocal stack
        if stack is None:
            return None
        if count > len(stack):
            flow.stack_faults.append(f"{va:#x}:stack_underflow")
            stack = None
            return None
        popped = stack[len(stack) - count:]
        stack = stack[:len(stack) - count]
        return popped

    if mnem in _NO_EFFECT or mnem in _JCC or (mnem == "jmp" and not insn["indirect"]):
        for op in ops:
            if op[0] == "mem":
                touch(op)
        return regs, stack
    if mnem in ("mov", "movzx", "movsx"):
        if len(ops) != 2:
            lose("operand_count")
            return regs, stack
        values = value_of(ops[1])
        if mnem != "mov":
            values = _opaque_from(values)
        if ops[0] == ("reg", "ebp") or ops[0] == ("reg", "esp"):
            if ops[0][1] == "esp" and ops[1] == ("reg", "ebp") and stack is not None:
                ebp = regs["ebp"]
                if len(ebp) == 1 and next(iter(ebp))[0] == "sp" and next(iter(ebp))[1] % 4 == 0 \
                        and 0 <= next(iter(ebp))[1] // 4 <= len(stack):
                    stack = stack[:next(iter(ebp))[1] // 4]
                    return regs, stack
            if ops[0][1] == "ebp":
                regs["ebp"] = values
                return regs, stack
        write(ops[0], values)
        return regs, stack
    if mnem == "lea":
        if len(ops) != 2 or ops[1][0] != "mem" or ops[0][0] != "reg":
            lose("lea_form")
            return regs, stack
        mem = ops[1][1]
        address = _lea(mem, regs, stack)
        if mem["index"] is not None:
            # [base + index] address: the receiver in either position is a use.
            _use_rcv(rec, va, regs.get(mem["base"], frozenset()) | regs.get(mem["index"], frozenset()))
        if stack is not None and ops[0][1] != "esp":
            for v in address:
                if v[0] == "sp" and v[1] % 4 == 0 and 1 <= v[1] // 4 <= len(stack):
                    i = v[1] // 4 - 1
                    slot_event("addr", _marks(stack[i], SLOTOF))  # address taken: a local
                    escaped = frozenset((ESCAPED, p) for p in _marks(stack[i], SLOTOF))
                    stack = stack[:i] + (stack[i] | escaped,) + stack[i + 1:]
        write(ops[0], address)
        return regs, stack
    if mnem == "push":
        if len(ops) != 1:
            lose("operand_count")
            return regs, stack
        values = value_of(ops[0])
        if ops[0][0] == "reg" and ops[0][1] != "esp":
            # push reg is either an argument, a spill, or MSVC's local-slot allocation
            # (push ecx). Which one is judged after the flow from what happens to the slot.
            ks = {v[1] for v in values if v[0] == "rcv"}
            if ks:
                rec.push_rcv[va] = ks
            values = values | {(FRESH, va), (SLOTOF, va)}
        push(values)
        return regs, stack
    if mnem == "pop":
        if len(ops) != 1:
            lose("operand_count")
            return regs, stack
        popped = pop(1)
        if popped:
            slot_event("read", _marks(popped[0], FRESH))
        write(ops[0], _strip(popped[0]) if popped else frozenset({UNKNOWN}))
        return regs, stack
    if mnem in ("add", "sub"):
        if len(ops) != 2:
            lose("operand_count")
            return regs, stack
        sign = 1 if mnem == "add" else -1
        dst, src = ops
        if dst == ("reg", "esp"):
            if src[0] == "imm" and src[1] % 4 == 0:
                amount = src[1] if src[1] < 0x80000000 else src[1] - 0x100000000
                amount *= sign
                if amount >= 0:
                    pop(amount // 4)
                else:
                    for _ in range(-amount // 4):
                        push(frozenset({LOCAL}))
            else:
                flow.stack_faults.append(f"{va:#x}:untracked_esp_adjust")
                stack = None
            return regs, stack
        if dst[0] == "reg":
            if src[0] == "imm":
                delta = src[1] if src[1] < 0x80000000 else src[1] - 0x100000000
                write(dst, _add(regs[dst[1]], sign * delta))
            else:
                write(dst, _opaque_from(regs[dst[1]] | value_of(src)))
            return regs, stack
        value_of(src) if src[0] == "mem" else None
        if dst[0] == "mem":
            note_slot(_mem_location(dst[1], regs, stack), reading=True)  # read-modify-write
        write(dst, value_of(src) if src[0] == "reg" else frozenset({OPAQUE}))
        return regs, stack
    if mnem in ("inc", "dec"):
        if len(ops) != 1:
            lose("operand_count")
            return regs, stack
        if ops[0][0] == "reg" and ops[0][1] != "esp":
            write(ops[0], _add(regs[ops[0][1]], 1 if mnem == "inc" else -1))
        elif ops[0][0] == "mem":
            touch(ops[0])
        else:
            write(ops[0], frozenset({OPAQUE}))
        return regs, stack
    if mnem == "xor" and len(ops) == 2 and ops[0] == ops[1] and ops[0][0] == "reg":
        write(ops[0], frozenset({("const", 0)}))
        return regs, stack
    if mnem in _DEST_OPAQUE or mnem == "xor" or mnem.startswith("set") or mnem.startswith("cmov"):
        if not ops:
            lose("operand_count")
            return regs, stack
        for op in ops[1:]:
            value_of(op)
        if ops[0][0] in ("reg", "sub"):
            if ops[0][1] == "esp":
                write(ops[0], frozenset({OPAQUE}))
            else:
                base = regs[ops[0][1]]
                write(ops[0], base | _opaque_from(base) if mnem.startswith("cmov") else _opaque_from(base))
        else:
            touch(ops[0])
        return regs, stack
    if mnem == "imul" and len(ops) >= 2:
        for op in ops[1:]:
            value_of(op)
        write(ops[0], frozenset({OPAQUE}))
        return regs, stack
    if mnem in ("mul", "imul", "div", "idiv") and len(ops) == 1:
        value_of(ops[0])
        regs["eax"] = frozenset({OPAQUE})
        regs["edx"] = frozenset({OPAQUE})
        return regs, stack
    if mnem in ("cdq", "cwd"):
        regs["edx"] = frozenset({OPAQUE})
        return regs, stack
    if mnem in ("cwde", "cbw"):
        regs["eax"] = frozenset({OPAQUE})
        return regs, stack
    if mnem == "leave":
        ebp = regs["ebp"]
        if stack is not None and len(ebp) == 1 and next(iter(ebp))[0] == "sp" \
                and next(iter(ebp))[1] % 4 == 0 and 0 <= next(iter(ebp))[1] // 4 <= len(stack):
            stack = stack[:next(iter(ebp))[1] // 4]
            popped = pop(1)
            regs["ebp"] = _strip(popped[0]) if popped else frozenset({UNKNOWN})
        else:
            flow.stack_faults.append(f"{va:#x}:untracked_leave")
            stack = None
            regs["ebp"] = frozenset({UNKNOWN})
        return regs, stack
    if mnem == "xchg" and len(ops) == 2 and ops[0][0] == "reg" and ops[1][0] == "reg" \
            and "esp" not in (ops[0][1], ops[1][1]):
        a, b = regs[ops[0][1]], regs[ops[1][1]]
        regs[ops[0][1]], regs[ops[1][1]] = b, a
        return regs, stack
    if mnem.startswith("f") and mnem not in ("fnstsw", "fstsw"):
        # x87: no general-register effect; memory operands are still field accesses.
        for op in ops:
            touch(op)
        return regs, stack
    if mnem in ("fnstsw", "fstsw"):
        for op in ops:
            if op[0] == "mem":
                touch(op)
            elif op[0] in ("reg", "sub"):
                regs[op[1]] = frozenset({OPAQUE})
        return regs, stack
    if mnem == "call":
        for op in ops:
            if op[0] == "mem":
                touch(op)
        arity = 0
        if stack is not None:
            for slot in reversed(stack):
                core = _strip(slot)
                if core == frozenset({LOCAL}) or (len(core) == 1 and next(iter(core))[0] == "entry"):
                    break
                if _marks(slot, SLOTOF) & local_slots:
                    break  # a push-allocated slot addressed as a local is not an argument
                arity += 1
        cleanup = "callee"
        if nxt is not None and nxt["mnem"] == "add" and len(nxt["ops"]) == 2 \
                and nxt["ops"][0] == ("reg", "esp") and nxt["ops"][1][0] == "imm" and nxt["ops"][1][1] % 4 == 0:
            cleanup = "caller"
            arity = nxt["ops"][1][1] // 4
        ambiguous = nxt is not None and nxt["mnem"] == "pop" and nxt["ops"] in ([("reg", "ecx")], [("reg", "edx")])
        if ambiguous:
            # MSVC pops a caller-saved register right after a call either to clean up
            # a cdecl argument or to free a push-ecx local; the arity cannot be told.
            flow.stack_faults.append(f"{va:#x}:pop_after_call_cleanup_ambiguous")
        if stack is not None:
            for slot in stack[max(0, len(stack) - arity):]:
                slot_event("read", _marks(slot, FRESH))  # consumed as an argument
            # The callee may read a slot whose address escaped while the pushed value was
            # still there, and may write any escaped slot: its value is opaque afterwards.
            slot_event("maybe", fresh_escaped())
            stack = tuple(
                frozenset({OPAQUE}) | frozenset(v for v in slot if v[0] in (SLOTOF, ESCAPED))
                if _marks(slot, ESCAPED) else slot
                for slot in stack
            )
        _use_rcv(rec, va, regs["ecx"])
        rec.calls[va] = {
            "va": va,
            "target": insn["target"],
            "indirect": insn["indirect"],
            "arity": arity if stack is not None and not ambiguous else None,
            "cleanup": cleanup,
            "this": sorted(_render(v) for v in regs["ecx"]),
        }
        if cleanup == "callee" and arity:
            pop(arity)
        for r in CLOBBERED:
            regs[r] = frozenset({("clobber",)})
        return regs, stack
    if mnem in ("ret", "retn"):
        _use_rcv(rec, va, regs["eax"])
        rec.rets[va] = {"va": va, "imm": insn.get("ret_imm"), "eax": regs["eax"],
                        "depth": None if stack is None else len(stack)}
        return None
    lose(f"unmodelled_{mnem or 'empty'}")
    for op in ops:
        if op[0] == "mem":
            touch(op)
    return regs, stack


# --------------------------------------------------------------------------
# Extraction


def _return_class(values: frozenset) -> str:
    if not values or UNKNOWN in values:
        return "undetermined"
    if any(v[0] == "entry" for v in values):
        return "unwritten"
    if all(v[0] == "rcv" and v[1] == 0 for v in values):
        return "receiver"
    if all(v[0] == "rcv" and v[1] is not None for v in values) and len({v[1] for v in values}) == 1:
        return f"receiver{next(iter(values))[1]:+#x}"
    if all(v[0] == "clobber" for v in values):
        return "callee_result"
    return "other"


def extract_contract(
    listing: Mapping[int, tuple[bytes, str]] | None,
    *,
    entry: int,
    size: int | None,
    truncated: bool = False,
) -> dict[str, Any]:
    """Derive contract features from one function's decoded x86-32 listing.

    ``size`` is ``func_knowledge.size`` (body byte count). Without it the
    listing cannot be shown complete, so the result is marked incomplete.
    Pass ``truncated=True`` when the stored ``asm`` was longer than what was
    read (``length(asm)`` above the ``substr`` limit).
    """
    incomplete: list[str] = []
    if truncated:
        incomplete.append("listing_truncated")
    if not listing:
        return _features(entry, size, None, ["listing_unavailable"], _Flow(), _Recorder(), {})
    if size is None:
        incomplete.append("size_unavailable")
    insns: dict[int, dict[str, Any]] = {}
    order = sorted(listing)
    if order[0] != entry:
        incomplete.append("listing_does_not_start_at_entry")
    cursor = order[0]
    for va in order:
        raw, text = listing[va]
        if va != cursor:
            incomplete.append(f"gap_or_overlap_at_{va:#x}")
        cursor = va + len(raw)
        insn = _decode(va, bytes(raw), text)
        if not insn["mnem"]:
            incomplete.append(f"empty_text_at_{va:#x}")
        if insn.get("undecoded_branch"):
            incomplete.append(f"undecoded_branch_at_{va:#x}")
        insns[va] = insn
    covered = sum(len(listing[va][0]) for va in order)
    if size is not None and covered != size:
        incomplete.append(f"covered_{covered}_bytes_of_{size}")
    for insn in insns.values():
        if insn["mnem"] == "jmp" and insn["indirect"]:
            incomplete.append(f"indirect_jump_at_{insn['va']:#x}")
        if (insn["mnem"] == "jmp" or insn["mnem"] in _JCC) and insn["target"] is not None \
                and insn["target"] not in insns:
            incomplete.append(f"branch_leaves_listing_at_{insn['va']:#x}")

    # A push-reg slot seen addressed as a local stops the call-arity walk; that can move
    # later stack offsets, so repeat until the set of such slots stops growing.
    local_slots: frozenset = frozenset()
    for _ in range(MAX_PUSH_SLOT_PASSES):
        flow, rec, states, flow_incomplete = _run_flow(insns, order, entry, local_slots)
        grown = local_slots | _slot_sites(rec, states, "addr")
        if grown == local_slots:
            break
        local_slots = grown
    else:
        flow_incomplete = flow_incomplete + ["push_slot_passes_not_converged"]
    incomplete.extend(flow_incomplete)
    if not rec.rets:
        incomplete.append("no_reachable_ret")
    return _features(entry, size, insns, sorted(set(incomplete)), flow, rec, states)


def _run_flow(insns: dict, order: list, entry: int, local_slots: frozenset):
    flow, rec = _Flow(), _Recorder()
    states: dict[int, Any] = {}
    incomplete: list[str] = []
    if entry in insns:
        states[entry] = _entry_state()
        work = [entry]
        budget = 200 * max(1, len(insns))
        index = {va: i for i, va in enumerate(order)}
        while work:
            budget -= 1
            if budget < 0:
                incomplete.append("dataflow_not_converged")
                break
            va = work.pop()
            insn = insns[va]
            i = index[va]
            nxt = insns[order[i + 1]] if i + 1 < len(order) else None
            out = _step(flow, rec, insn, nxt, states[va], local_slots)
            if out is None or insn["mnem"] in _TERMINAL:
                continue
            if any(v[0] in _MARKERS for values in out[0].values() for v in values):
                raise RuntimeError(f"push-slot marker reached a register at {va:#x}")
            succs = []
            if insn["mnem"] == "jmp":
                if insn["target"] in insns:
                    succs.append(insn["target"])
            else:
                if insn["mnem"] in _JCC and insn["target"] in insns:
                    succs.append(insn["target"])
                if nxt is not None:
                    succs.append(nxt["va"])
                else:
                    incomplete.append(f"falls_off_listing_at_{va:#x}")
            for succ in succs:
                merged, changed = _merge(flow, succ, states.get(succ), out)
                if changed:
                    states[succ] = merged
                    if succ not in work:
                        work.append(succ)
    return flow, rec, states, incomplete


def _slot_sites(rec: _Recorder, states, kind: str) -> frozenset:
    return frozenset(site for va, events in rec.slot_events.items() if va in states
                     for k, site in events if k == kind)


def _receiver_form(ks: set) -> tuple:
    if not ks:
        return ("unused", None)
    if 0 in ks:
        return ("passthrough", 0)
    if None in ks:
        return (None, None)
    if len(ks) == 1:
        return ("adjusted", next(iter(ks)))
    return ("adjusted_multi", sorted(ks))


def _features(entry, size, insns, incomplete, flow: _Flow, rec: _Recorder, states) -> dict[str, Any]:
    complete = not incomplete
    lost = sorted(set(flow.lost))
    stack_faults = sorted(set(flow.stack_faults))
    for ret in rec.rets.values():
        if ret["depth"] not in (0,):
            stack_faults.append(f"{ret['va']:#x}:stack_not_balanced_at_ret")
    stack_faults = sorted(set(stack_faults))
    reached = set(states)

    # Receiver formation. A push of the receiver counts as a use when its slot is
    # read, reloaded or passed to a call; it is a local-slot allocation when the
    # pushed value is overwritten or discarded unread; otherwise it is undecided.
    uses = {va: ks for va, ks in rec.uses.items() if va in reached and ks}
    read = _slot_sites(rec, states, "read")
    maybe = _slot_sites(rec, states, "maybe")
    push_slots: dict[str, str] = {}
    undecided: dict[int, set] = {}
    for site, site_ks in sorted(rec.push_rcv.items()):
        if site not in reached:
            continue
        if site in read:
            status = "use"
            uses[site] = uses.get(site, set()) | site_ks
        elif site in maybe or stack_faults or lost:
            status = "undecided"
            undecided[site] = site_ks
        else:
            status = "local_slot"
        push_slots[f"{site:#x}"] = status
    ks = set().union(*uses.values()) if uses else set()
    derivations = sorted((va, k) for va, kset in rec.derivations.items() if va in reached for k in kset)
    receiver: dict[str, Any] = {"form": None, "k": None, "formed_at": None,
                                "use_offsets": sorted(k for k in ks if k is not None)}
    if push_slots:
        receiver["push_slots"] = push_slots
    if complete and not lost:
        form, k = _receiver_form(ks)
        if undecided and _receiver_form(ks.union(*undecided.values())) != (form, k):
            form, k = None, None  # the verdict hangs on a push we cannot classify
        receiver.update(form=form, k=k)
        if receiver["form"] in ("passthrough", "adjusted"):
            sites = [va for va, k in derivations if k == receiver["k"]]
            receiver["formed_at"] = min(sites) if sites else min(uses)
    receiver["determined"] = receiver["form"] is not None

    # Return contract.
    eax: frozenset = frozenset()
    for ret in rec.rets.values():
        eax = eax | ret["eax"]
    return_class = _return_class(eax) if complete and not lost and rec.rets else "undetermined"
    # EAX is the return value only when every ret sees a value this function wrote there and
    # no x87 result can be in ST0. Otherwise the class is a description, not a contract.
    return_why: list[str] = []
    if return_class != "undetermined":
        if any(any(v[0] == "entry" for v in ret["eax"]) for va, ret in rec.rets.items() if va in reached):
            return_why.append("eax_not_written_on_a_path")
        if any(any(v[0] == "clobber" for v in ret["eax"]) for va, ret in rec.rets.items() if va in reached):
            return_why.append("eax_left_by_a_callee")
        if any(insns[va]["mnem"].startswith("f") for va in reached if va in insns):
            return_why.append("x87")
    ret_imms = sorted({ret["imm"] for ret in rec.rets.values() if ret["imm"] is not None})

    # Field offsets relative to the receiver and argument bases.
    offsets: Counter = Counter()
    for va, items in rec.accesses.items():
        if va in reached:
            offsets.update(items)
    field_offsets: dict[str, dict[str, int]] = {}
    for (root, off), count in sorted(offsets.items()):
        field_offsets.setdefault(root, {})[f"{off:#x}"] = count

    calls = [rec.calls[va] for va in sorted(rec.calls) if va in reached]
    callees_ok = complete and not stack_faults and all(c["arity"] is not None for c in calls)
    return {
        "entry": entry,
        "size": size,
        "complete": complete,
        "incomplete_reasons": incomplete,
        "tracking_lost": lost,
        "stack_faults": stack_faults,
        "receiver": receiver,
        "return": {
            "class": return_class,
            "eax_at_ret": sorted(_render(v) for v in eax),
            "determined": return_class != "undetermined" and not return_why,
            "undetermined_reasons": return_why,
        },
        "ret_cleanup": {"imm": ret_imms, "determined": complete and bool(ret_imms)},
        "field_offsets": field_offsets,
        "callees": [
            {"va": c["va"], "target": c["target"], "indirect": c["indirect"],
             "arity": c["arity"], "cleanup": c["cleanup"], "this": c["this"]}
            for c in calls
        ],
        "callees_determined": callees_ok,
    }


# --------------------------------------------------------------------------
# Compatibility


_RETURN_COMPATIBLE = {
    "receiver": {"receiver"},
    "unwritten": {"unwritten", "callee_result"},
    "other": {"other", "callee_result"},
    "callee_result": {"callee_result", "unwritten", "other"},
}


def _returns_compatible(left: str, right: str) -> bool:
    if left in _RETURN_COMPATIBLE:
        return right in _RETURN_COMPATIBLE[left]
    return left == right  # receiver+k classes


def contract_compatibility(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compare two ``extract_contract`` results.

    Returns ``{"verdict", "reasons", "axes", "differences"}``. ``verdict`` is
    ``compatible``, ``incompatible`` or ``unknown``. ``reasons`` names each
    hard axis that differs. ``differences`` lists soft facts (field offsets,
    callee ``this`` expressions, callee count) that never decide the verdict.
    """
    if not left or not right:
        return {"verdict": "unknown", "reasons": [], "differences": [],
                "axes": {axis: {"status": "undetermined"} for axis in HARD_AXES},
                "notes": ["features_unavailable"]}
    axes: dict[str, dict[str, Any]] = {}

    def axis(name: str, determined: bool, lval: Any, rval: Any, same: bool) -> None:
        if not determined:
            axes[name] = {"status": "undetermined", "left": lval, "right": rval}
        else:
            axes[name] = {"status": "same" if same else "differs", "left": lval, "right": rval}

    lr, rr = left["receiver"], right["receiver"]
    lrv, rrv = (lr["form"], lr["k"]), (rr["form"], rr["k"])
    axis("receiver", lr["determined"] and rr["determined"], lrv, rrv, lrv == rrv)

    lc, rc = left["return"]["class"], right["return"]["class"]
    axis("return", left["return"]["determined"] and right["return"]["determined"], lc, rc,
         _returns_compatible(lc, rc))

    li, ri = left["ret_cleanup"]["imm"], right["ret_cleanup"]["imm"]
    axis("ret_cleanup", left["ret_cleanup"]["determined"] and right["ret_cleanup"]["determined"],
         li, ri, li == ri)

    lcalls, rcalls = left["callees"], right["callees"]
    lsig = [(c["arity"], c["cleanup"]) for c in lcalls]
    rsig = [(c["arity"], c["cleanup"]) for c in rcalls]
    differences: list[dict[str, Any]] = []
    if len(lcalls) != len(rcalls):
        differences.append({"kind": "callee_count", "left": len(lcalls), "right": len(rcalls)})
        axes["callees"] = {"status": "undetermined", "left": lsig, "right": rsig,
                           "note": "callee counts differ; positions not comparable"}
    else:
        axis("callees", left["callees_determined"] and right["callees_determined"], lsig, rsig, lsig == rsig)
        for pos, (lcall, rcall) in enumerate(zip(lcalls, rcalls)):
            if lcall["this"] != rcall["this"]:
                differences.append({"kind": "callee_this", "position": pos,
                                    "left": lcall["this"], "right": rcall["this"]})

    for root in sorted(set(left["field_offsets"]) | set(right["field_offsets"])):
        lo = Counter(left["field_offsets"].get(root, {}))
        ro = Counter(right["field_offsets"].get(root, {}))
        if lo != ro:
            differences.append({"kind": "field_offsets", "root": root,
                                "only_left": dict(sorted((lo - ro).items())),
                                "only_right": dict(sorted((ro - lo).items()))})

    reasons = [{"axis": name, "left": axes[name]["left"], "right": axes[name]["right"]}
               for name in HARD_AXES if axes[name]["status"] == "differs"]
    both_complete = bool(left["complete"] and right["complete"])
    if reasons:
        verdict = "incompatible"
    elif both_complete and all(axes[name]["status"] == "same" for name in HARD_AXES):
        verdict = "compatible"
    else:
        verdict = "unknown"
    notes = []
    if not both_complete:
        notes.append("listing_incomplete")
    return {"verdict": verdict, "reasons": reasons, "axes": axes,
            "differences": differences, "notes": notes}
