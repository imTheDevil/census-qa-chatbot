# Single image used for both services (API + UI); the command differs per service.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code, recipes, source markdown, and UI config.
COPY app/ ./app/
COPY ui/ ./ui/
COPY recipes/ ./recipes/
COPY data/markdown/ ./data/markdown/
COPY .chainlit/ ./.chainlit/
COPY chainlit.md ./

# Runtime dirs (populated by ingestion / at request time).
RUN mkdir -p data/processed workspace/sessions

EXPOSE 8000 8501

# Default command (overridden by docker-compose per service).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
