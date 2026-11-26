# Build context: the "03 Software" folder (needs RF-One Data Store and Clover Data Explorer).
# One image, two uses: the web site (default command) and one order reader per restaurant
# (command: python manage.py sync --location-id <id>).
FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY ["RF-One Data Store/requirements.txt", "/app/rfone-data-store-requirements.txt"]
COPY ["Clover Data Explorer/requirements.txt", "/app/clover-explorer-requirements.txt"]
RUN pip install --no-cache-dir -r /app/rfone-data-store-requirements.txt \
    && pip install --no-cache-dir -r /app/clover-explorer-requirements.txt \
    && pip install --no-cache-dir "Flask>=3.0,<4" gunicorn==23.0.0
COPY ["RF-One Data Store", "/app/RF-One Data Store"]
COPY ["Clover Data Explorer", "/app/Clover Data Explorer"]
COPY ["Kitchen Board", "/app/Kitchen Board"]
WORKDIR "/app/Kitchen Board"
EXPOSE 8080
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "30", "wsgi:app"]
