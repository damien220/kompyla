"""Two-layer deduplication: exact (SHA-256) and near-duplicate (MinHash LSH)."""

from __future__ import annotations

import hashlib
import re

from datasketch import MinHash, MinHashLSH


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for tok in _tokens(text):
        m.update(tok.encode("utf-8"))
    return m


class Deduplicator:
    """Detects exact and near-duplicate text content.

    Exact: SHA-256 of whitespace-normalized content.
    Near: MinHash LSH with configurable Jaccard threshold (default 0.85).
    """

    def __init__(self, threshold: float = 0.85, num_perm: int = 128):
        self._exact: set[str] = set()
        self._lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._num_perm = num_perm
        self._counter = 0

    def register_hash(self, content_hash: str) -> None:
        """Seed the exact-match set from existing index entries."""
        if content_hash:
            self._exact.add(content_hash)

    def is_duplicate(self, text: str, exact_hash: str | None = None) -> bool:
        h = exact_hash or _content_hash(text)
        if h in self._exact:
            return True
        m = _minhash(text, num_perm=self._num_perm)
        return bool(self._lsh.query(m))

    def add(self, text: str, exact_hash: str | None = None) -> None:
        h = exact_hash or _content_hash(text)
        self._exact.add(h)
        self._counter += 1
        try:
            self._lsh.insert(f"doc-{self._counter}-{h[:8]}", _minhash(text, num_perm=self._num_perm))
        except ValueError:
            # Key collision — skip; the exact-hash set already covers it.
            pass
