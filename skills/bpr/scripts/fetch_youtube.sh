#!/bin/bash
# fetch_youtube.sh — pull subs + metadata from a YouTube URL, ready for /bpr.
#
# Usage:
#   ./fetch_youtube.sh <youtube-url> <output-dir>
#
# Outputs in <output-dir>:
#   transcript.txt      — cleaned plain-text transcript (deduped, tags stripped)
#   metadata.json       — title / uploader / upload_date / description / duration
#   transcript.*.vtt    — raw vtt (kept for debugging)
#
# Requires: yt-dlp (install: `brew install yt-dlp` or `uv tool install yt-dlp`).
# Does NOT require ffmpeg or whisper.

set -euo pipefail

URL="${1:-}"
OUT_DIR="${2:-}"

if [[ -z "$URL" || -z "$OUT_DIR" ]]; then
  echo "Usage: $0 <youtube-url> <output-dir>" >&2
  exit 2
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "ERROR: yt-dlp not installed." >&2
  echo "Install with one of:" >&2
  echo "  brew install yt-dlp" >&2
  echo "  uv tool install yt-dlp" >&2
  echo "  pipx install yt-dlp" >&2
  exit 3
fi

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. metadata (title / uploader / description / date / duration)
echo "→ Fetching metadata..."
yt-dlp --dump-json --skip-download "$URL" \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
out = {k: d.get(k) for k in (
  "title", "uploader", "uploader_id", "channel", "channel_id",
  "upload_date", "duration", "duration_string", "description",
  "tags", "categories", "webpage_url",
)}
print(json.dumps(out, ensure_ascii=False, indent=2))
' > metadata.json
echo "  saved metadata.json"

# 2. subs — prefer uploaded, fall back to auto-generated
echo "→ Fetching subtitles (prefer uploaded, fallback auto)..."
yt-dlp \
  --write-subs --write-auto-subs \
  --sub-langs "en-orig,en,en-GB,en-US" \
  --skip-download \
  -o "transcript.%(ext)s" \
  "$URL" 2>&1 | grep -E "(Writing|already)" || true

# Find which vtt actually downloaded
VTT_FILE=""
for cand in transcript.en-orig.vtt transcript.en.vtt transcript.en-GB.vtt transcript.en-US.vtt; do
  if [[ -f "$cand" ]]; then
    VTT_FILE="$cand"
    break
  fi
done

if [[ -z "$VTT_FILE" ]]; then
  echo "ERROR: no English subtitles found (uploaded or auto)." >&2
  echo "Possible reasons:" >&2
  echo "  - Video has no captions at all" >&2
  echo "  - YouTube blocked the request (try again, or use a different network)" >&2
  echo "Fallback: download audio with 'yt-dlp -x' and run whisper manually." >&2
  exit 4
fi

echo "  using $VTT_FILE"

# 3. clean vtt → plain text
echo "→ Cleaning VTT..."
python3 "$SCRIPT_DIR/clean_vtt.py" "$VTT_FILE" transcript.txt

echo ""
echo "✓ Done. Outputs in $OUT_DIR:"
ls -la transcript.txt metadata.json 2>/dev/null

echo ""
echo "Next step: feed transcript.txt to /bpr along with metadata.json for"
echo "title / uploader / host context."
