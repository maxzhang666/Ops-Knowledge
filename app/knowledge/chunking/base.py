from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChunkResult:
    content: str
    level: int = 0  # 0-3: document → section → subsection → paragraph
    position: int = 0
    metadata: dict = field(default_factory=dict)


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        ...

    def get_config_schema(self) -> dict:
        return {
            "chunk_size": {"type": "int", "default": 500, "min": 50, "max": 8000},
            "chunk_overlap": {"type": "int", "default": 50, "min": 0, "max": 500},
        }
