FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# NOTE: data/ is excluded from the image (.dockerignore: /data/), so the
# FAISS index, metadata, chunks.json and auth stores are NOT baked in.
# Seed them before first boot - either bind-mount the host ./data directory
# (docker-compose.yml already maps ./data:/app/data) or populate /app/data
# in the container with the corpus build scripts.

# Run with uvicorn.
# Single worker on purpose: each worker loads the embedding model and the
# whole FAISS index into its own process, so --workers 4 multiplies RAM use
# with no benefit for this retrieval-bound app (compose sets no memory
# limits). Scale with more replicas instead of more workers.
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
