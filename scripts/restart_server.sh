#!/bin/bash
# Restart the DevCore server safely: stop the running one, wait for port 5000 to be free,
# start the new one in the DevCore virtualenv, and check it answers.
# Run from Windows:  wsl.exe -e bash /mnt/c/Users/michael/Documents/DevCore/scripts/restart_server.sh
VENV="${DEVCORE_VENV:-$HOME/.venvs/devcore}"
CORE_DIR="$(cd "$(dirname "$0")/../core" && pwd)"
LOG=/tmp/devcore_server.log
PORT=5000

port_busy() { (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null; }

pids=$(pgrep -f "python3 -u server.py")
if [ -n "$pids" ]; then
  echo "Stopping old server (PID $pids)..."
  kill $pids
  for i in $(seq 1 30); do pgrep -f "python3 -u server.py" >/dev/null || break; sleep 0.5; done
  if pgrep -f "python3 -u server.py" >/dev/null; then
    echo "It didn't stop in 15 s; forcing it."
    pkill -9 -f "python3 -u server.py"
    sleep 1
  fi
fi

for i in $(seq 1 20); do port_busy || break; sleep 0.5; done
if port_busy; then
  echo "Port $PORT is still in use by something else; not starting. Check: ss -ltnp | grep :$PORT"
  exit 1
fi

echo "==== restart $(date) ====" >> "$LOG"
cd "$CORE_DIR" || exit 1
VIRTUAL_ENV="$VENV" PATH="$VENV/bin:$PATH" setsid nohup python3 -u server.py >> "$LOG" 2>&1 < /dev/null &
echo "Started new server (PID $!). Waiting for it to answer..."

for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/tickets")
  if [ "$code" = "200" ]; then
    echo "OK: server is up and the new routes answer."
    # Keep the local e-profile backend (login/admin/projects) running next to DevCore.
    # Set DEVCORE_SKIP_EPROFILE=1 to restart DevCore alone.
    if [ -z "${DEVCORE_SKIP_EPROFILE:-}" ]; then
      bash "$(dirname "$0")/eprofile_server.sh" || echo "Warning: e-profile backend did not start (see /tmp/eprofile_server.log)."
    fi
    exit 0
  fi
  if ! kill -0 $! 2>/dev/null; then break; fi
  sleep 1
done
echo "The server did not come up. Last log lines:"
tail -20 "$LOG"
exit 1
