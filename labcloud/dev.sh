#!/bin/bash
# Run the whole lab cloud LOCALLY (real containers via Docker, local throwaway database). Run in WSL:
#     bash labcloud/dev.sh
# Then open the printed address. Nothing here touches Cloudflare. The dev secret below is for local use only.
export PATH="$HOME/.local/node/bin:$PATH"
cd "$(dirname "$0")" || exit 1
STATE="${LAB_DEV_STATE:-$HOME/.cache/siraugga-lab-dev}"
mkdir -p "$STATE"
npx --yes wrangler@4 d1 execute mikeytech --config wrangler.jsonc --local --persist-to "$STATE" \
    --file lab_schema.sql > /dev/null
exec npx --yes wrangler@4 dev --config wrangler.jsonc --local --persist-to "$STATE" --port 8788 \
    --var "LAB_MASTER_SECRET:${LAB_MASTER_SECRET:-local-dev-only}"
