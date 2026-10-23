# SELECTION_AWS_PUBLISH_001 — the Selection service (App Runner `rfone-selection`).
# Build context: a zip of committed files holding `RF-One Data Store/` and
# `Selection/` plus this Dockerfile and buildspec.yml at its root.
# No .env is copied. AI runs through AWS Bedrock (boto3, from the Data Store
# requirements) with the instance role; RFONE_SELECTION_AI / _AI_CV switch it on.
# One worker (with threads): the app migrates the shared schema at import, and
# two workers would run the same Alembic upgrade concurrently.
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["Selection/requirements.txt", "/app/selection-requirements.txt"]

RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/selection-requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["Selection", "/app/Selection"]

WORKDIR "/app/Selection"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
