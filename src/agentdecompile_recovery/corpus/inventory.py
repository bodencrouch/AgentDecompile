"""Inventory every program in the Odyssey repository.

Records format, architecture, compiler spec, function counts, and — critically —
how many functions carry a *user-supplied* name (Lane's annotation corpus) versus
an auto-generated ``FUN_``/``thunk_`` name.
"""

from __future__ import annotations

import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from . import ghidra_env as ge

OUT = ge.resolve_workspace() / "extract" / "inventory.json"


def summarize(program) -> dict:
    from ghidra.program.model.symbol import SourceType

    lang = program.getLanguage()
    ldesc = lang.getLanguageDescription()
    mem = program.getMemory()

    fm = program.getFunctionManager()
    counts = {
        "total": 0,
        "external": 0,
        "thunk": 0,
        "default_named": 0,
        "user_named": 0,
        "imported_named": 0,
        "analysis_named": 0,
        "with_namespace": 0,
        "with_custom_sig": 0,
        "with_plate_comment": 0,
    }
    by_source: dict[str, int] = {}
    for f in fm.getFunctions(True):
        counts["total"] += 1
        if f.isExternal():
            counts["external"] += 1
        if f.isThunk():
            counts["thunk"] += 1
        sym = f.getSymbol()
        st = str(sym.getSource()) if sym is not None else "NONE"
        by_source[st] = by_source.get(st, 0) + 1
        name = str(f.getName())
        if name.startswith(("FUN_", "thunk_FUN_", "SUB_", "UndefinedFunction_")):
            counts["default_named"] += 1
        if sym is not None:
            if sym.getSource() == SourceType.USER_DEFINED:
                counts["user_named"] += 1
            elif sym.getSource() == SourceType.IMPORTED:
                counts["imported_named"] += 1
            elif sym.getSource() == SourceType.ANALYSIS:
                counts["analysis_named"] += 1
        ns = f.getParentNamespace()
        if ns is not None and not ns.isGlobal():
            counts["with_namespace"] += 1
        if f.hasCustomVariableStorage() or f.getSignatureSource() == SourceType.USER_DEFINED:
            counts["with_custom_sig"] += 1
        if f.getComment():
            counts["with_plate_comment"] += 1

    st = program.getSymbolTable()
    sym_total = st.getNumSymbols()

    # Namespaces that look like C++ classes carry a lot of Lane's structure.
    for ns in st.getDefinedSymbols():
        pass

    dtm = program.getDataTypeManager()

    blocks = []
    for b in mem.getBlocks():
        blocks.append(
            {
                "name": str(b.getName()),
                "start": f"0x{b.getStart().getOffset():x}",
                "size": int(b.getSize()),
                "x": bool(b.isExecute()),
                "init": bool(b.isInitialized()),
            }
        )

    props = {}
    opts = program.getOptions("Program Information")
    for k in opts.getOptionNames():
        try:
            props[str(k)] = str(opts.getValueAsString(k))
        except Exception:
            pass

    return {
        "name": str(program.getName()),
        "language_id": str(ldesc.getLanguageID()),
        "processor": str(ldesc.getProcessor()),
        "endian": str(ldesc.getEndian()),
        "size_bits": int(ldesc.getSize()),
        "compiler_spec": str(program.getCompilerSpec().getCompilerSpecID()),
        "executable_format": str(program.getExecutableFormat()),
        "executable_path": str(program.getExecutablePath()),
        "executable_md5": str(program.getExecutableMD5()),
        "image_base": f"0x{program.getImageBase().getOffset():x}",
        "min_addr": f"0x{mem.getMinAddress().getOffset():x}" if mem.getMinAddress() else None,
        "max_addr": f"0x{mem.getMaxAddress().getOffset():x}" if mem.getMaxAddress() else None,
        "functions": counts,
        "function_symbol_sources": by_source,
        "symbols_total": int(sym_total),
        "datatypes": int(dtm.getDataTypeCount(True)),
        "blocks": blocks,
        "program_info": props,
    }


def main() -> None:
    results = []
    for rec in ge.list_files():
        path = rec["path"]
        print(f"[*] {path}", flush=True)
        try:
            with ge.open_program(path) as prog:
                info = summarize(prog)
        except Exception:
            traceback.print_exc()
            info = {"error": traceback.format_exc(limit=3)}
        info["repo_path"] = path
        info["repo_version"] = rec["version"]
        results.append(info)
        f = info.get("functions", {})
        print(
            f"    {info.get('language_id')} {info.get('executable_format')} "
            f"funcs={f.get('total')} user_named={f.get('user_named')}",
            flush=True,
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1))
    print(f"[+] wrote {OUT}")


if __name__ == "__main__":
    main()
