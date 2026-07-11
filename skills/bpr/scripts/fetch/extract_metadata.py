#!/usr/bin/env python3
"""Extract publish-date / title / author / publication slug from any blog or
article URL — for use in /bpr filename construction.

Usage:
  python3 extract_metadata.py <URL>

Output: pretty JSON on stdout with keys:
  date          ISO YYYY-MM-DD or null
  title         Page title (cleaned) or null
  author        First author name or null
  publication   Publication / domain display name (e.g. "andrewchen.com")
  source_slug   Suggested kebab-case slug for filename (e.g. "andrew-chen")
  canonical     <link rel="canonical">'s href, or input URL
  source        Which strategy hit (debug field)

Date priority (highest first):
  1. JSON-LD <script type="application/ld+json"> → datePublished / dateCreated / uploadDate
  2. OG meta  <meta property="article:published_time">
  3. Generic meta: pubdate / date / DC.date.issued / parsely-pub-date / sailthru.date
  4. HTML5 <time datetime="...">
  5. URL pattern /YYYY/MM/DD/
  6. null  (caller should ask user)

YouTube URLs:
  Returned with date=null and a note pointing to scripts/fetch/fetch_youtube.sh.
  Don't try to scrape YouTube here — yt-dlp's metadata.json is the real source.

No external deps — only stdlib (urllib + re + json).
"""
import json
import re
import sys
import urllib.request
from urllib.parse import urlparse


# ────────────────────────────────────────────────────────────────────────────
# Source slug map.  Add new entries here when you encounter publications that
# need a non-default slug.  Keys are matched against host (preferred) then
# registered domain (last 2 parts).  Path-prefix keys (e.g. "anthropic.com/news")
# also supported.
# ────────────────────────────────────────────────────────────────────────────
SOURCE_SLUGS = {
    # Single-author essay sites
    "paulgraham.com": "paul-graham",
    "nav.al": "naval",
    "andrewchen.com": "andrew-chen",
    "stratechery.com": "stratechery",
    "ben-evans.com": "ben-evans",

    # Newsletters / blogs
    "lennysnewsletter.com": "lennys-podcast",
    "every.to": "every",
    "platformer.news": "platformer",
    "noahpinion.blog": "noahpinion",

    # AI lab blogs
    "anthropic.com": "anthropic-blog",
    "openai.com": "openai-blog",
    "deepmind.google": "deepmind-blog",
    "deepmind.com": "deepmind-blog",
    "blog.google": "google-blog",
    "huggingface.co": "huggingface-blog",

    # Generic platforms (fallback, prefer to override per-publication)
    "substack.com": "substack",
    "medium.com": "medium",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "youtu.be": "youtube",

    # YC ecosystem
    "ycombinator.com": "y-combinator",
    "ycombinator.com/blog": "yc-blog",

    # Path-prefix variants
    "anthropic.com/news": "anthropic-blog",
    "anthropic.com/research": "anthropic-research",
}


