#!/usr/bin/env bash
# Push the current working tree to the server and restart the service.
#
#   ./deploy/deploy.sh root@sunucu.ornek ~/.ssh/id_ed25519_sunucu
#
# Transfer is tar-over-ssh rather than rsync: rsync is not present in Git Bash
# on Windows, tar is everywhere.
#
# Only code is copied. The database and HTTP cache live in /var/lib/het on the
# server and are never touched from here. The previous release is kept at
# /opt/het.old so a bad deploy can be rolled back in one move.
set -euo pipefail

TARGET=${1:?"kullanım: deploy.sh user@host [ssh-key]"}
KEY=${2:-}
APP_DIR=/opt/het
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SSH=(ssh -o BatchMode=yes)
[[ -n "$KEY" ]] && SSH+=(-i "$KEY")

echo "→ $TARGET:$APP_DIR"

tar czf - -C "$SRC" \
    --exclude='.git' \
    --exclude='data' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    . | "${SSH[@]}" "$TARGET" "
set -euo pipefail
rm -rf $APP_DIR.new
mkdir -p $APP_DIR.new
tar xzf - -C $APP_DIR.new

# Shell scripts and unit files written on Windows can carry CRLF, which makes
# systemd and bash fail in confusing ways. Normalise on arrival.
find $APP_DIR.new -type f \( -name '*.sh' -o -name '*.service' \) \
    -exec sed -i 's/\r\$//' {} +

if [[ -d $APP_DIR ]]; then
  rm -rf $APP_DIR.old
  mv $APP_DIR $APP_DIR.old
fi
mv $APP_DIR.new $APP_DIR
chown -R root:root $APP_DIR
chmod -R go-w $APP_DIR
"

if "${SSH[@]}" "$TARGET" "systemctl is-enabled het.service &>/dev/null"; then
  "${SSH[@]}" "$TARGET" "
    install -m 644 $APP_DIR/deploy/het.service /etc/systemd/system/het.service
    systemctl daemon-reload
    systemctl restart het.service
    sleep 1
    systemctl is-active het.service
  "
  echo "yeniden başlatıldı."
else
  echo "servis henüz kurulu değil — sunucuda çalıştır:"
  echo "  sudo bash $APP_DIR/deploy/install.sh"
fi
