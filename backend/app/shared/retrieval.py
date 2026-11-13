"""Cross-slice retrieval constants for the conversation-history flat index.

The knowledge search service and the agent history indexer must agree on the
window size, recall depth, and fusion constant. Keeping them here avoids a
knowledge-to-agent module dependency while leaving the source of truth in one
place.
"""

HISTORY_WINDOW_CHARS = 256
HISTORY_WINDOW_OVERLAP_CHARS = 32
HISTORY_WINDOW_STRIDE_CHARS = HISTORY_WINDOW_CHARS - HISTORY_WINDOW_OVERLAP_CHARS

HISTORY_VECTOR_RECALL_LIMIT = 128
HISTORY_RESULT_LIMIT = 15
HISTORY_RRF_K = 60.0
# A final relevance floor for the history lane. BM25-positive hits always pass;
# otherwise the cosine score must clear this baseline. Without it, an unrelated
# query still fills all 15 slots with short transcript fragments.
HISTORY_MIN_VECTOR_SIMILARITY = 0.4
# Ultra-short acknowledgements ("OK", "1", "~") have a high cosine baseline in
# some embedding models. A vector-only match must also carry at least this much
# text; a BM25-positive match is not length-filtered.
HISTORY_MIN_VECTOR_CONTENT_CHARS = 8


__all__ = [
    "HISTORY_MIN_VECTOR_CONTENT_CHARS",
    "HISTORY_MIN_VECTOR_SIMILARITY",
    "HISTORY_RESULT_LIMIT",
    "HISTORY_RRF_K",
    "HISTORY_VECTOR_RECALL_LIMIT",
    "HISTORY_WINDOW_CHARS",
    "HISTORY_WINDOW_OVERLAP_CHARS",
    "HISTORY_WINDOW_STRIDE_CHARS",
]
