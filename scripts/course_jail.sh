#!/bin/bash
# Run one course step command for a Tier 1-4 learner inside a sealed box (bubblewrap):
#   * the learner's own course copy (playground/.course_sandboxes/<id>) is the only writable place,
#     mounted where the course expects it: /home/michael/alp-env/temp_phase2_sandbox;
#   * the course tools (alp-env Python environment, bicep, system programs) are read-only;
#     nothing else from the home folder, no Windows drives (/mnt), no DevCore;
#   * no network, a private /tmp, no other processes visible;
#   * killed after COURSE_JAIL_TIMEOUT seconds (default 60).
# Only core/routes/projects.py calls this, with an allowlisted course command.
#
# usage: course_jail.sh <command> [args...]      (DEVCORE_COURSE_SANDBOX must be set by the server)
set -u
BOX="${DEVCORE_COURSE_SANDBOX:-}"
if [ -z "$BOX" ] || [ ! -d "$BOX" ]; then
  echo "course_jail: no course sandbox for this learner." >&2
  exit 2
fi
case "$(realpath "$BOX")" in
  */playground/.course_sandboxes/*) ;;
  *) echo "course_jail: refusing a sandbox outside playground/.course_sandboxes." >&2; exit 2 ;;
esac
if [ "$#" -eq 0 ]; then
  echo "usage: course_jail.sh <command> [args...]" >&2
  exit 2
fi
ENV_ROOT=/home/michael/alp-env
WORK="$ENV_ROOT/temp_phase2_sandbox"
ARGS=(--ro-bind /usr /usr --ro-bind /etc /etc
      --symlink usr/bin /bin --symlink usr/sbin /sbin --symlink usr/lib /lib)
[ -d /usr/lib64 ] && ARGS+=(--symlink usr/lib64 /lib64)
ARGS+=(--proc /proc --dev /dev --tmpfs /tmp --tmpfs /home --dir /home/michael)
for part in bin lib include share pyvenv.cfg; do
  [ -e "$ENV_ROOT/$part" ] && ARGS+=(--ro-bind "$ENV_ROOT/$part" "$ENV_ROOT/$part")
done
[ -L "$ENV_ROOT/lib64" ] && ARGS+=(--symlink lib "$ENV_ROOT/lib64")
ARGS+=(--bind "$BOX" "$WORK" --chdir "$WORK"
       --unshare-all --die-with-parent --new-session
       --clearenv --setenv HOME /home/michael --setenv VIRTUAL_ENV "$ENV_ROOT"
       --setenv DOTNET_BUNDLE_EXTRACT_BASE_DIR /tmp/dotnet
       --setenv BC_SKIP_MAPPING TRUE --setenv LOG_LEVEL ERROR
       --setenv PATH "$ENV_ROOT/bin:/usr/local/bin:/usr/bin:/bin"
       --setenv LANG C.UTF-8 --setenv PYTHONDONTWRITEBYTECODE 1)
exec timeout --kill-after=5 "${COURSE_JAIL_TIMEOUT:-60}" bwrap "${ARGS[@]}" -- "$@"
