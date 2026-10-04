# One image: the API serves the built web app. Build from the repo root:  docker build -f deploy/Dockerfile -t prescribble .
FROM node:22-slim AS web
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages/engine/package.json packages/engine/
COPY packages/widget/package.json packages/widget/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund
COPY packages packages
COPY apps/web apps/web
COPY models models
RUN npm run build:web

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY apps/api/requirements.txt .
RUN pip install -r requirements.txt
COPY apps/api/ ./
COPY --from=web /repo/apps/web/dist /app/web
COPY models/ /app/models/
# the training pipeline (stroke cutting, rasteriser, sequence features): the server scores with the very code the model was trained with
COPY src/__init__.py src/common.py src/classsets.py /app/src/
COPY src/data/__init__.py src/data/partial.py /app/src/data/
RUN useradd --system --uid 10001 prescribble && mkdir /data && chown prescribble /data
USER prescribble
ENV PRESCRIBBLE_ENV=prod \
    PRESCRIBBLE_WEB_DIST=/app/web \
    PRESCRIBBLE_MODELS_DIR=/app/models \
    PRESCRIBBLE_DATABASE_URL=sqlite:////data/prescribble.db
VOLUME /data
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8100/healthz', timeout=4)"
# one process on purpose: live classroom rooms keep their sockets in memory. --ws-max-size caps a WebSocket message at 64 KB (clients only ever send a short token).
# Behind a reverse proxy set FORWARDED_ALLOW_IPS to the proxy's address, or every visitor shares the proxy's IP and the per-IP limits (sign-in, joins) hit everyone at once.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100", "--ws-max-size", "65536"]
