# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (optional, most wheels are manylinux)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY socketlab/requirements.txt /app/socketlab/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/socketlab/requirements.txt

# App source
COPY socketlab/src /app/socketlab/src

ENV PYTHONPATH=/app

ENTRYPOINT ["python","-m","socketlab.src.socketlab.cli"]
CMD ["--help"]
