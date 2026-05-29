"""Streamlit UI for browsing, searching, and querying the KB.

Run via:  kompyla serve [--kb path]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import streamlit as st
import yaml

from kompyla.config import KompylaConfig
from kompyla.llm import get_provider
from kompyla.query.qa import answer_question
from kompyla.schema.generator import generate_schema
from kompyla.schema.models import DomainSchema
from kompyla.storage.index import MetaIndex
from kompyla.storage.layout import KBLayout


# ---------- arg parsing ----------

def _kb_path_from_args() -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", type=Path, default=None)
    args, _ = parser.parse_known_args()
    if args.kb:
        return args.kb
    if env := os.getenv("KOMPYLA_KB"):
        return Path(env)
    return Path.cwd()


# ---------- helpers ----------

def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2].lstrip() if len(parts) >= 3 else text


@st.cache_resource
def _load_kb(kb_path_str: str):
    layout = KBLayout(Path(kb_path_str))
    if not layout.schema_file.exists():
        return None
    schema = DomainSchema(**yaml.safe_load(layout.schema_file.read_text()))
    index = MetaIndex(layout.meta_db)
    cfg = KompylaConfig.load()
    return layout, index, schema, cfg


# ---------- first-run setup ----------

def _setup_screen(kb_path: Path) -> None:
    st.title("Kompyla — First-run setup")
    st.info(
        f"No knowledge base found at **`{kb_path}`**. "
        "Fill in the form below to initialise one."
    )

    with st.form("init_form"):
        domain = st.text_input(
            "Research domain",
            placeholder="e.g. electric vehicles, quantum computing …",
        )
        st.caption(
            "The domain drives the KB schema (page types, entity categories, seed queries). "
            "You can change it later by re-running `kompyla init`."
        )
        submitted = st.form_submit_button("Initialise KB", type="primary")

    if not submitted:
        return
    if not domain.strip():
        st.error("Please enter a domain name.")
        return

    cfg = KompylaConfig.load()
    try:
        llm = get_provider(cfg.llm)
    except Exception as exc:
        st.error(f"Could not load LLM provider: {exc}")
        st.info(
            "Set the appropriate API key environment variable and restart the container, "
            "or configure an Ollama endpoint via `OLLAMA_BASE_URL`."
        )
        return

    with st.spinner(f"Generating schema for **{domain.strip()}** using `{llm.model_name}` …"):
        try:
            layout = KBLayout(kb_path)
            layout.create()
            schema = generate_schema(domain.strip(), llm)
            layout.schema_file.write_text(
                yaml.dump(schema.model_dump(), allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            layout.kb_config.write_text(
                yaml.dump({"domain": domain.strip()}, allow_unicode=True),
                encoding="utf-8",
            )
        except Exception as exc:
            st.error(f"Initialisation failed: {exc}")
            return

    st.success(
        f"KB initialised at `{kb_path}` — "
        f"{len(schema.page_types)} page types, "
        f"{len(schema.seed_queries)} seed queries."
    )
    st.info("The page will reload automatically in a moment.")
    st.cache_resource.clear()
    st.rerun()


# ---------- main ----------

def main() -> None:
    kb_path = _kb_path_from_args()
    loaded = _load_kb(str(kb_path))

    if loaded is None:
        st.set_page_config(page_title="Kompyla — Setup", layout="centered", page_icon=None)
        _setup_screen(kb_path)
        return

    st.set_page_config(page_title="Kompyla", layout="wide", page_icon=None)
    layout, index, schema, cfg = loaded

    st.sidebar.title("Kompyla")
    st.sidebar.caption(f"Domain: **{schema.domain}**")
    st.sidebar.caption(f"Path: `{layout.root}`")

    page = st.sidebar.radio(
        "View",
        ["Browse", "Search", "Ask", "Retrieve", "Compile", "Maintain", "Export", "Stats", "Advanced"],
    )

    if page == "Browse":
        _browse(layout, index)
    elif page == "Search":
        _search(layout, index)
    elif page == "Ask":
        _ask(layout, index, schema, cfg)
    elif page == "Retrieve":
        _retrieve(layout, index, schema, cfg)
    elif page == "Compile":
        _compile(layout, index, schema, cfg)
    elif page == "Maintain":
        _maintain(layout, index, schema, cfg)
    elif page == "Export":
        _export(layout, index)
    elif page == "Stats":
        _stats(layout, index)
    elif page == "Advanced":
        _advanced(layout, index, schema, cfg)


def _browse(layout: KBLayout, index: MetaIndex) -> None:
    pages = index.all_pages()
    st.header("Browse Wiki")

    types = sorted({(p["page_type"] or "misc") for p in pages})
    selected_type = st.selectbox("Page type", ["all"] + types)
    min_conf = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)

    filtered = [
        p for p in pages
        if (selected_type == "all" or p["page_type"] == selected_type)
        and (p["confidence"] or 0) >= min_conf
    ]

    st.caption(f"{len(filtered)} of {len(pages)} pages")

    titles = [p["title"] for p in filtered]
    if not titles:
        st.info("No pages match.")
        return
    chosen = st.selectbox("Page", titles)
    page = next(p for p in filtered if p["title"] == chosen)

    wpath = Path(page["wiki_path"])
    if wpath.exists():
        col1, col2, col3 = st.columns(3)
        col1.metric("Confidence", f"{(page['confidence'] or 0):.0%}")
        col2.metric("Type", page["page_type"] or "misc")
        col3.metric("Updated", (page["updated_at"] or "")[:10])
        st.markdown(_strip_frontmatter(wpath.read_text(encoding="utf-8")))


def _search(layout: KBLayout, index: MetaIndex) -> None:
    st.header("Search")
    q = st.text_input("Query", "")
    if not q:
        return
    q_lower = q.lower()
    pages = index.all_pages()
    hits = []
    for p in pages:
        wpath = Path(p["wiki_path"])
        if not wpath.exists():
            continue
        text = wpath.read_text(encoding="utf-8").lower()
        if q_lower in p["title"].lower() or q_lower in text:
            hits.append(p)
    st.caption(f"{len(hits)} hit(s)")
    for p in hits[:20]:
        with st.expander(f"**{p['title']}** — {(p['confidence'] or 0):.0%}"):
            wpath = Path(p["wiki_path"])
            text = _strip_frontmatter(wpath.read_text(encoding="utf-8"))
            # Highlight first matching context
            idx = text.lower().find(q_lower)
            if idx >= 0:
                start = max(0, idx - 200)
                snippet = text[start:idx + 400]
                st.markdown(f"_{snippet}_")
            st.markdown("---")
            st.markdown(text[:2000])


def _ask(layout: KBLayout, index: MetaIndex, schema: DomainSchema, cfg) -> None:
    st.header("Ask")
    question = st.text_area("Question", "", height=100)
    save = st.checkbox("Save answer back to wiki as synthesis page", value=False)
    if st.button("Ask", disabled=not question.strip()):
        with st.spinner(f"Thinking with {cfg.llm.model} ..."):
            llm = get_provider(cfg.llm)
            answer, saved = answer_question(question, layout, index, schema, llm, save_as_page=save)
        st.markdown(answer)
        if saved:
            st.success(f"Saved as `{saved.relative_to(layout.root)}`")


def _retrieve(layout: KBLayout, index: MetaIndex, schema: DomainSchema, cfg) -> None:
    st.header("Retrieve")
    tab_fetch, tab_search = st.tabs(["Fetch URL", "Search Sources"])

    # ---- 2a. Fetch a single URL ----
    with tab_fetch:
        st.subheader("Fetch a single URL")
        url = st.text_input("URL", placeholder="https://… or https://youtu.be/…")
        if st.button("Fetch", disabled=not url.strip()):
            from kompyla.retriever.youtube import YouTubeConnector
            from kompyla.retriever.extractor import extract_url
            from kompyla.retriever.orchestrator import _save_doc, _content_hash
            from kompyla.retriever.base import FetchedDoc

            url = url.strip()
            is_youtube = "youtube.com" in url or "youtu.be" in url

            with st.status("Fetching…", expanded=True) as s:
                try:
                    if is_youtube:
                        s.update(label="Fetching YouTube transcript…")
                        doc = YouTubeConnector(
                            languages=cfg.retrieval.youtube_languages
                        ).fetch_url(url)
                        if doc is None:
                            st.error("Could not fetch transcript (disabled, missing, or invalid URL).")
                            s.update(label="Failed", state="error")
                            st.stop()
                    else:
                        s.update(label="Extracting web page…")
                        content = extract_url(url)
                        if not content:
                            st.error("Failed to fetch or extract content from URL.")
                            s.update(label="Failed", state="error")
                            st.stop()
                        doc = FetchedDoc(title=url, url=url, content=content, source_type="web")

                    h = _content_hash(doc.content)
                    if index.find_by_hash(h):
                        st.warning("Already in raw/ (content hash match) — skipped.")
                        s.update(label="Skipped — already exists", state="complete")
                    else:
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
                        st.success(f"Saved → `{path.relative_to(layout.root)}`")
                        s.update(label="Done", state="complete")
                        st.session_state["last_fetch"] = 1
                        st.cache_resource.clear()
                except Exception as exc:
                    st.error(f"Failed: {exc}")
                    s.update(label="Error", state="error")

    # ---- 2b. Search sources via orchestrator ----
    with tab_search:
        st.subheader("Search Sources")
        query_input = st.text_input(
            "Query",
            placeholder="Leave empty to use schema seed queries",
        )
        all_sources = ["web", "arxiv", "github", "rss", "youtube"]
        default_sources = [s for s in cfg.retrieval.enabled_sources if s in all_sources]
        selected_sources = st.multiselect("Sources", all_sources, default=default_sources)
        max_results = st.slider("Max results per source", 1, 20, cfg.retrieval.max_per_source)
        skip_relevance = st.checkbox(
            "Skip relevance filter",
            value=not cfg.retrieval.use_relevance_filter,
        )

        if st.button("Search", disabled=not selected_sources):
            from kompyla.retriever import (
                WebSearchConnector, ArxivConnector, GitHubConnector,
                RSSConnector, YouTubeConnector,
            )
            from kompyla.retriever.orchestrator import RetrievalOrchestrator
            from kompyla.filter.relevance import RelevanceScorer

            rcfg = cfg.retrieval
            available = {
                "web": WebSearchConnector(
                    serper_api_key=rcfg.serper_api_key,
                    brave_api_key=rcfg.brave_api_key,
                    exa_api_key=rcfg.exa_api_key,
                    serpapi_api_key=rcfg.serpapi_api_key,
                ),
                "arxiv": ArxivConnector(),
                "github": GitHubConnector(token=rcfg.github_token),
                "rss": RSSConnector(feeds=rcfg.rss_feeds),
                "youtube": YouTubeConnector(languages=rcfg.youtube_languages),
            }
            connectors = [available[s] for s in selected_sources if s in available]
            queries = [query_input.strip()] if query_input.strip() else schema.seed_queries
            scorer = None if skip_relevance else RelevanceScorer(get_provider(cfg.llm))

            with st.status("Searching…", expanded=True) as s:
                s.update(label=f"Querying {len(connectors)} source(s) with {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}…")
                try:
                    orch = RetrievalOrchestrator(
                        connectors=connectors,
                        layout=layout,
                        index=index,
                        relevance_scorer=scorer,
                        max_per_source=max_results,
                        min_relevance=rcfg.min_relevance,
                    )
                    summary = orch.search(queries, schema=schema)
                    s.update(label="Done", state="complete")
                except Exception as exc:
                    st.error(f"Search failed: {exc}")
                    s.update(label="Error", state="error")
                    st.stop()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Fetched", summary["fetched"])
            col2.metric("After dedup", summary["after_dedup"])
            col3.metric("Accepted", summary["accepted"])
            col4.metric("Saved", summary["saved"])

            if summary["saved"] > 0:
                st.session_state["last_fetch"] = summary["saved"]
                st.info(f"{summary['saved']} new doc(s) saved — go to **Compile** to fold them into the wiki.")
                st.cache_resource.clear()
            else:
                st.info("No new documents saved (all filtered or already indexed).")


def _compile(layout: KBLayout, index: MetaIndex, schema: DomainSchema, cfg) -> None:
    from kompyla.compiler.compile import compile_document
    from kompyla.compiler.ingest import ingest_raw
    from kompyla.compiler.linker import rebuild_master_index

    st.header("Compile")

    ingest_raw(layout, index)
    pending = index.pending_raw_docs()

    last_fetch = st.session_state.get("last_fetch", 0)
    col1, col2 = st.columns(2)
    col1.metric("Pending docs", len(pending))
    if last_fetch:
        col2.info(f"{last_fetch} new doc(s) from last Retrieve")

    if not pending:
        st.info("No pending documents to compile.")
        return

    if st.button("Compile all pending", type="primary"):
        llm = get_provider(cfg.llm)
        compiled = 0
        errors: list[tuple[str, str]] = []
        progress = st.progress(0)
        status_line = st.empty()

        with st.status(f"Compiling {len(pending)} doc(s) with {cfg.llm.model}…", expanded=True) as s:
            for i, row in enumerate(pending):
                raw_path = Path(row["path"])
                status_line.write(f"`{raw_path.name}` …")
                try:
                    wiki_path = compile_document(raw_path, layout, schema, llm, index)
                    if wiki_path:
                        st.write(f"  `{raw_path.name}` → `wiki/{wiki_path.name}`")
                        compiled += 1
                    else:
                        st.write(f"  `{raw_path.name}` — skipped (empty)")
                except Exception as exc:
                    errors.append((raw_path.name, str(exc)))
                    st.write(f"  `{raw_path.name}` — error: {exc}")
                progress.progress((i + 1) / len(pending))

            rebuild_master_index(layout, index)
            status_line.empty()
            s.update(label=f"Done — {compiled} page(s) written", state="complete")

        if errors:
            with st.expander(f"{len(errors)} error(s)"):
                for name, msg in errors:
                    st.error(f"`{name}`: {msg}")

        st.success(f"{compiled} page(s) written. Index updated.")
        st.session_state.pop("last_fetch", None)
        st.cache_resource.clear()


def _maintain(layout: KBLayout, index: MetaIndex, schema: DomainSchema, cfg) -> None:
    st.header("Maintain")
    tab_lint, tab_gaps, tab_feedback, tab_schedule = st.tabs(["Lint", "Gaps", "Feedback", "Schedule"])

    # ---- 4a. Lint ----
    with tab_lint:
        stale_days = st.number_input("Stale threshold (days)", min_value=1, value=180)
        conf_threshold = st.slider("Low-confidence threshold", 0.0, 1.0, 0.6, 0.05)

        if st.button("Run lint"):
            from kompyla.evolver.lint import (
                lint_kb,
                find_broken_links,
                find_low_confidence_pages,
                find_orphan_pages,
                find_stale_pages,
            )
            import pandas as pd

            with st.status("Running lint…", expanded=True) as s:
                out = lint_kb(layout, index, days_stale=int(stale_days), conf_threshold=conf_threshold)
                pages = index.all_pages()
                broken = find_broken_links(layout, pages)
                low_conf = find_low_confidence_pages(pages, threshold=conf_threshold)
                stale = find_stale_pages(pages, days=int(stale_days))
                orphans = find_orphan_pages(layout, pages)
                s.update(label="Done", state="complete")

            with st.expander(f"Broken links ({len(broken)})"):
                if broken:
                    st.dataframe(pd.DataFrame(broken, columns=["Source", "Broken link"]), use_container_width=True)
                else:
                    st.info("No broken links.")

            with st.expander(f"Low-confidence pages ({len(low_conf)}, < {conf_threshold:.0%})"):
                if low_conf:
                    st.dataframe(
                        pd.DataFrame([{"Title": p["title"], "Confidence": f"{(p['confidence'] or 0):.0%}"} for p in low_conf]),
                        use_container_width=True,
                    )
                else:
                    st.info("All pages above threshold.")

            with st.expander(f"Stale pages ({len(stale)}, > {int(stale_days)} days)"):
                if stale:
                    st.dataframe(
                        pd.DataFrame([{"Title": p["title"], "Updated": (p["updated_at"] or "")[:10]} for p in stale]),
                        use_container_width=True,
                    )
                else:
                    st.info("No stale pages.")

            with st.expander(f"Orphan pages ({len(orphans)})"):
                if orphans:
                    st.dataframe(pd.DataFrame([{"Title": p["title"]} for p in orphans]), use_container_width=True)
                else:
                    st.info("No orphan pages.")

            st.caption(f"Report saved → `{out.relative_to(layout.root)}`")

    # ---- 4b. Gaps ----
    with tab_gaps:
        skip_llm = st.checkbox("Skip LLM topic suggestions (broken-link gaps only)")

        if st.button("Detect gaps"):
            from kompyla.evolver.gaps import detect_gaps

            llm = None if skip_llm else get_provider(cfg.llm)
            with st.status("Detecting gaps…", expanded=True) as s:
                result = detect_gaps(layout, index, schema, llm)
                s.update(label="Done", state="complete")
            st.session_state["gap_result"] = result

        result = st.session_state.get("gap_result")
        if result is not None:
            broken_q = result["broken_link_queries"]
            topic_q = result["topic_gap_queries"]

            col1, col2 = st.columns(2)
            col1.metric("Broken-link gaps", len(broken_q))
            col2.metric("LLM topic gaps", len(topic_q))

            with st.expander(f"Broken-link queries ({len(broken_q)})"):
                for q in broken_q:
                    st.write(f"- {q}")

            with st.expander(f"Topic-gap queries ({len(topic_q)})"):
                for q in topic_q:
                    st.write(f"- {q}")

            all_queries = list(dict.fromkeys(broken_q + topic_q))
            if all_queries and st.checkbox("Auto-fill detected gaps"):
                if st.button("Fill gaps via retrieval"):
                    from kompyla.retriever import (
                        ArxivConnector, GitHubConnector, RSSConnector,
                        WebSearchConnector, YouTubeConnector,
                    )
                    from kompyla.retriever.orchestrator import RetrievalOrchestrator
                    from kompyla.filter.relevance import RelevanceScorer

                    rcfg = cfg.retrieval
                    available = {
                        "web": WebSearchConnector(
                            serper_api_key=rcfg.serper_api_key,
                            brave_api_key=rcfg.brave_api_key,
                            exa_api_key=rcfg.exa_api_key,
                            serpapi_api_key=rcfg.serpapi_api_key,
                        ),
                        "arxiv": ArxivConnector(),
                        "github": GitHubConnector(token=rcfg.github_token),
                        "rss": RSSConnector(feeds=rcfg.rss_feeds),
                        "youtube": YouTubeConnector(languages=rcfg.youtube_languages),
                    }
                    connectors = [available[s] for s in rcfg.enabled_sources if s in available]
                    scorer = RelevanceScorer(get_provider(cfg.llm)) if rcfg.use_relevance_filter else None

                    with st.status(f"Auto-filling {len(all_queries)} quer{'y' if len(all_queries) == 1 else 'ies'}…", expanded=True) as s:
                        try:
                            orch = RetrievalOrchestrator(
                                connectors=connectors, layout=layout, index=index,
                                relevance_scorer=scorer, min_relevance=rcfg.min_relevance,
                                max_per_source=rcfg.max_per_source,
                            )
                            summary = orch.search(all_queries, schema=schema)
                            s.update(label="Done", state="complete")
                        except Exception as exc:
                            st.error(f"Auto-fill failed: {exc}")
                            s.update(label="Error", state="error")
                            st.stop()

                    st.success(f"{summary['saved']} new doc(s) saved — go to **Compile** to fold them in.")
                    st.session_state["last_fetch"] = summary["saved"]
                    st.cache_resource.clear()

    # ---- 4c. Feedback ----
    with tab_feedback:
        from kompyla.feedback.store import FeedbackStore, VALID_SIGNALS

        store = FeedbackStore(layout.feedback_db)
        sub_add, sub_view, sub_apply = st.tabs(["Add", "View", "Apply"])

        with sub_add:
            pages = index.all_pages()
            titles = [p["title"] for p in pages]
            if not titles:
                st.info("No wiki pages yet.")
            else:
                page_title = st.selectbox("Page", titles)
                signal = st.radio("Signal", sorted(VALID_SIGNALS), horizontal=True)
                note = st.text_input("Note (optional)")
                if st.button("Record feedback"):
                    store.add(page_title, signal, note)
                    st.success(f"Recorded: `{page_title}` → {signal}")

        with sub_view:
            import pandas as pd

            rows = store.all_feedback()
            if rows:
                st.dataframe(
                    pd.DataFrame([
                        {"Page": r["page_title"], "Signal": r["signal"],
                         "Note": r["note"] or "", "Date": r["created_at"][:10]}
                        for r in rows[:50]
                    ]),
                    use_container_width=True,
                )
            else:
                st.info("No feedback recorded yet.")

        with sub_apply:
            st.write("Adjust confidence scores based on accumulated feedback signals.")
            if st.button("Apply to confidence scores", type="primary"):
                from kompyla.feedback.apply import apply_feedback as _apply_fb

                result = _apply_fb(layout, index, store)
                st.success(f"{result['updated']} page(s) updated, {result['skipped']} skipped.")
                if result["flagged_for_research"]:
                    with st.expander(f"Flagged for re-research ({len(result['flagged_for_research'])})"):
                        for t in result["flagged_for_research"]:
                            st.write(f"- {t}")
                st.cache_resource.clear()

        store.close()

    # ---- 4d. Schedule ----
    with tab_schedule:
        from kompyla.scheduler.schedule import is_due, load_schedule, mark_ran, save_schedule

        sched = load_schedule(layout)

        col1, col2, col3 = st.columns(3)
        col1.metric("Status", "Enabled" if sched["enabled"] else "Disabled")
        col2.metric("Interval", f"{sched['interval_hours']}h")
        col3.metric("Last run", (sched.get("last_run_at") or "Never")[:10])

        if is_due(sched):
            st.info("A scheduled run is due now.")

        st.divider()

        enabled = st.toggle("Enable scheduled runs", value=bool(sched["enabled"]))
        interval = st.number_input("Interval (hours)", min_value=1, max_value=168, value=int(sched["interval_hours"]))

        if st.button("Save schedule"):
            sched["enabled"] = enabled
            sched["interval_hours"] = interval
            save_schedule(layout, sched)
            st.success("Schedule saved.")

        st.divider()
        st.caption(
            "**Run now** executes a full retrieve → compile → lint → gaps cycle. "
            "The `--daemon` mode (background polling) is CLI-only."
        )
        if st.button("Run now", type="primary"):
            from kompyla.scheduler.runner import run_cycle

            with st.status("Running full cycle…", expanded=True) as s:
                try:
                    result = run_cycle(layout, index, schema, cfg)
                    mark_ran(layout, load_schedule(layout))
                    s.update(label="Done", state="complete")
                except Exception as exc:
                    st.error(f"Cycle failed: {exc}")
                    s.update(label="Error", state="error")
                    st.stop()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Docs fetched", result.get("searched", 0))
            c2.metric("Pages compiled", result.get("compiled", 0))
            c3.metric("Gap queries", result.get("gap_queries", 0))
            c4.metric("Errors", len(result.get("errors", [])))

            if result.get("errors"):
                with st.expander(f"{len(result['errors'])} error(s)"):
                    for e in result["errors"]:
                        st.error(e)

            st.cache_resource.clear()


_MIME = {
    "html": "text/html",
    "md":   "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf":  "application/pdf",
    "marp": "text/markdown",
}


def _export(layout: KBLayout, index: MetaIndex) -> None:
    from kompyla.presenter import (
        bundle_kb_markdown, generate_kb_charts, html_to_pdf,
        md_to_docx, md_to_pptx, page_to_marp, render_kb_html,
        render_marp_html, render_page_html,
    )
    from kompyla.presenter.pdf_export import PDFExportNotAvailable

    st.header("Export")
    tab_page, tab_slides, tab_charts = st.tabs(["Page export", "Slides", "Charts"])

    pages = index.all_pages()
    titles = [p["title"] for p in pages]

    # ---- 5a. Page export ----
    with tab_page:
        export_kb = st.checkbox("Export entire KB")

        if export_kb:
            fmt_kb = st.selectbox("Format", ["html", "md"], key="fmt_kb")
            if st.button("Export KB", type="primary"):
                layout.outputs.mkdir(parents=True, exist_ok=True)
                with st.status("Exporting…", expanded=False) as s:
                    try:
                        if fmt_kb == "md":
                            text = bundle_kb_markdown(layout, index)
                            target = layout.outputs / "kb_bundle.md"
                            target.write_text(text, encoding="utf-8")
                        else:
                            text = render_kb_html(layout, index)
                            target = layout.outputs / "kb_index.html"
                            target.write_text(text, encoding="utf-8")
                        s.update(label="Done", state="complete")
                    except Exception as exc:
                        st.error(f"Export failed: {exc}")
                        s.update(label="Error", state="error")
                        st.stop()
                st.download_button(
                    label=f"Download {target.name}",
                    data=target.read_bytes(),
                    file_name=target.name,
                    mime=_MIME[fmt_kb],
                )
        else:
            if not titles:
                st.info("No wiki pages yet — compile some documents first.")
            else:
                chosen_title = st.selectbox("Page", titles, key="export_page")
                fmt = st.selectbox("Format", ["html", "md", "docx", "pptx", "pdf", "marp"], key="fmt_page")
                if st.button("Export", type="primary"):
                    page = next(p for p in pages if p["title"] == chosen_title)
                    wiki_path = Path(page["wiki_path"])
                    md_text = wiki_path.read_text(encoding="utf-8")
                    layout.outputs.mkdir(parents=True, exist_ok=True)
                    base = layout.outputs / wiki_path.stem

                    with st.status("Exporting…", expanded=False) as s:
                        try:
                            if fmt == "md":
                                target = base.with_suffix(".md")
                                target.write_text(md_text, encoding="utf-8")
                            elif fmt == "html":
                                target = base.with_suffix(".html")
                                target.write_text(render_page_html(wiki_path), encoding="utf-8")
                            elif fmt == "docx":
                                target = base.with_suffix(".docx")
                                md_to_docx(md_text, target, title=chosen_title)
                            elif fmt == "pptx":
                                target = base.with_suffix(".pptx")
                                md_to_pptx(md_text, target, deck_title=chosen_title)
                            elif fmt == "marp":
                                target = base.with_suffix(".marp.md")
                                target.write_text(page_to_marp(wiki_path), encoding="utf-8")
                            elif fmt == "pdf":
                                target = base.with_suffix(".pdf")
                                html_to_pdf(render_page_html(wiki_path), target)
                            s.update(label="Done", state="complete")
                        except PDFExportNotAvailable as exc:
                            st.error(str(exc))
                            s.update(label="Error", state="error")
                            st.stop()
                        except Exception as exc:
                            st.error(f"Export failed: {exc}")
                            s.update(label="Error", state="error")
                            st.stop()

                    st.download_button(
                        label=f"Download {target.name}",
                        data=target.read_bytes(),
                        file_name=target.name,
                        mime=_MIME[fmt],
                    )

    # ---- 5b. Slides ----
    with tab_slides:
        if not titles:
            st.info("No wiki pages yet.")
        else:
            slide_title = st.selectbox("Page", titles, key="slides_page")
            show_preview = st.checkbox("Show HTML preview inline")

            if st.button("Generate Marp slides", type="primary"):
                page = next(p for p in pages if p["title"] == slide_title)
                wiki_path = Path(page["wiki_path"])
                layout.outputs.mkdir(parents=True, exist_ok=True)

                with st.status("Generating slides…", expanded=False) as s:
                    try:
                        marp_md = page_to_marp(wiki_path)
                        target = layout.outputs / f"{wiki_path.stem}.marp.md"
                        target.write_text(marp_md, encoding="utf-8")
                        s.update(label="Done", state="complete")
                    except Exception as exc:
                        st.error(f"Slide generation failed: {exc}")
                        s.update(label="Error", state="error")
                        st.stop()

                st.download_button(
                    label=f"Download {target.name}",
                    data=target.read_bytes(),
                    file_name=target.name,
                    mime="text/markdown",
                )

                if show_preview:
                    html_preview = render_marp_html(marp_md)
                    st.html(html_preview)

    # ---- 5c. Charts ----
    with tab_charts:
        if st.button("Regenerate charts"):
            with st.status("Generating charts…", expanded=False) as s:
                paths = generate_kb_charts(layout, index)
                s.update(label=f"{len(paths)} chart(s) generated", state="complete")
            if not paths:
                st.info("No data to chart yet.")

        charts_dir = layout.outputs / "charts"
        if charts_dir.exists():
            imgs = sorted(charts_dir.glob("*.png"))
            if imgs:
                for img in imgs:
                    st.image(str(img), caption=img.stem.replace("_", " ").title())
            else:
                st.info("No charts yet — click Regenerate charts.")
        else:
            st.info("No charts yet — click Regenerate charts.")


def _stats(layout: KBLayout, index: MetaIndex) -> None:
    st.header("Stats")
    pages = index.all_pages()
    raw = index.all_raw_docs()
    pending = index.pending_raw_docs()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wiki pages", len(pages))
    c2.metric("Raw docs", len(raw))
    c3.metric("Pending", len(pending))
    avg = sum(p["confidence"] or 0 for p in pages) / len(pages) if pages else 0
    c4.metric("Avg confidence", f"{avg:.0%}" if pages else "—")

    from kompyla.presenter.charts import generate_kb_charts
    if st.button("Refresh charts"):
        generate_kb_charts(layout, index)

    charts_dir = layout.outputs / "charts"
    if charts_dir.exists():
        for img in sorted(charts_dir.glob("*.png")):
            st.image(str(img), caption=img.stem.replace("_", " ").title())


def _advanced(layout: KBLayout, index: MetaIndex, schema: DomainSchema, cfg) -> None:
    st.header("Advanced")
    tab_synth, tab_crossref = st.tabs(["Synth Q&A", "Crossref"])

    # ---- 6a. Synth Q&A ----
    with tab_synth:
        st.subheader("Generate training data")
        st.caption(
            "Produces a JSONL file of (prompt, completion) pairs from high-confidence "
            "wiki pages, suitable for fine-tuning LLMs."
        )

        pages = index.all_pages()
        min_conf = st.slider("Min confidence", 0.5, 1.0, 0.7, 0.05)
        eligible = [p for p in pages if (p["confidence"] or 0) >= min_conf]
        st.caption(f"{len(eligible)} page(s) eligible at this threshold.")

        pairs_per_page = st.number_input("Q&A pairs per page", min_value=1, max_value=10, value=3)

        if st.button("Generate training data", type="primary", disabled=not eligible):
            from kompyla.synth.generator import generate_training_data, save_training_data

            llm = get_provider(cfg.llm)
            layout.outputs.mkdir(parents=True, exist_ok=True)
            target = layout.outputs / "training_data.jsonl"

            with st.status(
                f"Generating {pairs_per_page} pair(s) × {len(eligible)} page(s) "
                f"using {cfg.llm.model}…",
                expanded=True,
            ) as s:
                try:
                    records = generate_training_data(
                        layout, index, llm,
                        min_confidence=min_conf,
                        pairs_per_page=int(pairs_per_page),
                    )
                    save_training_data(records, target)
                    s.update(label=f"Done — {len(records)} record(s)", state="complete")
                except Exception as exc:
                    st.error(f"Generation failed: {exc}")
                    s.update(label="Error", state="error")
                    st.stop()

            st.download_button(
                label=f"Download {target.name} ({len(records)} records)",
                data=target.read_bytes(),
                file_name=target.name,
                mime="application/x-ndjson",
            )

    # ---- 6b. Crossref ----
    with tab_crossref:
        st.subheader("Cross-reference with another KB")
        st.caption("Finds pages with overlapping topics between this KB and a second one.")

        target_path_str = st.text_input(
            "Path to second KB",
            placeholder="/path/to/other_kb",
        )
        threshold = st.slider("Similarity threshold (Jaccard)", 0.05, 0.5, 0.15, 0.05)
        use_llm = st.checkbox("Annotate connections with LLM notes (slower)")

        if st.button("Find connections", type="primary", disabled=not target_path_str.strip()):
            from kompyla.crossref.bridge import find_connections, write_crossref_report
            import pandas as pd

            target_path = Path(target_path_str.strip())
            target_layout = KBLayout(target_path)

            if not target_layout.schema_file.exists():
                st.error(f"No Kompyla KB found at `{target_path}` — schema file missing.")
                st.stop()

            target_index = MetaIndex(target_layout.meta_db)
            target_domain = (
                yaml.safe_load(target_layout.kb_config.read_text()).get("domain", target_path.name)
                if target_layout.kb_config.exists()
                else target_path.name
            )
            llm = get_provider(cfg.llm) if use_llm else None

            with st.status(
                f"Comparing `{layout.root.name}` ↔ `{target_domain}`…",
                expanded=True,
            ) as s:
                try:
                    results = find_connections(
                        layout, index,
                        target_layout, target_index,
                        threshold=threshold,
                        llm=llm,
                    )
                    target_index.close()
                    report_path = write_crossref_report(results, layout, target_domain)
                    s.update(label=f"Done — {len(results)} connection(s)", state="complete")
                except Exception as exc:
                    st.error(f"Crossref failed: {exc}")
                    s.update(label="Error", state="error")
                    st.stop()

            st.metric("Connections found", len(results))

            if results:
                df = pd.DataFrame([
                    {
                        "Source page": r.source_title,
                        "Target page": r.target_title,
                        "Similarity": f"{r.similarity:.0%}",
                        "Shared terms": ", ".join(r.shared_terms[:6]),
                        "Note": r.note or "",
                    }
                    for r in results
                ])
                st.dataframe(df, use_container_width=True)

                st.download_button(
                    label=f"Download report ({report_path.name})",
                    data=report_path.read_bytes(),
                    file_name=report_path.name,
                    mime="text/markdown",
                )
            else:
                st.info("No overlapping pages found above the similarity threshold.")


main()
