# SELECTION_AWS_PUBLISH_001 — the Selection service (App Runner `rfone-selection`).
# Build context: made by release_selection.py from one pushed Git commit —
# `RF-One Data Store/`, `Selection/`, this Dockerfile and RELEASE_COMMIT.
# The CodeBuild project's own buildspec (buildspec.yml here) refuses any
# other context. AI runs through Bedrock (boto3); no .env is copied.
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["Selection/requirements.txt", "/app/selection-requirements.txt"]

RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/selection-requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["Selection", "/app/Selection"]
COPY ["RELEASE_COMMIT", "/app/RELEASE_COMMIT"]

WORKDIR "/app/Selection"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
