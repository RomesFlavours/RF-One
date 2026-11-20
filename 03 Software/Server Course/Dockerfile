# RF-One Trainer (test) — App Runner service `rfone-trainer-test`.
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app

EXPOSE 8080
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "--timeout", "180", "app:app"]
