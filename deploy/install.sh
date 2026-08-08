#!/usr/bin/env bash
# One-time setup on the Hetzner box. Run as root:
#   bash install.sh
#
# Assumes the code has already been copied to /opt/het (see deploy.sh).
set -euo pipefail

APP_DIR=/opt/het
STATE_DIR=/var/lib/het
PORT=8765

if [[ $EUID -ne 0 ]]; then
  echo "root olarak çalıştır: sudo bash install.sh" >&2
  exit 1
fi

# Python 3.11+ is required (the code uses `X | None` annotations at runtime).
python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11+ gerekli, bulunan: {sys.version.split()[0]}")
PY

if [[ ! -d "$APP_DIR/het" ]]; then
  echo "$APP_DIR/het yok — önce kodu kopyala (deploy.sh)." >&2
  exit 1
fi

id -u het &>/dev/null || useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin het

install -d -o het -g het -m 750 "$STATE_DIR" "$STATE_DIR/cache"
chown -R root:root "$APP_DIR"          # code is read-only to the service user
chmod -R go-w "$APP_DIR"

install -m 644 "$APP_DIR/deploy/het.service" /etc/systemd/system/het.service
systemctl daemon-reload
systemctl enable --now het.service

sleep 1
systemctl --no-pager --lines=20 status het.service || true

echo
echo "Servis çalışıyor: 127.0.0.1:$PORT"
echo
if command -v tailscale &>/dev/null; then
  echo "Kullanımdaki tailscale serve portları:"
  tailscale serve status 2>/dev/null | grep -oE '^https?://[^ ]+' | sed 's/^/  /' || echo "  (yok)"
  echo
  # Never suggest the bare `tailscale serve --bg <port>` form: it claims 443,
  # which on a shared box silently steals another app's address.
  echo "Yayınlamak için BOŞ bir HTTPS portu seç ve açıkça belirt:"
  echo "  tailscale serve --bg --https=10000 http://127.0.0.1:$PORT"
  echo
  echo "Adres: https://<makine>.<tailnet>.ts.net:10000"
else
  echo "UYARI: tailscale kurulu değil. Servis şu an sadece sunucunun kendisinden erişilebilir."
  echo "Kur:  curl -fsSL https://tailscale.com/install.sh | sh && tailscale up"
fi
