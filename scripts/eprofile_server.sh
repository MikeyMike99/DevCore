#!/bin/bash
# Run the e-profile backend (login, admin panel, projects, blog, ...) locally, next to DevCore.
# It listens on 127.0.0.1 only; the public site reaches it through DevCore's router
# (services/eprofile_bridge) and the tunnel. Newsletter work stays with CyberBrief, so
# e-profile's own background daemon is switched off here.
#
#   bash scripts/eprofile_server.sh            (re)start it
#   bash scripts/eprofile_server.sh stop       stop it
#   bash scripts/eprofile_server.sh setup      create/refresh its virtualenv
set -u
EPROFILE_DIR="$(cd "$(dirname "$0")/../playground/e_profile" && pwd)"
VENV="${EPROFILE_VENV:-$HOME/.venvs/eprofile}"
PORT="${EPROFILE_PORT:-5100}"
LOG=/tmp/eprofile_server.log
PIDFILE=/tmp/eprofile_server.pid

stop() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")"
    for i in $(seq 1 20); do kill -0 "$(cat "$PIDFILE")" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$(cat "$PIDFILE")" 2>/dev/null
  fi
  rm -f "$PIDFILE"
}

setup() {
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV" || exit 1
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$EPROFILE_DIR/requirements.txt" gunicorn cryptography || exit 1
  echo "virtualenv ready: $VENV"
}

case "${1:-start}" in
  stop)  stop; echo "e-profile stopped"; exit 0 ;;
  setup) setup; exit $? ;;
esac

[ -x "$VENV/bin/gunicorn" ] || setup || exit 1
stop
cd "$EPROFILE_DIR" || exit 1
echo "==== start $(date) ====" >> "$LOG"
# One worker (its JSON data files are not multi-process safe), several threads.
EPROFILE_BACKGROUND_DAEMON=off EPROFILE_PA_USAGE_SYNC=on nohup "$VENV/bin/gunicorn" server:app \
  --bind "127.0.0.1:$PORT" --workers 1 --threads 8 --timeout 120 \
  --forwarded-allow-ips="127.0.0.1" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
for i in $(seq 1 40); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/robots.txt"; then
    echo "e-profile is up on 127.0.0.1:$PORT (PID $(cat "$PIDFILE"))"; exit 0
  fi
  kill -0 "$(cat "$PIDFILE")" 2>/dev/null || break
  sleep 0.5
done
echo "e-profile did not start; last log lines:"; tail -20 "$LOG"; exit 1
