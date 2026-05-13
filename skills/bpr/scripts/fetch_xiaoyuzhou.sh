#!/bin/bash
# fetch_xiaoyuzhou.sh — pull an episode page from 小宇宙 (xiaoyuzhoufm.com)
# into a workdir ready for transcription via 飞书妙记 (lark-minutes).
#
# Usage:
#   ./fetch_xiaoyuzhou.sh <episode-url> <output-dir>
#
# URL patterns supported:
#   https://www.xiaoyuzhoufm.com/episode/<id>
#   https://xyzfm.com/episode/<id>
#
# Outputs in <output-dir>:
#   audio.m4a (or audio.mp3)   — raw audio file, ready for lark-minutes upload
#   metadata.json              — title / podcast / pub_date / duration / description
#   page.html                  — raw page snapshot (for debug)
#
# Why this script doesn't transcribe:
#   小宇宙 has no public subtitle / transcript API. After downloading the
#   audio, hand it to 飞书妙记 (lark-cli drive +upload → minutes +upload →
#   vc +notes --minute-tokens) to get a 逐字稿. See SKILL.md "URL 输入处理".
#
# Requires: curl, /usr/bin/python3 (for HTML parsing — no extra deps).

set -euo pipefail

URL="${1:-}"
OUT_DIR="${2:-}"

if [[ -z "$URL" || -z "$OUT_DIR" ]]; then
  echo "Usage: $0 <xiaoyuzhou-episode-url> <output-dir>" >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl not found." >&2
  exit 3
fi

mkdir -p "$OUT_DIR"
PAGE="$OUT_DIR/page.html"

echo "→ Fetching episode page..."
curl -sL --max-time 30 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -o "$PAGE" "$URL"

PAGE_SIZE=$(wc -c < "$PAGE" | tr -d ' ')
if [[ "$PAGE_SIZE" -lt 500 ]]; then
  echo "ERROR: page too small ($PAGE_SIZE bytes), likely blocked or invalid URL." >&2
  exit 4
fi
echo "  page size: $PAGE_SIZE bytes"

echo "→ Extracting audio URL + metadata (og:* + JSON-LD)..."
/usr/bin/python3 - "$PAGE" "$OUT_DIR" <<'PYEOF'
import json
import re
import sys
from html import unescape
from pathlib import Path

page_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
html = page_path.read_text(encoding="utf-8", errors="ignore")

def find_meta(prop):
    """Return <meta property="prop" content="..."> value, or empty."""
    m = re.search(
        r'<meta\s+(?:property|name)=["\']' + re.escape(prop) + r'["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if m: return unescape(m.group(1))
    m = re.search(
        r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']' + re.escape(prop) + r'["\']',
        html, re.IGNORECASE,
    )
    return unescape(m.group(1)) if m else ""

# --- Pass 1: og:* meta tags (baseline) ---
audio_url = find_meta("og:audio") or find_meta("og:audio:url") or find_meta("twitter:player:stream")
title     = find_meta("og:title") or find_meta("twitter:title") or ""
podcast   = find_meta("og:site_name") or ""
desc      = find_meta("og:description") or find_meta("description") or ""
pub_date  = find_meta("article:published_time") or find_meta("og:updated_time") or ""

# --- Pass 2: JSON-LD PodcastEpisode (richer than og:*) ---
# 小宇宙 embeds <script type="application/ld+json">{"@type":"PodcastEpisode",...}</script>
# which has datePublished, timeRequired, partOfSeries.name (real podcast series name)
jsonld_pub = ""
jsonld_series = ""
jsonld_duration = ""
for m in re.finditer(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([^<]+)</script>',
    html,
):
    try:
        data = json.loads(m.group(1))
    except Exception:
        continue
    if isinstance(data, list):
        candidates = data
    else:
        candidates = [data]
    for d in candidates:
        if not isinstance(d, dict): continue
        if d.get("@type") in ("PodcastEpisode", "Episode") or "datePublished" in d:
            jsonld_pub      = d.get("datePublished", "") or jsonld_pub
            jsonld_duration = d.get("timeRequired", "")  or jsonld_duration
            series = d.get("partOfSeries") or d.get("inSeries") or {}
            if isinstance(series, dict):
                jsonld_series = series.get("name", "") or jsonld_series

# Prefer JSON-LD values when present
if jsonld_pub:
    # Normalize "2026-05-11T00:00:00.000Z" → "2026-05-11"
    pub_date = jsonld_pub.split("T")[0]
if jsonld_series:
    # JSON-LD series.name is the REAL podcast name (e.g. "张小珺Jùn｜商业访谈录"),
    # whereas og:site_name is just "小宇宙" (the platform). Prefer JSON-LD.
    podcast = jsonld_series
elif not podcast:
    podcast = "小宇宙"

# Episode id from URL (stored in $URL by caller, parse from page <link rel=canonical> if available)
m = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\'][^"\']*?/episode/([a-z0-9]+)', html, re.IGNORECASE)
episode_id = m.group(1) if m else ""

