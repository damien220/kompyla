"""HTML → PDF via WeasyPrint (optional dep, install with: pip install kompyla[pdf])."""

from __future__ import annotations

from pathlib import Path


class PDFExportNotAvailable(RuntimeError):
    pass


def html_to_pdf(html: str, out_path: Path) -> Path:
    """Render an HTML document to PDF.

    Raises PDFExportNotAvailable if weasyprint is not installed.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError as exc:
        raise PDFExportNotAvailable(
            "PDF export requires WeasyPrint. Install it with:\n"
            "  pip install kompyla[pdf]\n"
            "or open the generated HTML and print to PDF from your browser."
        ) from exc

    HTML(string=html).write_pdf(str(out_path))
    return out_path
