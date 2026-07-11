#!/usr/bin/env python3
"""
extract_images.py — BPR essay/blog 模式抓图 + 自托管

从源站 HTML 抓正文配图,过滤噪声,下载到 Transcript/images/<stem>/,
用 Pillow 按宽高比定 <figure class="from-source ..."> 变体,写 .manifest.json,
并把「锚点(注入到哪个正文块之后)→ 本地图信息」以 JSON 打到 stdout,
供 BPR 主流程注入。

用法:
  python3 extract_images.py \
    --html /tmp/raw.html \
    --blocks /tmp/article.json \
    --stem 2026-07-07_publication_author_topic \
    --transcript-dir "/Users/ken/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript" \
    [--content-class available-content] [--refresh]

stdout JSON:
  {"anchors":[[article_index, {"file","variant","alt"}], ...],
   "hero":[{"file","variant","alt"}, ...],
   "skipped":[{"url","reason"}...],
   "coverage":{"candidates":N,"downloaded":M,"ratio":0.xx}}

设计决定(见 SKILL.md / lessons-learned L7):
- 只抓正文容器内的图;尺寸/关键词过滤噪声(头像/icon/promo)
- 命名 NN_<slug>.ext(顺序号 + 轻语义,hero→01_hero);后缀保留源格式
- 变体:ratio>=1.8 banner / ratio<0.8 portrait / 否则 min边<500 square 否则 wide
- 下载失败重试2次→跳过并记录,绝不回退热链
- 幂等:.manifest.json 记 seq/id/file,已存在且 id 未变则复用;--refresh 强制全重下
- 锚点:按「图前最近的文本块」的前 45 字匹配到 article blocks 的 index;index=-1 → hero
"""
import argparse, html, json, os, re, subprocess, sys

NOISE_RE = re.compile(r'avatar|icon|logo|profile|button|badge|emoji|spacer|pixel|tracking', re.I)
MIN_DIM = 100          # 长宽任一 < 100px 视为 icon/头像
SQUARE_MAX = 500       # 普通图短边 < 500 归 square,否则 wide


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def norm(t):
    return re.sub(r'\s+', ' ', t)[:45]


def conv_links(inner):
    def repl(m):
        return f'[{re.sub(r"<[^>]*>", "", m.group(2))}]({m.group(1)})'
    inner = re.sub(r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', repl, inner, flags=re.S)
    return html.unescape(re.sub(r'<[^>]+>', '', inner)).strip()


def img_id(url):
    """稳定去重键:优先 S3/CDN 里的图片 id,否则 URL 末段。"""
    m = re.search(r'images%2F([0-9a-fA-F-]{6,})', url) or re.search(r'/([0-9a-fA-F]{8,})[._]', url)
    if m:
        return m.group(1)
    base = re.sub(r'[?#].*$', '', url).rstrip('/').split('/')[-1]
    return base or url[-40:]


def slugify(text, fallback):
    if not text:
        return fallback
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    s = '-'.join(s.split('-')[:4])
    return s or fallback


def ext_from(url, content_type):
    if content_type:
        ct = content_type.split(';')[0].strip().lower()
        m = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
             'image/svg+xml': 'svg', 'image/gif': 'gif'}.get(ct)
        if m:
            return m
    m = re.search(r'\.(png|jpe?g|webp|svg|gif)(?:[?#]|$)', url, re.I)
    return (m.group(1).lower().replace('jpeg', 'jpg')) if m else 'png'


def walk(seg):
    """按文档顺序产出 ('img', url) 和 ('text', txt)。图优先取全分辨率 a.image-link,
    否则 <img src>。"""
    pat = re.compile(
        r'(<a\b[^>]*class="[^"]*image-link[^"]*"[^>]*>)'      # 1: substack full-res anchor
        r'|(<img\b[^>]*>)'                                     # 2: bare img
        r'|<(h[1-6]|p|blockquote|li|figcaption)[^>]*>(.*?)</\3>',  # 3/4: text block
        re.S)
    for m in pat.finditer(seg):
        if m.group(1):
            h = re.search(r'href="([^"]+)"', m.group(1))
            if h:
                yield 'img', html.unescape(h.group(1)), m.group(1)
        elif m.group(2):
            s = re.search(r'src="([^"]+)"', m.group(2))
            if s and not s.group(1).startswith('data:'):
                yield 'img', html.unescape(s.group(1)), m.group(2)
        else:
            txt = conv_links(m.group(4))
            if txt:
                yield 'text', txt, m.group(4)


def download(url, dest):
    """curl 重试2次,验 content-type 是 image/*。返回 content_type 或 None。"""
    for _ in range(3):
        # HEAD-ish: fetch with type probe
        r = sh(['curl', '-sL', '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
                '--max-time', '40', '-w', '%{content_type}', '-o', dest, url])
        ct = (r.stdout or '').strip().splitlines()[-1] if r.stdout else ''
        if r.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 0:
            if ct.startswith('image/') or dest.endswith('.svg'):
                return ct
    if os.path.exists(dest):
        os.remove(dest)
    return None


