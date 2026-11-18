#!/bin/bash
# Siraugga Lab Cloud setup. The lab container is BUILT HERE, from source, on the machine doing the setup/deploy.
# No built image, archive or binary is ever stored in git.
#
#   bash labcloud/setup.sh check                      prerequisites only
#   bash labcloud/setup.sh local                      install deps, build the lab image, run the audit, create the local settings file
#   bash labcloud/setup.sh env                        only create the private local settings file (~/.config/siraugga/lab_cloud.env)
#   LAB_DOMAIN=lab.example.com bash labcloud/setup.sh deploy [--dry-run]
#                                                     build + audit + deploy to Cloudflare, then verify the live site
#   Optional for deploy: SIRAUGGA_ORIGIN=https://your-siraugga-site   (the site allowed to embed the lab page)
#
# Run it in WSL/Linux. `deploy` needs: Docker running, Node 20+, the Cloudflare token in <repo>/.env.cloudflare, and the
# Cloudflare Workers Paid plan (Containers). It asks you to type DEPLOY before it changes anything online.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
export PATH="$HOME/.local/node/bin:$PATH"
MODE="${1:-}"
DRY=0; [ "${2:-}" = "--dry-run" ] && DRY=1
SECRET_FILE="${LAB_SECRET_FILE:-$HOME/.config/siraugga/lab_master_secret}"
IMAGE_TAG="siraugga-lab-image"

say() { printf '\n== %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi; }

prereqs() {
  say "Checking prerequisites"
  command -v node    >/dev/null || die "node not found (Node 20+ needed)"
  command -v npm     >/dev/null || die "npm not found"
  command -v python3 >/dev/null || die "python3 not found"
  command -v docker  >/dev/null || die "docker not found"
  docker info >/dev/null 2>&1   || die "Docker is installed but not running"
  echo "  node $(node --version), $(docker --version | cut -d, -f1)"
}

install_deps() {
  say "Installing Worker dependencies (exact versions from package-lock.json)"
  (cd "$HERE" && run npm ci --no-audit --no-fund)
}

build_image() {
  say "Building the lab image from source (it is not stored in git)"
  run docker build -q -t "$IMAGE_TAG" "$HERE/image"
}

local_env() {
  # Private file (outside git) with the local connection settings; the Siraugga server and dev.sh both read it.
  LOCAL_ENV="$HOME/.config/siraugga/lab_cloud.env"
  say "Local connection settings"
  if [ -f "$LOCAL_ENV" ]; then
    echo "  using the existing $LOCAL_ENV (not shown)"
    return
  fi
  mkdir -p "$(dirname "$LOCAL_ENV")"
  (umask 077
   { echo "SIRAUGGA_LAB_URL=http://127.0.0.1:8788"
     echo "SIRAUGGA_LAB_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"; } > "$LOCAL_ENV")
  chmod 600 "$LOCAL_ENV"
  echo "  created $LOCAL_ENV (mode 600, not shown). Restart the Siraugga server to pick it up: bash restart_server.sh"
}

static_audit() {
  say "Audit (static checks + unit tests) - must pass before anything is deployed"
  (cd "$REPO" && run python3 scripts/audit_labcloud.py --no-live)
}

make_deploy_config() {
  # Writes a gitignored copy of wrangler.jsonc with the real domain (and optional embedding site) filled in.
  python3 - "$HERE/wrangler.jsonc" "$1" "$LAB_DOMAIN" "${SIRAUGGA_ORIGIN:-}" <<'PY'
import json, re, sys
src, dst, domain, origin = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
text = "\n".join(re.sub(r"\s//[^\n\"]*$", "", ln) for ln in text.splitlines() if not ln.strip().startswith("//"))
cfg = json.loads(text)
cfg["routes"] = [{"pattern": domain, "custom_domain": True}]
if origin:
    cfg.setdefault("vars", {})["EMBED_ORIGINS"] = origin
json.dump(cfg, open(dst, "w", encoding="utf-8"), indent=2)
PY
}

deploy() {
  prereqs
  : "${LAB_DOMAIN:?set LAB_DOMAIN, e.g.  LAB_DOMAIN=lab.example.com bash labcloud/setup.sh deploy}"
  [[ "$LAB_DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$ ]] || die "LAB_DOMAIN does not look like a domain name"
  ENVF="$REPO/.env.cloudflare"
  [ -f "$ENVF" ] || die "missing $ENVF (Cloudflare API token and account id)"
  install_deps
  build_image
  static_audit

  say "Master secret"
  if [ -f "$SECRET_FILE" ]; then
    echo "  using the existing secret file (not shown)"
  elif [ "$DRY" = 1 ]; then
    echo "  [dry-run] would create a random secret at $SECRET_FILE (mode 600)"
  else
    mkdir -p "$(dirname "$SECRET_FILE")"
    (umask 077; python3 -c 'import secrets; print(secrets.token_hex(32), end="")' > "$SECRET_FILE")
    chmod 600 "$SECRET_FILE"
    echo "  created $SECRET_FILE (not shown)"
  fi

  say "Deploy configuration (generated, gitignored)"
  GEN="$HERE/.wrangler-deploy.jsonc"
  make_deploy_config "$GEN"
  echo "  domain: $LAB_DOMAIN   config: $GEN"

  if [ "$DRY" = 1 ]; then
    echo "  [dry-run] would ask you to type DEPLOY, then:"
  else
    echo
    echo "About to change things ONLINE: add the lab_progress table, deploy the Worker + lab container to $LAB_DOMAIN,"
    echo "and set the Worker secret."
    read -r -p "Type DEPLOY to continue: " answer
    [ "$answer" = "DEPLOY" ] || die "cancelled, nothing was changed online"
    set -a; . "$ENVF"; set +a          # Cloudflare token for wrangler; never printed
  fi

  say "Database table"
  run npx --yes wrangler@4 d1 execute mikeytech --config "$GEN" --remote --file "$HERE/lab_schema.sql"
  say "Deploying (wrangler builds the container image from labcloud/image and uploads it)"
  run npx --yes wrangler@4 deploy --config "$GEN"
  say "Worker secret"
  if [ "$DRY" = 1 ]; then
    echo "  [dry-run] would upload the secret file to the Worker"
  else
    npx --yes wrangler@4 secret put LAB_MASTER_SECRET --config "$GEN" < "$SECRET_FILE"
  fi

  say "Verifying the live site (attack probes + course steps; includes the 'no internet' check)"
  if [ "$DRY" = 1 ]; then
    echo "  [dry-run] would run: audit_labcloud.py --url https://$LAB_DOMAIN --require-live"
  else
    (cd "$REPO" && SIRAUGGA_LAB_SECRET="$(cat "$SECRET_FILE")" python3 scripts/audit_labcloud.py --url "https://$LAB_DOMAIN" --require-live)
  fi

  say "Done. On the Siraugga server set:"
  echo "  SIRAUGGA_LAB_URL=https://$LAB_DOMAIN"
  echo "  SIRAUGGA_LAB_SECRET=<the contents of $SECRET_FILE>   (this script never prints it)"
  echo "Then check in the Cloudflare dashboard that the container cap (max_instances) is what you expect."
}

case "$MODE" in
  check)  prereqs ;;
  env)    local_env ;;
  local)  prereqs; install_deps; build_image; static_audit; local_env
          say "Ready. Start the local stack with:  bash labcloud/dev.sh   (then test:  python3 scripts/audit_labcloud.py)" ;;
  deploy) deploy ;;
  *)      sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
