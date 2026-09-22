#!/usr/bin/env bash
# 클라우드 VM 준비 (AWS EC2 · 오라클 클라우드 공통). VM 안에서 한 번 돌린다.
#
#   bash deploy/vm-setup.sh
#
# 하는 일: Docker 설치 → 방화벽 열기 → 스왑(메모리 작을 때) → 확인.
# 여러 번 돌려도 안전하다. Ubuntu 기준이다.
set -euo pipefail

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()  { printf '   \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '   \033[33m!\033[0m %s\n' "$*"; }

# ── 1. Docker ───────────────────────────────────────────────────────────
say "Docker"
if command -v docker >/dev/null 2>&1; then
  ok "이미 설치됨 ($(docker --version))"
else
  curl -fsSL https://get.docker.com | sudo sh
  ok "설치 완료"
fi

# sudo 없이 쓰려면 그룹에 넣어야 한다. 반영은 다시 로그인해야 된다.
if ! id -nG "$USER" | grep -qw docker; then
  sudo usermod -aG docker "$USER"
  warn "docker 그룹에 추가했습니다 — 한 번 로그아웃했다 다시 접속해야 적용됩니다"
fi

sudo systemctl enable --now docker >/dev/null 2>&1 || true

# ── 2. 방화벽 ───────────────────────────────────────────────────────────
# **오라클에서만 필요하다.** 오라클 이미지는 콘솔의 보안 목록과 별개로
# 인스턴스 안에서도 22번 말고 전부 막아 둔다. 콘솔만 열고 여기를 안 열면
# "포트는 열었는데 접속이 안 되는" 상태가 되는데, 오라클에서 가장 많이
# 걸리는 함정이다.
#
# AWS EC2의 Ubuntu AMI는 안쪽을 막지 않으므로 이 절은 아무것도 바꾸지
# 않고 지나간다. 그래도 돌려서 나쁠 것은 없다.
say "방화벽 (인스턴스 내부)"
if command -v firewall-cmd >/dev/null 2>&1 && sudo firewall-cmd --state >/dev/null 2>&1; then
  sudo firewall-cmd --permanent --add-service=http  >/dev/null
  sudo firewall-cmd --permanent --add-service=https >/dev/null
  sudo firewall-cmd --reload >/dev/null
  ok "firewalld에 80·443 열었습니다"
else
  # Ubuntu 이미지는 iptables 규칙이 그대로 박혀 있다.
  for port in 80 443; do
    if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
      sudo iptables -I INPUT 6 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
    fi
  done
  if command -v netfilter-persistent >/dev/null 2>&1; then
    sudo netfilter-persistent save >/dev/null
  else
    sudo apt-get install -y iptables-persistent >/dev/null 2>&1 || true
    sudo netfilter-persistent save >/dev/null 2>&1 || warn "규칙을 저장하지 못했습니다 — 재부팅하면 사라질 수 있습니다"
  fi
  ok "iptables에 80·443 열었습니다"
fi

warn "클라우드 콘솔에도 80·443 수신 규칙이 필요합니다 (여기서는 못 합니다)"
warn "  AWS: 보안 그룹  ·  오라클: 서브넷 > 보안 목록"

# ── 3. 스왑 ─────────────────────────────────────────────────────────────
# next build가 실측 435MB를 쓴다. 1GB 인스턴스(t3.micro·t2.micro·오라클 AMD
# 마이크로)에서는 npm ci와 겹치면서 OOM으로 죽는다. 메모리가 넉넉하면 건너뛴다.
say "메모리"
mem_mb=$(free -m | awk '/^Mem:/{print $2}')
swap_mb=$(free -m | awk '/^Swap:/{print $2}')
printf '   메모리 %sMB · 스왑 %sMB\n' "$mem_mb" "$swap_mb"

if [ "$mem_mb" -lt 2048 ] && [ "$swap_mb" -lt 2048 ]; then
  # 1GB 인스턴스(t3.micro 등)에서 npm ci와 next build가 겹친다. 넉넉하게
  # 잡는다 — 디스크는 남고, 모자라서 빌드가 죽으면 처음부터 다시다.
  warn "메모리가 작습니다. 빌드 중 죽지 않도록 스왑 4GB를 만듭니다"
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  # 기본 swappiness(60)로는 스왑이 남아 있어도 OOM 킬러가 먼저 움직인다.
  sudo sysctl -w vm.swappiness=80 >/dev/null
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=80' | sudo tee -a /etc/sysctl.conf >/dev/null
  ok "스왑 4GB 추가"
else
  ok "충분합니다"
fi

# ── 4. 확인 ─────────────────────────────────────────────────────────────
say "정리"
ok "아키텍처 $(uname -m)"
ok "공인 IP $(curl -s --max-time 5 ifconfig.me || echo '(확인 실패)')"
cat <<'NEXT'

   다음:
     1) 콘솔에 80·443 수신 규칙 추가 (아직이면)
        AWS: 보안 그룹  ·  오라클: 서브넷 > 보안 목록
     2) 한 번 로그아웃 후 다시 접속 (docker 그룹 반영)
     3) 코드를 올리고:
          cp .env.deploy.example .env   # POSTGRES_PASSWORD 채우기
          docker compose -f docker-compose.prod.yml up -d --build

NEXT
