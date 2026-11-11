#!/bin/bash
# Boot start for Siraugga: run by the Windows task "Siraugga autostart" when the computer
# starts, before anyone signs in. Starts the Cloudflare tunnel and the server (if they are not
# already running), then keeps WSL alive so they stay up.
#
# The tunnel token lives in ~/.config/devcore/tunnel.env (mode 600): TUNNEL_TOKEN=...
LOG=/tmp/siraugga_autostart.log
DIR="$(cd "$(dirname "$0")" && pwd)"
TOKEN_FILE="$HOME/.config/devcore/tunnel.env"
exec >> "$LOG" 2>&1
echo "==== autostart $(date) ===="

# Wait for networking (WSL can take a few seconds after boot).
for i in $(seq 1 30); do getent hosts cloudflare.com >/dev/null 2>&1 && break; sleep 2; done

if ! pgrep -f "cloudflared tunnel" >/dev/null; then
  if [ -f "$TOKEN_FILE" ]; then
    set -a; . "$TOKEN_FILE"; set +a
    setsid nohup "$HOME/.local/bin/cloudflared" tunnel --no-autoupdate run >> /tmp/cloudflared.log 2>&1 < /dev/null &
    unset TUNNEL_TOKEN
    echo "Started Cloudflare tunnel."
  else
    echo "No $TOKEN_FILE; tunnel not started."
  fi
else
  echo "Tunnel already running."
fi

if [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/api/tickets)" = "200" ]; then
  echo "Server already running."
else
  bash "$DIR/restart_server.sh"
fi

# Keep this WSL session (and so the server and tunnel) running.
exec sleep infinity
