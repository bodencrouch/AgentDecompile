"""Tests for language-specific readable source validators."""

from __future__ import annotations

import pytest

from agentdecompile_recovery.corpus.source_claims import (
    is_readable_source,
    is_real_c,
    is_recovered_source,
    shim_reason,
)
from agentdecompile_recovery.languages.registry import SourceLanguage
from agentdecompile_recovery.languages.validators import (
    is_readable_high_level_source,
    shim_reason_for,
)

pytestmark = pytest.mark.unit

VALID_C = "int add(int x) { return x + 1; }\n"
SHIM_C = "void copied(void) { __asm { nop } }\n"
SYMBOL_ALIAS_C = (
    'extern float *g_fFPS_ptr __asm__("PTR_g_fFPS");\n'
    "int f(void) { return 1; }\n"
)

VALID_RUST = "pub fn add_one(x: i32) -> i32 {\n    x + 1\n}\n"
ASM_RUST = "pub fn shim() {\n    unsafe { asm!(\"nop\"); }\n}\n"
GLOBAL_ASM_RUST = "core::arch::global_asm!(\".byte 0x90\");\n"
NAKED_RUST = "#[naked]\npub unsafe extern \"C\" fn f() {}\n"


def test_c_shim_detection() -> None:
    assert is_real_c(VALID_C)
    assert not is_real_c(SHIM_C)
    assert not is_real_c("__declspec(naked) void f(void) {}")
    assert not is_real_c("ASM_NAKED void f(void) {}\n")
    assert is_real_c(SYMBOL_ALIAS_C)
    assert shim_reason("void f(void) { _emit 0x90; }") == "_emit"
    assert is_readable_high_level_source(VALID_C, SourceLanguage.C)
    assert not is_readable_high_level_source(SHIM_C, SourceLanguage.C)
    assert is_readable_source(VALID_C, "c")
    assert not is_recovered_source(SHIM_C)
    assert shim_reason_for(SHIM_C, SourceLanguage.CXX) is not None


def test_rust_asm_rejection() -> None:
    assert not is_readable_high_level_source(ASM_RUST, SourceLanguage.RUST)
    assert shim_reason_for(ASM_RUST, SourceLanguage.RUST) == "asm!("
    assert not is_readable_high_level_source(GLOBAL_ASM_RUST, SourceLanguage.RUST)
    assert "core::arch::" in (shim_reason_for(GLOBAL_ASM_RUST, SourceLanguage.RUST) or "")
    assert not is_readable_high_level_source(NAKED_RUST, SourceLanguage.RUST)
    assert not is_recovered_source(ASM_RUST, SourceLanguage.RUST)


def test_valid_rust_fn_ok() -> None:
    assert is_readable_high_level_source(VALID_RUST, SourceLanguage.RUST)
    assert is_readable_source(VALID_RUST, "rust")
    assert is_recovered_source(VALID_RUST, SourceLanguage.RUST)
    assert shim_reason_for(VALID_RUST, SourceLanguage.RUST) is None
