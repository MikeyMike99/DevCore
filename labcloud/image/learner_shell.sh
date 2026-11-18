#!/bin/bash
# Limits on file size and open files; the container itself is capped and disposable.
ulimit -f 20480 -n 256   # (no -u: RLIMIT_NPROC counts per host user; each lab is its own disposable VM anyway)
# ttyd drops to the learner user but leaves HOME pointing at /root.
export HOME=/home/learner USER=learner LOGNAME=learner
cd "$HOME" || exit 1
export PS1='\[\e[32m\]learner@lab\[\e[0m\]:\w\$ ' TERM=xterm-256color
exec bash --noprofile --norc -i
