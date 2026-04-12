from __future__ import annotations

from app.knowledge.chunking.base import ChunkingStrategy
from app.knowledge.chunking.code import CodeAwareStrategy
from app.knowledge.chunking.composite import CompositeStrategy
from app.knowledge.chunking.markdown import MarkdownStrategy
from app.knowledge.chunking.qa import QAPairStrategy
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy
from app.knowledge.chunking.sentence import SentenceStrategy
from app.knowledge.chunking.table import TableAwareStrategy

_STRATEGIES: dict[str, type[ChunkingStrategy]] = {
    "recursive": RecursiveCharacterStrategy,
    "markdown": MarkdownStrategy,
    "sentence": SentenceStrategy,
    "table": TableAwareStrategy,
    "code": CodeAwareStrategy,
    "qa": QAPairStrategy,
}


def get_strategy(name: str) -> ChunkingStrategy:
    cls = _STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}")
    return cls()


def get_composite(primary: str, secondary: str) -> CompositeStrategy:
    return CompositeStrategy(get_strategy(primary), get_strategy(secondary))


def list_strategies() -> list[str]:
    return list(_STRATEGIES.keys())
