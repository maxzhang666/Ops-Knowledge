from __future__ import annotations

import re


def extract_citations(text: str, chunk_count: int) -> list[int]:
    """Extract valid [N] citation references from text.

    Returns a sorted list of unique valid citation numbers
    (1-based, within chunk_count range).
    """
    if chunk_count <= 0:
        return []

    pattern = re.compile(r"\[(\d+)\]")
    matches = pattern.findall(text)

    valid: set[int] = set()
    for m in matches:
        num = int(m)
        if 1 <= num <= chunk_count:
            valid.add(num)

    return sorted(valid)
