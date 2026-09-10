"""Narrow, auditable normalization for Java/native decompiler comparison.

This deliberately does *not* parse or reformat C.  A content mismatch remains
a mismatch; the secondary layout predicate only classifies it for review.
"""

from __future__ import annotations

import re


def canonicalize(text: str) -> str:
    """Normalize line endings and trailing line whitespace, ending in one LF."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip(" \t") for line in lines]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


_LAYOUT = re.compile(r"\s+")


def layout_collapsed(text: str) -> str:
    """A diagnostic-only whitespace collapse; never use it to declare a match."""
    return _LAYOUT.sub(" ", canonicalize(text)).strip()
