import re

import structlog

from app.knowledge.chunking.base import ChunkingStrategy, ChunkResult
from app.knowledge.chunking.recursive import RecursiveCharacterStrategy

logger = structlog.get_logger(__name__)


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

# M6.6 — heading-only 判定阈值：body 去掉空白后 < 30 字符即视为
# heading-only。用字符数而非 token 数：中文不靠空格分词、token-based
# 阈值会把 30 字符长的中文段错判为 heading-only。
# M6.7 — 阈值默认 30，可被 config['heading_only_min_chars'] 覆盖；
# 设 0 关闭合并（恢复 M6.6 之前行为）。
_HEADING_ONLY_MIN_CHARS = 30


def _is_heading_only(body: str, threshold: int) -> bool:
    """Body 文本是否短到不值得作为独立 chunk emit。"""
    if threshold <= 0:
        return False
    return len(body.strip()) < threshold


class MarkdownStrategy(ChunkingStrategy):
    def chunk(self, text: str, config: dict) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        chunk_size = config.get("chunk_size", 500)
        overlap = config.get("chunk_overlap", 50)
        heading_only_min_chars = int(
            config.get("heading_only_min_chars", _HEADING_ONLY_MIN_CHARS) or 0
        )
        sections = self._split_by_headings(text)

        fallback = RecursiveCharacterStrategy()
        results: list[ChunkResult] = []
        pos = 0
        # M6.6 — 暂存连续的 heading-only section（一直累积到遇到正文 section）
        # 元素：(heading, level, body) —— M6.7 起 body 也保留，避免短 body 被吞
        pending: list[tuple[str, int, str]] = []
        merged_count = 0  # 统计本次 chunking 触发了多少次合并

        def _flush_pending_to_parts() -> list[str]:
            """把 pending 累积的 heading + 短 body 展开成顺序拼接的 parts。"""
            out: list[str] = []
            for h, _, b in pending:
                out.append(h)
                b_strip = b.strip()
                if b_strip:
                    out.append(b_strip)
            return out

        for heading, level, body in sections:
            # 没有 heading（preamble）但 body 短：当孤立片段处理，单独 emit 或丢弃
            # 有 heading 且 body heading-only：暂存（含 body 一并保留），不 emit
            if heading and _is_heading_only(body, heading_only_min_chars):
                pending.append((heading, level, body))
                merged_count += 1
                continue

            # 这个 section 有实质正文 → 拼上 pending 累积的 heading + 短 body 路径
            prefix_parts = _flush_pending_to_parts()
            if heading:
                prefix_parts.append(heading)
            prefix_block = "\n\n".join(prefix_parts)

            content = (
                f"{prefix_block}\n\n{body}".strip() if prefix_block else body.strip()
            )
            if not content:
                pending = []
                continue

            # metadata.heading 取最具体的（当前 heading 优先，否则 pending 最后一个）
            meta_heading = heading or (pending[-1][0] if pending else "")
            # level 取最早 pending 的（外层结构）；无 pending 时取当前 level
            actual_level = pending[0][1] if pending else level

            if len(content) <= chunk_size:
                meta = {"heading": meta_heading} if meta_heading else {}
                results.append(ChunkResult(
                    content=content, level=actual_level, position=pos, metadata=meta,
                ))
                pos += 1
            else:
                # 长内容 fallback：仅给第一个 sub-chunk 拼前缀块，避免每段都重复
                sub_chunks = fallback.chunk(
                    body, {"chunk_size": chunk_size, "chunk_overlap": overlap},
                )
                for i, sc in enumerate(sub_chunks):
                    meta = {"heading": meta_heading} if meta_heading else {}
                    if i == 0 and prefix_block:
                        sc.content = f"{prefix_block}\n\n{sc.content}"
                    sc.level = actual_level
                    sc.position = pos
                    sc.metadata = meta
                    results.append(sc)
                    pos += 1

            pending = []  # 已被消费

        # 文档末尾仍有 pending（整页全是 heading-only 的目录页 / 末尾短段）
        # → emit 一个汇总 chunk 保留所有 heading + 短 body，避免内容丢失
        if pending:
            content = "\n\n".join(_flush_pending_to_parts())
            meta = {"heading": pending[-1][0]}
            results.append(ChunkResult(
                content=content,
                level=pending[0][1],
                position=pos,
                metadata=meta,
            ))

        if merged_count:
            logger.info(
                "markdown_heading_only_merged",
                merged=merged_count,
                total_sections=len(sections),
                final_chunks=len(results),
            )

        return results

    @staticmethod
    def _split_by_headings(text: str) -> list[tuple[str, int, str]]:
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return [("", 0, text)]

        sections: list[tuple[str, int, str]] = []
        # Text before first heading
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(("", 0, preamble))

        for i, m in enumerate(matches):
            level = len(m.group(1))  # 1-3
            heading = m.group(0)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append((heading, level, body))

        return sections
