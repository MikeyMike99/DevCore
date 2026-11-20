#!/bin/bash
# Keeps the Cloudflare tunnel alive. Every 20s it asks cloudflared's own /ready endpoint
# whether it has a live connection to Cloudflare. If that fails 3 times in a row (process
# dead, or running but never connected e.g. DNS was not ready at boot), it restarts the tunnel.
# Only the tunnel is touched; the server is never restarted from here.
TOKEN_FILE="$HOME/.config/devcore/tunnel.env"
CF="$HOME/.local/bin/cloudflared"
METRICS=127.0.0.1:20241
LOG=/tmp/siraugga_tunnel_watchdog.log

# Only one watchdog at a time.
exec 9>/tmp/siraugga_tunnel_watchdog.lock
flock -n 9 || exit 0

start_tunnel() {
  pkill -f "cloudflared tunnel" 2>/dev/null; sleep 2
  [ -f "$TOKEN_FILE" ] || { echo "$(date) no token file" >> "$LOG"; return; }
  ( set -a; . "$TOKEN_FILE"; set +a
    setsid nohup "$CF" tunnel --no-autoupdate --metrics "$METRICS" run >> /tmp/cloudflared.log 2>&1 < /dev/null & )
  echo "$(date) tunnel (re)started" >> "$LOG"
}

fails=0
while true; do
  if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://$METRICS/ready)" = "200" ]; then
    fails=0
  else
    fails=$((fails+1))
    if [ "$fails" -ge 3 ]; then
      # wait for DNS before trying again
      getent hosts api.cloudflare.com >/dev/null 2>&1 && { start_tunnel; fails=0; sleep 30; }
    fi
  fi
  sleep 20
done
