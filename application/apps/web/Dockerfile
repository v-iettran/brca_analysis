# Runtime image for the MOFA-Guided Oncology Research Copilot Next.js UI.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Docker only exposes build arguments that are declared with ARG. INTERNAL_API_URL
# has to be one of them: Next.js resolves rewrites() during `next build` and freezes
# the result into .next/routes-manifest.json, so if it is missing here the proxy rule
# is baked in empty and every /api/* request 404s at runtime — no matter what the
# environment says once the container is running.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_PUBLIC_DEMO_MODE=false
ARG INTERNAL_API_URL
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_PUBLIC_DEMO_MODE \
    INTERNAL_API_URL=$INTERNAL_API_URL
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000
CMD ["npm", "start"]
