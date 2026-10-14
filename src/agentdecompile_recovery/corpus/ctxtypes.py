"""Real types and callee signatures for recovery prompts.

Shown in the prompt, not in ctx.h: putting Ghidra layouts into the compile
context collides with bodies that define the same structs themselves.
"""

from __future__ import annotations

import json
import re

from .ghidra_sanitize import c_name

PRIMITIVE = {
    "void", "int", "char", "float", "double", "long", "short", "signed",
    "unsigned", "bool", "const", "volatile",
    "undefined", "undefined1", "undefined2", "undefined3", "undefined4",
    "undefined5", "undefined6", "undefined7", "undefined8",
    "byte", "sbyte", "word", "dword", "qword", "uchar", "ushort", "uint",
    "ulong", "ulonglong", "longlong", "code", "unicode", "wchar16", "wchar32",
    "size_t", "ptrdiff_t", "float10", "pointer", "__int64",
}

_TYPE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9:]*")
MAX_TYPES = 24
MAX_TYPE_CHARS = 8000
MAX_CALLEES = 24


def type_names(text: str) -> list[str]:
    if not text or "<" in text:
        return []
    out = []
    for m in _TYPE_TOKEN.finditer(text):
        t = m.group(0)
        if t in PRIMITIVE or "::" in t:
            continue
        out.append(t)
    return out


def load_types(con, binary_id: int) -> dict[str, str]:
    types: dict[str, str] = {}
    try:
        from . import migrations
        from .store import type_inventory_available

        if migrations.user_version(con) >= 13 and not type_inventory_available(con):
            return {}
        for r in con.execute(
                "SELECT name, definition FROM ghidra_type"
                " WHERE binary_id=? AND definition IS NOT NULL AND definition<>''",
                (binary_id,)):
            types[str(r["name"])] = str(r["definition"]).strip()
    except Exception:
        return {}
    return types


def load_signatures(con, binary_id: int) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in con.execute(
            "SELECT addr, COALESCE(canon_key, name) AS nm, signature,"
            "       return_type, param_types, calling_convention"
            "  FROM func WHERE binary_id=?", (binary_id,)):
        try:
            params = json.loads(r["param_types"] or "[]")
        except (ValueError, TypeError):
            params = []
        out[int(r["addr"])] = {
            "name": str(r["nm"] or ""),
            "signature": r["signature"] or "",
            "return_type": r["return_type"] or "",
            "params": [str(p) for p in params],
            "convention": (r["calling_convention"] or "").lower(),
        }
    return out


def declare_callee(info: dict, known: set[str], *, thiscall_dummy_edx: bool = True) -> str | None:
    """Render captured types; reject unsupported C-proxy ABI instead of inventing it.

    Ordinary native declarations may retain known by-value structures. Thiscall
    lowering requires explicit first-pointer storage and modeled scalar/pointer
    return/arguments; a missing return is never fabricated as void.
    None means unavailable declaration, not permission to discard source/facts.
    """
    if not isinstance(info.get('name'), str):
        return None
    name = c_name(info['name'])
    if not name or name.startswith(("FUN_", "SUB_", "thunk_")):
        return None

    def render(t: str) -> str | None:
        if not isinstance(t, str):
            return None
        t = t.strip()
        if not t or re.search(r'[<>()\[\]&.,:;{}=]', t):
            return None
        words = t.replace('*', ' ').split()
        if not words or any(not re.fullmatch(r'[A-Za-z_]\w*', word) for word in words):
            return None
        base = ' '.join(word for word in words if word not in {'const', 'volatile'})
        if not base or base in known or all(word in PRIMITIVE for word in base.split()):
            return t
        # An opaque pointer spelling preserves pointer depth, not pointee layout.
        return 'void ' + '*' * t.count('*') if '*' in t else None

    return_type, params = info.get('return_type'), info.get('params')
    if (not isinstance(return_type, str) or not isinstance(params, (list, tuple))
            or any(not isinstance(p, str) for p in params)):
        return None
    conv = info.get('convention')
    if conv == '__thiscall':
        if (not params or '*' not in params[0]
                or not _plain_c_proxy_type_supported(return_type, allow_void=True)
                or any(not _plain_c_proxy_type_supported(p) for p in params)
                or (not thiscall_dummy_edx and len(params) > 1)):
            return None
    ret = render(return_type)
    if ret is None:
        return None
    args = []
    for p in params:
        r = render(p)
        if r is None:
            return None
        args.append(r)

    if conv == "__thiscall":
        rest = args[1:]
        args = [args[0] + ' this_ecx'] + (["int edx_unused"] if thiscall_dummy_edx and rest else []) + rest
        decl = f"{ret} __fastcall {name}({', '.join(args) or 'void'});"
    elif conv in ("__cdecl", "__stdcall", "__fastcall"):
        decl = f"{ret} {conv} {name}({', '.join(args) or 'void'});"
    elif conv in ('', None):
        decl = f"{ret} {name}({', '.join(args) or 'void'});"
    else:
        return None  # unknown convention cannot silently become the compiler default.
    return decl


