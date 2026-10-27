#!/usr/bin/env sh
# Fetch Cohere's published Qwen3.8-Flash-Next investigation trace (not redistributed here: no license declared).
set -eu
REV="028b7cd7d931586dbfa05463903be9d45c4924ac"
SHA256="7110edee1203a58c8dea3b0e3f0a18a86fa42515a655b7b1901a7dda0278d1e6"
URL="https://huggingface.co/datasets/CohereLabs/10-2026-qwen-investigation-traces/resolve/${REV}/qwen-investigation.jsonl"
DIR="$(cd "$(dirname "$0")/.." && pwd)/fixtures/cohere"
OUT="$DIR/qwen-investigation.jsonl"
mkdir -p "$DIR"
echo "Fetching $URL"
curl -fsSL "$URL" -o "$OUT.tmp"
GOT="$( (sha256sum "$OUT.tmp" 2>/dev/null || shasum -a 256 "$OUT.tmp") | awk '{print $1}')"
if [ "$GOT" != "$SHA256" ]; then
  echo "sha256 mismatch: got $GOT expected $SHA256" >&2; rm -f "$OUT.tmp"; exit 1
fi
mv "$OUT.tmp" "$OUT"
echo "OK -> $OUT"
