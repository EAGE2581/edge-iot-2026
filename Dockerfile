# ── Stage 1: builder ──
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY collector.py alarm_codes.yaml ./
COPY app/ ./app/

ENV PYTHONUNBUFFERED=1

CMD ["python3", "collector.py", "config.yaml"]
