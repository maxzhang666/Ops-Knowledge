import re

from bs4 import BeautifulSoup, NavigableString, Tag

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 3, "h5": 3, "h6": 3}
_BLOCK_TAGS = {
    "p", "table", "ul", "ol", "div", "section", "article",
    "blockquote", "pre", "dl", "figure", "details",
}
_WHITESPACE_RE = re.compile(r"\s+")


class HTMLStructureStrategy(ChunkingStrategy):
    """Split HTML by semantic tag boundaries (headings, paragraphs, tables, lists)."""

    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        chunk_size = config.get("chunk_size", 500)
        overlap = config.get("chunk_overlap", 50)

        soup = BeautifulSoup(text, "html.parser")
        sections = self._extract_sections(soup)

        fallback = RecursiveCharacterStrategy()
        results: list[ChunkResult] = []
        pos = 0

        for heading, level, body in sections:
            content = f"{heading}\n\n{body}".strip() if heading else body.strip()
            if not content:
                continue
            if len(content) <= chunk_size:
                meta = {"heading": heading} if heading else {}
                results.append(ChunkResult(
                    content=content, level=level, position=pos, metadata=meta,
                ))
                pos += 1
            else:
                sub = fallback.chunk(body, {"chunk_size": chunk_size, "chunk_overlap": overlap})
                for i, sc in enumerate(sub):
                    meta = {"heading": heading} if heading else {}
                    if i == 0 and heading:
                        sc.content = f"{heading}\n\n{sc.content}"
                    sc.level = level
                    sc.position = pos
                    sc.metadata = meta
                    results.append(sc)
                    pos += 1

        return results

    def _extract_sections(self, soup: BeautifulSoup) -> list[tuple[str, int, str]]:
        """Walk top-level elements and group by heading hierarchy."""
        sections: list[tuple[str, int, str]] = []
        current_heading = ""
        current_level = 0
        current_body: list[str] = []

        for el in self._iter_top_blocks(soup):
            if isinstance(el, Tag) and el.name in _HEADING_TAGS:
                # Flush previous section
                body_text = "\n\n".join(current_body)
                if current_heading or body_text.strip():
                    sections.append((current_heading, current_level, body_text))
                current_heading = self._get_text(el)
                current_level = _HEADING_TAGS[el.name]
                current_body = []
            else:
                block_text = self._render_block(el)
                if block_text:
                    current_body.append(block_text)

        # Flush last section
        body_text = "\n\n".join(current_body)
        if current_heading or body_text.strip():
            sections.append((current_heading, current_level, body_text))

        return sections if sections else [("", 0, self._get_text(soup))]

    def _iter_top_blocks(self, soup: BeautifulSoup):
        """Yield top-level block elements, unwrapping body/html wrappers."""
        root = soup
        if soup.body:
            root = soup.body
        for child in root.children:
            if isinstance(child, NavigableString):
                text = child.strip()
                if text:
                    yield child
            elif isinstance(child, Tag):
                yield child

    def _render_block(self, el) -> str:
        if isinstance(el, NavigableString):
            return str(el).strip()
        if not isinstance(el, Tag):
            return ""
        if el.name == "table":
            return self._render_table(el)
        if el.name in ("ul", "ol"):
            return self._render_list(el)
        return self._get_text(el)

    @staticmethod
    def _render_table(table: Tag) -> str:
        rows: list[str] = []
        for tr in table.find_all("tr"):
            cells = [_WHITESPACE_RE.sub(" ", c.get_text()).strip() for c in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        return "\n".join(rows)

    @staticmethod
    def _render_list(lst: Tag) -> str:
        items: list[str] = []
        for li in lst.find_all("li", recursive=False):
            text = _WHITESPACE_RE.sub(" ", li.get_text()).strip()
            items.append(f"- {text}")
        return "\n".join(items)

    @staticmethod
    def _get_text(el) -> str:
        raw = el.get_text(separator=" ") if isinstance(el, Tag) else str(el)
        return _WHITESPACE_RE.sub(" ", raw).strip()
