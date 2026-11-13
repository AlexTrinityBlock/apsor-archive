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


__all__ = [
    "HISTORY_RESULT_LIMIT",
    "HISTORY_RRF_K",
    "HISTORY_VECTOR_RECALL_LIMIT",
    "HISTORY_WINDOW_CHARS",
    "HISTORY_WINDOW_OVERLAP_CHARS",
    "HISTORY_WINDOW_STRIDE_CHARS",
]
