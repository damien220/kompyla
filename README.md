# Kompyla

**Autonomous research agent that builds and evolves a structured knowledge base.**
![Kompyla](Kompyla.jpg)

Kompyla treats an LLM like a compiler: raw documents go in, structured wiki pages come out. It extends Andrej Karpathy's LLM Knowledge Base pattern with an active retrieval layer that fetches new sources automatically, a self-evolving feedback loop that detects gaps and flags stale knowledge, and a full presentation pipeline (HTML, DOCX, PPTX, slide decks, charts).

```
Research query
     │
     ▼
┌──────────────┐    web · arxiv · GitHub · RSS · YouTube
│ Search Agent │──────────────────────────────────────────
└──────┬───────┘   dedup + relevance filter
       │ clean .md files
       ▼
  raw/ directory
       │
       ▼
┌──────────────┐
│  Compiler    │──── LLM: raw → structured wiki page
└──────┬───────┘
       │
       ▼
  wiki/ (the KB)  ◄──── Health check · Gap detection · Feedback
       │
       ▼
┌──────────────┐
│   Present    │──── Q&A · slides · charts · HTML · DOCX · PPTX
└──────────────┘
```

```mermaid
flowchart TD
    %% ============ 1. INITIALISATION ============
    subgraph INIT["1 — Initialisation"]
        U1[/User: research domain/]
        I1[kompyla init]
        I2[LLM: generate schema]
        I3[(Domain Schema)]
        I4[(KB directory structure)]
        U1 --> I1 --> I2 --> I3
        I2 --> I4
    end

    %% ============ 2. RETRIEVAL ============
    subgraph RETR["2 — Retrieval"]
        R0[Retrieval Orchestrator]
        R1[Source connectors:<br/>Web · arXiv · GitHub<br/>RSS · YouTube]
        R2[Dedup: SHA-256<br/>+ MinHash]
        R3[Relevance filter<br/>LLM scoring]
        R4[(raw/ documents)]
        R0 --> R1 --> R2 --> R3 --> R4
    end

    %% ============ 3. COMPILATION ============
    subgraph COMP["3 — Compilation"]
        C1[Pending raw docs]
        C2[LLM Compiler]
        C3{Wiki page<br/>exists?}
        C4[Write new page]
        C5[LLM merge pass]
        C6[Master Index update]
        C1 --> C2 --> C3
        C3 -->|No| C4 --> C6
        C3 -->|Yes| C5 --> C6
    end

    %% ============ 4. EVOLUTION ============
    subgraph EVOL["4 — Evolution"]
        E0[(Wiki KB)]
        E1[Lint: links, stale,<br/>orphans, confidence]
        E2[Gap Detection:<br/>broken-link + LLM gaps]
        E3[/User Feedback/]
        E4[Confidence delta]
        E0 --> E1
        E0 --> E2
        E0 --> E3 --> E4 --> E0
    end

    %% ============ 5. QUERY & PRESENTATION ============
    subgraph PRES["5 — Query & Presentation"]
        Q1[/User question/]
        Q2[Q&A Engine]
        Q3[LLM answer<br/>with citations]
        Q4{Save as<br/>synthesis?}
        Q5[(Synthesis page)]
        P0[Export: HTML · DOCX<br/>PPTX · Marp · PDF<br/>Markdown · Charts]
        Q1 --> Q2 --> Q3 --> Q4
        Q4 -->|Yes| Q5
    end

    %% ============ 6. AUTOMATION ============
    subgraph AUTO["6 — Automation"]
        A1[Scheduler<br/>daemon / cron]
        A2[Full cycle: retrieve<br/>compile · lint · gaps]
        A3[Cross-Reference Bridge]
        A4[(Other domain KB)]
        A5[(Comparison report)]
        A1 --> A2
        A3 --> A4
        A3 --> A5
    end

    %% ============ CROSS-LAYER FLOWS (minimal) ============
    I3 -->|seed queries| R0
    R4 --> C1
    C6 --> E0
    E2 -->|auto-fill| R0
    E0 --> Q2
    E0 --> P0
    Q5 -.-> E0
    A2 -->|triggers| R0

    %% ============ STYLING ============
    classDef initLayer fill:#fff4d6,stroke:#b8860b,stroke-width:2px,color:#000
    classDef retrLayer fill:#d6e8ff,stroke:#1f4e8c,stroke-width:2px,color:#000
    classDef compLayer fill:#d6f5d6,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef evolLayer fill:#ffe2c4,stroke:#cc5500,stroke-width:2px,color:#000
    classDef presLayer fill:#e8d6ff,stroke:#5b2c8c,stroke-width:2px,color:#000
    classDef autoLayer fill:#e0e0e0,stroke:#555555,stroke-width:2px,color:#000

    class INIT initLayer
    class RETR retrLayer
    class COMP compLayer
    class EVOL evolLayer
    class PRES presLayer
    class AUTO autoLayer

    ...
```

