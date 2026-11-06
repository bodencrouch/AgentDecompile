"""Language-aware wording in craft_prompt output."""

from __future__ import annotations

import pytest

from agentdecompile_recovery.craft_prompt import (
    SamplingCFunction,
    craft_prompt,
    craft_prompt_rules,
    craft_prompt_task_line,
)
from agentdecompile_recovery.languages import SourceLanguage

pytestmark = pytest.mark.unit

_MINIMAL_KWARGS = dict(
    platform="win32",
    module_path="src/main.c",
    asm_name="target_fn",
    asm_code="ret",
    called_functions_declarations={},
    type_definitions=[],
)


class TestCraftPromptLanguages:
    def test_default_target_language_uses_cxx_wording(self):
        prompt = craft_prompt(**_MINIMAL_KWARGS, sampling=[])

        assert "readable C++" in prompt
        assert "high-level C++ only" in prompt
        assert "readable Rust" not in prompt

    def test_rust_target_language_uses_rust_wording_and_fence(self):
        sampling = [
            SamplingCFunction(
                name="helper",
                c_code="fn helper() -> i32 { 1 }",
                asm_code="mov eax, 1\nret",
                calls_target=False,
            )
        ]
        prompt = craft_prompt(**_MINIMAL_KWARGS, sampling=sampling, target_language=SourceLanguage.RUST)

        assert "readable Rust" in prompt
        assert "high-level Rust only" in prompt
        assert "```rust\nfn helper()" in prompt
        assert "```cpp" not in prompt

    def test_helper_functions_reflect_language_choice(self):
        cpp_task = craft_prompt_task_line(SourceLanguage.CXX, "Windows (32-bit)", "x86", "fn")
        rust_rules = craft_prompt_rules(SourceLanguage.RUST)

        assert "as readable C++" in cpp_task
        assert "high-level Rust only" in rust_rules
        assert "high-level C++ only" not in rust_rules
