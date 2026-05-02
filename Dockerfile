# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for trafilatura, lxml, WeasyPrint (optional), and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt1-dev libffi-dev libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY kompyla/ kompyla/

# Install with optional pdf support; no dev extras
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e ".[pdf]"


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 libffi8 libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages and source from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin/kompyla    /usr/local/bin/kompyla
COPY --from=builder /usr/local/bin/streamlit  /usr/local/bin/streamlit
COPY --from=builder /build/kompyla            /app/kompyla

# KB is mounted at runtime — /kb is the default mount point
VOLUME ["/kb"]

# Streamlit port
EXPOSE 8501

# Environment
ENV KOMPYLA_KB=/kb \
    PYTHONUNBUFFERED=1

# Default: launch the Streamlit UI
CMD ["streamlit", "run", "/app/kompyla/ui/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--browser.gatherUsageStats=false"]