---

## What Kompyla does

| Capability                  | Description                                                                                                                      |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **KB scaffolding**          | LLM generates a domain schema (page types, entity categories, seed queries) from a plain-English topic                           |
| **Agentic retrieval**       | Searches the web (Serper / Brave / Exa / SerpAPI; DuckDuckGo fallback), arXiv, GitHub, RSS feeds, and YouTube transcripts       |
| **Deduplication**           | SHA-256 exact matching + MinHash LSH for near-duplicate detection (Jaccard ≥ 0.85)                                               |
| **Incremental compilation** | Raw `.md` files are compiled into structured wiki pages; when a page already exists, a second LLM pass merges new information in |
| **Health checks**           | Finds broken internal links, stale pages (>180 days), low-confidence pages, and orphans                                          |
| **Gap detection**           | Deterministic broken-link gaps + LLM-suggested missing topics                                                                    |
| **Q&A**                     | Natural-language questions answered from the wiki with citations; answers can be saved back as synthesis pages                   |
| **Presentation**            | HTML, Markdown bundle, DOCX, PPTX, Marp slide decks, and PDF (optional) exports                                                  |
| **Charts**                  | Confidence histogram, pages-by-type, and raw-docs-by-source PNGs                                                                 |
| **Web UI**                  | Streamlit app with Browse, Search, Ask, and Stats tabs; guided setup screen on first run                                         |
| **Scheduler**               | Periodic research cycle (fetch → compile → lint → gaps) with configurable interval                                               |
| **Cross-referencing**       | Find shared topics between two separate domain KBs                                                                               |
| **Feedback**                | Flag pages as wrong, outdated, excellent, or unclear; apply to confidence scores                                                 |
| **Synthetic data**          | Generate Q&A training pairs from high-confidence pages for model fine-tuning                                                     |

---

## Requirements

