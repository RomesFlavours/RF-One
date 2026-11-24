# RF-One Conoscenza service (10 System/Conoscenza/README.md).
# Build context: a Conoscenza-only source snapshot (see README) with
#   Dockerfile, requirements.txt, RF-One Data Store/{conoscenza.py, conoscenza_aws_setup.py,
#   rfone_data_store/__init__.py, rfone_data_store/conoscenza/}
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
COPY ["requirements.txt", "/app/requirements.txt"]
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
WORKDIR "/app/RF-One Data Store"
RUN useradd --system --uid 10001 conoscenza
USER conoscenza
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "60", "rfone_data_store.conoscenza.http_app:app"]
