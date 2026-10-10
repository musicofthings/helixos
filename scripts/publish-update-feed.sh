#!/usr/bin/env bash
# Upload electron-updater feed files to the Cloudflare R2 bucket behind
# https://releases.helixos.dev, then verify the public feed serves what we uploaded.
#
#   scripts/publish-update-feed.sh <assets-dir>
#
# Required env (unless DRY_RUN=1): CLOUDFLARE_API_TOKEN (R2 edit), CLOUDFLARE_ACCOUNT_ID, R2_BUCKET
# Optional env: FEED_PREFIX (default "desktop"), FEED_URL (default https://releases.helixos.dev/desktop)
#               DRY_RUN=1 prints what would be uploaded and does not touch the network.
#
# Upload order matters: archives and blockmaps first, latest-mac.yml last, so a
# client can never read a feed that points at a file that is not there yet.
set -euo pipefail

ASSETS_DIR="${1:?usage: publish-update-feed.sh <assets-dir>}"
FEED_PREFIX="${FEED_PREFIX:-desktop}"
FEED_URL="${FEED_URL:-https://releases.helixos.dev/desktop}"
DRY_RUN="${DRY_RUN:-0}"
FEED_FILE="$ASSETS_DIR/latest-mac.yml"

if [ ! -f "$FEED_FILE" ]; then
  echo "No latest-mac.yml in $ASSETS_DIR; nothing to publish" >&2
  exit 1
fi

if [ "$DRY_RUN" != "1" ]; then
  : "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
  : "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID is required}"
  : "${R2_BUCKET:?R2_BUCKET is required}"
fi

# Files the feed references (path:/url: entries), each with its blockmap if present.
referenced=$(grep -E '^ *(- )?(path|url):' "$FEED_FILE" | sed -E 's/^ *(- )?(path|url): *//' | sort -u)
if [ -z "$referenced" ]; then
  echo "latest-mac.yml references no files" >&2
  exit 1
fi

upload() { # <file> <content-type> <cache-control>
  local file="$1" type="$2" cache="$3" key
  key="$FEED_PREFIX/$(basename "$file")"
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] put $key  ($type; $cache)"
  else
    echo "Uploading $key"
    npx --yes wrangler@4 r2 object put "$R2_BUCKET/$key" --remote \
      --file "$file" --content-type "$type" --cache-control "$cache"
  fi
}

for name in $referenced; do
  [ -f "$ASSETS_DIR/$name" ] || { echo "Missing referenced file: $name" >&2; exit 1; }
  upload "$ASSETS_DIR/$name" "application/zip" "public, max-age=31536000, immutable"
  [ -f "$ASSETS_DIR/$name.blockmap" ] && \
    upload "$ASSETS_DIR/$name.blockmap" "application/octet-stream" "public, max-age=31536000, immutable"
done
upload "$FEED_FILE" "text/yaml" "no-cache"

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would verify $FEED_URL/latest-mac.yml"
  exit 0
fi

for attempt in 1 2 3 4 5; do
  if curl -fsS "$FEED_URL/latest-mac.yml?verify=$RANDOM" | cmp -s - "$FEED_FILE"; then
    echo "Verified: $FEED_URL/latest-mac.yml matches the uploaded feed"
    exit 0
  fi
  echo "Feed not yet identical at $FEED_URL (attempt $attempt/5); retrying..." >&2
  sleep 5
done
echo "Published feed at $FEED_URL does not match latest-mac.yml" >&2
exit 1
