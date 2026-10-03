# One image: the API serves the built web app. Build from the repo root:  docker build -f deploy/Dockerfile -t prescribble .
FROM node:22-slim AS web
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages/engine/package.json packages/engine/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund
COPY packages packages
COPY apps/web apps/web
COPY models models
RUN npm run build -w @prescribble/web

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY apps/api/requirements.txt .
RUN pip install -r requirements.txt
COPY apps/api/ ./
COPY --from=web /repo/apps/web/dist /app/web
RUN useradd --system --uid 10001 prescribble && mkdir /data && chown prescribble /data
USER prescribble
ENV PRESCRIBBLE_ENV=prod \
    PRESCRIBBLE_WEB_DIST=/app/web \
    PRESCRIBBLE_DATABASE_URL=sqlite:////data/prescribble.db
VOLUME /data
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8100/healthz', timeout=4)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
