from __future__ import annotations

from app.knowledge.chunking.base import ChunkingStrategy
from app.knowledge.chunking.composite import CompositeStrategy
from app.knowledge.chunking.registry import get_strategy

PRESETS: dict[str, dict] = {
    "general": {
        "strategy": "recursive",
        "params": {"chunk_size": 500, "chunk_overlap": 50},
    },
    "qa": {
        "strategy": "qa",
        "params": {"chunk_size": 800, "chunk_overlap": 0},
    },
    "book": {
        "strategy": "composite",
        "primary": "recursive",
        "params": {"chunk_size": 1000, "chunk_overlap": 100},
    },
    "technical": {
        "strategy": "markdown",
        "secondary": "code",
        "params": {"chunk_size": 600, "chunk_overlap": 50},
    },
    "paper": {
        "strategy": "pdf_layout",
        "secondary": "composite",
        "params": {"chunk_size": 800, "chunk_overlap": 80},
    },
    "custom": {
        "strategy": "recursive",
        "params": {"chunk_size": 500, "chunk_overlap": 50},
    },
}


def get_strategy_for_preset(name: str) -> tuple[ChunkingStrategy, dict]:
    preset = PRESETS.get(name)
    if preset is None:
        raise ValueError(f"Unknown preset: {name}")

    params = dict(preset["params"])
    strategy_name = preset["strategy"]

    if strategy_name == "composite" and "primary" in preset:
        primary = get_strategy(preset["primary"])
        secondary = get_strategy("recursive")
        return CompositeStrategy(primary, secondary), params

    primary = get_strategy(strategy_name)

    if "secondary" in preset:
        sec_name = preset["secondary"]
        if sec_name == "composite":
            secondary = CompositeStrategy(get_strategy("recursive"), get_strategy("sentence"))
        else:
            secondary = get_strategy(sec_name)
        return CompositeStrategy(primary, secondary), params

    return primary, params
