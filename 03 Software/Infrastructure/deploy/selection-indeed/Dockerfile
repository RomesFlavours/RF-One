# Build from repository root:
# docker build -f "03 Software/Infrastructure/deploy/selection-indeed/Dockerfile" .
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 DISPLAY=:99 HOME=/home/browser
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc tini && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY ["03 Software/Infrastructure/deploy/selection-indeed/requirements.txt", "/app/requirements.txt"]
RUN pip install --no-cache-dir -r requirements.txt \
    && PLAYWRIGHT_BROWSERS_PATH=/opt/browsers playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 browser \
    && mkdir /data && chmod 700 /data
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
COPY ["03 Software/Selection/indeed_protocol.py", "/app/indeed_protocol.py"]
COPY ["03 Software/Selection/indeed_worker", "/app/indeed_worker"]
COPY ["03 Software/Infrastructure/deploy/selection-indeed/start.sh", "/app/start.sh"]
COPY ["03 Software/Infrastructure/deploy/selection-indeed/gunicorn.conf.py", "/app/gunicorn.conf.py"]
COPY ["03 Software/Infrastructure/deploy/selection-indeed/chromium-as-browser", "/app/chromium-as-browser"]
RUN sed -i 's/\r$//' /app/start.sh /app/chromium-as-browser && chmod 755 /app/start.sh /app/chromium-as-browser
ENV RFONE_INDEED_BROWSER_LAUNCHER=/app/chromium-as-browser
EXPOSE 8080
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["/app/start.sh"]
