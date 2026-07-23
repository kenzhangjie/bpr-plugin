#!/usr/bin/env python3
"""Build ~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/{index,posters}.html from BPR HTML files.

This is a personal publishing tool for ken.solar — separate from the BPR plugin
itself (which only generates per-content HTML/poster).

Usage:
  /usr/bin/python3 "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/bin/build_index.py"

Generates:
  - index.html  : landing page with bio + chronological entry list (with poster thumbs)
  - posters.html: visual gallery of all posters (only entries with -poster.png)

Both share a lightbox preview (click thumb → modal, ESC/click outside to close).

Idempotent. Safe to rerun anytime.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date as _date
from html import escape
from pathlib import Path

import os
# Default: $TRANSCRIPT_DIR env var, then arg1, then cwd (allows running on Vercel).
_default = os.environ.get("TRANSCRIPT_DIR") or os.getcwd()
TRANSCRIPT_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else _default).resolve()
INDEX_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else TRANSCRIPT_DIR / "index.html"
POSTERS_PATH = TRANSCRIPT_DIR / "posters.html"
BASE_URL = "https://bpr.ken.solar"

# "Added" ordering source of truth. The filename only carries the *content* date;
# this manifest records when each entry was first added to the site. It must be
# maintained LOCALLY (where file birthtimes are real) and shipped with the deploy —
# on Vercel build the checkout birthtimes are bogus, so existing entries here are
# authoritative and never overwritten. No leading dot, so `vercel --prod` uploads it.
ADDED_MANIFEST = TRANSCRIPT_DIR / "added-dates.json"


def load_added_manifest() -> dict:
    try:
        data = json.loads(ADDED_MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_added_manifest(manifest: dict) -> None:
    try:
        ADDED_MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        print(f"WARN: could not write {ADDED_MANIFEST.name}: {e}", file=sys.stderr)

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([^_]+)_(.+)\.html$")
TAG_STRIP_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

# ── Tag taxonomy ─────────────────────────────────────────────────
# Format tags (1 per entry, derived from source slug)
FORMAT_BY_SOURCE = {
    "lennys-podcast": "podcast",
    "20vc": "podcast",
    "dwarkesh-podcast": "podcast",
    "naval-podcast": "podcast",
    "training-data": "podcast",
    "sales-podcast": "podcast",
    "y-combinator": "talk",
    "ai-summit": "talk",
    "sequoia": "talk",
    "anthropic-blog": "essay",
    "naval-blog": "essay",
    "andrew-chen": "essay",
    "paul-graham": "essay",
    "pmarchive": "essay",
}

# Topic tags (multiple per entry, derived from h1 + zh keywords)
TOPIC_KEYWORDS = {
    "agent":      ["agent", "agentic", "/loop", "loops", "claude code", "harness", "sub-agent"],
    "coding":     ["coding", "code", "developer", "programmer", "software engineer"],
    "growth":     ["growth", "arr", "ltv", "cac", "retention", "churn", "scale"],
    "product":    ["product", "pm", "product manager", "ship", "shipping"],
    "ai-models":  ["model", "gpt", "claude", "opus", "sonnet", "haiku", "llm", "foundation", "training"],
    "philosophy": ["philosophy", "specific knowledge", "leverage", "wealth", "free", "wisdom", "naval"],
    "leadership": ["team", "org", "leadership", "manager", "founder", "ceo"],
    "design":     ["design", "designer", "ux", "ui"],
    "business":   ["saas", "startup", "moat", "powers", "business", "revenue", "pricing"],
    "infra":      ["infra", "infrastructure", "system", "architecture", "database", "sql"],
}

ALL_TOPIC_TAGS = list(TOPIC_KEYWORDS.keys())
ALL_FORMAT_TAGS = ["podcast", "essay", "talk"]


def infer_tags(h1: str, zh: str, eyebrow: str, source: str) -> list[str]:
    """Pick 2-4 topic tags + 1 format tag based on heuristic content match."""
    text = f"{h1} {zh} {eyebrow}".lower()
    tags: list[str] = []

    # format (1)
    fmt = FORMAT_BY_SOURCE.get(source)
    if fmt:
        tags.append(fmt)

    # topics (multiple)
    topic_scores: dict[str, int] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score:
            topic_scores[topic] = score
    # take top 3 by score
    top_topics = sorted(topic_scores.items(), key=lambda x: -x[1])[:3]
    tags.extend(t for t, _ in top_topics)
    return tags


def clean(text: str) -> str:
    text = TAG_STRIP_RE.sub("", text)
    text = WS_RE.sub(" ", text)
    return text.strip()


def extract_h1_with_em(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.+?)</h1>", html, re.DOTALL)
    if not m:
        return ""
    inner = m.group(1)
    inner = re.sub(r"<(?!/?em\b)[^>]+>", "", inner, flags=re.IGNORECASE)
    return WS_RE.sub(" ", inner).strip()


def extract_field(html: str, css_class: str) -> str:
    pattern = (
        rf'class="[^"]*\b{re.escape(css_class)}\b[^"]*"[^>]*>(.+?)</'
        r"(?:p|div|h[1-6]|span|section|header|footer|article)>"
    )
    m = re.search(pattern, html, re.DOTALL)
    return clean(m.group(1)) if m else ""


def parse_entry(path: Path) -> dict | None:
    m = FILENAME_RE.match(path.name)
    if not m:
        return None
    iso, source, rest = m.groups()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    # File creation date — used to bootstrap the added-dates manifest for entries
    # not yet recorded. Falls back to mtime, then the content date.
    try:
        st = path.stat()
        birth_ts = getattr(st, "st_birthtime", None) or st.st_mtime
        birth = _date.fromtimestamp(birth_ts).isoformat()
    except Exception:
        birth = iso
    stem = path.stem
    # If the file is in a subdir (e.g., bytedance/), capture the collection name.
    # Top-level files have collection = "".
    try:
        rel_parent = path.parent.relative_to(TRANSCRIPT_DIR)
        collection = str(rel_parent) if str(rel_parent) != "." else ""
    except ValueError:
        collection = ""
    # Poster / card live alongside the .html, in the same dir.
    poster_dir = path.parent
    poster = poster_dir / f"{stem}-poster.png"
    card = poster_dir / f"{stem}-card.png"
    # href is relative to TRANSCRIPT_DIR root
    href_prefix = f"{collection}/" if collection else ""
    poster_href = f"{href_prefix}{stem}-poster.png" if poster.exists() else None
    card_href = f"{href_prefix}{stem}-card.png" if card.exists() else None

    h1 = extract_h1_with_em(text) or rest.replace("-", " ").title()
    zh = extract_field(text, "hero-zh")
    eyebrow = extract_field(text, "hero-eyebrow")

    # tags: prefer <meta name="tags" content="..."> if present, else infer
    meta_tag_match = re.search(r'<meta\s+name="tags"\s+content="([^"]+)"', text)
    if meta_tag_match:
        tags = [t.strip() for t in meta_tag_match.group(1).split(",") if t.strip()]
    else:
        tags = infer_tags(h1, zh, eyebrow, source)

    return {
        "iso": iso,
        "year": iso[:4],
        "birth": birth,
        "source": source,
        "rest": rest,
        "href": f"{href_prefix}{path.name}",
        "collection": collection,
        "poster_href": poster_href,
        "card_href": card_href,
        "tags": tags,
        "h1": h1,
        "zh": zh,
        "eyebrow": eyebrow,
    }


def collect_entries() -> list[dict]:
    entries: list[dict] = []
    # Scan top-level + one level deep subdirs (e.g., bytedance/*.html)
    candidates = list(TRANSCRIPT_DIR.glob("*.html")) + list(TRANSCRIPT_DIR.glob("*/*.html"))
    for f in candidates:
        if f.name in ("index.html", "posters.html"):
            continue
        if f.name.endswith("-poster.html"):
            continue
        # Skip files in images/ or .vercel/ subdirs
        if any(part in ("images", ".vercel", "node_modules") for part in f.parts):
            continue
        e = parse_entry(f)
        if e:
            entries.append(e)

    # Resolve each entry's "added" date from the manifest (source of truth).
    # New entries (not yet recorded) are stamped with their file birthtime and
    # persisted; existing records are never overwritten.
    manifest = load_added_manifest()
    changed = False
    for e in entries:
        key = e["href"]
        if key in manifest:
            e["added"] = manifest[key]
        else:
            e["added"] = e["birth"]
            manifest[key] = e["added"]
            changed = True
    if changed:
        save_added_manifest(manifest)

    entries.sort(key=lambda x: x["iso"], reverse=True)
    return entries


# ─── shared lightbox markup / styles / script ───

LIGHTBOX_HTML = """
  <div class="lightbox" id="lightbox" hidden role="dialog" aria-label="海报预览">
    <span class="lightbox-hint">Scroll · 滚动 · 点图放大</span>
    <button class="lightbox-close" aria-label="关闭">×</button>
    <img class="lightbox-img" src="" alt="">
    <a class="lightbox-original" href="" target="_blank" rel="noopener">在新标签页打开 ↗</a>
  </div>"""

LIGHTBOX_CSS = """
    /* lightbox — readable width + vertical scroll for long posters */
    .lightbox{
      position:fixed; inset:0; z-index:100;
      background:rgba(0,0,0,0.92);
      backdrop-filter:blur(10px);
      overflow-y:auto;
      padding:80px 24px 100px;
      animation:lb-fade .15s ease-out;
    }
    .lightbox[hidden]{display:none}
    @keyframes lb-fade{ from{opacity:0} to{opacity:1} }
    .lightbox-img{
      display:block;
      width:min(720px, 92vw);   /* readable comic-strip width on desktop */
      max-width:100%;
      height:auto;              /* preserves aspect ratio, scrolls vertically */
      margin:0 auto;
      box-shadow:0 30px 80px -20px rgba(0,0,0,0.6);
      border-radius:6px;
      animation:lb-zoom .2s cubic-bezier(.2,.7,.3,1.1);
      cursor:zoom-in;
    }
    /* click image to toggle bigger size for finer reading */
    .lightbox-img.zoom{
      width:min(1080px, 96vw);
      cursor:zoom-out;
    }
    @media(max-width:600px){
      .lightbox{padding:60px 12px 80px}
      .lightbox-img{width:96vw}
      .lightbox-img.zoom{width:100vw}
    }
    @keyframes lb-zoom{ from{opacity:0; transform:scale(0.97)} to{opacity:1; transform:scale(1)} }

    .lightbox-close{
      position:fixed; top:24px; right:24px; z-index:101;
      width:48px; height:48px;
      background:rgba(255,255,255,0.12); color:#fff;
      border:1px solid rgba(255,255,255,0.22); border-radius:50%;
      font-size:24px; cursor:pointer;
      display:flex; align-items:center; justify-content:center;
      transition:all .15s;
      backdrop-filter:blur(8px);
    }
    .lightbox-close:hover{background:rgba(255,255,255,0.22)}

    .lightbox-original{
      position:fixed; bottom:24px; left:50%; z-index:101;
      transform:translateX(-50%);
      font-family:var(--sans); font-size:12.5px;
      color:rgba(255,255,255,0.85);
      background:rgba(255,255,255,0.12); padding:9px 18px;
      border-radius:999px; border:1px solid rgba(255,255,255,0.22);
      text-decoration:none;
      transition:all .15s;
      backdrop-filter:blur(8px);
      letter-spacing:.04em;
    }
    .lightbox-original:hover{background:rgba(255,255,255,0.22); color:#fff}

    /* hint pill at top — tells user to scroll */
    .lightbox-hint{
      position:fixed; top:24px; left:50%; z-index:101;
      transform:translateX(-50%);
      font-family:var(--sans); font-size:11px;
      color:rgba(255,255,255,0.7);
      background:rgba(255,255,255,0.08); padding:6px 14px;
      border-radius:999px; border:1px solid rgba(255,255,255,0.15);
      letter-spacing:.12em; text-transform:uppercase;
      pointer-events:none;
      backdrop-filter:blur(8px);
    }"""

LIGHTBOX_JS = """
    (function(){
      var lb=document.getElementById('lightbox');
      if(!lb)return;
      var img=lb.querySelector('.lightbox-img');
      var link=lb.querySelector('.lightbox-original');
      var close=lb.querySelector('.lightbox-close');
      function open(href){
        img.src=href; link.href=href;
        img.classList.remove('zoom');
        lb.scrollTop=0;
        lb.removeAttribute('hidden');
        document.body.style.overflow='hidden';
      }
      function shut(){
        lb.setAttribute('hidden','');
        img.src='';
        img.classList.remove('zoom');
        document.body.style.overflow='';
      }
      document.querySelectorAll('a.entry-poster, a.poster-card-img').forEach(function(a){
        a.addEventListener('click',function(e){
          e.preventDefault();
          open(a.getAttribute('href'));
        });
      });
      // click image toggles zoom; click the dark backdrop closes
      img.addEventListener('click',function(e){
        e.stopPropagation();
        img.classList.toggle('zoom');
      });
      close.addEventListener('click',shut);
      lb.addEventListener('click',function(e){
        // only close if click is on backdrop (not on image)
        if(e.target===lb)shut();
      });
      document.addEventListener('keydown',function(e){
        if(e.key==='Escape'&&!lb.hasAttribute('hidden'))shut();
      });
    })();"""


# ─── shared base styles ───

BASE_TOKENS = """
    :root {
      --paper:#f5efe4; --ink:#2a2520; --ink-soft:#5c554c; --ink-faint:#8a8278;
      --rule:#c9bfae; --accent:#b04a2f; --accent-soft:#d68a72;
      --sun-1:#f3a93b; --sun-2:#e57341;
      --serif-en:'Playfair Display',Georgia,serif;
      --serif-zh:'Noto Serif SC',-apple-system,'PingFang SC',serif;
      --sans:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    }
    [data-theme="dark"] {
      --paper:#1a1612; --ink:#e8dfd1; --ink-soft:#b5ac9e; --ink-faint:#7a7264;
      --rule:#3a3128; --accent:#e07050; --accent-soft:#a85b3f;
      --sun-1:#e57341; --sun-2:#a85b3f;
    }
    *{box-sizing:border-box}
    html,body{margin:0;padding:0}
    body{
      background:var(--paper); color:var(--ink);
      font-family:var(--serif-zh); line-height:1.7;
      -webkit-font-smoothing:antialiased;
      transition:background .25s, color .25s;
    }
    a{color:inherit; text-decoration:none}
    body::before{
      content:''; position:fixed; top:-200px; right:-200px; width:600px; height:600px;
      background:radial-gradient(circle, rgba(243,169,59,0.18) 0%, rgba(229,115,65,0.08) 40%, transparent 70%);
      pointer-events:none; z-index:0;
    }
    [data-theme="dark"] body::before{
      background:radial-gradient(circle, rgba(229,115,65,0.12) 0%, rgba(168,91,63,0.06) 40%, transparent 70%);
    }
    .theme-toggle{
      position:fixed; top:20px; right:20px; z-index:50;
      width:40px; height:40px; border:1px solid var(--rule); border-radius:50%;
      background:var(--paper); color:var(--ink-soft);
      font-size:18px; cursor:pointer;
      display:flex; align-items:center; justify-content:center;
      transition:all .15s;
    }
    .theme-toggle:hover{color:var(--accent); border-color:var(--accent-soft)}

    /* nav: top-right text link to switch between index ↔ posters */
    .top-nav{
      position:fixed; top:30px; right:80px; z-index:49;
      font-family:var(--sans); font-size:12px;
      letter-spacing:.18em; text-transform:uppercase;
      color:var(--ink-faint);
    }
    .top-nav a{
      color:var(--ink-soft);
      border-bottom:1px dotted var(--rule);
      transition:all .15s;
    }
    .top-nav a:hover{color:var(--accent); border-bottom-color:var(--accent)}

    @media(max-width:600px){
      .top-nav{position:static; padding:24px 28px 0; text-align:right}
    }
"""

SORT_FILTER_JS = """
    (function(){
      var list=document.getElementById('entryList');
      if(!list)return;
      var entries=Array.prototype.slice.call(list.querySelectorAll('.entry'));
      var sortBtns=document.querySelectorAll('#sortToggle .sort-btn');
      var chips=document.querySelectorAll('#tagFilter .tag-chip');
      var state={sort:'iso', tag:'all'};

      function makeSep(label){
        var li=document.createElement('li');
        li.className='period-sep';
        li.setAttribute('data-period',label);
        li.textContent=label;
        return li;
      }

      function rebuild(){
        var key = state.sort==='added' ? 'added' : 'iso';
        var sorted = entries.slice().sort(function(a,b){
          var av=a.getAttribute('data-'+key)||'', bv=b.getAttribute('data-'+key)||'';
          return av<bv?1:(av>bv?-1:0);  // descending — newest first
        });
        // drop existing separators, then re-lay-out in sorted order
        var old=list.querySelectorAll('.period-sep');
        for(var i=0;i<old.length;i++){old[i].remove();}
        list.classList.toggle('by-added', state.sort==='added');
        var curPeriod=null;
        sorted.forEach(function(e){
          var tags=(e.getAttribute('data-tags')||'').split(/\\s+/);
          var visible = state.tag==='all' || tags.indexOf(state.tag)>-1;
          e.classList.toggle('hidden', !visible);
          // year separators only in content-time mode, before each visible year
          if(state.sort==='iso' && visible){
            var yr=e.getAttribute('data-year');
            if(yr!==curPeriod){ curPeriod=yr; list.appendChild(makeSep(yr)); }
          }
          list.appendChild(e);
        });
      }

      sortBtns.forEach(function(b){
        b.addEventListener('click',function(){
          state.sort=b.getAttribute('data-sort');
          sortBtns.forEach(function(x){x.classList.toggle('active',x===b);});
          try{localStorage.setItem('bpr-sort',state.sort);}catch(e){}
          rebuild();
        });
      });
      chips.forEach(function(c){
        c.addEventListener('click',function(){
          state.tag=c.dataset.tag;
          chips.forEach(function(x){x.classList.toggle('active',x.dataset.tag===state.tag);});
          rebuild();
        });
      });

      try{
        var saved=localStorage.getItem('bpr-sort');
        if(saved==='added'||saved==='iso'){
          state.sort=saved;
          sortBtns.forEach(function(x){x.classList.toggle('active',x.getAttribute('data-sort')===saved);});
        }
      }catch(e){}
      rebuild();
    })();"""

THEME_TOGGLE_JS = """
    (function(){
      var t=document.querySelector('.theme-toggle');
      var saved=localStorage.getItem('bpr-theme');
      if(saved){document.documentElement.dataset.theme=saved}
      t.addEventListener('click',function(){
        var cur=document.documentElement.dataset.theme;
        var next=cur==='dark'?'light':'dark';
        document.documentElement.dataset.theme=next;
        localStorage.setItem('bpr-theme',next);
      });
    })();"""

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Noto+Serif+SC:wght@400;500;600;700&display=swap" rel="stylesheet">'
)


def og_meta(title: str, description: str, image: str, url: str, type_: str = "website") -> str:
    """Render Open Graph + Twitter card meta tags."""
    return f"""<meta property="og:type" content="{type_}">
  <meta property="og:site_name" content="BPR · ken.solar">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:image" content="{escape(image)}">
  <meta property="og:url" content="{escape(url)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{escape(image)}">"""


def latest_card_url(entries: list[dict]) -> str:
    """Return the URL of the most recent entry that has a share card."""
    for e in entries:
        if e.get("card_href"):
            return f"{BASE_URL}/{e['card_href']}"
    return f"{BASE_URL}/og-default.png"  # fallback if no card exists yet


def render_entry_li(e: dict) -> str:
    iso = e["iso"]
    pretty_date = f'{iso[:4]} · {iso[5:7]} · {iso[8:10]}'
    h1_html = e["h1"]
    zh = escape(e["zh"]) if e["zh"] else ""
    eyebrow = escape(e["eyebrow"]) if e["eyebrow"] else ""
    href = escape(e["href"])
    source_tag = escape(e["source"])
    tags = e.get("tags", [])
    tags_attr = " ".join(tags)
    collection = e.get("collection", "")
    has_poster = bool(e.get("poster_href"))
    poster_href = escape(e["poster_href"]) if has_poster else ""
    cls = "entry has-poster" if has_poster else "entry"

    poster_block = ""
    if has_poster:
        poster_block = f"""
  <a class="entry-poster" href="{poster_href}" aria-label="海报 PNG">
    <img src="{poster_href}" loading="lazy" alt="">
    <span class="entry-poster-badge">📷</span>
  </a>"""

    tags_html = ""
    if tags:
        tag_spans = " ".join(f'<span class="entry-tag">{escape(t)}</span>' for t in tags)
        tags_html = f'<div class="entry-tags">{tag_spans}</div>'

    collection_html = ""
    if collection:
        collection_html = f'<span class="entry-collection">📁 {escape(collection)}</span>'

    added = e.get("added", "")
    added_html = f'<div class="entry-added">+ {escape(added)}</div>' if added else ""

    return f"""<li class="{cls}" data-tags="{escape(tags_attr)}" data-collection="{escape(collection)}" data-iso="{iso}" data-added="{escape(added)}" data-year="{iso[:4]}">
  <div class="entry-date">{pretty_date}{added_html}</div>
  <div class="entry-body">
    <div class="entry-source">{source_tag} {collection_html}</div>
    <a class="entry-h1-link" href="{href}"><h3 class="entry-h1">{h1_html}</h3></a>
    {f'<div class="entry-zh">{zh}</div>' if zh else ''}
    {f'<div class="entry-eyebrow">{eyebrow}</div>' if eyebrow else ''}
    {tags_html}
  </div>{poster_block}
</li>"""


def render_index(entries: list[dict]) -> str:
    today = _date.today().isoformat()

    # Single flat list. Server renders in original/content order (iso desc) with
    # year separators, so the page reads correctly with no JS. The sort toggle
    # re-orders client-side ("added" mode flattens — no separators).
    list_items: list[str] = []
    cur_year: str | None = None
    for e in entries:  # already iso desc
        if e["year"] != cur_year:
            cur_year = e["year"]
            list_items.append(
                f'<li class="period-sep" data-period="{cur_year}">{cur_year}</li>'
            )
        list_items.append(render_entry_li(e))
    entry_list = "\n".join(list_items)
    count = len(entries)
    poster_count = sum(1 for e in entries if e.get("poster_href"))
    # posters gallery is generated only when at least one poster exists;
    # with zero posters the nav link and stat are suppressed (see main()).
    posters_nav = '<div class="top-nav"><a href="posters.html">Posters →</a></div>' if poster_count else ""
    posters_stat = f'<div><strong>含海报</strong><a href="posters.html">{poster_count} 张 →</a></div>' if poster_count else ""

    # build tag filter chips — count entries per tag, only show tags with >=1
    tag_counts: dict[str, int] = {}
    for e in entries:
        for t in e.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    # order: format tags first, then topics by count desc
    fmt_tags_present = [t for t in ALL_FORMAT_TAGS if t in tag_counts]
    topic_tags_present = sorted(
        [t for t in tag_counts if t not in ALL_FORMAT_TAGS],
        key=lambda t: -tag_counts[t],
    )
    chip_html_parts = ['<button class="tag-chip active" data-tag="all">All <em>{}</em></button>'.format(count)]
    for t in fmt_tags_present:
        chip_html_parts.append(
            f'<button class="tag-chip" data-tag="{escape(t)}">{escape(t)} <em>{tag_counts[t]}</em></button>'
        )
    if fmt_tags_present and topic_tags_present:
        chip_html_parts.append('<span class="tag-divider">·</span>')
    for t in topic_tags_present:
        chip_html_parts.append(
            f'<button class="tag-chip" data-tag="{escape(t)}">{escape(t)} <em>{tag_counts[t]}</em></button>'
        )
    tag_chips = "\n        ".join(chip_html_parts)

    og = og_meta(
        title="BPR · Read in Both Worlds",
        description="Editorial-grade bilingual reader · 3-step translation · slow reading for the AI era · 双语阅读日志",
        image=latest_card_url(entries),
        url=f"{BASE_URL}/",
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>BPR · Read in Both Worlds · ken.solar</title>
  <meta name="description" content="Editorial-grade bilingual reader. Three-step translation. Slow reading for the AI era.">
  {og}
  {FONT_LINK}
  <style>
{BASE_TOKENS}
    .container{{
      max-width:780px; margin:0 auto;
      padding:80px 28px 120px;
      position:relative; z-index:1;
    }}
    .sun-mark{{width:48px; height:48px; margin-bottom:32px; display:block}}

    .hero{{margin-bottom:96px}}
    .eyebrow{{
      font-family:var(--sans); font-size:12px; letter-spacing:.22em;
      text-transform:uppercase; color:var(--ink-faint);
      margin-bottom:28px;
    }}
    .hero h1{{
      font-family:var(--serif-en); font-weight:700;
      font-size:64px; line-height:1.04; margin:0 0 18px;
      letter-spacing:-.02em;
    }}
    .hero h1 em{{font-style:italic; color:var(--accent)}}
    @media(max-width:768px){{ .hero h1{{font-size:42px}} }}
    .hero-zh{{
      font-family:var(--serif-zh); font-weight:500;
      font-size:20px; color:var(--ink-soft);
      margin-bottom:36px; letter-spacing:.02em;
    }}
    .lede p{{
      font-family:var(--serif-zh); font-size:16.5px;
      color:var(--ink-soft); line-height:1.85;
      margin:0 0 14px; max-width:640px;
    }}
    .lede em{{font-family:var(--serif-en); font-style:italic; color:var(--ink); font-weight:500}}
    .tagline{{
      font-family:var(--serif-en); font-style:italic;
      font-size:18px; color:var(--accent);
      margin-top:24px;
    }}
    .meta-bar{{
      margin-top:42px; padding-top:24px;
      border-top:1px solid var(--rule);
      display:flex; gap:32px; flex-wrap:wrap;
      font-family:var(--sans); font-size:12px;
      color:var(--ink-faint); letter-spacing:.05em;
    }}
    .meta-bar strong{{color:var(--ink-soft); font-weight:500; margin-right:6px}}

    .entries{{list-style:none; margin:0; padding:0}}
    /* year separator — a list item acting as the period header, so the whole
       list can be re-sorted client-side without nested section wrappers */
    .period-sep{{
      list-style:none;
      font-family:var(--serif-en); font-weight:500;
      font-size:14px; letter-spacing:.4em;
      color:var(--accent); margin:56px 0 28px;
      padding-bottom:16px; border-bottom:1px solid var(--rule);
    }}
    .period-sep:first-child{{margin-top:0}}
    .entry{{
      margin:0;
      display:grid;
      grid-template-columns:120px 1fr;
      gap:32px;
      padding:24px 0;
      border-bottom:1px dashed var(--rule);
      align-items:start;
      transition:background .15s;
    }}
    .entry.has-poster{{grid-template-columns:120px 1fr 110px}}
    .entry:last-child{{border-bottom:none}}
    .entry:hover{{background:rgba(176,74,47,0.04)}}
    [data-theme="dark"] .entry:hover{{background:rgba(224,112,80,0.06)}}
    @media(max-width:600px){{
      .entry, .entry.has-poster{{grid-template-columns:1fr; gap:12px; padding:20px 0}}
    }}
    .entry-date{{
      font-family:var(--sans); font-size:12px; letter-spacing:.1em;
      color:var(--ink-faint); padding-top:6px;
    }}
    /* "added" date — hidden until the list is sorted by added time */
    .entry-added{{
      display:none;
      font-family:var(--sans); font-size:11px; letter-spacing:.04em;
      color:var(--accent-soft); margin-top:5px;
    }}
    #entryList.by-added .entry-added{{display:block}}
    .entry-source{{
      display:inline-block;
      font-family:var(--sans); font-size:10px; font-weight:500;
      letter-spacing:.18em; text-transform:uppercase;
      color:var(--accent-soft);
      margin-bottom:8px;
    }}
    .entry-collection{{
      display:inline-block;
      margin-left:8px;
      padding:1px 8px;
      font-family:var(--sans); font-size:10px; font-weight:500;
      letter-spacing:.06em; text-transform:none;
      color:var(--accent);
      background:rgba(176,74,47,0.08);
      border:1px solid rgba(176,74,47,0.2);
      border-radius:3px;
    }}
    .entry-h1-link{{display:block}}
    .entry-h1{{
      font-family:var(--serif-en); font-weight:600;
      font-size:24px; line-height:1.25; margin:0 0 8px;
      transition:color .15s;
    }}
    .entry-h1 em{{font-style:italic; color:var(--accent)}}
    .entry:hover .entry-h1{{color:var(--accent)}}
    .entry-zh{{
      font-family:var(--serif-zh); font-size:14.5px;
      color:var(--ink-soft); line-height:1.6;
      margin-bottom:8px;
    }}
    .entry-eyebrow{{
      font-family:var(--sans); font-size:11px;
      color:var(--ink-faint); letter-spacing:.04em;
    }}
    /* tags read like newsprint "filed under" — dot-separated small caps,
       no pills, no borders, no padding. Pure typographic labels. */
    .entry-tags{{
      margin-top:14px;
      font-family:var(--sans);
      font-size:10px;
      letter-spacing:.2em;
      text-transform:uppercase;
      color:var(--ink-faint);
      line-height:1.6;
    }}
    .entry-tag{{
      display:inline;
      padding:0; border:0; background:none;
      transition:color .15s;
    }}
    .entry-tag + .entry-tag::before{{
      content:"·";
      color:var(--rule);
      margin:0 8px;
      letter-spacing:0;
    }}
    .entry:hover .entry-tag{{ color:var(--ink-soft) }}

    /* tag filter — interactive but editorial.
       inactive: small caps text, hairline underline on hover
       active:   underline in accent + small count */
    .tag-filter{{
      margin:36px 0 48px;
      padding:18px 0;
      border-top:1px solid var(--rule);
      border-bottom:1px solid var(--rule);
    }}
    .tag-filter-label{{
      font-family:var(--sans); font-size:10px;
      letter-spacing:.22em; text-transform:uppercase;
      color:var(--ink-faint); margin-bottom:12px;
    }}
    .tag-chips{{
      display:flex; flex-wrap:wrap; gap:0; align-items:baseline;
      column-gap:0; row-gap:6px;
    }}
    .tag-divider{{
      color:var(--rule); font-family:var(--sans);
      padding:0 12px; font-size:11px;
    }}
    .tag-chip{{
      font-family:var(--sans); font-size:11px;
      color:var(--ink-soft); background:transparent;
      padding:4px 10px;
      border:0; border-radius:0;
      cursor:pointer; transition:color .15s, border-color .15s;
      letter-spacing:.18em; text-transform:uppercase;
      border-bottom:1px solid transparent;
    }}
    .tag-chip em{{
      font-style:normal; font-size:9px; color:var(--ink-faint);
      margin-left:4px; font-weight:400; letter-spacing:0;
    }}
    .tag-chip:hover{{ color:var(--accent) }}
    .tag-chip.active{{
      color:var(--accent);
      border-bottom-color:var(--accent);
    }}
    .tag-chip.active em{{ color:var(--accent-soft) }}

    /* sort toggle — same editorial language as the tag filter */
    .sort-toggle{{
      margin:-24px 0 48px;
      display:flex; align-items:baseline; gap:18px; flex-wrap:wrap;
    }}
    .sort-toggle-label{{
      font-family:var(--sans); font-size:10px;
      letter-spacing:.22em; text-transform:uppercase;
      color:var(--ink-faint);
    }}
    .sort-btns{{display:flex; gap:0; align-items:baseline}}
    .sort-btn{{
      font-family:var(--sans); font-size:11px;
      color:var(--ink-soft); background:transparent;
      padding:4px 10px;
      border:0; border-radius:0;
      cursor:pointer; transition:color .15s, border-color .15s;
      letter-spacing:.18em; text-transform:uppercase;
      border-bottom:1px solid transparent;
    }}
    .sort-btn:hover{{ color:var(--accent) }}
    .sort-btn.active{{
      color:var(--accent);
      border-bottom-color:var(--accent);
    }}

    /* hide entries that don't match selected tag */
    .entry.hidden{{ display:none }}
    .entry-poster{{
      position:relative; display:block;
      width:110px; height:150px;
      border-radius:6px; overflow:hidden;
      background:#1a1a1a;
      border:1px solid var(--rule);
      box-shadow:0 4px 14px -4px rgba(0,0,0,0.15);
      transition:transform .25s ease, box-shadow .25s ease;
      align-self:start; cursor:zoom-in;
    }}
    .entry-poster:hover{{
      transform:translateY(-2px) scale(1.03);
      box-shadow:0 8px 24px -6px rgba(0,0,0,0.25);
    }}
    .entry-poster img{{
      width:100%; height:100%;
      object-fit:cover; object-position:top;
      display:block;
    }}
    .entry-poster-badge{{
      position:absolute; bottom:6px; right:6px;
      background:rgba(0,0,0,0.65); color:#fff;
      font-size:10px; padding:2px 6px;
      border-radius:4px;
      letter-spacing:.05em;
      backdrop-filter:blur(6px);
    }}
    @media(max-width:600px){{
      .entry-poster{{width:100%; height:200px; cursor:pointer}}
      .entry-poster img{{object-position:top center}}
    }}

    footer{{
      margin-top:120px; padding-top:36px;
      border-top:1px solid var(--rule);
      font-family:var(--sans); font-size:12px;
      color:var(--ink-faint); line-height:1.7;
      display:flex; justify-content:space-between; flex-wrap:wrap; gap:16px;
    }}
    footer a{{color:var(--ink-soft); border-bottom:1px dotted var(--rule)}}
    footer a:hover{{color:var(--accent); border-bottom-color:var(--accent)}}
{LIGHTBOX_CSS}
  </style>
</head>
<body>

  <button class="theme-toggle" aria-label="切换主题">◐</button>
  {posters_nav}

  <div class="container">

    <header class="hero">
      <svg class="sun-mark" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <circle cx="24" cy="24" r="9" fill="var(--sun-1)"/>
        <g stroke="var(--accent)" stroke-width="2" stroke-linecap="round">
          <line x1="24" y1="3"  x2="24" y2="11"/>
          <line x1="24" y1="37" x2="24" y2="45"/>
          <line x1="3"  y1="24" x2="11" y2="24"/>
          <line x1="37" y1="24" x2="45" y2="24"/>
          <line x1="9"  y1="9"  x2="14.5" y2="14.5"/>
          <line x1="33.5" y1="33.5" x2="39" y2="39"/>
          <line x1="9"  y1="39" x2="14.5" y2="33.5"/>
          <line x1="33.5" y1="14.5" x2="39" y2="9"/>
        </g>
      </svg>
      <div class="eyebrow">BPR · ken.solar · 2026—</div>
      <h1>Read in <em>Both Worlds</em></h1>
      <div class="hero-zh">双语阅读日志 · Editorial-grade Bilingual Reader</div>
      <div class="lede">
        <p>把高密度的英文播客与长文,慢慢嚼成<em>可以重复读</em>的双语版本。</p>
        <p>每一篇都跑一遍 <em>Analyze → Translate → Review → Polish</em> 四步法翻译,然后用印刷品级的字体排版,做成单文件 HTML。</p>
        <p>不为快,只为耐心读者。</p>
      </div>
      <div class="tagline">Slow reading for the AI era.</div>
      <div class="meta-bar">
        <div><strong>已收录</strong>{count} 篇</div>
        {posters_stat}
        <div><strong>更新</strong>{today}</div>
        <div><strong>站点</strong><a href="https://ken.solar">ken.solar</a></div>
      </div>
    </header>

    <div class="tag-filter" id="tagFilter">
      <div class="tag-filter-label">FILTER · 筛选</div>
      <div class="tag-chips">
        {tag_chips}
      </div>
    </div>

    <div class="sort-toggle" id="sortToggle">
      <div class="sort-toggle-label">SORT · 排序</div>
      <div class="sort-btns">
        <button class="sort-btn active" data-sort="iso">内容时间</button>
        <button class="sort-btn" data-sort="added">新增时间</button>
      </div>
    </div>

    <ul class="entries" id="entryList">
{entry_list}
    </ul>

    <footer>
      <div>by <strong style="color:var(--ink-soft)">ken</strong> · built with <code style="font-family:ui-monospace,Menlo,monospace;background:rgba(176,74,47,.08);padding:1px 6px;border-radius:4px;color:var(--accent)">/bpr</code></div>
      <div>{count} entries · last build {today}</div>
    </footer>

  </div>
{LIGHTBOX_HTML}

  <script>{THEME_TOGGLE_JS}{LIGHTBOX_JS}{SORT_FILTER_JS}</script>

<script src="https://mark.ken.solar/embed.js?v=1" defer></script>
</body>
</html>
"""


def render_poster_card(e: dict) -> str:
    iso = e["iso"]
    pretty_date = f'{iso[:4]}—{iso[5:7]}—{iso[8:10]}'
    h1_html = e["h1"]
    zh = escape(e["zh"]) if e["zh"] else ""
    href = escape(e["href"])
    source_tag = escape(e["source"])
    poster_href = escape(e["poster_href"])

    return f"""<article class="poster-card">
  <a class="poster-card-img" href="{poster_href}" aria-label="放大预览">
    <img src="{poster_href}" loading="lazy" alt="">
    <span class="poster-card-badge">📷 {pretty_date}</span>
  </a>
  <div class="poster-card-body">
    <div class="poster-card-source">{source_tag}</div>
    <a class="poster-card-title" href="{href}"><h3>{h1_html}</h3></a>
    {f'<div class="poster-card-zh">{zh}</div>' if zh else ''}
  </div>
</article>"""


def render_posters_page(entries: list[dict]) -> str:
    today = _date.today().isoformat()
    poster_entries = [e for e in entries if e.get("poster_href")]
    count = len(poster_entries)

    if count == 0:
        cards = (
            '<div class="empty">'
            '<p>还没有海报。</p>'
            '<p style="font-size:14px;color:var(--ink-faint);margin-top:8px">'
            '跑 <code>/bpr all &lt;URL&gt;</code> 会附带生成 hidpi 海报。</p>'
            '</div>'
        )
    else:
        cards = "\n".join(render_poster_card(e) for e in poster_entries)

    og = og_meta(
        title="Posters · BPR · ken.solar",
        description="Visual library of BPR posters · click to preview · 双语长图,微信 / Telegram 友好",
        image=latest_card_url(poster_entries) if poster_entries else f"{BASE_URL}/og-default.png",
        url=f"{BASE_URL}/posters.html",
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Posters · BPR · ken.solar</title>
  <meta name="description" content="Visual library of BPR posters. Click to preview, click title for full HTML.">
  {og}
  {FONT_LINK}
  <style>
{BASE_TOKENS}
    .container{{
      max-width:1180px; margin:0 auto;
      padding:80px 28px 120px;
      position:relative; z-index:1;
    }}
    .hero{{margin-bottom:64px; max-width:780px}}
    .eyebrow{{
      font-family:var(--sans); font-size:12px; letter-spacing:.22em;
      text-transform:uppercase; color:var(--ink-faint);
      margin-bottom:24px;
    }}
    .hero h1{{
      font-family:var(--serif-en); font-weight:700;
      font-size:54px; line-height:1.05; margin:0 0 14px;
      letter-spacing:-.02em;
    }}
    .hero h1 em{{font-style:italic; color:var(--accent)}}
    @media(max-width:768px){{ .hero h1{{font-size:38px}} }}
    .hero-zh{{
      font-family:var(--serif-zh); font-weight:500;
      font-size:18px; color:var(--ink-soft);
      margin-bottom:24px;
    }}
    .lede{{
      font-family:var(--serif-zh); font-size:15.5px;
      color:var(--ink-soft); line-height:1.8;
      max-width:620px;
    }}
    .lede em{{font-family:var(--serif-en); font-style:italic; color:var(--ink); font-weight:500}}
    .meta-bar{{
      margin-top:32px; padding-top:20px;
      border-top:1px solid var(--rule);
      display:flex; gap:24px; flex-wrap:wrap;
      font-family:var(--sans); font-size:12px;
      color:var(--ink-faint); letter-spacing:.05em;
    }}
    .meta-bar strong{{color:var(--ink-soft); font-weight:500; margin-right:6px}}

    .gallery{{
      display:grid;
      grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));
      gap:32px;
      margin-top:48px;
    }}
    .poster-card{{
      display:flex; flex-direction:column;
      gap:16px;
    }}
    .poster-card-img{{
      position:relative; display:block;
      width:100%; aspect-ratio:3/4;
      border-radius:10px; overflow:hidden;
      background:#0B0F19;
      border:1px solid var(--rule);
      box-shadow:0 8px 24px -8px rgba(0,0,0,0.2);
      transition:transform .3s ease, box-shadow .3s ease;
      cursor:zoom-in;
    }}
    .poster-card-img:hover{{
      transform:translateY(-4px) scale(1.02);
      box-shadow:0 16px 40px -10px rgba(0,0,0,0.3);
    }}
    .poster-card-img img{{
      width:100%; height:100%;
      object-fit:cover; object-position:top;
      display:block;
    }}
    .poster-card-badge{{
      position:absolute; top:10px; left:10px;
      background:rgba(0,0,0,0.65); color:#fff;
      font-family:var(--sans); font-size:10px;
      padding:4px 9px; border-radius:4px;
      letter-spacing:.08em;
      backdrop-filter:blur(8px);
    }}
    .poster-card-body{{padding:0 4px}}
    .poster-card-source{{
      font-family:var(--sans); font-size:10px; font-weight:500;
      letter-spacing:.18em; text-transform:uppercase;
      color:var(--accent-soft);
      margin-bottom:10px;
    }}
    .poster-card-title{{display:block}}
    .poster-card-title h3{{
      font-family:var(--serif-en); font-weight:600;
      font-size:20px; line-height:1.25; margin:0 0 8px;
      transition:color .15s;
    }}
    .poster-card-title:hover h3{{color:var(--accent)}}
    .poster-card-title h3 em{{font-style:italic; color:var(--accent)}}
    .poster-card-zh{{
      font-family:var(--serif-zh); font-size:13.5px;
      color:var(--ink-soft); line-height:1.55;
    }}

    .empty{{
      max-width:520px; margin:64px auto;
      text-align:center;
      padding:48px 32px;
      border:1px dashed var(--rule); border-radius:12px;
      color:var(--ink-soft);
    }}
    .empty code{{
      font-family:ui-monospace,Menlo,monospace;
      background:rgba(176,74,47,.08);
      padding:2px 8px; border-radius:4px;
      color:var(--accent);
    }}

    footer{{
      margin-top:120px; padding-top:36px;
      border-top:1px solid var(--rule);
      font-family:var(--sans); font-size:12px;
      color:var(--ink-faint); line-height:1.7;
      display:flex; justify-content:space-between; flex-wrap:wrap; gap:16px;
    }}
    footer a{{color:var(--ink-soft); border-bottom:1px dotted var(--rule)}}
    footer a:hover{{color:var(--accent); border-bottom-color:var(--accent)}}
{LIGHTBOX_CSS}
  </style>
