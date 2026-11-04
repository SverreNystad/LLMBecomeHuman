# One Python image serves the static frontend + FastAPI API and can run CLI experiments.
# There is no separate Node/frontend build: dashboard_assets are served by FastAPI.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY detroit_benchmark/ ./detroit_benchmark/
COPY examples/ ./examples/
COPY demo_runs/ ./demo_runs/
COPY tests/ ./tests/
COPY pytest.ini ./

EXPOSE 8000
CMD ["python", "-m", "detroit_benchmark", "dashboard", "--runs-dir", "/app/runs", "--graphs-dir", "/app/data", "--host", "0.0.0.0", "--port", "8000"]
