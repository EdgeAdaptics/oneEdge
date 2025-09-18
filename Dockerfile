FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/oneedge

FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir /tmp/wheels -r requirements.txt

FROM base AS runtime

ENV PYTHONPATH=/opt/oneedge

RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libffi8 \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /tmp/wheels /tmp/wheels
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt \
    && rm -rf /tmp/wheels

COPY . .

CMD ["python", "scripts/run_dashboard.py"]
