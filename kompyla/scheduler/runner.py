"""Scheduled research cycle: fetch → compile → lint → gaps (one full pass)."""

from __future__ import annotations

from pathlib import Path

from kompyla.compiler.compile import compile_document
from kompyla.compiler.ingest import ingest_raw
from kompyla.compiler.linker import rebuild_master_index
from kompyla.config import KompylaConfig
from kompyla.evolver.gaps import detect_gaps
from kompyla.evolver.lint import lint_kb
from kompyla.llm import get_provider
from kompyla.schema.models import DomainSchema
from kompyla.storage.index import MetaIndex
from kompyla.storage.layout import KBLayout


def run_cycle(
    layout: KBLayout,
    index: MetaIndex,
    schema: DomainSchema,
    cfg: KompylaConfig,
    *,
    run_search: bool = True,
    run_compile: bool = True,
    run_lint: bool = True,
    run_gaps: bool = True,
    queries: list[str] | None = None,
) -> dict:
    """Run one full maintenance cycle and return a summary dict."""
    summary: dict = {
        "searched": 0,
        "compiled": 0,
        "lint_report": None,
        "gap_queries": 0,
        "errors": [],
    }

    llm = get_provider(cfg.llm)

    # -- Retrieval --
    if run_search:
        try:
            from kompyla.filter.dedup import Deduplicator
            from kompyla.filter.relevance import RelevanceScorer
            from kompyla.retriever.orchestrator import RetrievalOrchestrator

            connectors = _build_connectors(cfg)
            if connectors:
                scorer = RelevanceScorer(llm) if cfg.retrieval.use_relevance_filter else None
                orch = RetrievalOrchestrator(
                    connectors=connectors,
                    layout=layout,
                    index=index,
                    relevance_scorer=scorer,
                    deduplicator=Deduplicator(),
                    min_relevance=cfg.retrieval.min_relevance,
                    max_per_source=cfg.retrieval.max_per_source,
                )
                search_queries = queries or schema.seed_queries
                result = orch.search(search_queries, schema=schema)
                summary["searched"] = result.get("saved", 0)
        except Exception as exc:
            summary["errors"].append(f"search: {exc}")

    # -- Compile --
    if run_compile:
        try:
            ingest_raw(layout, index)
            pending = index.pending_raw_docs()
            for row in pending:
                raw_path = Path(row["path"])
                try:
                    compile_document(raw_path, layout, schema, llm, index)
                    summary["compiled"] += 1
                except Exception as exc:
                    summary["errors"].append(f"compile {raw_path.name}: {exc}")
            if pending:
                rebuild_master_index(layout, index)
        except Exception as exc:
            summary["errors"].append(f"compile-phase: {exc}")

    # -- Lint --
    if run_lint:
        try:
            out = lint_kb(layout, index)
            summary["lint_report"] = str(out)
        except Exception as exc:
            summary["errors"].append(f"lint: {exc}")

    # -- Gaps --
    if run_gaps:
        try:
            gaps_result = detect_gaps(layout, index, schema, llm)
            all_gaps = gaps_result.get("broken_link_queries", []) + gaps_result.get("topic_gap_queries", [])
            summary["gap_queries"] = len(all_gaps)
        except Exception as exc:
            summary["errors"].append(f"gaps: {exc}")

    return summary


def _build_connectors(cfg: KompylaConfig) -> list:
    from kompyla.retriever import (
        ArxivConnector,
        GitHubConnector,
        RSSConnector,
        WebSearchConnector,
        YouTubeConnector,
    )

    available: dict = {
        "web":     WebSearchConnector(api_key=cfg.retrieval.tavily_api_key),
        "arxiv":   ArxivConnector(),
        "github":  GitHubConnector(token=cfg.retrieval.github_token),
        "rss":     RSSConnector(feeds=cfg.retrieval.rss_feeds),
        "youtube": YouTubeConnector(languages=cfg.retrieval.youtube_languages),
    }
    return [available[name] for name in cfg.retrieval.enabled_sources if name in available]
