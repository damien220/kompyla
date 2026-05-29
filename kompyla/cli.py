"""Kompyla CLI — kompyla <command> [options]"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import KompylaConfig, RetrievalConfig
from .llm import get_provider
from .schema.generator import generate_schema
from .schema.models import DomainSchema
from .storage.index import MetaIndex
from .storage.layout import KBLayout
from .compiler.ingest import ingest_raw
from .compiler.compile import compile_document
from .compiler.linker import rebuild_master_index

app = typer.Typer(
    name="kompyla",
    add_completion=False,
    help="Autonomous research agent — build and evolve a knowledge base.",
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_schema(layout: KBLayout) -> DomainSchema:
    return DomainSchema(**yaml.safe_load(layout.schema_file.read_text()))


def _require_kb(layout: KBLayout) -> None:
    if not layout.schema_file.exists():
        console.print(
            "[red]No knowledge base found here.[/red] "
            "Run [bold]kompyla init <domain>[/bold] first."
        )
        raise typer.Exit(1)


def _build_connectors(cfg: RetrievalConfig, only: list[str] | None = None):
    """Instantiate the source connectors selected in config (intersected with `only`)."""
    from .retriever import (
        WebSearchConnector, ArxivConnector, GitHubConnector,
        RSSConnector, YouTubeConnector,
    )

    requested = only or cfg.enabled_sources
    available: dict[str, object] = {
        "web":     WebSearchConnector(
                       serper_api_key=cfg.serper_api_key,
                       brave_api_key=cfg.brave_api_key,
                       exa_api_key=cfg.exa_api_key,
                       serpapi_api_key=cfg.serpapi_api_key,
                   ),
        "arxiv":   ArxivConnector(),
        "github":  GitHubConnector(token=cfg.github_token),
        "rss":     RSSConnector(feeds=cfg.rss_feeds),
        "youtube": YouTubeConnector(languages=cfg.youtube_languages),
    }
    return [available[name] for name in requested if name in available]


# ---------------------------------------------------------------------------
# Commands — Phase 1
# ---------------------------------------------------------------------------

@app.command()
def init(
    domain: str = typer.Argument(..., help="Research domain, e.g. 'electric vehicles'"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="KB root directory (default: ./<domain-slug>)"),
) -> None:
    """Scaffold a new knowledge base and generate its domain schema."""
    slug = domain.lower().replace(" ", "_")
    kb_path = path or Path.cwd() / slug
    layout = KBLayout(kb_path)
    layout.create()

    cfg = KompylaConfig.load()
    llm = get_provider(cfg.llm)

    console.print(f"Generating schema for [bold]{domain}[/bold] using [cyan]{llm.model_name}[/cyan]...")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as p:
        p.add_task("Calling LLM...")
        schema = generate_schema(domain, llm)

    layout.schema_file.write_text(
        yaml.dump(schema.model_dump(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    layout.kb_config.write_text(
        yaml.dump({"domain": domain}, allow_unicode=True),
        encoding="utf-8",
    )

    console.print(f"[green]KB initialised at[/green] {layout.root}")
    console.print(f"  [dim]page types:[/dim]        {len(schema.page_types)}")
    console.print(f"  [dim]entity categories:[/dim] {len(schema.entity_categories)}")
    console.print(f"  [dim]seed queries:[/dim]      {len(schema.seed_queries)}")
    console.print(
        f"\nDrop sources into [bold]{layout.raw}/[/bold] then run [bold]kompyla compile[/bold], "
        f"\nor run [bold]kompyla search[/bold] to fetch sources automatically."
    )


@app.command()
def compile(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k", help="KB root (default: current directory)"),
) -> None:
    """Compile all new raw/ documents into wiki/ pages."""
    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    schema = _load_schema(layout)
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()
    llm = get_provider(cfg.llm)

    ingest_raw(layout, index)
    pending = index.pending_raw_docs()

    if not pending:
        console.print("[yellow]No new documents to compile.[/yellow]")
        index.close()
        return

    console.print(
        f"Compiling [bold]{len(pending)}[/bold] document(s) "
        f"using [cyan]{llm.model_name}[/cyan]..."
    )
    compiled = 0
    for row in pending:
        raw_path = Path(row["path"])
        console.print(f"  [dim]{raw_path.name}[/dim] ...", end=" ")
        try:
            wiki_path = compile_document(raw_path, layout, schema, llm, index)
        except Exception as exc:
            console.print(f"[red]error:[/red] {exc}")
            continue
        if wiki_path:
            console.print(f"[green]→ wiki/{wiki_path.name}[/green]")
            compiled += 1
        else:
            console.print("[yellow]skipped (empty)[/yellow]")

    rebuild_master_index(layout, index)
    index.close()
    console.print(
        f"\n[green]Done.[/green] {compiled} page(s) written. "
        f"Index updated at [dim]index/index.md[/dim]"
    )


@app.command()
def status(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k", help="KB root (default: current directory)"),
) -> None:
    """Show a summary of the knowledge base state."""
    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)

    pages = index.all_pages()
    all_raw = index.all_raw_docs()
    pending = index.pending_raw_docs()
    by_source: dict[str, int] = {}
    for row in all_raw:
        by_source[row["source_type"] or "manual"] = by_source.get(row["source_type"] or "manual", 0) + 1
    index.close()

    avg_conf = sum(p["confidence"] for p in pages) / len(pages) if pages else 0.0
    domain = yaml.safe_load(layout.kb_config.read_text()).get("domain", "—")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]KB root[/bold]", str(layout.root))
    table.add_row("[bold]Domain[/bold]", domain)
    table.add_row("[bold]Wiki pages[/bold]", str(len(pages)))
    table.add_row("[bold]Raw docs (total)[/bold]", str(len(all_raw)))
    table.add_row("[bold]Pending compilation[/bold]", str(len(pending)))
    table.add_row("[bold]Avg confidence[/bold]", f"{avg_conf:.0%}" if pages else "—")
    if by_source:
        breakdown = ", ".join(f"{k}:{v}" for k, v in sorted(by_source.items()))
        table.add_row("[bold]By source[/bold]", breakdown)

    console.print(table)


# ---------------------------------------------------------------------------
# Commands — Phase 2
# ---------------------------------------------------------------------------

@app.command()
def search(
    query: Optional[str] = typer.Argument(None, help="Search query. Default: use schema seed_queries."),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k", help="KB root"),
    sources: Optional[str] = typer.Option(None, "--sources", "-s", help="Comma-separated subset, e.g. 'web,arxiv'"),
    max_per_source: int = typer.Option(0, "--max", "-n", help="Max results per source (0 = config default)"),
    min_relevance: float = typer.Option(-1.0, "--min-relevance", help="Override config (0–1; -1 = use config)"),
    no_filter: bool = typer.Option(False, "--no-filter", help="Skip the LLM relevance filter"),
) -> None:
    """Run the retrieval orchestrator: search sources, dedup, score, save to raw/."""
    from .retriever.orchestrator import RetrievalOrchestrator
    from .filter.relevance import RelevanceScorer
    from .filter.dedup import Deduplicator

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    schema = _load_schema(layout)
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()

    only = [s.strip() for s in sources.split(",")] if sources else None
    connectors = _build_connectors(cfg.retrieval, only=only)
    if not connectors:
        console.print("[red]No connectors enabled or available.[/red] Configure retrieval in ~/.kompyla/config.yaml.")
        raise typer.Exit(1)

    use_filter = (not no_filter) and cfg.retrieval.use_relevance_filter
    scorer = RelevanceScorer(get_provider(cfg.llm)) if use_filter else None
    dedup = Deduplicator()

    orchestrator = RetrievalOrchestrator(
        connectors=connectors,
        layout=layout,
        index=index,
        relevance_scorer=scorer,
        deduplicator=dedup,
        min_relevance=min_relevance if min_relevance >= 0 else cfg.retrieval.min_relevance,
        max_per_source=max_per_source or cfg.retrieval.max_per_source,
    )

    queries = [query] if query else schema.seed_queries
    enabled = ", ".join(orchestrator.enabled_sources())
    console.print(
        f"Searching [bold]{len(queries)}[/bold] query/queries across "
        f"[cyan]{enabled}[/cyan]"
        + (f" · filter [cyan]{scorer.llm.model_name if scorer else 'off'}[/cyan]"),
    )

    summary = orchestrator.search(queries, schema=schema)
    index.close()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]Queries run[/bold]", str(summary["queries"]))
    table.add_row("[bold]Sources hit[/bold]", str(summary["sources"]))
    table.add_row("[bold]Fetched[/bold]", str(summary["fetched"]))
    table.add_row("[bold]After dedup[/bold]", str(summary["after_dedup"]))
    table.add_row("[bold]Accepted[/bold]", str(summary["accepted"]))
    table.add_row("[bold]Saved to raw/[/bold]", str(summary["saved"]))
    console.print(table)
    if summary["saved"]:
        console.print("\nRun [bold]kompyla compile[/bold] to fold these into the wiki.")


@app.command()
def fetch(
    url: str = typer.Argument(..., help="URL to fetch (YouTube, web page, etc.)"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k", help="KB root"),
) -> None:
    """Fetch a single URL and save it to raw/ as markdown."""
    from .retriever.youtube import YouTubeConnector
    from .retriever.extractor import extract_url
    from .retriever.orchestrator import _save_doc, _content_hash
    from .retriever.base import FetchedDoc

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()

    is_youtube = "youtube.com" in url or "youtu.be" in url

    if is_youtube:
        console.print(f"Fetching YouTube transcript for [cyan]{url}[/cyan]...")
        doc = YouTubeConnector(languages=cfg.retrieval.youtube_languages).fetch_url(url)
        if doc is None:
            console.print("[red]Could not fetch transcript (disabled, missing, or invalid URL).[/red]")
            raise typer.Exit(1)
    else:
        console.print(f"Extracting [cyan]{url}[/cyan]...")
        content = extract_url(url)
        if not content:
            console.print("[red]Failed to fetch or extract content.[/red]")
            raise typer.Exit(1)
        doc = FetchedDoc(
            title=url, url=url, content=content, source_type="web",
        )

    h = _content_hash(doc.content)
    if index.find_by_hash(h):
        console.print("[yellow]Already in raw/ (content hash match) — skipped.[/yellow]")
        index.close()
        return

    doc.metadata["_content_hash"] = h
    path = _save_doc(doc, layout)
    index.upsert_raw_doc(
        path,
        url=doc.url,
        source_type=doc.source_type,
        relevance_score=doc.relevance_score,
        content_hash=h,
        title=doc.title,
    )
    index.close()
    console.print(f"[green]Saved →[/green] {path.relative_to(layout.root)}")


@app.command()
def query(
    question: str = typer.Argument(..., help="Natural-language question to ask the wiki"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    save: bool = typer.Option(False, "--save", help="File the answer back into the wiki as a synthesis page"),
) -> None:
    """Ask a question against the wiki; optionally save the answer as a new page."""
    from .query.qa import answer_question

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    schema = _load_schema(layout)
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()
    llm = get_provider(cfg.llm)

    console.print(f"Answering with [cyan]{llm.model_name}[/cyan]...\n")
    answer, saved = answer_question(question, layout, index, schema, llm, save_as_page=save)
    index.close()

    console.print(answer)
    if saved:
        console.print(f"\n[green]Filed as wiki page →[/green] {saved.relative_to(layout.root)}")


@app.command()
def lint(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    stale_days: int = typer.Option(180, "--stale-days", help="Pages older than this are flagged stale"),
    conf_threshold: float = typer.Option(0.6, "--conf-threshold", help="Pages below this confidence are flagged"),
) -> None:
    """Run health checks (broken links, stale, low-confidence, orphan pages)."""
    from .evolver.lint import lint_kb

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)

    out = lint_kb(layout, index, days_stale=stale_days, conf_threshold=conf_threshold)
    index.close()

    console.print(f"[green]Lint report →[/green] {out.relative_to(layout.root)}")
    console.print("\n" + out.read_text())


@app.command()
def gaps(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM-suggested topic gaps; only broken links"),
    auto_fill: bool = typer.Option(False, "--auto-fill", help="Run retrieval orchestrator on detected gaps"),
) -> None:
    """Detect knowledge gaps; optionally fill them via the retrieval orchestrator."""
    from .evolver.gaps import detect_gaps

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    schema = _load_schema(layout)
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()

    llm = None if no_llm else get_provider(cfg.llm)
    result = detect_gaps(layout, index, schema, llm)

    broken = result["broken_link_queries"]
    topics = result["topic_gap_queries"]

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]Broken-link gaps[/bold]", str(len(broken)))
    table.add_row("[bold]LLM-suggested topic gaps[/bold]", str(len(topics)))
    console.print(table)

    if broken:
        console.print("\n[bold]Broken-link queries:[/bold]")
        for q in broken[:20]:
            console.print(f"  - {q}")
    if topics:
        console.print("\n[bold]Topic-gap queries:[/bold]")
        for q in topics:
            console.print(f"  - {q}")

    if auto_fill and (broken or topics):
        from .retriever.orchestrator import RetrievalOrchestrator
        from .filter.relevance import RelevanceScorer
        from .filter.dedup import Deduplicator

        connectors = _build_connectors(cfg.retrieval)
        if not connectors:
            console.print("\n[red]No retrieval connectors enabled.[/red]")
            index.close()
            raise typer.Exit(1)

        scorer = RelevanceScorer(get_provider(cfg.llm)) if cfg.retrieval.use_relevance_filter else None
        orch = RetrievalOrchestrator(
            connectors=connectors, layout=layout, index=index,
            relevance_scorer=scorer, deduplicator=Deduplicator(),
            min_relevance=cfg.retrieval.min_relevance,
            max_per_source=cfg.retrieval.max_per_source,
        )
        all_queries = list(dict.fromkeys(broken + topics))
        console.print(f"\n[cyan]Auto-filling[/cyan] with {len(all_queries)} query/queries...")
        summary = orch.search(all_queries, schema=schema)
        console.print(f"[green]Saved {summary['saved']} new doc(s) to raw/[/green] — run `kompyla compile`.")

    index.close()


@app.command()
def export(
    title: Optional[str] = typer.Argument(None, help="Wiki page title (omit with --all)"),
    fmt: str = typer.Option("html", "--format", "-f", help="md | html | docx | pptx | pdf | marp"),
    all_pages: bool = typer.Option(False, "--all", help="Export the whole KB instead of one page"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output path"),
) -> None:
    """Export a wiki page (or the whole KB) to md / html / docx / pptx / pdf / marp."""
    from .presenter import (
        bundle_kb_markdown, render_kb_html, render_page_html,
        md_to_docx, md_to_pptx, page_to_marp, render_marp_html, html_to_pdf,
    )
    from .presenter.pdf_export import PDFExportNotAvailable

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)

    if not all_pages and not title:
        console.print("[red]Provide a page title or use --all.[/red]")
        index.close()
        raise typer.Exit(1)

    fmt = fmt.lower()
    layout.outputs.mkdir(parents=True, exist_ok=True)

    if all_pages:
        if fmt == "md":
            text = bundle_kb_markdown(layout, index)
            target = out or layout.outputs / "kb_bundle.md"
            target.write_text(text, encoding="utf-8")
        elif fmt == "html":
            html = render_kb_html(layout, index)
            target = out or layout.outputs / "kb_index.html"
            target.write_text(html, encoding="utf-8")
        else:
            console.print("[red]--all only supports --format md or html.[/red]")
            index.close()
            raise typer.Exit(1)
        index.close()
        console.print(f"[green]Exported →[/green] {target.relative_to(layout.root)}")
        return

    # Single page
    page = next((p for p in index.all_pages() if p["title"].lower() == title.lower()), None)
    index.close()
    if not page:
        console.print(f"[red]Page not found:[/red] {title}")
        raise typer.Exit(1)

    wiki_path = Path(page["wiki_path"])
    md_text = wiki_path.read_text(encoding="utf-8")
    base = layout.outputs / wiki_path.stem

    try:
        if fmt == "md":
            target = out or base.with_suffix(".md")
            target.write_text(md_text, encoding="utf-8")
        elif fmt == "html":
            target = out or base.with_suffix(".html")
            target.write_text(render_page_html(wiki_path), encoding="utf-8")
        elif fmt == "docx":
            target = out or base.with_suffix(".docx")
            md_to_docx(md_text, target, title=page["title"])
        elif fmt == "pptx":
            target = out or base.with_suffix(".pptx")
            md_to_pptx(md_text, target, deck_title=page["title"])
        elif fmt == "marp":
            target = out or base.with_suffix(".marp.md")
            target.write_text(page_to_marp(wiki_path), encoding="utf-8")
        elif fmt == "pdf":
            target = out or base.with_suffix(".pdf")
            html_to_pdf(render_page_html(wiki_path), target)
        else:
            console.print(f"[red]Unknown format:[/red] {fmt}")
            raise typer.Exit(1)
    except PDFExportNotAvailable as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Exported →[/green] {target.relative_to(layout.root)}")


@app.command()
def slides(
    title: str = typer.Argument(..., help="Wiki page title"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    html: bool = typer.Option(False, "--html", help="Also render an HTML deck (printable)"),
) -> None:
    """Generate a Marp markdown slide deck from a wiki page."""
    from .presenter.slides import page_to_marp, render_marp_html

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)
    page = next((p for p in index.all_pages() if p["title"].lower() == title.lower()), None)
    index.close()
    if not page:
        console.print(f"[red]Page not found:[/red] {title}")
        raise typer.Exit(1)

    wiki_path = Path(page["wiki_path"])
    layout.outputs.mkdir(parents=True, exist_ok=True)
    marp_md = page_to_marp(wiki_path)
    md_out = layout.outputs / f"{wiki_path.stem}.marp.md"
    md_out.write_text(marp_md, encoding="utf-8")
    console.print(f"[green]Marp markdown →[/green] {md_out.relative_to(layout.root)}")

    if html:
        html_out = layout.outputs / f"{wiki_path.stem}.slides.html"
        html_out.write_text(render_marp_html(marp_md), encoding="utf-8")
        console.print(f"[green]HTML deck →[/green] {html_out.relative_to(layout.root)}")


@app.command()
def chart(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
) -> None:
    """Generate KB statistics charts (PNG) under outputs/charts/."""
    from .presenter.charts import generate_kb_charts

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)
    paths = generate_kb_charts(layout, index)
    index.close()
    if not paths:
        console.print("[yellow]No data to chart yet.[/yellow]")
        return
    console.print(f"[green]Generated {len(paths)} chart(s):[/green]")
    for p in paths:
        console.print(f"  {p.relative_to(layout.root)}")


@app.command()
def serve(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    port: int = typer.Option(8501, "--port", "-p"),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Address to bind. Use 127.0.0.1 for local-only, 0.0.0.0 for WSL2/devcontainer/server.",
    ),
) -> None:
    """Launch the Streamlit web UI for browsing, searching, and querying the KB."""
    import os
    import subprocess
    import sys
    from . import ui

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)

    app_path = Path(ui.__file__).parent / "app.py"
    env = os.environ.copy()
    env["KOMPYLA_KB"] = str(layout.root)

    display_host = "localhost" if host == "127.0.0.1" else host
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.port", str(port),
        "--server.address", host,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    console.print(f"Starting Streamlit on [cyan]http://{display_host}:{port}[/cyan] for KB at {layout.root}")
    subprocess.run(cmd, env=env)


# ---------------------------------------------------------------------------
# Commands — Phase 5
# ---------------------------------------------------------------------------

@app.command()
def schedule(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    enable: bool = typer.Option(False, "--enable", help="Enable scheduled runs"),
    disable: bool = typer.Option(False, "--disable", help="Disable scheduled runs"),
    interval: int = typer.Option(0, "--interval", help="Interval in hours (0 = keep current)"),
    run_now: bool = typer.Option(False, "--run-now", help="Execute one cycle immediately"),
    daemon: bool = typer.Option(False, "--daemon", help="Loop forever, running when due"),
    status: bool = typer.Option(False, "--status", help="Show current schedule config"),
) -> None:
    """Configure and run the periodic research-and-compile cycle."""
    import time
    import yaml as _yaml

    from .scheduler.schedule import is_due, load_schedule, mark_ran, save_schedule
    from .scheduler.runner import run_cycle

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)
    schema = _load_schema(layout)
    cfg = KompylaConfig.load()

    sched = load_schedule(layout)

    if enable:
        sched["enabled"] = True
        save_schedule(layout, sched)
        console.print("[green]Schedule enabled.[/green]")
    if disable:
        sched["enabled"] = False
        save_schedule(layout, sched)
        console.print("[yellow]Schedule disabled.[/yellow]")
    if interval > 0:
        sched["interval_hours"] = interval
        save_schedule(layout, sched)
        console.print(f"Interval set to [cyan]{interval}h[/cyan].")

    if status or (not enable and not disable and not run_now and not daemon):
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold]Enabled[/bold]", str(sched.get("enabled", False)))
        table.add_row("[bold]Interval[/bold]", f"{sched.get('interval_hours', 24)}h")
        table.add_row("[bold]Last run[/bold]", sched.get("last_run_at") or "never")
        table.add_row("[bold]Due now[/bold]", str(is_due(sched)))
        console.print(table)
        index.close()
        return

    def _run_one():
        console.print("[cyan]Running research cycle…[/cyan]")
        result = run_cycle(layout, index, schema, cfg)
        mark_ran(layout, load_schedule(layout))
        console.print(
            f"  searched={result['searched']}  compiled={result['compiled']}"
            f"  gap_queries={result['gap_queries']}"
        )
        if result["errors"]:
            for e in result["errors"]:
                console.print(f"  [red]error:[/red] {e}")
        if result["lint_report"]:
            console.print(f"  lint → {result['lint_report']}")

    if run_now:
        _run_one()
        index.close()
        return

    if daemon:
        console.print(
            f"[cyan]Daemon mode[/cyan] — interval {sched.get('interval_hours', 24)}h. "
            "Ctrl-C to stop."
        )
        try:
            while True:
                sched = load_schedule(layout)
                if is_due(sched):
                    _run_one()
                time.sleep(60)
        except KeyboardInterrupt:
            console.print("Stopped.")
        index.close()


@app.command()
def crossref(
    target_kb: Path = typer.Option(..., "--kb-target", help="Path to the other KB to compare against"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    threshold: float = typer.Option(0.15, "--threshold", "-t", help="Minimum Jaccard similarity (0–1)"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output report path"),
    use_llm: bool = typer.Option(False, "--llm", help="Annotate connections with LLM notes"),
) -> None:
    """Find shared topics between this KB and another KB."""
    from .crossref.bridge import find_connections, write_crossref_report
    import yaml as _yaml

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    target_layout = KBLayout(target_kb)
    if not target_layout.schema_file.exists():
        console.print(f"[red]No KB found at {target_kb}.[/red]")
        raise typer.Exit(1)

    index = MetaIndex(layout.meta_db)
    target_index = MetaIndex(target_layout.meta_db)
    cfg = KompylaConfig.load()

    llm = get_provider(cfg.llm) if use_llm else None
    target_domain = _yaml.safe_load(target_layout.kb_config.read_text()).get("domain", target_kb.name)

    console.print(
        f"Cross-referencing [cyan]{layout.root.name}[/cyan] ↔ [cyan]{target_domain}[/cyan] "
        f"(threshold={threshold:.0%})…"
    )
    results = find_connections(
        layout, index, target_layout, target_index,
        threshold=threshold, llm=llm,
    )
    index.close()
    target_index.close()

    console.print(f"[green]{len(results)} connection(s) found.[/green]")
    if results:
        report = out or None
        if report:
            from .crossref.bridge import write_crossref_report as _write
            report = _write(results, layout, target_domain)
            if out:
                import shutil
                shutil.copy(report, out)
                report = out
        else:
            report = write_crossref_report(results, layout, target_domain)
        console.print(f"[green]Report →[/green] {report}")
        for r in results[:10]:
            console.print(f"  {r.source_title!r} ↔ {r.target_title!r}  ({r.similarity:.0%})")


@app.command()
def feedback(
    title: Optional[str] = typer.Argument(None, help="Wiki page title to give feedback on"),
    signal: Optional[str] = typer.Option(None, "--signal", "-s",
        help="Feedback signal: wrong | outdated | excellent | unclear"),
    note: str = typer.Option("", "--note", "-n", help="Optional free-text note"),
    list_all: bool = typer.Option(False, "--list", help="List all stored feedback"),
    apply: bool = typer.Option(False, "--apply", help="Apply feedback deltas to confidence scores"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
) -> None:
    """Record user feedback on wiki pages and optionally apply it to confidence scores."""
    from .feedback.store import FeedbackStore, VALID_SIGNALS
    from .feedback.apply import apply_feedback as _apply

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    store = FeedbackStore(layout.feedback_db)

    if list_all:
        rows = store.all_feedback()
        if not rows:
            console.print("[dim]No feedback recorded yet.[/dim]")
        else:
            table = Table("Page", "Signal", "Note", "Date", box=None)
            for r in rows[:50]:
                table.add_row(r["page_title"], r["signal"], r["note"] or "", r["created_at"][:10])
            console.print(table)
        store.close()
        return

    if apply:
        index = MetaIndex(layout.meta_db)
        result = _apply(layout, index, store)
        index.close()
        store.close()
        console.print(
            f"[green]Applied feedback:[/green] "
            f"{result['updated']} page(s) updated, {result['skipped']} skipped."
        )
        if result["flagged_for_research"]:
            console.print("[yellow]Flagged for re-research:[/yellow]")
            for t in result["flagged_for_research"]:
                console.print(f"  - {t}")
        return

    if not title or not signal:
        console.print("[red]Provide a page title and --signal (wrong|outdated|excellent|unclear).[/red]")
        store.close()
        raise typer.Exit(1)

    if signal not in VALID_SIGNALS:
        console.print(f"[red]--signal must be one of: {', '.join(sorted(VALID_SIGNALS))}[/red]")
        store.close()
        raise typer.Exit(1)

    store.add(title, signal, note)
    store.close()
    console.print(f"[green]Feedback recorded:[/green] {title!r} → {signal}")
    if note:
        console.print(f"  Note: {note}")
    console.print("Run [bold]kompyla feedback --apply[/bold] to update confidence scores.")


@app.command()
def synth(
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output JSONL path"),
    min_conf: float = typer.Option(0.7, "--min-conf", help="Minimum page confidence"),
    pairs: int = typer.Option(3, "--pairs", "-n", help="Q&A pairs per page"),
) -> None:
    """Generate synthetic Q&A training data from high-confidence wiki pages."""
    from .synth.generator import generate_training_data, save_training_data

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()
    llm = get_provider(cfg.llm)

    pages = [p for p in index.all_pages() if (p["confidence"] or 0) >= min_conf]
    if not pages:
        console.print(f"[yellow]No pages with confidence ≥ {min_conf:.0%}.[/yellow]")
        index.close()
        return

    console.print(
        f"Generating {pairs} Q&A pair(s) per page across "
        f"[bold]{len(pages)}[/bold] pages using [cyan]{llm.model_name}[/cyan]…"
    )
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as prog:
        prog.add_task("Generating…")
        records = generate_training_data(layout, index, llm, min_confidence=min_conf, pairs_per_page=pairs)

    index.close()
    layout.outputs.mkdir(parents=True, exist_ok=True)
    target = out or layout.outputs / "training_data.jsonl"
    save_training_data(records, target)
    console.print(f"[green]Saved {len(records)} record(s) →[/green] {target.relative_to(layout.root)}")


@app.command("add-youtube")
def add_youtube(
    url: str = typer.Argument(..., help="YouTube video URL"),
    kb_path: Optional[Path] = typer.Option(None, "--kb", "-k", help="KB root (default: current directory)"),
    language: list[str] = typer.Option(["en"], "--lang", "-l", help="Transcript language code(s), in priority order"),
) -> None:
    """Fetch a YouTube transcript and drop it into raw/ for compilation."""
    from .retriever.youtube import fetch_youtube
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

    layout = KBLayout(kb_path or Path.cwd())
    _require_kb(layout)

    console.print(f"Fetching transcript for [cyan]{url}[/cyan]...")
    try:
        out = fetch_youtube(url, layout.raw, languages=language)
    except TranscriptsDisabled:
        console.print("[red]Transcripts are disabled for this video.[/red]")
        raise typer.Exit(1)
    except NoTranscriptFound:
        console.print(
            f"[red]No transcript found[/red] in languages: {language}. "
            "Try --lang with a different language code."
        )
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red]Invalid URL:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"[green]Saved →[/green] {out.relative_to(layout.root)}")
    console.print("Run [bold]kompyla compile[/bold] to add it to the wiki.")