</head>
<body>

  <button class="theme-toggle" aria-label="切换主题">◐</button>
  <div class="top-nav"><a href="index.html">← Index</a></div>

  <div class="container">

    <header class="hero">
      <div class="eyebrow">BPR · POSTERS · ken.solar</div>
      <h1>Visual <em>Library</em></h1>
      <div class="hero-zh">海报图册 · 每张都是 1080 宽长图,微信 / Telegram 友好</div>
      <p class="lede">
        每篇 <em>/bpr all</em> 都会附带生成一张 <em>hidpi</em>(2160 宽)的长图海报——把双语 HTML 里最锋利的金句、stats、takeaway 浓缩到一张可分享的视觉里。
        点缩略图放大,点标题进入完整 HTML reader。
      </p>
      <div class="meta-bar">
        <div><strong>海报</strong>{count} 张</div>
        <div><strong>更新</strong>{today}</div>
        <div><strong>回到</strong><a href="index.html">阅读列表 ←</a></div>
      </div>
    </header>

    <div class="gallery">
{cards}
    </div>

    <footer>
      <div>by <strong style="color:var(--ink-soft)">ken</strong> · ken.solar</div>
      <div>{count} posters · last build {today}</div>
    </footer>

  </div>
{LIGHTBOX_HTML}

  <script>{THEME_TOGGLE_JS}{LIGHTBOX_JS}</script>

<script src="https://mark.ken.solar/embed.js?v=1" defer></script>
</body>
</html>
"""


def main() -> int:
    entries = collect_entries()
    if not entries:
        print("No BPR entries found.", file=sys.stderr)
        return 1

    # L5 hard rule: drop any case-mismatched leftover before writing
    for cand in ("INDEX.html", "Index.html", "POSTERS.html", "Posters.html"):
        p = TRANSCRIPT_DIR / cand
        if p.exists():
            p.unlink()

    poster_count = sum(1 for e in entries if e.get("poster_href"))

    INDEX_PATH.write_text(render_index(entries), encoding="utf-8")
    print(f"✓ index.html   ({INDEX_PATH.stat().st_size:,} bytes, {len(entries)} entries)")

    # posters.html only when at least one poster exists; else drop any leftover
    if poster_count:
        POSTERS_PATH.write_text(render_posters_page(entries), encoding="utf-8")
        print(f"✓ posters.html ({POSTERS_PATH.stat().st_size:,} bytes, {poster_count} posters)")
    else:
        if POSTERS_PATH.exists():
            POSTERS_PATH.unlink()
        print("· posters.html skipped (0 posters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
