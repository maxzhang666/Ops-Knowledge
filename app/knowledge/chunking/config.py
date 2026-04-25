"""Chunking config typed accessor (P24.M1).

``chunking_config`` is a JSONB blob per KB — schema-free for flexibility.
To keep the known keys coherent across ingestion / UI / validation, this
module exposes a single dataclass that parses & defaults the recognized
fields. Unknown keys are preserved (``raw``) but not type-checked.

Recognized keys:
  * preset                  — str, default "general"
  * chunk_size              — int, overrides preset default
  * chunk_overlap           — int, overrides preset default
  * delimiter               — str, custom separator prepended to RecursiveCharacter's SEPARATORS
  * auto_keywords           — bool (P24), emit 3-5 LLM keywords per chunk into metadata
  * auto_questions          — bool (P24), emit 1-2 LLM questions per chunk into metadata
  * use_raptor              — bool (P24), build hierarchical summary tree via RAPTOR
  * raptor_max_levels       — int (default 3), upper bound on RAPTOR recursion depth
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkingConfig:
    preset: str = "general"
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    delimiter: str | None = None

    auto_keywords: bool = False
    auto_questions: bool = False

    use_raptor: bool = False
    raptor_max_levels: int = 3

    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, cfg: dict | None) -> "ChunkingConfig":
        cfg = cfg or {}
        return cls(
            preset=str(cfg.get("preset", "general")),
            chunk_size=_opt_int(cfg.get("chunk_size")),
            chunk_overlap=_opt_int(cfg.get("chunk_overlap")),
            delimiter=cfg.get("delimiter") or None,
            auto_keywords=bool(cfg.get("auto_keywords", False)),
            auto_questions=bool(cfg.get("auto_questions", False)),
            use_raptor=bool(cfg.get("use_raptor", False)),
            raptor_max_levels=max(1, int(cfg.get("raptor_max_levels", 3))),
            raw=cfg,
        )

    @property
    def needs_enrichment(self) -> bool:
        """是否需要调 LLM 做 chunk metadata 丰富。"""
        return self.auto_keywords or self.auto_questions


def _opt_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
