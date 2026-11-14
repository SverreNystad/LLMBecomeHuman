# One Python image serves the static frontend + FastAPI API and can run CLI experiments.
# There is no separate Node/frontend build: dashboard_assets are served by FastAPI.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-cache

COPY detroit_benchmark/ ./detroit_benchmark/
COPY examples/ ./examples/
COPY demo_runs/ ./demo_runs/
COPY tests/ ./tests/
COPY pytest.ini ./

# Saved runs + story data baked in so the dashboard shows them without mounts
# (Kubernetes). Same layout as docker-compose, which mounts over these read-only.
COPY data/ ./data/
COPY runs/ ./saved_runs/runs/
COPY demo_runs/ ./saved_runs/previews/

EXPOSE 8000
CMD ["python", "-m", "detroit_benchmark", "dashboard", "--runs-dir", "/app/saved_runs", "--graphs-dir", "/app/data", "--host", "0.0.0.0", "--port", "8000"]
