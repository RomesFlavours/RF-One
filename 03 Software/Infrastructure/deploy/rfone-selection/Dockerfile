# SELECTION_AWS_PUBLISH_001 — the Selection service (App Runner `rfone-selection`).
# Build context: a zip of committed files holding `RF-One Data Store/` and
# `Selection/` plus this Dockerfile, server_entrypoint.py and the Linux lock file.
# No .env or desktop session is copied. Server AI uses explicit API credentials
# injected at runtime; OCR and extraction remain available independently.
FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY ["requirements-linux.lock", "/app/requirements-linux.lock"]
RUN pip install --no-cache-dir --no-compile -r /app/requirements-linux.lock && pip check

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["Selection", "/app/Selection"]

COPY ["server_entrypoint.py", "/app/server_entrypoint.py"]
WORKDIR "/app/Selection"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1
ENV RFONE_SELECTION_RULE_AI_PROVIDER=openai RFONE_SELECTION_ENGINE=conversation RFONE_SELECTION_REQUIRE_RFONE_LOGIN=1

ENTRYPOINT ["python", "/app/server_entrypoint.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "150", "--graceful-timeout", "110", "app:app"]

ARG RFONE_RELEASE_COMMIT
LABEL org.opencontainers.image.revision=$RFONE_RELEASE_COMMIT
