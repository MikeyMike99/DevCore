#!/bin/bash
# Run one command for an in-game/app developer inside a sealed box (bubblewrap):
#   * only their sandbox copy of the project is visible, at /work (read-write);
#   * system programs are read-only; no home folder, no Windows drives (/mnt), no DevCore;
#   * no network, a private /tmp, no other processes visible;
#   * killed after DEV_JAIL_TIMEOUT seconds (default 120).
# The developer's agent may run commands ONLY through this script (.agents/raugus_hook.py).
#
# usage: dev_jail.sh <command> [args...]      (DEVCORE_DEV_SANDBOX must be set by the server)
set -u
BOX="${DEVCORE_DEV_SANDBOX:-}"
if [ -z "$BOX" ] || [ ! -d "$BOX" ]; then
  echo "dev_jail: no developer sandbox for this task." >&2
  exit 2
fi
case "$(realpath "$BOX")" in
  */playground/.dev_sandboxes/*) ;;
  *) echo "dev_jail: refusing a sandbox outside playground/.dev_sandboxes." >&2; exit 2 ;;
esac
if [ "$#" -eq 0 ]; then
  echo "usage: dev_jail.sh <command> [args...]" >&2
  exit 2
fi
ARGS=(--ro-bind /usr /usr --ro-bind /etc /etc
      --symlink usr/bin /bin --symlink usr/sbin /sbin --symlink usr/lib /lib)
[ -d /usr/lib64 ] && ARGS+=(--symlink usr/lib64 /lib64)
ARGS+=(--proc /proc --dev /dev --tmpfs /tmp
       --bind "$BOX" /work --chdir /work
       --unshare-all --die-with-parent --new-session
       --clearenv --setenv PATH /usr/local/bin:/usr/bin:/bin --setenv HOME /work
       --setenv LANG C.UTF-8 --setenv PYTHONDONTWRITEBYTECODE 1)
exec timeout --kill-after=5 "${DEV_JAIL_TIMEOUT:-120}" bwrap "${ARGS[@]}" -- "$@"
