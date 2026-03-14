# ── Stage 1: Builder ── Install dependencies in isolated layer
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements-engine.txt .
RUN pip install --user --no-cache-dir -r requirements-engine.txt

# ── Stage 2: Runtime ── Minimal production image
FROM python:3.11-slim
WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy source code (respects .dockerignore)
COPY . .

# Data directory (Volume mount point)
RUN mkdir -p .data/genome

EXPOSE 8800

# --workers 1: SessionManager memory pool must be globally unique
# --loop uvloop: asyncio performance optimization
CMD ["uvicorn", "engine_api:app", \
     "--host", "0.0.0.0", "--port", "8800", \
     "--workers", "1", "--loop", "uvloop"]
