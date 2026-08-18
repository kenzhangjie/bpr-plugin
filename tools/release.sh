#!/usr/bin/env bash
# Release helper for ddr-plugin.
#
# Usage:
#   ./tools/release.sh <new-version> "<commit message>"
#
# Example:
#   ./tools/release.sh 1.0.1 "patch: fix YouTube auto-subs re-segmentation"
#
# What it does:
#   1. Bumps version in plugin.json + marketplace.json (3 places)
#   2. Verifies CHANGELOG.md has [Unreleased] entries (or warns)
#   3. Stages, commits, tags, pushes — all in one go
#
# What it does NOT do:
#   - Create the tag remotely as a Release (do that on GitHub web for release notes)
#   - Update CHANGELOG.md content (you do that manually before running this)

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <new-version> \"<commit message>\""
  echo "Example: $0 1.0.1 \"patch: fix yt-dlp re-segmentation\""
  exit 2
fi

NEW_VERSION="$1"
MESSAGE="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Read current version
OLD_VERSION=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")

if [[ "$OLD_VERSION" == "$NEW_VERSION" ]]; then
  echo "✗ Version already at $NEW_VERSION — nothing to bump"
  exit 1
fi

echo "▶ Bumping $OLD_VERSION → $NEW_VERSION"

# Verify clean working tree
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "✗ Working tree not clean. Commit or stash first."
  git status --short
  exit 1
fi

# 1. Bump version in 3 places
sed -i.bak "s/\"version\": \"$OLD_VERSION\"/\"version\": \"$NEW_VERSION\"/g" \
  .claude-plugin/plugin.json .claude-plugin/marketplace.json
rm -f .claude-plugin/plugin.json.bak .claude-plugin/marketplace.json.bak

# 2. Verify versions are now in sync
python3 - <<EOF
import json
with open('.claude-plugin/plugin.json') as f:
    pj = json.load(f)
with open('.claude-plugin/marketplace.json') as f:
    mj = json.load(f)
plugin_v = pj['version']
mp_v = mj['metadata']['version']
mp_plugin_v = mj['plugins'][0]['version']
assert plugin_v == mp_v == mp_plugin_v == "$NEW_VERSION", \
    f'version sync broken after bump: {plugin_v}, {mp_v}, {mp_plugin_v}'
print(f'✓ Versions in sync: {plugin_v}')
EOF

# 3. Warn if CHANGELOG [Unreleased] is empty
if grep -A 1 '## \[Unreleased\]' CHANGELOG.md | tail -1 | grep -qE '^$|^## '; then
  echo "⚠️  CHANGELOG.md [Unreleased] section appears empty."
  echo "    You probably want to add entries before tagging."
  read -r -p "    Continue anyway? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# 4. Show diff for review
echo ""
echo "▶ Diff preview:"
git diff --stat
echo ""
read -r -p "Proceed with commit + tag + push? [y/N] " ans
[[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted. Reverting bump."; git checkout -- .claude-plugin/; exit 1; }

# 5. Commit + tag + push
git add -A
git commit -m "v${NEW_VERSION}: ${MESSAGE}"
git tag "v${NEW_VERSION}"
git push
git push --tags

echo ""
echo "✅ Released v${NEW_VERSION}"
echo ""
echo "Next:"
echo "  - Open https://github.com/kenzhangjie/ddr-plugin/releases/new?tag=v${NEW_VERSION}"
echo "    to write release notes (paste from CHANGELOG)"
