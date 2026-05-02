from pathlib import Path

from ..storage.layout import KBLayout
from ..storage.index import MetaIndex

# Formats the compiler can process as plain text
_TEXT_SUFFIXES = {".md", ".txt", ".rst"}


def ingest_raw(layout: KBLayout, index: MetaIndex) -> list[Path]:
    """Register every untracked text file in raw/ into the metadata index.

    Returns the full list of text files found (including already-tracked ones).
    """
    found: list[Path] = []
    for path in sorted(layout.raw.rglob("*")):
        if path.is_file() and path.suffix in _TEXT_SUFFIXES:
            index.upsert_raw_doc(path)
            found.append(path)
    return found
