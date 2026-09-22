# 키네틱 배포

AWS EC2·오라클 클라우드에 올리는 절차는 [deploy/CLOUD.md](deploy/CLOUD.md)에 있다.
아래는 호스트와 무관한 공통 내용이다.

한 번에 넷이 뜬다: Postgres → 백엔드(FastAPI) → 프론트(Next) → Caddy.
브라우저는 **Caddy 하나만** 본다.

```
cp .env.deploy.example .env     # POSTGRES_PASSWORD만 채우면 일단 뜬다
docker compose -f docker-compose.prod.yml up -d --build
```

`http://localhost` 로 열린다. 내리려면 `... down`, 데이터까지 지우려면 `... down -v`.

## 값

| 이름 | 없으면 |
|---|---|
| `POSTGRES_PASSWORD` | **뜨지 않는다.** 아무 긴 문자열 (`openssl rand -base64 24`) |
| `SITE_ADDRESS` | `:80` 으로 뜬다. 도메인을 넣으면 Caddy가 인증서를 받아 HTTPS |
| `COOKIE_SECURE` | `false`. **HTTPS일 때만 `true`** — HTTP인데 켜면 쿠키가 안 실려 로그인이 조용히 실패한다 |
| `CHARGER_API_KEY` | `GET /api/chargers` 만 501 |
| `KMA_API_KEY` | `GET /api/solar-forecast` 만 501 |
| `GEMINI_API_KEY` | `POST /api/chat` 만 501 |

키 셋은 없어도 나머지는 전부 돈다. 기동 시점에 막지 않는 건 의도다.

## 알아 둘 것

**백엔드 포트를 밖으로 열지 않는다.** 인증이 httpOnly 쿠키라 브라우저가 보는
출처가 하나여야 한다. 백엔드를 따로 노출하면 그 순간 교차 출처가 되고 쿠키
구조가 무너진다.

**`/api/*` 는 Caddy가 직접 가른다.** 개발에서는 Next의 rewrite가 그 일을 하지만
배포에서는 못 한다 — `output: "standalone"` 은 rewrite 목적지를 **빌드 시점에
구워 넣어서**, 이미지 안에서는 `BACKEND_URL` 기본값 `localhost:8000`이 컨테이너
자기 자신을 가리킨다. 실제로 그렇게 500을 봤다.

**마이그레이션은 백엔드 컨테이너가 뜨면서 돌린다** (`alembic upgrade head`).
스키마가 코드보다 뒤처진 채로 서비스되면 500이 나는데, 그때는 원인이 배포인지
코드인지 구분하기 어렵다.

## 확인된 것 (2026-09-22, 로컬 스택)

```
/ /timeline /stations /ask            200
/health                               200   미확인 요금 2건
/api/timeline?day=2026-10-07          200   중간 08-15 / 최대 15-21
/api/recommend (게스트)                200   2,373원 / 바로 2,772원 / 절감 399원
/api/auth/signup → /api/me            201 → 200   (DB·마이그레이션 동작)
/api/chargers                         501   키 없음 — 설계대로
```