def dims(path):
    if path.endswith('.svg'):
        # try width/height or viewBox
        try:
            s = open(path, encoding='utf-8', errors='ignore').read(4000)
            vb = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', s)
            if vb:
                return float(vb.group(1)), float(vb.group(2))
            w = re.search(r'width="([\d.]+)', s); h = re.search(r'height="([\d.]+)', s)
            if w and h:
                return float(w.group(1)), float(h.group(1))
        except Exception:
            pass
        return 1200.0, 600.0  # svg 默认按 banner
    try:
        from PIL import Image
        with Image.open(path) as im:
            return float(im.width), float(im.height)
    except Exception:
        return 0.0, 0.0


def variant(w, h):
    if w <= 0 or h <= 0:
        return 'wide'
    r = w / h
    if r >= 1.8:
        return 'banner'
    if r < 0.8:
        return 'portrait'
    return 'square' if min(w, h) < SQUARE_MAX else 'wide'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True)
    ap.add_argument('--blocks', required=True)
    ap.add_argument('--stem', required=True)
    ap.add_argument('--transcript-dir', required=True)
    ap.add_argument('--content-class', default='available-content')
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()

    raw = open(a.html, encoding='utf-8', errors='ignore').read()
    blocks = json.load(open(a.blocks))
    bkeys = {norm(b['text']): i for i, b in enumerate(blocks)}

    # 正文容器:优先 content-class,回退 <article>/<main>,再回退全文
    start = raw.find(a.content_class)
    if start == -1:
        m = re.search(r'<(article|main)\b', raw)
        start = m.start() if m else 0
    seg = raw[start:start + 600000]

    outdir = os.path.join(a.transcript_dir, 'images', a.stem)
    os.makedirs(outdir, exist_ok=True)
    manifest_path = os.path.join(outdir, '.manifest.json')
    manifest = {}
    if os.path.exists(manifest_path) and not a.refresh:
        try:
            manifest = {m['id']: m for m in json.load(open(manifest_path))}
        except Exception:
            manifest = {}

    # 收集 (article_index, url)，按文档顺序去重
    seen = set()
    items = []            # [(anchor_index, url)]
    last_idx = -1
    for kind, val, rawtag in walk(seg):
        if kind == 'text':
            i = bkeys.get(norm(val))
            if i is not None:
                last_idx = i
        else:
            iid = img_id(val)
            if iid in seen:
                continue
            # 关键词过滤(URL 或 alt)
            alt_m = re.search(r'alt="([^"]*)"', rawtag)
            alt = html.unescape(alt_m.group(1)) if alt_m else ''
            if NOISE_RE.search(val) or NOISE_RE.search(alt):
                continue
            seen.add(iid)
            items.append((last_idx, val, iid, alt))

    anchors, hero, skipped, new_manifest = [], [], [], []
    seq = 0
    for anchor_idx, url, iid, alt in items:
        seq += 1
        is_hero = anchor_idx < 0 and seq == 1
        # 幂等:命中 manifest 且文件在 → 复用
        cached = manifest.get(iid)
        if cached and os.path.exists(os.path.join(a.transcript_dir, cached['file'])):
            entry = cached
        else:
            ext_guess = ext_from(url, '')
            slug = 'hero' if is_hero else slugify(alt, 'figure')
            fname = f'{seq:02d}_{slug}.{ext_guess}'
            dest = os.path.join(outdir, fname)
            ct = download(url, dest)
            if not ct:
                skipped.append({'url': url, 'reason': 'download-failed'})
                continue
            # 修正后缀(content-type 更准)
            real_ext = ext_from(url, ct)
            if real_ext != ext_guess:
                new = os.path.join(outdir, f'{seq:02d}_{slug}.{real_ext}')
                os.replace(dest, new); dest = new; fname = os.path.basename(new)
            w, h = dims(dest)
            # 尺寸过滤:长宽任一 < 100 → 噪声,删掉
            if 0 < min(w, h) < MIN_DIM:
                os.remove(dest)
                skipped.append({'url': url, 'reason': f'too-small({int(w)}x{int(h)})'})
                continue
            entry = {'id': iid, 'seq': seq, 'file': f'images/{a.stem}/{fname}',
                     'variant': 'banner' if is_hero else variant(w, h),
                     'alt': alt, 'w': int(w), 'h': int(h), 'src_url': url}
        new_manifest.append(entry)
        rec = {'file': entry['file'], 'variant': entry['variant'], 'alt': entry['alt']}
        if is_hero:
            hero.append(rec)
        else:
            anchors.append([anchor_idx, rec])

    json.dump(new_manifest, open(manifest_path, 'w'), ensure_ascii=False, indent=1)
    cand = len(items)
    got = len(new_manifest)
    print(json.dumps({
        'anchors': anchors, 'hero': hero, 'skipped': skipped,
        'coverage': {'candidates': cand, 'downloaded': got,
                     'ratio': round(got / cand, 3) if cand else 1.0}
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
