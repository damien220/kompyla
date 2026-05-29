"""YouTube transcript connector — URL fetching only (no search)."""

from __future__ import annotations

import re
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from .base import FetchedDoc, SourceConnector

_VIDEO_ID_PATTERNS = [
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
]


def _extract_video_id(url: str) -> str:
    for pattern in _VIDEO_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def _transcript_to_markdown(video_id: str, url: str, segments) -> str:
    """Group transcript segments into ~60-second paragraphs."""
    lines = [
        "---",
        "source_type: youtube",
        f"video_id: {video_id}",
        f"url: {url}",
        "---",
        "",
        f"# YouTube Transcript — {video_id}",
        "",
        f"**Source:** {url}",
        "",
        "## Transcript",
        "",
    ]

    paragraph: list[str] = []
    paragraph_start = 0.0
    for seg in segments:
        # v1.x returns FetchedTranscriptSnippet dataclasses; v0.x returned dicts
        start = seg.start if hasattr(seg, "start") else seg["start"]
        text = seg.text if hasattr(seg, "text") else seg["text"]
        if start - paragraph_start > 60 and paragraph:
            lines.append(" ".join(paragraph))
            lines.append("")
            paragraph = []
            paragraph_start = start
        paragraph.append(text.strip())

    if paragraph:
        lines.append(" ".join(paragraph))
        lines.append("")

    return "\n".join(lines)


def _fetch_transcript(url: str, languages: list[str] | None = None) -> tuple[str, str, list[dict]]:
    """Return (video_id, markdown_content, raw_segments)."""
    video_id = _extract_video_id(url)
    langs = languages or ["en"]

    transcript_list = YouTubeTranscriptApi().list(video_id)
    try:
        transcript = transcript_list.find_transcript(langs)
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(langs)

    fetched = transcript.fetch()
    # v1.x: FetchedTranscript is iterable; to_raw_data() gives list-of-dicts for callers
    segments = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
    return video_id, _transcript_to_markdown(video_id, url, fetched), segments


def fetch_youtube(url: str, raw_dir: Path, languages: list[str] | None = None) -> Path:
    """Save a YouTube transcript to raw_dir as a markdown file. Returns the path."""
    video_id, content, _ = _fetch_transcript(url, languages)
    out = raw_dir / f"youtube_{video_id}.md"
    out.write_text(content, encoding="utf-8")
    return out


class YouTubeConnector(SourceConnector):
    """SourceConnector wrapper around YouTube transcript fetching.

    Search is unsupported (would need YouTube Data API key); URL fetch works.
    """

    name = "youtube"

    def __init__(self, languages: list[str] | None = None):
        self.languages = languages or ["en"]

    def fetch_url(self, url: str) -> FetchedDoc | None:
        try:
            video_id, content, _ = _fetch_transcript(url, self.languages)
        except (NoTranscriptFound, TranscriptsDisabled, ValueError):
            return None
        return FetchedDoc(
            title=f"YouTube Transcript — {video_id}",
            url=url,
            content=content,
            source_type=self.name,
            metadata={"video_id": video_id},
        )
