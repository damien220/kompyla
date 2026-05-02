import pytest

from kompyla.retriever.youtube import _extract_video_id, _transcript_to_markdown


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
])
def test_extract_video_id(url, expected):
    assert _extract_video_id(url) == expected


def test_extract_video_id_invalid():
    with pytest.raises(ValueError):
        _extract_video_id("https://example.com/not-youtube")


def test_transcript_paragraph_grouping():
    segments = [
        {"start": 0.0,  "text": "Hello"},
        {"start": 5.0,  "text": "world"},
        {"start": 65.0, "text": "Second"},
        {"start": 70.0, "text": "paragraph"},
    ]
    md = _transcript_to_markdown("abc", "https://youtu.be/abc", segments)
    assert "Hello world" in md
    assert "Second paragraph" in md
    # Two distinct paragraphs separated by blank lines
    transcript_section = md.split("## Transcript", 1)[1]
    paragraphs = [p.strip() for p in transcript_section.split("\n\n") if p.strip()]
    assert len(paragraphs) == 2