# ────────────────────────────────────────────────────────────────────────────
# HTTP fetch
# ────────────────────────────────────────────────────────────────────────────
def fetch(url, timeout=10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get("Content-Type", "")
        m = re.search(r"charset=([^\s;]+)", ctype, re.IGNORECASE)
        charset = m.group(1) if m else "utf-8"
        return raw.decode(charset, errors="replace")


# ────────────────────────────────────────────────────────────────────────────
# Date helpers
# ────────────────────────────────────────────────────────────────────────────
def normalize_date(s):
    """Accept ISO-ish strings, return YYYY-MM-DD, else None."""
    if not s:
        return None
    s = str(s).strip()
    # 2024-05-07T12:34:56+00:00 / 2024-05-07
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 20240507
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 2024/05/07
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


# ────────────────────────────────────────────────────────────────────────────
# JSON-LD parsing
# ────────────────────────────────────────────────────────────────────────────
def find_jsonld(html):
    """Return all JSON-LD payloads as a flat list of dicts."""
    blocks = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        body = m.group(1).strip()
        # Some sites wrap JSON in HTML comments — strip them
        body = re.sub(r"^<!--", "", body)
        body = re.sub(r"-->$", "", body)
        try:
            data = json.loads(body)
        except Exception:
            continue
        if isinstance(data, list):
            blocks.extend(data)
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                blocks.extend(data["@graph"])
            blocks.append(data)
    return blocks


def date_from_jsonld(blocks):
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for key in ("datePublished", "dateCreated", "uploadDate", "dateModified"):
            d = normalize_date(b.get(key))
            if d:
                return d, f"jsonld:{key}"
    return None, None


def author_from_jsonld(blocks):
    for b in blocks:
        if not isinstance(b, dict):
            continue
        a = b.get("author")
        if isinstance(a, dict):
            if a.get("name"):
                return a["name"]
        elif isinstance(a, list) and a:
            first = a[0]
            if isinstance(first, dict) and first.get("name"):
                return first["name"]
            if isinstance(first, str):
                return first
        elif isinstance(a, str) and a:
            return a
    return None


def title_from_jsonld(blocks):
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for key in ("headline", "name"):
            t = b.get(key)
            if isinstance(t, str) and t.strip():
                return t.strip()
    return None


# ────────────────────────────────────────────────────────────────────────────
# Meta tag extraction
# ────────────────────────────────────────────────────────────────────────────
def _meta_content(html, attr_name, attr_value):
    """Look up <meta {attr_name}="{attr_value}" content="..."> in either order."""
    av = re.escape(attr_value)
    patterns = [
        rf'<meta[^>]+{attr_name}=["\']{av}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+{attr_name}=["\']{av}["\']',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def date_from_og(html):
    val = _meta_content(html, "property", "article:published_time")
    if val:
        d = normalize_date(val)
        if d:
            return d, "og:article:published_time"
    return None, None


def date_from_generic_meta(html):
    candidates = [
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "publish-date"),
        ("name", "date"),
        ("name", "DC.date.issued"),
        ("name", "dc.date.issued"),
        ("name", "parsely-pub-date"),
        ("name", "sailthru.date"),
        ("name", "article:published"),
        ("itemprop", "datePublished"),
    ]
    for attr_name, attr_value in candidates:
        val = _meta_content(html, attr_name, attr_value)
        if val:
            d = normalize_date(val)
            if d:
                return d, f"meta:{attr_value}"
    return None, None


def date_from_html5_time(html):
    """Find first <time datetime="..."> with a parseable date."""
    for m in re.finditer(
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    ):
        d = normalize_date(m.group(1))
        if d:
            return d, "html5:time"
    return None, None


def date_from_url(url):
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "url:slug"
    return None, None


def date_from_wp_uploads(html):
    """WordPress posts upload images to /wp-content/uploads/YYYY/MM/.
    The most-frequently-occurring YYYY/MM is almost always the post's
    publish month — author uploaded the post's images at write time.
    Requires ≥3 mentions for confidence (avoids matching old logo paths)."""
    paths = re.findall(r"wp-content/uploads/(\d{4})/(\d{2})/", html)
    if not paths:
        return None, None
    from collections import Counter
    counter = Counter(f"{y}/{m}" for y, m in paths)
    most_common, count = counter.most_common(1)[0]
    if count < 3:
        return None, None
    y, m = most_common.split("/")
    return f"{y}-{m}-01", "wp-uploads"


def date_from_body_text(html):
    """Scan the first ~1500 chars of stripped body text for 'Month YYYY'
    or 'Month DD, YYYY'. Useful for old-school sites (paulgraham.com)
    that put the date as plain text at the top of the article."""
    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1) if body_match else html
    body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    head = text[:1500]

    months = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }
    pat_full = (
        r"\b(January|February|March|April|May|June|July|August"
        r"|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b"
    )
    m = re.search(pat_full, head)
    if m:
        return (
            f"{int(m.group(3)):04d}-{months[m.group(1)]:02d}-{int(m.group(2)):02d}",
            "body:month-day-year",
        )
    pat_short = (
        r"\b(January|February|March|April|May|June|July|August"
        r"|September|October|November|December)\s+(\d{4})\b"
    )
    m = re.search(pat_short, head)
    if m:
        return (
            f"{int(m.group(2)):04d}-{months[m.group(1)]:02d}-01",
            "body:month-year",
        )
    return None, None


