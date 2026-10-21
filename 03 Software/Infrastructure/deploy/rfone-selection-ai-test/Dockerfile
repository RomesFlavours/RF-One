# SELECTION_AI_TEST_DEPLOY_001 — Selection AI prototype, TEST environment only (App Runner `rfone-selection-ai-test`).
# Build context: a zip holding `RF-One Data Store/` and `Selection Prototype/` plus this Dockerfile and buildspec.yml.
# No .env and no secret is copied: configuration comes from App Runner environment variables and Secrets Manager.
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["Selection Prototype/requirements.txt", "/app/prototype-requirements.txt"]
RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/prototype-requirements.txt

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["Selection Prototype", "/app/Selection Prototype"]

WORKDIR "/app/Selection Prototype"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1
# One worker (threads for concurrency): the schema is migrated at import, never by two processes at once.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "180", "app:app"]
