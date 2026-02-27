# MCP Server — runs via stdio, not as HTTP service.
# This Dockerfile is for distribution/containerized usage.
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ─── Runtime ──────────────────────────────────────────────
FROM node:20-slim AS runtime

RUN groupadd -r openclaw && useradd -r -g openclaw openclaw

WORKDIR /app

COPY --from=builder /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/dist ./dist

USER openclaw

ENTRYPOINT ["node", "dist/index.js"]
