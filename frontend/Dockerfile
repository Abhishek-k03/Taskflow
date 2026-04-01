# syntax=docker/dockerfile:1

# ---- deps ----
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- builder ----
FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Only /ws needs this at build time - /api and /health are Route Handlers
# that read TASKFLOW_BACKEND_URL fresh per request instead (see
# next.config.ts). Defaults to the runtime default so a plain `docker build`
# with no --build-arg still produces a working image for the common case.
ARG TASKFLOW_BACKEND_URL=http://localhost:8000
ENV TASKFLOW_BACKEND_URL=$TASKFLOW_BACKEND_URL
# Needed at build time only because the /ws rewrite is baked in; /api gets
# its key at request time from the runtime env instead.
ARG TASKFLOW_API_KEY=
ENV TASKFLOW_API_KEY=$TASKFLOW_API_KEY
RUN npm run build

# ---- runtime ----
FROM node:24-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# output: 'standalone' in next.config.ts traces only the deps each page
# actually needs, instead of shipping the full node_modules tree.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

# /api and /health honor TASKFLOW_BACKEND_URL set here at container start,
# with no rebuild needed. /ws does not - see the ARG above.
CMD ["node", "server.js"]
