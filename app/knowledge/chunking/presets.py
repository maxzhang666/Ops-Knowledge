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
        "strategy": "markdown",
        "secondary": "sentence",
        "params": {"chunk_size": 1000, "chunk_overlap": 100},
    },
    "technical": {
        "strategy": "code",
        "secondary": "recursive",
        "params": {"chunk_size": 600, "chunk_overlap": 50},
    },
    "paper": {
        "strategy": "markdown",
        "secondary": "recursive",
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

    primary = get_strategy(preset["strategy"])
    params = dict(preset["params"])

    if "secondary" in preset:
        secondary = get_strategy(preset["secondary"])
        return CompositeStrategy(primary, secondary), params

    return primary, params