- Python 3.11 or later
- One LLM provider — see [LLM providers](#llm-providers) below

Optional extras:

```bash
pip install "kompyla[pdf]"          # WeasyPrint for PDF export
pip install "kompyla[search]"       # Exa and SerpAPI backends
pip install "kompyla[pdf,search]"   # both
```

---

## LLM providers

Kompyla supports four providers. The `provider` key in `config.yaml` selects which one is used.

| Provider      | Config value  | Required env var    | Notes                                                              |
| ------------- | ------------- | ------------------- | ------------------------------------------------------------------ |
| **Ollama**    | `ollama`      | —                   | Fully offline. Install from [ollama.com](https://ollama.com), then `ollama pull llama3.2` |
| **Anthropic** | `anthropic`   | `ANTHROPIC_API_KEY` | Claude models (e.g. `claude-sonnet-4-6`)                           |
| **OpenAI**    | `openai`      | `OPENAI_API_KEY`    | GPT-4o and other OpenAI models                                     |
| **Gemini**    | `gemini`      | `GEMINI_API_KEY`    | Gemini 2.0 Flash and other Google models (uses `google-genai` SDK) |

---

## Installation

### From source

```bash
git clone https://github.com/damien220/kompyla.git
cd kompyla
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### PyPI

```bash
pip install kompyla
```

---

## Docker

Kompyla ships with a `Dockerfile` and `docker-compose.yml` so you can run the full stack — Streamlit UI, CLI, scheduler, and optionally an offline Ollama instance — without touching your local Python environment.

### Build the image

```bash
docker build -t kompyla:latest .
```

The image installs `kompyla[pdf,search]` so all LLM providers and all web search backends are available out of the box.

### First run — initialise the KB

On first start the KB directory (`/kb`) is empty. The Streamlit UI detects this automatically and shows a **setup screen** where you type your research domain and click **Initialise KB**. The LLM generates the domain schema and the app reloads into the normal Browse / Search / Ask / Stats view.

If you prefer the CLI:

```bash
docker compose --profile cli run --rm cli init "electric vehicles" --kb /kb
```

### Option A — Streamlit UI only (bring your own LLM)

```bash
# With Anthropic
ANTHROPIC_API_KEY=sk-... KOMPYLA_KB_PATH=./my_kb docker compose up kompyla-ui

# With a locally running Ollama on the host
OLLAMA_BASE_URL=http://host.docker.internal:11434 \
KOMPYLA_KB_PATH=./my_kb docker compose up kompyla-ui
```

Open `http://localhost:8501` in your browser.

### Option B — Full offline stack (Ollama bundled)

```bash
# Pull the model once (cached in a named Docker volume)
docker compose --profile ollama run --rm ollama ollama pull llama3.2

# Start UI + Ollama together
KOMPYLA_KB_PATH=./my_kb docker compose --profile ollama up
```

### One-off CLI commands

The `cli` service lets you run any `kompyla` command against the mounted KB:

```bash
# Compile documents
docker compose --profile cli run --rm cli compile --kb /kb

# Ask a question
docker compose --profile cli run --rm cli query "What is solid-state battery?" --kb /kb
```

### Background scheduler (auto-research)

```bash
KOMPYLA_KB_PATH=./my_kb docker compose --profile scheduler up -d scheduler
```

### Environment variables for Docker

Copy `.env.example` to `.env` in the project root (never commit `.env`):

```bash
# .env
KOMPYLA_KB_PATH=./my_kb      # host path mounted as /kb inside the container
KOMPYLA_PORT=8501             # host port for the UI (default 8501)

# LLM — uncomment the provider you use
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AIza...
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# Web search — first key present wins; DuckDuckGo used if none are set
# SERPER_API_KEY=...
# BRAVE_API_KEY=...
# EXA_API_KEY=...
# SERPAPI_API_KEY=...

# Optional
# GITHUB_TOKEN=ghp_...
```

Then simply:

```bash
docker compose up                          # UI only
docker compose --profile ollama up         # UI + bundled Ollama
docker compose --profile scheduler up -d  # add background scheduler
```

---

## Quick start

### 1. Configure your LLM

Copy the example config and edit it:

```bash
mkdir -p ~/.kompyla
cp config.yaml.example ~/.kompyla/config.yaml
```

Default uses Ollama + `llama3.2`. To use Claude instead:

```yaml
# ~/.kompyla/config.yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-6
```

Set `ANTHROPIC_API_KEY` in your shell (or add `anthropic_api_key:` to the config file).

### 2. Create a knowledge base

```bash
kompyla init "electric vehicles" --path ./ev_kb
cd ev_kb
```

This calls the LLM to generate a domain schema with page types, entity categories, and seed search queries.

### 3. Fetch sources

```bash
kompyla search                       # uses schema seed queries, all enabled sources
kompyla search "solid-state batteries" --sources web,arxiv
kompyla fetch https://example.com/article
kompyla add-youtube https://www.youtube.com/watch?v=...
```

Fetched documents land in `raw/` as markdown files.

### 4. Compile into the wiki

```bash
kompyla compile
```

Each raw document is transformed by the LLM into a structured wiki page in `wiki/`. If a page for that topic already exists, the new content is merged in.

### 5. Explore

```bash
kompyla status                       # overview metrics
kompyla query "What is the range of the Tesla Model 3?"
kompyla serve                        # open http://localhost:8501
```

---

## All commands

```text
kompyla init <domain>                  Scaffold a new KB and generate its domain schema
kompyla compile                        Compile raw/ documents into wiki/ pages
kompyla status                         Show KB metrics (pages, raw docs, confidence)

kompyla search [query]                 Retrieve from web/arxiv/GitHub/RSS/YouTube
kompyla fetch <url>                    Fetch and save a single URL to raw/
kompyla add-youtube <url>              Fetch a YouTube transcript into raw/

kompyla query <question>               Answer a question from the wiki
kompyla lint                           Run health checks (broken links, stale, orphans)
kompyla gaps [--auto-fill]             Detect knowledge gaps; optionally fill them

kompyla export <title> -f html|md|docx|pptx|pdf|marp
kompyla export --all -f md|html        Whole-KB bundle
kompyla slides <title> [--html]        Generate a Marp slide deck
kompyla chart                          Generate stats PNGs

kompyla serve [--port 8501]            Launch Streamlit UI

kompyla schedule --enable --interval 24   Enable periodic research cycle
kompyla schedule --run-now               Run one cycle immediately
kompyla schedule --daemon                Loop forever
kompyla schedule --status                Show current schedule

kompyla crossref --kb-target path/to/other/kb   Find topic overlaps across KBs
kompyla feedback <title> --signal wrong|outdated|excellent|unclear
kompyla feedback --apply               Apply feedback deltas to confidence scores
kompyla synth [--out training.jsonl]   Generate Q&A training data
```

---

## Configuration reference

`~/.kompyla/config.yaml` (env vars override file values):

```yaml
llm:
  provider: ollama          # "ollama", "anthropic", "openai", or "gemini"
  model: llama3.2           # any Ollama model; or "claude-sonnet-4-6", "gpt-4o", "gemini-2.0-flash"
  ollama_base_url: http://localhost:11434
  # anthropic_api_key: ...  # or ANTHROPIC_API_KEY env var
  # openai_api_key: ...     # or OPENAI_API_KEY env var
  # gemini_api_key: ...     # or GEMINI_API_KEY env var

retrieval:
  enabled_sources: [web, arxiv, github, rss]   # add "youtube" if needed
  max_per_source: 5
  min_relevance: 0.5
  use_relevance_filter: true
  # Web search — first key present wins; DuckDuckGo used as free fallback if none set
  # serper_api_key: ...     # or SERPER_API_KEY env var
  # brave_api_key: ...      # or BRAVE_API_KEY env var
  # exa_api_key: ...        # or EXA_API_KEY env var   (requires kompyla[search])
  # serpapi_api_key: ...    # or SERPAPI_API_KEY env var (requires kompyla[search])
  # github_token: ...       # or GITHUB_TOKEN env var
  rss_feeds:
    - https://hnrss.org/frontpage
  youtube_languages: [en]
```

### Environment variables

| Variable            | Purpose                                                                       |
| ------------------- | ----------------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) API key                                                    |
| `OPENAI_API_KEY`    | OpenAI API key                                                                |
| `GEMINI_API_KEY`    | Google Gemini API key                                                         |
| `OLLAMA_BASE_URL`   | Override Ollama server URL (default `http://localhost:11434`)                 |
| `SERPER_API_KEY`    | Serper web search — Google results, $1/1K queries                             |
| `BRAVE_API_KEY`     | Brave Search API — free tier: 2 K queries/month                               |
| `EXA_API_KEY`       | Exa.ai semantic search — free tier available (`kompyla[search]` required)    |
| `SERPAPI_API_KEY`   | SerpAPI multi-engine search (`kompyla[search]` required)                      |
| `GITHUB_TOKEN`      | GitHub API token (raises rate limits for the GitHub connector)                |
| `KOMPYLA_KB`        | Default KB path (used by `kompyla serve` and the Docker image)                |

> **Web search fallback** — if no search API key is set, Kompyla falls back to DuckDuckGo automatically (no key required, no extra package). Snippet results are enriched with full page text via trafilatura.

---

## Knowledge base layout

```
my_kb/
├── kompyla.yaml          Domain config + schedule state
├── raw/                  Fetched source documents (auto-populated)
│   ├── web/
│   ├── arxiv/
│   ├── github/
│   └── youtube/
├── wiki/                 Compiled structured wiki pages
├── index/
│   ├── schema.yaml       Domain schema (page types, entities, relationships)
│   ├── index.md          Master index grouped by page type
│   ├── meta.db           SQLite metadata index
│   └── feedback.db       User feedback store
└── outputs/              Exports (HTML, DOCX, PPTX, charts, training data)
    ├── charts/
    └── training_data.jsonl
```

---

## Offline mode (Ollama)

Kompyla works entirely offline with Ollama — no API key or internet connection required for the LLM step.

```bash
# Install Ollama: https://ollama.com
ollama serve
ollama pull llama3.2          # or llama3.1, mistral, qwen2.5, etc.

# Set provider in config
# llm:
#   provider: ollama
#   model: llama3.2
```

Retrieval connectors (web, GitHub, YouTube) still require internet access, but the compilation, Q&A, and gap-detection steps are all local.

---

## Running tests

```bash
pip install -e ".[dev]"
pytest                   # 50 tests across all phases
pytest tests/test_phase5.py -v   # Phase 5 only
```

The test suite covers: deduplication, YouTube transcript parsing, KB health checks, Q&A page selection, all presenter/export modules, scheduler logic, feedback store, cross-KB referencing, and synth data parsing.

---

## Architecture overview

```
kompyla/
├── schema/         Domain schema generation and Pydantic models
├── storage/        KBLayout (filesystem), MetaIndex (SQLite)
├── llm/            LLMProvider ABC + OllamaProvider, AnthropicProvider, OpenAIProvider, GeminiProvider
├── retriever/      SourceConnector ABC + Web (multi-backend), arXiv, GitHub, RSS, YouTube
├── filter/         RelevanceScorer (LLM), Deduplicator (SHA-256 + MinHash)
├── compiler/       raw/ → wiki/ pipeline, incremental merge, linker
├── evolver/        lint, gap detection, confidence helpers
├── query/          Q&A with citation, synthesis page filing
├── presenter/      HTML, Markdown, DOCX, PPTX, Marp, PDF, charts
├── ui/             Streamlit app (Setup / Browse / Search / Ask / Stats)
├── scheduler/      Periodic cycle runner and schedule state
├── crossref/       Multi-KB topic bridge
├── feedback/       Feedback store and confidence delta application
├── synth/          Synthetic Q&A training data generator
└── cli.py          Typer CLI — all 17 commands
```

### Key design decisions

- **LLM as compiler, not chatbot** — the model transforms raw sources into structured knowledge; it does not answer from its own weights.
- **Incremental over one-shot** — every operation touches only the relevant slice of the KB.
- **Relevance before ingest** — the filter layer rejects noise at the edge; a small clean KB beats a large noisy one.
- **Markdown + SQLite as substrate** — plain files give portability and git-diffable history; SQLite adds queryable metadata without a server.
- **Confidence and provenance are first-class** — every wiki page carries a confidence score and a list of source documents.
- **Search with graceful degradation** — API-backed search (Serper → Brave → Exa → SerpAPI) is preferred when a key is configured; DuckDuckGo is the always-available zero-config fallback.

---

## Contributing

Contributions are welcome. Please follow these steps:

1. **Fork** the repository and create a feature branch:

   ```bash
   git checkout -b feature/my-improvement
   ```

2. **Install dev dependencies:**

   ```bash
   pip install -e ".[dev]"
   ```

3. **Write tests** for your change. The project targets 100% test coverage for deterministic modules (no LLM, no network).

4. **Run the full test suite** before opening a PR:

   ```bash
   pytest
   ```

5. **Follow existing code style:**
   - No type comments — use type annotations throughout.
   - No docstrings for obvious methods — a clear name beats a paragraph.
   - New source connectors must implement `SourceConnector` from `kompyla/retriever/base.py`.
   - New CLI commands go in `kompyla/cli.py` using the Typer pattern already established.

6. **Open a pull request** with a clear description of what changed and why.

### Adding a new LLM provider

1. Create `kompyla/llm/<name>_provider.py` implementing `LLMProvider` (single `chat(messages, system) -> str` method).
2. Import it in `kompyla/llm/__init__.py` and add a branch to `get_provider()`.
3. Add `<name>_api_key: str | None = None` to `LLMConfig` in `kompyla/config.py` and the `os.getenv(...)` override in `KompylaConfig.load()`.
4. Expose the env var in `.env.example` and in `docker-compose.yml` (the `x-env` anchor covers all services automatically).

### Adding a new source connector

```python
# kompyla/retriever/my_source.py
from kompyla.retriever.base import FetchedDoc, SourceConnector

class MySourceConnector(SourceConnector):
    @property
    def name(self) -> str:
        return "mysource"

    def search(self, query: str, max_results: int = 5) -> list[FetchedDoc]:
        ...

    def fetch_url(self, url: str) -> FetchedDoc | None:
        ...

    def is_available(self) -> bool:
        ...
```

Register it in `kompyla/retriever/__init__.py` and add it to `_build_connectors()` in `cli.py`.

---

## Roadmap

### Completed

- [x] KB scaffolding — domain schema generation from a plain-English topic
- [x] Agentic retrieval — web (Serper / Brave / Exa / SerpAPI / DuckDuckGo fallback), arXiv, GitHub, RSS, and YouTube connectors
- [x] Incremental compilation with LLM merge pass
- [x] Health checks — broken links, stale pages, orphans, low-confidence
- [x] Gap detection — deterministic + LLM-suggested topics
- [x] Natural-language Q&A with citation and synthesis page filing
- [x] Presentation exports — HTML, Markdown bundle, DOCX, PPTX, Marp slides, charts, PDF (optional)
- [x] Streamlit web UI — Setup (first-run), Browse, Search, Ask, Stats
- [x] Scheduled research cycle (`kompyla schedule --daemon`)
- [x] Multi-KB cross-referencing (`kompyla crossref`)
- [x] User feedback integration (`kompyla feedback`)
- [x] Synthetic Q&A training data generator (`kompyla synth`)
- [x] Docker image + `docker-compose.yml` — all LLM providers, all search backends, first-run UI
- [x] Four LLM providers: Ollama, Anthropic, OpenAI, Gemini (`google-genai` SDK)
- [x] Comprehensive README with architecture overview, contributing guide, and license
- [x] Architecture flowchart in README (Mermaid)
- [x] Publish to PyPI (`pip install kompyla`)

### Upcoming

- [ ] GitHub Actions CI for automated test runs on every push
- [ ] Embedding-based semantic search (sentence-transformers) as an alternative to keyword overlap
- [ ] Graph view of the wiki (entity relationships, cross-links) in the Streamlit UI
- [ ] Multi-user collaboration mode with shared feedback
- [ ] Example pre-built knowledge bases (electric vehicles, WebGPU frameworks)

---

## License

**MIT License**

Copyright (c) 2026 Kompyla Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## Acknowledgements

Kompyla is inspired by [Andrej Karpathy's LLM Knowledge Base](https://github.com/karpathy/llm.c) pattern — using an LLM as a compiler that transforms raw documents into structured, interlinked knowledge. Kompyla extends this with an active retrieval agent, a self-evolving feedback loop, and a full presentation pipeline.
