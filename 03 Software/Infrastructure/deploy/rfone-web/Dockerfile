FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["RF-One Web/requirements.txt", "/app/rfone-web-requirements.txt"]

RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/rfone-web-requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["RF-One Web", "/app/RF-One Web"]
COPY ["Training", "/app/Training"]
COPY ["Shared UI", "/app/Shared UI"]
# The Tips calculation service (used by tips_validation_routes.py) imports the
# Clover connector, which loads clover_explorer from /app/Clover Data Explorer.
COPY ["Clover Data Explorer", "/app/Clover Data Explorer"]

WORKDIR "/app/RF-One Web"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
