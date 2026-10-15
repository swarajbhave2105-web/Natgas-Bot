FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

COPY live_feed/package.json /app/live_feed/package.json
RUN cd /app/live_feed && npm install --omit=dev

COPY . /app
RUN python -m compileall -q /app/backend
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
