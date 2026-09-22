# 클라우드에 올리기

AWS EC2와 오라클 클라우드 둘 다 같은 방식으로 돈다. 다른 건 ①②뿐이다.

제가 못 하는 것: **계정 생성, 인스턴스 생성, 콘솔 설정.** ①②③은 직접
하셔야 합니다. ④부터는 제가 붙을 수 있습니다.

---

## ① 인스턴스 만들기

**이미지는 Ubuntu.** (22.04 또는 24.04)

Amazon Linux 2023도 되지만 Docker 설치 방식이 다르고(`dnf`), 아래 스크립트와
절차가 Ubuntu 기준(`ubuntu@` 계정)이라 손이 더 갑니다.

**메모리 2GB 이상을 권합니다.** `next build`만 실측 **435MB**를 쓰고 `npm ci`가
겹칩니다. 1GB로도 되지만 스왑을 타면서 느려집니다(15분 이상).

| | 권장 | 최소 |
|---|---|---|
| **AWS EC2** | `t3.small` (2GB) · ARM이면 `t4g.small` | `t3.micro` (1GB) + 스왑 |
| **오라클** | `VM.Standard.A1.Flex` ARM 4코어/24GB — Always Free | AMD 마이크로 (1GB) + 스왑 |

**아키텍처를 AMI와 맞추세요.** `t4g`·Ampere는 **Arm** AMI, `t3`·`t2`는 **x86**
AMI입니다. 어긋나면 인스턴스가 아예 안 뜹니다.

> 오라클 ARM은 인기가 많아 "Out of capacity"가 자주 뜹니다. 다른 가용성
> 도메인으로 바꾸거나 시간을 두고 다시 시도하세요.

SSH 키페어를 만들어 두세요 — 나중에 접속할 유일한 방법입니다. 만든 뒤
**공인 IP**를 적어 두세요.

## ② 포트 열기 (콘솔)

`0.0.0.0/0` 에서 TCP **80**과 **443** 수신 허용.

- **AWS**: 인스턴스 → 보안 → 보안 그룹 → 인바운드 규칙 편집
- **오라클**: 인스턴스 → 서브넷 → 보안 목록 → 수신 규칙 추가

**오라클은 이것만으로 안 됩니다.** 오라클 이미지는 인스턴스 *안에서도* 22번
말고 전부 막아 둡니다. ④의 스크립트가 그쪽을 엽니다. 이 두 겹을 몰라서 몇
시간 헤매는 경우가 가장 흔합니다. AWS의 Ubuntu AMI는 안쪽을 막지 않으므로
보안 그룹만 열면 됩니다.

## ③ 주소 정하기 (HTTPS를 쓸 거면)

Caddy가 인증서를 자동으로 받으려면 **IP가 아니라 이름**이 필요합니다.

- 도메인이 있으면 A 레코드를 인스턴스 IP로
- 없으면 **DuckDNS**(무료, 카드 불필요)에서 `kinetic.duckdns.org` 같은 주소를
  만들어 IP를 연결

이름이 없으면 HTTP(`http://<IP>`)로 써도 됩니다. 그때는 `COOKIE_SECURE=false`를
유지해야 합니다 — HTTP인데 켜면 쿠키가 안 실려 로그인이 조용히 실패합니다.

> AWS는 인스턴스를 껐다 켜면 공인 IP가 바뀝니다. 탄력적 IP(Elastic IP)를
> 붙여 두면 고정됩니다.

---

## ④ VM 준비

```bash
ssh -i <키파일>.pem ubuntu@<공인IP>
```

코드를 올립니다. 저장소가 비공개라 rsync가 가장 간단합니다.

```bash
# 내 맥에서
rsync -az -e "ssh -i <키파일>.pem" \
  --exclude node_modules --exclude .git --exclude .next \
  ~/orca/workspaces/EV_Charge_time_추천/frontend/ ubuntu@<공인IP>:~/kinetic/
```

VM 안에서:

```bash
cd ~/kinetic
bash deploy/vm-setup.sh     # Docker · 방화벽 · 스왑
exit                        # docker 그룹 반영하려면 재접속
```

## ⑤ 띄우기

```bash
ssh -i <키파일>.pem ubuntu@<공인IP>
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

2GB 이상이면 3~5분, 1GB면 15분 넘게 걸릴 수 있습니다.

## ⑥ 확인

```bash
docker compose -f docker-compose.prod.yml ps              # 넷 다 healthy 인지
curl -s localhost/health                                  # 미확인 요금 항목
docker compose -f docker-compose.prod.yml logs -f caddy    # 인증서 발급 로그
```

브라우저로 `https://<주소>` 또는 `http://<IP>`.

---

## 막혔을 때

**브라우저가 아무 응답 없이 멈춘다** — 콘솔의 보안 규칙이 빠졌거나(AWS·오라클
공통), 오라클이면 ④의 스크립트를 안 돌린 겁니다.
`sudo iptables -L INPUT -n --line-numbers`로 80·443이 ACCEPT인지 보세요.

**인증서를 못 받는다** — 이름이 실제로 그 IP를 가리키는지 먼저 확인하세요
(`dig +short <주소>`). Let's Encrypt가 80번으로 되물어 오므로 80도 열려 있어야
합니다.

**빌드 중 죽는다** — 메모리입니다. `free -m`으로 스왑이 잡혔는지 보고, 안 되면
더 큰 인스턴스로 옮기세요.

**로그인이 되는데 새로고침하면 풀린다** — HTTP인데 `COOKIE_SECURE=true`입니다.

**충전소가 501** — `CHARGER_API_KEY`가 비었습니다. 태양광은 `KMA_API_KEY`,
질문하기는 `GEMINI_API_KEY`. 키가 없어도 나머지는 전부 돕니다.
