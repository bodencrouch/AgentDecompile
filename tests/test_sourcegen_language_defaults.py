from __future__ import annotations

import pytest

from agentdecompile_recovery.languages.sourcegen_defaults import generator_task_fields

pytestmark = pytest.mark.unit


def test_generator_task_fields_c() -> None:
    fields = generator_task_fields("c")
    assert fields == {
        "extension": "c",
        "sourceLanguage": "c",
        "sourceQuality": "high-level-c",
    }


def test_generator_task_fields_cxx() -> None:
    fields = generator_task_fields("cxx")
    assert fields == {
        "extension": "cpp",
        "sourceLanguage": "c++",
        "sourceQuality": "high-level-c",
    }


def test_generator_task_fields_rust() -> None:
    fields = generator_task_fields("rust")
    assert fields == {
        "extension": "rs",
        "sourceLanguage": "rust",
        "sourceQuality": "high-level-rust",
    }
