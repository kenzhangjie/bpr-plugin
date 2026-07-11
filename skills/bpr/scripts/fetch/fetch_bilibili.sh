#!/bin/bash
# fetch_bilibili.sh — pull subs + metadata from a B 站 (bilibili.com) video.
# If no subtitles exist, also download audio for transcription via 飞书妙记.
#
# Usage:
#   ./fetch_bilibili.sh <video-url> <output-dir> [--no-cookies]
#
# URL patterns supported:
#   https://www.bilibili.com/video/BV<id>
#   https://b23.tv/<short>           (yt-dlp auto-resolves)
#
# Outputs in <output-dir>:
#   metadata.json              — title / uploader / upload_date / duration / description
#   transcript.txt             — cleaned plain-text transcript (IF subtitles available)
#   transcript.*.vtt           — raw vtt (debug, kept)
#   audio.m4a                  — audio file (IF no subs found, for lark-minutes transcription)
#
# Cookie behavior:
#   Many B 站 videos require login (members-only, 1080p, region-locked).
#   By default uses --cookies-from-browser chrome. Pass --no-cookies as 3rd arg to disable.
#
# Requires: yt-dlp.

set -euo pipefail

URL="${1:-}"
OUT_DIR="${2:-}"
NO_COOKIES="${3:-}"

if [[ -z "$URL" || -z "$OUT_DIR" ]]; then
  echo "Usage: $0 <bilibili-video-url> <output-dir> [--no-cookies]" >&2
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

COOKIE_ARGS=()
if [[ "$NO_COOKIES" != "--no-cookies" ]]; then
  COOKIE_ARGS=(--cookies-from-browser chrome)
fi

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Metadata
echo "→ Fetching metadata..."
yt-dlp "${COOKIE_ARGS[@]}" --dump-json --skip-download "$URL" \
  | /usr/bin/python3 -c '
import json, sys
d = json.load(sys.stdin)
out = {k: d.get(k) for k in (
  "title", "uploader", "uploader_id", "channel", "channel_id",
  "upload_date", "duration", "duration_string", "description",
  "tags", "categories", "webpage_url",
)}
out["source"] = "bilibili"
print(json.dumps(out, ensure_ascii=False, indent=2))
' > metadata.json
echo "  saved metadata.json"

# 2. Subtitles — try uploaded first, then auto-generated.
#    B 站 sub langs: zh-CN, zh-Hans, zh, ai-zh, en etc.
echo "→ Trying subtitles (uploaded / auto)..."
yt-dlp "${COOKIE_ARGS[@]}" \
  --write-subs --write-auto-subs \
  --sub-langs "zh-CN,zh-Hans,zh,ai-zh,en" \
  --skip-download \
  -o "transcript.%(ext)s" \
  "$URL" 2>&1 | grep -E "(Writing|already)" || true

VTT_FILE=""
for cand in transcript.zh-CN.vtt transcript.zh-Hans.vtt transcript.zh.vtt transcript.ai-zh.vtt transcript.en.vtt; do
  if [[ -f "$cand" ]]; then
    VTT_FILE="$cand"
    break
  fi
done

if [[ -n "$VTT_FILE" ]]; then
  echo "  ✓ found subtitles: $VTT_FILE"
  /usr/bin/python3 "$SCRIPT_DIR/clean_vtt.py" "$VTT_FILE" transcript.txt
  echo ""
  echo "✓ Done with subs. Outputs in $OUT_DIR:"
  ls -la transcript.txt metadata.json 2>/dev/null
  echo ""
  echo "Next step: feed transcript.txt to /bpr (with metadata.json for hero context)."
  exit 0
fi

# 3. No subs — download audio for transcription
echo "  ✗ no subtitles found. Falling back to audio download for 飞书妙记 transcription."
echo ""
echo "→ Downloading audio..."
yt-dlp "${COOKIE_ARGS[@]}" \
  -f "bestaudio[ext=m4a]/bestaudio" \
  -o "audio.%(ext)s" \
  "$URL" 2>&1 | grep -E "(download|Destination|already)" || true

AUDIO_FILE=""
for cand in audio.m4a audio.mp3 audio.aac audio.webm audio.ogg; do
  if [[ -f "$cand" ]]; then
    AUDIO_FILE="$(pwd)/$cand"
    break
  fi
done

if [[ -z "$AUDIO_FILE" ]]; then
  echo "ERROR: no audio file downloaded." >&2
  exit 4
fi

AUDIO_SIZE=$(wc -c < "$AUDIO_FILE" | tr -d ' ')
echo "  audio: $AUDIO_FILE ($(echo "scale=1; $AUDIO_SIZE / 1048576" | bc) MB)"

# Patch metadata.json with audio path
/usr/bin/python3 - "$OUT_DIR" "$AUDIO_FILE" <<'PYEOF'
import json, sys
from pathlib import Path
out_dir, audio_file = Path(sys.argv[1]), sys.argv[2]
meta = json.loads((out_dir / "metadata.json").read_text())
meta["audio_local"] = audio_file
(out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
PYEOF

echo ""
echo "✓ Done with audio. Outputs in $OUT_DIR:"
ls -la "$AUDIO_FILE" metadata.json 2>/dev/null
echo ""
echo "Next step: transcribe via 飞书妙记 — see SKILL.md '小宇宙 / Bilibili → 飞书妙记 流程'."
echo ""
echo "⚠️  precheck: lark-cli requires 7 minutes scopes (app console must enable + user re-auth)."
echo "    Run first:  lark-cli auth scopes | grep minutes"
echo "    Required:   minutes:minutes.search:read / minutes:minutes.basic:read /"
echo "                minutes:minutes.upload:write / minutes:minutes.media:export /"
echo "                minutes:minutes:readonly / minutes:minutes.artifacts:read /"
echo "                minutes:minutes.transcript:export"
echo ""
echo "⚠️  lark-cli drive +upload rejects absolute paths — MUST cd into WORKDIR first:"
AUDIO_BASE=$(basename "$AUDIO_FILE")
echo ""
echo "  cd \"$OUT_DIR\""
echo "  lark-cli drive +upload --file ./$AUDIO_BASE --as user        # → file_token"
echo "  lark-cli minutes +upload --file-token <file_token> --as user  # → minute_url"
echo "  lark-cli vc +notes --minute-tokens <minute_token> --as user   # → 逐字稿"
