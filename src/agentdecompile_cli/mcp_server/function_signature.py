"""Apply a function prototype with the Ghidra API that actually exists.

Ghidra's Function (FunctionDB) has no setSignature(). The GUI path is
FunctionSignatureParser (text -> FunctionDefinitionDataType) followed by
ApplyFunctionSignatureCmd, which calls Function.updateFunction(). Both are in
Ghidra 12.1's Base module (ghidra.app.util.parser / ghidra.app.cmd.function).

The parser does not understand calling-convention keywords, yet
str(Function.getSignature()) includes one ("int __stdcall f(int a)"), so a
known convention name before the function name is lifted out of the text and
set on the parsed definition instead.

Callers run apply_function_signature inside a program transaction; the
command does not open one itself.
"""

from __future__ import annotations

import logging

from typing import Any

logger = logging.getLogger(__name__)

# Function.UNKNOWN_CALLING_CONVENTION_STRING / DEFAULT_CALLING_CONVENTION_STRING
_UNKNOWN_CONVENTION = "unknown"
_DEFAULT_CONVENTION = "default"


def _calling_convention_names(program: Any) -> set[str]:
    names: set[str] = {_UNKNOWN_CONVENTION, _DEFAULT_CONVENTION}
    dtm = program.getDataTypeManager()
    for getter in ("getKnownCallingConventionNames", "getDefinedCallingConventionNames"):
        try:
            names.update(str(name) for name in getattr(dtm, getter)())
        except Exception as exc:  # older/partial managers: stripping just finds fewer names
            logger.debug("calling convention names via %s unavailable: %s", getter, exc)
    return names


def split_noreturn(signature_text: str) -> tuple[str, bool]:
    """Remove a leading ``noreturn`` token (FunctionSignature.NORETURN_DISPLAY_STRING).

    ``str(func.getSignature())`` on a non-returning function renders e.g.
    ``noreturn void __cdecl exit(int code)`` (FunctionSignature.getPrototypeString,
    FunctionDefinitionDataType.getPrototypeString): the noreturn marker comes first,
    ahead of the return type and calling convention. FunctionSignatureParser has no
    concept of it, so it must be stripped before parsing and reapplied afterwards via
    FunctionDefinitionDataType.setNoReturn(true).

    Returns (text without the token, True if the token was present).
    """
    tokens = signature_text.split(None, 1)
    if tokens and tokens[0] == "noreturn" and len(tokens) > 1:
        return tokens[1], True
    return signature_text, False


def split_calling_convention(signature_text: str, convention_names: set[str]) -> tuple[str, str | None]:
    """Remove a calling-convention token between the return type and the name.

    Returns (text without the token, convention name or None).
    """
    paren = signature_text.find("(")
    if paren < 0:
        return signature_text, None
    head, tail = signature_text[:paren], signature_text[paren:]
    tokens = head.split()
    # The last token is the function name; conventions sit before it.
    convention: str | None = None
    kept: list[str] = []
    for index, token in enumerate(tokens):
        if index < len(tokens) - 1 and token in convention_names and convention is None:
            convention = token
            continue
        kept.append(token)
    if convention is None:
        return signature_text, None
    return " ".join(kept) + tail, convention


def apply_function_signature(program: Any, func: Any, signature: Any, *, rename: bool) -> None:
    """Apply ``signature`` (prototype text or a FunctionSignature) to ``func``.

    ``rename`` renames the function to the signature's name; otherwise the
    current name is kept. Raises ValueError when Ghidra rejects the signature.
    """
    from ghidra.app.cmd.function import (  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
        ApplyFunctionSignatureCmd,
        FunctionRenameOption,
    )
    from ghidra.program.model.symbol import SourceType  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
    from ghidra.util.task import TaskMonitor  # pyright: ignore[reportMissingImports, reportMissingModuleSource]

    preserve_convention = False
    if isinstance(signature, str):
        from ghidra.app.util.parser import FunctionSignatureParser  # pyright: ignore[reportMissingImports, reportMissingModuleSource]

        text, no_return = split_noreturn(signature.strip().rstrip(";").strip())
        text, convention = split_calling_convention(text, _calling_convention_names(program))
        parser = FunctionSignatureParser(program.getDataTypeManager(), None)
        definition = parser.parse(func.getSignature(), text)
        if convention is not None and convention != _UNKNOWN_CONVENTION:
            definition.setCallingConvention(convention)
        else:
            # No convention in the text: keep the function's current one.
            preserve_convention = True
        if no_return:
            definition.setNoReturn(True)
        signature = definition

    rename_option = FunctionRenameOption.RENAME if rename else FunctionRenameOption.NO_CHANGE
    cmd = ApplyFunctionSignatureCmd(func.getEntryPoint(), signature, SourceType.USER_DEFINED, preserve_convention, rename_option)
    if not cmd.applyTo(program, TaskMonitor.DUMMY):
        raise ValueError(f"Ghidra rejected the signature for {func.getName()}: {cmd.getStatusMsg() or 'no reason given'}")
