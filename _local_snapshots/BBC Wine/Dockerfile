FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app /app
COPY deploy/aws_setup.py /app/aws_setup.py
COPY deploy/wines_seed.json /app/wines_seed.json
ENV PYTHONUNBUFFERED=1 BBC_SECURE_COOKIES=1
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "60", "app:app"]
