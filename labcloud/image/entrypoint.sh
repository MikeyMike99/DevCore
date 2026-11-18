#!/bin/sh
# Runs as root. LAB_ID is passed in by the Worker.
LAB="${LAB_ID:-}"
case "$LAB" in ""|*[!A-Za-z0-9_-]*) echo "bad LAB_ID" >&2; exit 1;; esac
[ -d "/labs/$LAB/seed" ] || { echo "unknown lab" >&2; exit 1; }
cp -a "/labs/$LAB/seed/." /home/learner/
chown -R learner:learner /home/learner
export LAB_ID="$LAB"
python3 /opt/grader.py &                      # root-only helper on :8080, reachable only through the Worker
exec ttyd -W -p 7681 -u "$(id -u learner)" -g "$(id -g learner)" /opt/learner_shell.sh
