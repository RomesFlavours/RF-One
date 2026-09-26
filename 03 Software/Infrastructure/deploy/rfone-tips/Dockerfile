FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["Tips/requirements.txt", "/app/tips-requirements.txt"]
COPY ["Clover Data Explorer/requirements.txt", "/app/clover-explorer-requirements.txt"]

RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/tips-requirements.txt \
    && pip install --no-cache-dir -r /app/clover-explorer-requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["Tips", "/app/Tips"]
COPY ["Clover Data Explorer", "/app/Clover Data Explorer"]
COPY ["Shared UI", "/app/Shared UI"]
COPY ["Training", "/app/Training"]

WORKDIR "/app/Tips"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app/Clover Data Explorer"

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
