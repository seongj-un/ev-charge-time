# syntax=docker/dockerfile:1

# ── 의존성 ──────────────────────────────────────────────────────────────
# uv.lock을 그대로 쓴다. 배포에서 버전이 바뀌면 "로컬에선 됐는데"가 생긴다.
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS deps
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# ── 실행 ────────────────────────────────────────────────────────────────
FROM python:3.13-alpine AS runtime
WORKDIR /app
# src 레이아웃이라 패키지가 /app/src 아래에 있다. uv sync는 의존성만
# 설치하므로(--no-install-project) 경로를 직접 알려 준다.
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src PYTHONUNBUFFERED=1

# psycopg[binary]가 런타임에 libpq를 찾는다.
RUN apk add --no-cache libpq

COPY --from=deps /app/.venv /app/.venv
COPY . .

# root로 돌리지 않는다.
RUN adduser -u 1001 -S evcharge && chown -R evcharge /app
USER evcharge

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"

# 마이그레이션을 먼저 돌리고 뜬다. 스키마가 코드보다 뒤처진 채로 서비스되면
# 500이 나는데, 그때는 원인이 배포인지 코드인지 구분하기 어렵다.
CMD ["sh", "-c", "alembic upgrade head && uvicorn evcharge.main:app --host 0.0.0.0 --port 8000"]