def title_from_html(html):
    val = _meta_content(html, "property", "og:title")
    if val:
        return val.strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def author_from_meta(html):
    for attr, val in (("name", "author"), ("property", "article:author")):
        v = _meta_content(html, attr, val)
        if v and not v.startswith("http"):  # skip URL-only article:author
            return v.strip()
    return None


# ────────────────────────────────────────────────────────────────────────────
# Publication / slug detection
# ────────────────────────────────────────────────────────────────────────────
def slug_from_domain(domain):
    domain = re.sub(r"^www\.", "", domain.lower())
    base = domain.rsplit(".", 1)[0]
    base = base.replace(".", "-")
    base = re.sub(r"[^a-z0-9-]+", "-", base).strip("-")
    return base or domain


def detect_publication(url):
    """Return (display_host, slug)."""
    parsed = urlparse(url)
    host = re.sub(r"^www\.", "", parsed.netloc.lower())

    # Path-prefix keys first (longer match wins)
    full = host + parsed.path
    path_keys = sorted(
        (k for k in SOURCE_SLUGS if "/" in k),
        key=len,
        reverse=True,
    )
    for k in path_keys:
        if full.startswith(k):
            return host, SOURCE_SLUGS[k]

    # Direct host match
    if host in SOURCE_SLUGS:
        return host, SOURCE_SLUGS[host]

    # Registered domain (last 2 parts)
    parts = host.split(".")
    if len(parts) >= 2:
        registered = ".".join(parts[-2:])
        if registered in SOURCE_SLUGS:
            return host, SOURCE_SLUGS[registered]

    return host, slug_from_domain(host)


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        sys.exit(2)

    url = sys.argv[1]
    parsed = urlparse(url)

    # YouTube — defer to fetch_youtube.sh
    if any(parsed.netloc.endswith(d) for d in ("youtube.com", "youtu.be")):
        publication, slug = detect_publication(url)
        print(json.dumps({
            "date": None,
            "title": None,
            "author": None,
            "publication": publication,
            "source_slug": slug,
            "canonical": url,
            "source": "youtube_skip",
            "note": "Use scripts/fetch/fetch_youtube.sh; date comes from metadata.json upload_date.",
        }, ensure_ascii=False, indent=2))
        return

    try:
        html = fetch(url)
    except Exception as e:
        print(json.dumps({"error": f"fetch failed: {e}", "url": url}, indent=2))
        sys.exit(1)

    blocks = find_jsonld(html)

    # Date — try strategies in priority order
    date, source = None, None
    for strategy in (
        lambda: date_from_jsonld(blocks),
        lambda: date_from_og(html),
        lambda: date_from_generic_meta(html),
        lambda: date_from_html5_time(html),
        lambda: date_from_url(url),
        lambda: date_from_wp_uploads(html),
        lambda: date_from_body_text(html),
    ):
        d, s = strategy()
        if d:
            date, source = d, s
            break

    title = title_from_jsonld(blocks) or title_from_html(html)
    author = author_from_jsonld(blocks) or author_from_meta(html)
    publication, source_slug = detect_publication(url)

    canon = None
    m = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if m:
        canon = m.group(1)

    print(json.dumps({
        "date": date,
        "title": title,
        "author": author,
        "publication": publication,
        "source_slug": source_slug,
        "canonical": canon or url,
        "source": source or "none",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