# Try to find audio URL from JSON-LD or __NEXT_DATA__ if og:audio is missing
if not audio_url:
    m = re.search(r'"contentUrl"\s*:\s*"([^"]+\.(?:m4a|mp3))"', html)
    if m: audio_url = m.group(1)
if not audio_url:
    m = re.search(r'(https?://[^"\']+\.(?:m4a|mp3))', html)
    if m: audio_url = m.group(1)

if not audio_url:
    print("ERROR: could not find audio URL on page", file=sys.stderr)
    print("  Searched: og:audio / og:audio:url / twitter:player:stream / JSON-LD contentUrl / regex", file=sys.stderr)
    sys.exit(5)

# Clean title — 小宇宙 usually appends " | 小宇宙" suffix
title = re.sub(r"\s*[|｜]\s*小宇宙.*$", "", title).strip()

meta = {
    "source":     "xiaoyuzhou",
    "title":      title,
    "podcast":    podcast,
    "description": desc[:500],
    "publish_date": pub_date,        # YYYY-MM-DD (real episode pubDate from JSON-LD)
    "duration":   jsonld_duration,   # ISO 8601 e.g. "PT230M"
    "audio_url":  audio_url,
    "episode_id": episode_id,
    "page_url":   "",
}
(out_dir / "metadata.json").write_text(
    json.dumps(meta, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"  title:        {title}")
print(f"  podcast:      {podcast}")
print(f"  publish_date: {pub_date or '(not found)'}")
print(f"  duration:     {jsonld_duration or '(not found)'}")
print(f"  audio:        {audio_url}")
PYEOF

# Re-read metadata to get audio URL
AUDIO_URL=$(/usr/bin/python3 -c "import json; print(json.load(open('$OUT_DIR/metadata.json'))['audio_url'])")

# Determine extension
EXT="m4a"
if [[ "$AUDIO_URL" == *.mp3 ]]; then EXT="mp3"; fi
AUDIO_FILE="$OUT_DIR/audio.$EXT"

echo "→ Downloading audio to $AUDIO_FILE..."
curl -sL --max-time 600 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  -H "Referer: https://www.xiaoyuzhoufm.com/" \
  -o "$AUDIO_FILE" "$AUDIO_URL"

AUDIO_SIZE=$(wc -c < "$AUDIO_FILE" | tr -d ' ')
if [[ "$AUDIO_SIZE" -lt 100000 ]]; then
  echo "ERROR: audio file suspiciously small ($AUDIO_SIZE bytes)" >&2
  exit 6
fi
echo "  audio size: $(echo "scale=1; $AUDIO_SIZE / 1048576" | bc) MB"

# Patch metadata.json with local audio file path
/usr/bin/python3 - "$OUT_DIR" "$AUDIO_FILE" <<'PYEOF'
import json, sys
from pathlib import Path
out_dir, audio_file = Path(sys.argv[1]), sys.argv[2]
meta = json.loads((out_dir / "metadata.json").read_text())
meta["audio_local"] = audio_file
(out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
PYEOF

echo ""
echo "✓ Done. Outputs in $OUT_DIR:"
ls -la "$OUT_DIR/audio.$EXT" "$OUT_DIR/metadata.json"
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
echo ""
echo "  cd \"$OUT_DIR\""
echo "  lark-cli drive +upload --file ./audio.$EXT --as user      # → file_token"
echo "  lark-cli minutes +upload --file-token <file_token> --as user  # → minute_url"
echo "  lark-cli vc +notes --minute-tokens <minute_token> --as user   # → 逐字稿"
