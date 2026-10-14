"""Compatibility declarations shared by recovered-C compilation paths."""

import re

PREAMBLE = """#ifndef NULL
#define NULL ((void*)0)
#endif
#define TRUE 1
#define FALSE 0
typedef unsigned char undefined;
typedef unsigned char undefined1;
typedef unsigned short undefined2;
typedef unsigned int undefined4;
typedef unsigned long long undefined8;
typedef unsigned char undefined3[3];
typedef unsigned char byte;
typedef unsigned char uchar;
typedef int bool;
typedef unsigned short word;
typedef unsigned short ushort;
typedef unsigned int dword;
typedef unsigned int uint;
typedef unsigned long ulong;
typedef unsigned int size_t;
typedef long double float10;
"""

_TYPEDEF_STATEMENT = re.compile(r"\btypedef\b([^;{}]*);", re.S)
_TYPEDEF_ALIAS = re.compile(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)?$")
_COMMENTS_AND_LITERALS = re.compile(
    r'/\*.*?\*/|//[^\r\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S
)


def _unconditionally_active(source: str) -> str:
    source = re.sub(r"\\\r?\n", "", source)
    code = _COMMENTS_AND_LITERALS.sub(lambda match: "\n" * match.group().count("\n"), source)
    stack: list[tuple[bool, bool | None, bool]] = []
    active = True
    lines = []
    for line in code.splitlines(keepends=True):
        directive = re.match(r"\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", line)
        if not directive:
            if active:
                lines.append(line)
            continue
        kind, expression = directive.group(1), directive.group(2).strip()
        if kind in {"if", "ifdef", "ifndef"}:
            # shortcut: unknown conditional branches stay inactive; include compiler defines before broadening this scan.
            condition = expression == "1" if kind == "if" and expression in {"0", "1"} else None
            parent = active
            stack.append((parent, condition, condition is not False))
            active = parent and condition is True
        elif kind == "elif" and stack:
            parent, condition, taken = stack[-1]
            next_condition = expression == "1" if expression in {"0", "1"} else None
            active = parent and not taken and next_condition is True
            stack[-1] = (parent, condition, taken or next_condition is not False)
        elif kind == "else" and stack:
            parent, condition, taken = stack[-1]
            active = parent and not taken and condition is False
            stack[-1] = (parent, condition, True)
        elif kind == "endif" and stack:
            active = stack.pop()[0]
    return "".join(lines)


def preamble_for_source(source: str) -> str:
    """Leave compatibility aliases to recovered C when it already defines them."""
    source_types = set()
    for statement in _TYPEDEF_STATEMENT.findall(_unconditionally_active(source)):
        declarators, start = [], 0
        parentheses = brackets = 0
        for index, char in enumerate(statement):
            if char == "(":
                parentheses += 1
            elif char == ")":
                parentheses = max(0, parentheses - 1)
            elif char == "[":
                brackets += 1
            elif char == "]":
                brackets = max(0, brackets - 1)
            elif char == "," and parentheses == brackets == 0:
                declarators.append(statement[start:index])
                start = index + 1
        declarators.append(statement[start:])
        for declarator in declarators:
            if "(" in declarator or ")" in declarator:
                # shortcut: complex declarators are skipped; use a C parser if one aliases a preamble type.
                continue
            alias = _TYPEDEF_ALIAS.search(declarator.strip())
            if alias:
                source_types.add(alias.group(1))
    if not source_types:
        return PREAMBLE
    lines = []
    for line in PREAMBLE.splitlines(keepends=True):
        if line.startswith("typedef "):
            alias = _TYPEDEF_ALIAS.search(line.rstrip().removesuffix(";").removeprefix("typedef ").strip())
            if alias and alias.group(1) in source_types:
                continue
        lines.append(line)
    return "".join(lines)
