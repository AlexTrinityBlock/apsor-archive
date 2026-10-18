"""Language-neutral text normalization and n-gram generation.

The index uses overlapping CJK bigrams, Latin words, and optional Latin
character trigrams. No tokenizer model or external service is required, which
keeps ingestion deterministic and works for mixed-language content.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_PATTERN = re.compile(r"[a-z0-9]+")
_CJK_RUN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_LATIN_RUN_PATTERN = re.compile(r"[a-z0-9]+(?:[._+-][a-z0-9]+)*")

ENGLISH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "his",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "she",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "with",
        "you",
        "your",
    }
)


def normalize_text(value: str) -> str:
    """Normalize compatibility forms and collapse punctuation to spaces."""
    normalized = unicodedata.normalize("NFKC", value).lower()
    characters: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace() or category[0] in {"L", "N", "M"}:
            characters.append(character)
        else:
            characters.append(" ")
    return " ".join("".join(characters).split())


def _cjk_bigrams(run: str) -> Iterable[str]:
    if len(run) == 1:
        yield run
        return
    for index in range(len(run) - 1):
        yield run[index : index + 2]


def _latin_trigrams(word: str) -> Iterable[str]:
    if len(word) < 5:
        return
    for index in range(len(word) - 2):
        yield word[index : index + 3]


def iter_index_terms(value: str) -> Iterable[str]:
    """Yield terms used by BM25 and exact text matching."""
    normalized = normalize_text(value)
    for run in _CJK_RUN_PATTERN.findall(normalized):
        yield from _cjk_bigrams(run)
    for word in _LATIN_RUN_PATTERN.findall(normalized):
        if len(word) > 1 or word.isdigit():
            yield word


def iter_embedding_terms(value: str) -> Iterable[str]:
    """Yield a slightly richer term set for signed feature hashing."""
    yield from iter_index_terms(value)
    normalized = normalize_text(value)
    for word in _LATIN_RUN_PATTERN.findall(normalized):
        yield from _latin_trigrams(word)


def term_frequencies(value: str) -> Counter[str]:
    """Return unique index terms with their frequency."""
    return Counter(iter_index_terms(value))


def count_terms(value: str) -> int:
    """Count index terms; used as the BM25 document length."""
    return sum(term_frequencies(value).values())


def unique_query_terms(value: str) -> list[str]:
    """Return ordered, de-duplicated query terms."""
    seen: set[str] = set()
    terms: list[str] = []
    for term in iter_index_terms(value):
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def fallback_unigrams(terms: Iterable[str]) -> list[str]:
    """Return single-character CJK terms for a fuzzy second pass."""
    unigrams: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if len(term) == 1 and _CJK_PATTERN.fullmatch(term) and term not in seen:
            seen.add(term)
            unigrams.append(term)
        elif len(term) == 2 and _CJK_PATTERN.fullmatch(term):
            for character in term:
                if character not in seen:
                    seen.add(character)
                    unigrams.append(character)
    return unigrams


def extract_themes(texts: Iterable[str], *, top_n: int = 3) -> list[str]:
    """Extract frequent meaningful terms for a summary's theme list."""
    counts: Counter[str] = Counter()
    for text in texts:
        for term in iter_index_terms(text):
            if term in ENGLISH_STOPWORDS:
                continue
            if len(term) == 1 and _LATIN_PATTERN.fullmatch(term):
                continue
            counts[term] += 1
    return [term for term, _count in counts.most_common(top_n)]
