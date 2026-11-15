#!/bin/bash
# Restart the Siraugga server cleanly: stop it AND every worker it started, then start it again.
# Run inside WSL:  bash /mnt/c/Users/michael/Documents/DevCore/restart_server.sh
ROOT=/mnt/c/Users/michael/Documents/DevCore
PY=/home/michael/.venvs/devcore/bin/python3
LOG=/tmp/devcore_server.out

PIDS=$(pgrep -f "python3 -u server.py")
for P in $PIDS; do
  PG=$(ps -o pgid= -p "$P" | tr -d ' ')
  kill -TERM -- "-$PG" 2>/dev/null          # the whole process group: server + agy workers + their helpers
done
for i in $(seq 1 10); do pgrep -f "python3 -u server.py" >/dev/null || break; sleep 1; done
for P in $(pgrep -f "python3 -u server.py"); do
  PG=$(ps -o pgid= -p "$P" | tr -d ' ')
  kill -KILL -- "-$PG" 2>/dev/null
done

# Workers left behind by an earlier unclean stop (their parent is gone, so nobody reads their output)
for P in $(pgrep -f "agy_real|semgrep-mcp|playwright-mcp|media_player/server.py"); do
  PP=$(ps -o ppid= -p "$P" | tr -d ' ')
  if [ "$PP" = "1" ] || ! kill -0 "$PP" 2>/dev/null; then kill "$P" 2>/dev/null; fi
done

cd "$ROOT/core" || exit 1
nohup setsid "$PY" -u server.py >> "$LOG" 2>&1 < /dev/null &
for i in $(seq 1 40); do curl -s -o /dev/null http://127.0.0.1:5000/ && { echo "Server is up."; exit 0; }; sleep 2; done
echo "Server did not answer in 80s - see $LOG"; exit 1
