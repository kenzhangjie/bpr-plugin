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

# Resolved BEFORE the cd below: BASH_SOURCE is whatever path the caller typed,
# so a relative invocation (`bash scripts/fetch/fetch_youtube.sh …`) stops
# resolving the moment the working directory changes. Doing it after the cd
# failed with "cd: scripts/fetch: No such file or directory", which reads like a
# broken install rather than a path bug.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

# Cookie strategy: YouTube increasingly blocks unauthenticated requests
# ("Sign in to confirm you're not a bot"). Try Chrome cookies first, fall
# back to no cookies. Browsers tried in order: chrome, safari, firefox, edge.
COOKIE_BROWSER=""
for b in chrome safari firefox edge; do
  if yt-dlp --cookies-from-browser "$b" --simulate --quiet "$URL" >/dev/null 2>&1; then
    COOKIE_BROWSER="$b"
    echo "→ Using cookies from: $b"
    break
  fi
done
if [[ -z "$COOKIE_BROWSER" ]]; then
  echo "→ No browser cookies usable, trying anonymous (may fail with bot check)"
fi
COOKIE_ARG=""
[[ -n "$COOKIE_BROWSER" ]] && COOKIE_ARG="--cookies-from-browser $COOKIE_BROWSER"

# 1. metadata (title / uploader / description / date / duration)
echo "→ Fetching metadata..."
yt-dlp $COOKIE_ARG --dump-json --skip-download "$URL" \
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
yt-dlp $COOKIE_ARG \
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