_CALL_TOKENS = re.compile(
    r'//[^\r\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    r'|[A-Za-z_]\w*|\s+|.', re.S
)


def _plain_c_proxy_type_supported(value: str, *, allow_void: bool = False) -> bool:
    """Only simple pointers and explicit primitive scalars have modeled ABI.

    A known structure definition does not prove by-value or hidden return
    storage conventions. Typedef names without scalar provenance, references,
    arrays and function-pointer declarators likewise need richer ABI facts.
    """
    if not value or re.search(r"[()\[\]&.]", value):
        return False
    words = value.replace("*", " ").split()
    if not words or not all(re.fullmatch(r"[A-Za-z_]\w*", word) for word in words):
        return False
    if "*" in value:
        return True
    words = [word for word in words if word not in {"const", "volatile"}]
    # PRIMITIVE is spelling vocabulary, not evidence that a typedef is scalar.
    # Unknown aliases can hide aggregate return storage or by-value layouts.
    builtins = {'char', 'short', 'int', 'long', 'signed', 'unsigned', 'float', 'double', '__int64'}
    return bool(words) and (words == ['void'] if allow_void and 'void' in words
                           else all(word in builtins for word in words))


def fix_thiscall_signatures(source):
    """Limited x86 C-only proxy for explicit Ghidra free-function `this`.

    Keep this in ECX; with explicit stack arguments reserve EDX SECOND. Native C++
    members, generic parameter names and unsupported ABI shapes stay unchanged
    so compilation refuses visibly. No calls are guessed or rewritten here:
    any use of a transformed name beyond its declarations refuses that name.
    Other translation units require fact-bound repair_thiscall_calls; this
    spelling helper does not prove architecture, ABI recovery or byte parity.
    """
    # Preprocessing can synthesize declarations/names and erase real uses.
    if any(token in source for token in ('#', '%:', '??', '\\\n', '\\\r')):
        return source
    masked = []
    for match in _CALL_TOKENS.finditer(source):
        value = match.group()
        if ((value == '/' and source.startswith('/*', match.start()))
                or value in {'"', "'"}):
            return source  # malformed lexical context cannot supply declaration facts.
        if value.startswith(('//', '/*', '"', "'")):
            masked.append(''.join('\n' if c == '\n' else ' ' for c in value))
        else:
            masked.append(value)
    text = ''.join(masked)
    if '__edx_pad' in set(re.findall(r'\b[A-Za-z_]\w*\b', text)):
        return source
    pattern = re.compile(r'^[ \t]*([A-Za-z_]\w*[\w \t*]*?)\b(__thiscall)\s+'
                         r'([A-Za-z_]\w*)\s*\(([^(){};]*)\)\s*(?=[{;])', re.M)
    declarations = []; depth = 0; cursor = 0
    for match in pattern.finditer(text):
        for char in text[cursor:match.start()]:
            depth += (char == '{') - (char == '}')
        cursor = match.start()
        if depth != 0:
            continue  # class/namespace/member and nested declarations are not C proxies.
        ret = re.sub(r'^(?:(?:extern|static|inline)\s+)+', '', match.group(1)).strip()
        if not _plain_c_proxy_type_supported(ret, allow_void=True):
            continue
        params = match.group(4).split(',')
        parsed = []
        for param in params:
            p = re.fullmatch(r'\s*(.+?)[ \t]*\b([A-Za-z_]\w*)\s*', param, re.S)
            if p is None or not _plain_c_proxy_type_supported(p.group(1).strip()):
                break
            parsed.append((p.group(1).strip(), p.group(2)))
        if (len(parsed) != len(params) or not parsed or '*' not in parsed[0][0]
                or parsed[0][1] not in {'this', 'this_ecx'}):
            continue
        first_end = match.start(4) + len(params[0])
        declarations.append((match.group(3), match.start(3), match.start(2), match.end(2),
                             first_end, len(params) > 1))
    if len(declarations) > 32:
        return source  # never partially change a repeated function's declarations.
    edits = []
    for name, name_at, start, end, first_end, needs_edx in declarations:
        declared = {entry[1] for entry in declarations if entry[0] == name}
        uses = {m.start() for m in re.finditer(r'\b' + re.escape(name) + r'\b', text)}
        if uses != declared:
            continue  # recursion/direct calls/address-taking need independent callee facts.
        edits.append((start, end, '__fastcall'))
        if needs_edx:
            edits.append((first_end, first_end, ', int __edx_pad'))
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def repair_thiscall_calls(source: str, callees: list[dict], *,
                          known_types: set[str] | None = None) -> tuple[str, list[str]]:
    """Adapt fact-bound, direct C calls together with their fastcall prototypes.

    A second integer/pointer fastcall argument consumes EDX, whereas thiscall
    passes every explicit argument on the stack. Reserve that slot without
    moving the original argument. Refuse unsupported syntax, shadowing and
    address-taking rather than guessing about indirect-call semantics. This
    repairs calling convention only, not SEH, layouts or byte parity.
    """
    targets: dict[str, int] = {}
    refused = []
    for info in callees:
        if info.get("convention") != "__thiscall" or len(info.get("params", [])) < 2:
            continue
        name = c_name(info.get("name", ""))
        if not name:
            continue
        if name in targets:
            refused.append(f"{name}: ambiguous callee identity")
        targets[name] = len(info["params"])
    if not targets:
        return source, []
    tokens = []
    for match in _CALL_TOKENS.finditer(source):
        value = match.group()
        if value == "/" and source.startswith("/*", match.start()):
            return source, ["thiscall repair refuses unterminated comments"]
        if value.isspace() or value.startswith(("//", "/*")):
            continue
        tokens.append((value, match.start(), match.end()))
    used = {value for value, _, _ in tokens} & targets.keys()
    if not used:
        return source, []
    for info in callees:
        name = c_name(info.get("name", ""))
        if name not in used:
            continue
        params = info.get("params", [])
        if (not params or "*" not in params[0]
                or not _plain_c_proxy_type_supported(info.get("return_type", ""), allow_void=True)
                or any(not _plain_c_proxy_type_supported(value) for value in params)):
            refused.append(f"{name}: aggregate or unmodeled calling-contract storage")
        if known_types is not None:
            signature_types = [info.get("return_type", ""), *params]
            if (any(set(type_names(value)) - known_types for value in signature_types)
                    or declare_callee(info, known_types) is None):
                refused.append(f"{name}: captured C types unavailable")
    if re.search(r"^\s*#", source, re.M):
        return source, ["thiscall repair refuses preprocessor-dependent calls"]
    if any(value in {'"', "'"} for value, _, _ in tokens):
        return source, ["thiscall repair refuses unterminated literals"]
    insertions = []
    opening = {"(": ")", "[": "]", "{": "}"}
    for index, (name, _, _) in enumerate(tokens):
        if name not in targets:
            continue
        previous = tokens[index - 1][0] if index else ""
        if (index + 1 >= len(tokens) or tokens[index + 1][0] != "("
                or previous in {".", ">", ":"}
                or (re.fullmatch(r"[A-Za-z_]\w*", previous) and previous != "return")):
            refused.append(f"{name}: not an unshadowed direct call")
            continue
        stack = [")"]
        commas = []
        end = None
        for cursor in range(index + 2, len(tokens)):
            value = tokens[cursor][0]
            if value in opening:
                stack.append(opening[value])
            elif value in {")", "]", "}"}:
                if not stack or value != stack.pop():
                    break
                if not stack:
                    end = cursor
                    break
            elif value == "," and len(stack) == 1:
                commas.append(cursor)
        if end is None or (end + 1 < len(tokens) and tokens[end + 1][0] == "{"):
            refused.append(f"{name}: malformed call or local definition")
            continue
        if len(commas) + 1 != targets[name]:
            refused.append(f"{name}: call arity differs from captured signature")
            continue
        boundaries = [index + 1, *commas, end]
        if any(right == left + 1 for left, right in zip(boundaries, boundaries[1:])):
            refused.append(f"{name}: empty argument")
            continue
        insertions.append(tokens[commas[0]][2])
    if refused:
        return source, sorted(set(refused))
    for offset in sorted(insertions, reverse=True):
        source = source[:offset] + " 0," + source[offset:]
    return source, []


