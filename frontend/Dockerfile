# syntax=docker/dockerfile:1

# ── 의존성 ──────────────────────────────────────────────────────────────
# package.json이 바뀌지 않으면 이 레이어는 캐시된다. 소스만 고칠 때 npm ci를
# 다시 돌지 않는다.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ── 빌드 ────────────────────────────────────────────────────────────────
FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# BACKEND_URL은 런타임 값이다. rewrite는 서버에서 평가되므로 빌드 때 필요 없다.
RUN npm run build

# ── 실행 ────────────────────────────────────────────────────────────────
FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# root로 돌리지 않는다.
RUN addgroup -g 1001 -S nodejs && adduser -u 1001 -S nextjs -G nodejs

# standalone 산출물은 필요한 node_modules를 이미 품고 있다.
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

# 컨테이너가 살아 있는지. Caddy가 이 앞에 서므로 내부 포트를 그대로 찌른다.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
