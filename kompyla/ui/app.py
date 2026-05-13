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

    page = st.sidebar.radio("View", ["Browse", "Search", "Ask", "Stats"])

    if page == "Browse":
        _browse(layout, index)
    elif page == "Search":
        _search(layout, index)
    elif page == "Ask":
        _ask(layout, index, schema, cfg)
    elif page == "Stats":
        _stats(layout, index)


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


main()