def prompt_section(fn: dict, callee_addrs: list[int], types: dict[str, str],
                   sigs: dict[int, dict]) -> str:
    wanted: list[str] = []
    seen: set[str] = set()

    def want(text: str) -> None:
        for t in type_names(text):
            if t in types and t not in seen:
                seen.add(t)
                wanted.append(t)

    want(fn.get("signature") or "")
    want(fn.get("class") or "")
    own = sigs.get(fn.get("addr", -1))
    if own:
        want(own["signature"])

    decls: list[str] = []
    for a in callee_addrs[:MAX_CALLEES]:
        info = sigs.get(a)
        if not info:
            continue
        d = declare_callee(info, set(types))
        if d:
            decls.append(d)
            want(info["signature"])

    if not wanted and not decls:
        return ""

    shown, used = [], 0
    for t in wanted[:MAX_TYPES]:
        d = types[t]
        if used + len(d) > MAX_TYPE_CHARS:
            break
        shown.append(d)
        used += len(d)

    out = ["\n## Types and declarations recovered from this binary\n"]
    if shown:
        out.append(
            "These are the REAL layouts, taken from analysis of this exact\n"
            "binary -- field names, offsets and sizes.\n\n"
            "```c\n" + "\n\n".join(shown) + "\n```\n")
    if decls:
        out.append(
            "\nCallee declarations derived from captured binary facts. A\n"
            "__fastcall declaration may be the limited x86 C thiscall proxy\n"
            "(this in ECX, dummy EDX second when stack arguments exist), not a\n"
            "recovered native member\n"
            "declaration. Calls require fact-bound argument repair; unsupported\n"
            "contracts are omitted, not replaced with invented signatures.\n\n"
            "```c\n" + "\n".join("extern " + d for d in decls) + "\n```\n")
    return "".join(out)
