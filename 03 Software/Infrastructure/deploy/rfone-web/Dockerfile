FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["RF-One Web/requirements.txt", "/app/rfone-web-requirements.txt"]

RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/rfone-web-requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
# MIGRATIONS.md: refuse an image whose chain lacks the revision applied on AWS.
ARG RFONE_AWS_SCHEMA_REVISION=
RUN python "/app/RF-One Data Store/check_migration_chain.py"
COPY ["RF-One Web", "/app/RF-One Web"]
COPY ["Training", "/app/Training"]
COPY ["Shared UI", "/app/Shared UI"]
# The Tips calculation service (used by tips_validation_routes.py) imports the
# Clover connector, which loads clover_explorer from /app/Clover Data Explorer.
COPY ["Clover Data Explorer", "/app/Clover Data Explorer"]

WORKDIR "/app/RF-One Web"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

# Bounds every AI call made without its own limit (Bank AI rules, Tips
# authoring) so it cannot hold a request thread for minutes.
ENV RFONE_AI_TIMEOUT_SECONDS=45

# gthread: a worker waiting on the AI still serves other requests on its other
# threads. In gthread mode --timeout only restarts a worker whose main loop
# stops; it does not end a slow request, so each request is bounded by its own
# AI limit (45 s per interview turn, below CloudFront's 60 s origin timeout).
# 4 threads per worker: a request can hold two database connections, so one
# worker needs at most 8, well inside SQLAlchemy's default pool of 15, and the
# two workers together stay a small share of the RDS connection limit.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "app:app"]
