from __future__ import annotations

import re

_SENTENCE_RE = re.compile(r"[.!?。！？]+")

# Weights
W_TOKEN = 0.4
W_DENSITY = 0.3
W_COHERENCE = 0.3


def score_chunk(content: str) -> float:
    if not content or not content.strip():
        return 0.0

    tokens = content.split()
    token_count = len(tokens)

    if token_count < 3:
        return round(token_count * 0.1, 4)

    # Token count score: penalize <30 or >1000
    if token_count < 5:
        token_score = 0.1
    elif token_count < 30:
        token_score = token_count / 30 * 0.6
    elif token_count <= 1000:
        token_score = 1.0
    else:
        token_score = max(0.3, 1.0 - (token_count - 1000) / 2000)

    # Density: unique tokens / total tokens
    unique_count = len(set(t.lower() for t in tokens))
    density = unique_count / token_count if token_count > 0 else 0.0
    density_score = min(density / 0.7, 1.0)

    # Coherence: based on sentence count relative to token count
    sentences = [s.strip() for s in _SENTENCE_RE.split(content) if s.strip()]
    sentence_count = max(len(sentences), 1)
    avg_sentence_len = token_count / sentence_count
    if avg_sentence_len < 3:
        coherence_score = 0.2
    elif avg_sentence_len < 8:
        coherence_score = avg_sentence_len / 8 * 0.7
    elif avg_sentence_len <= 40:
        coherence_score = 1.0
    else:
        coherence_score = max(0.4, 1.0 - (avg_sentence_len - 40) / 60)

    return round(
        W_TOKEN * token_score + W_DENSITY * density_score + W_COHERENCE * coherence_score,
        4,
    )
