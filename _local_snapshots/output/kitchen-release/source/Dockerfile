FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY ["03 Software/RF-One Data Store", "/app/RF-One Data Store"]
COPY ["03 Software/RF-One Web", "/app/RF-One Web"]
COPY ["03 Software/Shared UI", "/app/Shared UI"]
COPY release /app/release
WORKDIR "/app/RF-One Web"
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["gunicorn","--bind","0.0.0.0:8080","--workers","2","--timeout","60","kitchen_cloud:app"]
