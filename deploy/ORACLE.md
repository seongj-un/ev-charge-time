# 오라클 클라우드에 올리기

Always Free 한도 안에서 돈다. 카드 등록은 본인 확인용이고 과금되지 않는다.

제가 못 하는 것: **계정 생성, 인스턴스 생성, 콘솔 설정.** 아래 ①②③은 직접
하셔야 합니다. ④부터는 제가 붙을 수 있습니다.

---

## ① 인스턴스 만들기

**ARM(Ampere A1)을 고르세요.** `VM.Standard.A1.Flex`, 4 OCPU / 24GB까지 무료입니다.

AMD 마이크로(`VM.Standard.E2.1.Micro`)는 메모리가 1GB뿐이라 `next build`가
죽을 수 있습니다 — 실측으로 빌드만 435MB를 쓰고 `npm ci`가 겹칩니다. 설정
스크립트가 스왑을 만들어 보완하지만 느립니다.

> ARM은 인기가 많아 "Out of capacity"가 자주 뜹니다. 그러면 다른 가용성
> 도메인으로 바꾸거나 시간을 두고 다시 시도하세요.

- 이미지: **Ubuntu 22.04 또는 24.04** (아래 스크립트가 둘 다 처리합니다)
- SSH 공개키를 등록하세요 — 나중에 접속할 유일한 방법입니다
- 만든 뒤 **공인 IP**를 적어 두세요

## ② 포트 열기 (콘솔)

인스턴스 → 서브넷 → **보안 목록** → 수신 규칙 추가:

| 소스 CIDR | 프로토콜 | 목적지 포트 |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

**이것만으로는 안 됩니다.** 오라클 이미지는 인스턴스 *안에서도* 22번 말고
전부 막아 둡니다. ④의 스크립트가 그쪽을 엽니다. 이 두 겹을 몰라서 몇 시간
헤매는 경우가 가장 흔합니다.

## ③ 주소 정하기 (HTTPS를 쓸 거면)

Caddy가 인증서를 자동으로 받으려면 **IP가 아니라 이름**이 필요합니다.

- 도메인이 있으면 A 레코드를 인스턴스 IP로 지정
- 없으면 **DuckDNS**(무료, 카드 불필요)에서 `kinetic.duckdns.org` 같은 주소를
  만들어 IP를 연결

이름이 없으면 그냥 HTTP(`http://<IP>`)로 써도 됩니다. 그때는
`COOKIE_SECURE=false`를 유지해야 합니다 — HTTP인데 켜면 쿠키가 안 실려
로그인이 조용히 실패합니다.

---

## ④ VM 준비

```bash
ssh ubuntu@<공인IP>
```

코드를 올립니다. 저장소가 비공개라 둘 중 하나입니다.

```bash
# (가) 내 맥에서 그대로 밀어넣기 — 가장 간단
rsync -az --exclude node_modules --exclude .git --exclude .next \
  ~/orca/workspaces/EV_Charge_time_추천/frontend/ ubuntu@<공인IP>:~/kinetic/

# (나) GitHub 배포 키를 만들어 clone
```

그다음 VM 안에서:

```bash
cd ~/kinetic
bash deploy/oracle-setup.sh     # Docker · 방화벽 · 스왑
exit                            # docker 그룹 반영하려면 재접속
```

## ⑤ 띄우기

```bash
ssh ubuntu@<공인IP>
cd ~/kinetic
cp .env.deploy.example .env
nano .env
```

`.env`에 채울 것:

```ini
POSTGRES_PASSWORD=<openssl rand -base64 24 결과>

# 이름이 있으면
SITE_ADDRESS=kinetic.duckdns.org
COOKIE_SECURE=true

# 없으면
# SITE_ADDRESS=:80
# COOKIE_SECURE=false

CHARGER_API_KEY=<공공데이터포털 Decoding 키>
KMA_API_KEY=<같은 키>
GEMINI_API_KEY=<Google AI Studio 키>
```

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

ARM 4 OCPU면 3~5분, AMD 마이크로면 15분 넘게 걸릴 수 있습니다.

## ⑥ 확인

```bash
docker compose -f docker-compose.prod.yml ps        # 넷 다 healthy 인지
curl -s localhost/health                            # 미확인 요금 항목
docker compose -f docker-compose.prod.yml logs -f caddy   # 인증서 발급 로그
```

브라우저로 `https://<주소>` 또는 `http://<IP>`.

---

## 막혔을 때

**브라우저가 아무 응답 없이 멈춘다** — ②의 보안 목록과 ④의 스크립트, 둘 중
하나가 빠진 겁니다. `sudo iptables -L INPUT -n --line-numbers`로 80·443이
ACCEPT인지 보세요.

**인증서를 못 받는다** — 이름이 실제로 그 IP를 가리키는지 먼저 확인하세요
(`dig +short <주소>`). Let's Encrypt가 80번으로 되물어 오므로 80도 열려 있어야
합니다.

**빌드 중 죽는다** — 메모리입니다. `free -m`으로 스왑이 잡혔는지 보고,
안 되면 ARM 인스턴스로 옮기세요.

**로그인이 되는데 새로고침하면 풀린다** — HTTP인데 `COOKIE_SECURE=true`입니다.

**충전소가 501** — `CHARGER_API_KEY`가 비었습니다. 태양광은 `KMA_API_KEY`,
질문하기는 `GEMINI_API_KEY`. 키가 없어도 나머지는 전부 돕니다.
