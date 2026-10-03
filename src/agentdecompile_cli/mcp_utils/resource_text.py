"""Shared normalization for MCP resources/read text payloads."""

from __future__ import annotations

from typing import Any


def resource_texts(result: Any) -> list[Any]:
    """Return text values from accepted MCP resource result shapes, in order.

    Supports remote JSON-RPC dictionaries, local backend dictionaries, and SDK
    objects exposing ``contents``. Raw bytes are decoded as UTF-8 with
    replacement, including empty bytes (which produce an empty string).
    Unknown shapes and non-text content are ignored.
    """
    if isinstance(result, dict):
        raw = result.get("raw")
        if isinstance(raw, bytes):
            return [raw.decode("utf-8", errors="replace")]
        if isinstance(raw, str) and raw:
            return [raw]
        contents: Any = result.get("contents")
    else:
        contents = getattr(result, "contents", None)
    texts: list[Any] = []
    for content in contents or []:
        text = content.get("text") if isinstance(content, dict) else getattr(content, "text", None)
        if text:
            texts.append(text)
    return texts
