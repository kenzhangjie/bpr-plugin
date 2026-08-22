#!/usr/bin/env python3
"""
抓 Substack 播客的**官方文字稿**(带 speaker 标注 + 词级时间戳)。

为什么要有这个脚本(2026-08-23 加):
  YouTube 的字幕轨**没有说话人标注**,DDR 的英文 PREP 只能靠"提问方=主持人"启发式
  推,一期访谈实测 97.1% 对,错的那 3% 恰好是**第三个说话人**(赞助商口播嘉宾)——
  这类人靠启发式结构性推不出来。而 Lenny's Podcast 这类 Substack 播客,官方文字稿
  里就有 `speaker_map`,直接给名字。

  更关键的是:**签名 CDN 链接嵌在公开页 HTML 里,付费期次(audience=only_paid)照样拿得到**
  —— 页面正文被墙,transcription.json 不被墙。实测 4 期(3 期 only_paid)全部成功。

原理:
  Substack 每个 post 页面把整个 post 对象序列化进 `window._preloads`。播客 post 的
  `post.podcastUpload.transcription` 里有:
    · speaker_map   {"SPEAKER_0": "Michael Truell", ...}   ← 官方说话人名字
    · cdn_url       签名 URL,指向 transcription.json      ← 分段全文 + 时间戳
  cdn_url 带 Expires(约数月),每次加载页面都会重签,所以**现抓现用,不要缓存 URL**。

用法:
  # 1) 最常用:从 fetch_youtube.sh 产出的 metadata.json 自动找 transcript 链接
  #    (Lenny 每期 description 里都有 "*Transcript:* https://.../p/<slug>")
  python3 fetch_substack_transcript.py --from-youtube "$WORKDIR/metadata.json" --workdir "$WORKDIR"

  # 2) 直接给 post URL 或 slug(slug 走 --pub,默认 www.lennysnewsletter.com)
  python3 fetch_substack_transcript.py https://www.lennysnewsletter.com/p/<slug> --workdir "$WORKDIR"
  python3 fetch_substack_transcript.py <slug> --pub lennysnewsletter.com --workdir "$WORKDIR"

  # 3) 不知道 slug:按标题/嘉宾名在 podcast 归档里搜
  python3 fetch_substack_transcript.py --search "Michael Truell" --pub lennysnewsletter.com

产物(写进 --workdir):
  substack_transcript.json  原始分段(底档,别改)
  substack_turns.json       [{"speaker","start","sents":[...]}]  ← 交给 PREP / STRUCTURE
  substack_transcript.txt   "Name HH:MM:SS" 块格式(与妙记/火山导出同形,下游脚本可直接吃)
  substack_meta.json        title / post_date / canonical_url / speakers / words / audience

退出码:0 成功 · 2 输入非法 · 3 该 post 没有文字稿(不是播客 / 还没转录完)
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url, binary=False, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=timeout).read()
    return data if binary else data.decode("utf-8", "ignore")


def preloads(html):
    """取出 window._preloads(Substack 把整个 post 对象塞在这里)。"""
    m = re.search(r'window\._preloads\s*=\s*JSON\.parse\("(.*?)"\)\s*<?', html, re.S)
    if not m:
        return None
    return json.loads(json.loads('"' + m.group(1) + '"'))


def find_post_url(meta_path):
    """从 YouTube metadata.json 的 description 里找官方文字稿链接。

    Lenny 每期 description 固定有一行 `*Transcript:* https://www.lennysnewsletter.com/p/<slug>`,
    而且它是**第一个** /p/ 链接(后面的 /p/ 链接是 Referenced 里的往期节目)——所以取第一个。
    """
    d = json.load(open(meta_path, encoding="utf-8"))
    desc = d.get("description") or ""
    # 优先认显式标注的 Transcript: 行
    m = re.search(r'Transcript:?\**\s*(https://[^\s)]+/p/[a-z0-9\-]+)', desc, re.I)
    if m:
        return m.group(1), "description:Transcript-label"
    hits = re.findall(r'https://[a-z0-9.\-]+/p/[a-z0-9\-]+', desc)
    if hits:
        return hits[0], "description:first-/p/-link"
    return None, None


def search_archive(pub, query, limit=50):
    """在 podcast 归档页 + archive API 里按关键词找 slug。

    注意(实测 2026-08-23):Substack 的 `?search=` / `?type=podcast` / `?section=`
    参数在 lennysnewsletter.com 上**都不生效**(照样返回主 newsletter 最新几条),
    所以这里改成:抓 /podcast/archive 页面 HTML 里的 slug + 拿 API 前 N 条,
    然后本地按关键词过滤。只覆盖较近的期次;更早的期次请用 --from-youtube 或直接给 URL。
    另:archive API 的 `limit` **上限是 50**,填 51+ 直接 400。
    """
    cands = {}
    try:
        html = get(f"https://{pub}/podcast/archive")
        d = preloads(html) or {}
        for p in (d.get("posts") or d.get("archivePosts") or []):
            if p.get("slug"):
                cands[p["slug"]] = p.get("title", "")
        for s in re.findall(r'/p/([a-z0-9\-]+)', html):
            cands.setdefault(s, "")
    except Exception as e:
        print(f"  ! 归档页抓取失败: {e}", file=sys.stderr)
    try:
        api = json.loads(get(f"https://{pub}/api/v1/archive?sort=new&offset=0&limit={limit}"))
        for p in api:
            if p.get("slug"):
                cands[p["slug"]] = p.get("title", "")
    except Exception as e:
        print(f"  ! archive API 失败: {e}", file=sys.stderr)

    q = query.lower()
    toks = [t for t in re.split(r'\W+', q) if len(t) > 2]
    out = []
    for slug, title in cands.items():
        hay = (slug + " " + title).lower()
        score = sum(1 for t in toks if t in hay)
        if score:
            out.append((score, slug, title))
    out.sort(reverse=True)
    return out


def extract(post_url):
    try:
        html = get(post_url)
    except Exception as e:
        print(f"[2] 打不开 {post_url}: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
    d = preloads(html)
    if not d or "post" not in d:
        print(f"[2] 拿不到 window._preloads,这可能不是 Substack 页面: {post_url}", file=sys.stderr)
        sys.exit(2)
    p = d["post"]
    tr = ((p.get("podcastUpload") or {}).get("transcription")) or {}
    if not tr.get("cdn_url"):
        print(f"[3] 该 post 没有可下载的文字稿(status={tr.get('status')!r}, "
              f"是播客={bool(p.get('podcastUpload'))})。退回 YouTube 字幕路径。", file=sys.stderr)
        sys.exit(3)
    return p, tr


# 切句时**不许**被当成句号的东西。走 YT 轨那条路时,朴素的 `[.!?]\s` 正则把
# `cursor.com` / `2.0` / `$1,000` / `geteppo.com/lenny` 全切断了,事后手工补了 8 处。
# 官方稿本身没有这类断点错误,但切句是我们自己做的 —— 坑要在这一侧防。
_PROTECT = [
    # 路径部分**不能以 . 收尾** —— 否则 `vanta.com/lenny. That's ...` 里的句末句号
    # 会被当成 URL 的一部分吞掉,那两句就切不开(欠切,实测踩到过)。
    re.compile(r'\b(?:[A-Za-z0-9-]+\.)+(?:com|org|net|io|co|ai|dev|app|edu|gov|so|me|fm)\b'
               r'(?:/[A-Za-z0-9_\-./~%?&=#]*[A-Za-z0-9_\-/~%=#])?'),
    re.compile(r'\b\d+(?:\.\d+)+\b'),                                  # 2.0 / 4.0 / 1.5.3
    re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|Inc|Ltd|Fig|No|Vol)\.'),
    re.compile(r'\b(?:e\.g|i\.e|a\.m|p\.m|U\.S|U\.K|Ph\.D)\.', re.I),
    re.compile(r'\b(?:[A-Za-z]\.){2,}'),                               # A.I. / E.P.P.O.
]
# 用「插哨兵再 split」而不是「直接 split」:分隔符若写成 `(?<=[.!?])["\')\]]*\s+`,
# 那个 `["\')\]]*` 会被当成分隔符**消费掉**,`He said, "this is it." Then...` 的收尾引号
# 就没了 —— 而且**词数闸查不出来**(丢一个引号不改变词数)。所以把标点留在前一句里。
_SENT_END = re.compile(r'([.!?]["\')\]]*)\s+(?=["\'(\[]?[A-Z0-9])')


def split_sentences(text):
    """把一段切成句子:先把 URL / 小数 / 缩写藏起来再切,切完还原。"""
    text = (text or "").strip()
    if not text:
        return []
    vault = []

    def stash(m):
        vault.append(m.group(0))
        return f"\x00{len(vault) - 1}\x00"

    for pat in _PROTECT:
        text = pat.sub(stash, text)
    # 注意 replacement 里不能写 r'\1\x01' —— 原始串里的 `\x` 会被 re 的模板解析器拒掉
    # (bad escape \x)。用 lambda 直接拼,绕开模板转义。
    marked = _SENT_END.sub(lambda m: m.group(1) + '\x01', text)
    parts = [s.strip() for s in marked.split('\x01') if s.strip()]
    return [re.sub(r'\x00(\d+)\x00', lambda m: vault[int(m.group(1))], s) for s in parts]


def build(p, tr, split=True):
    segs = json.loads(get(tr["cdn_url"], binary=True))
    smap = tr.get("speaker_map") or {}

    def name(sp):
        n = smap.get(sp)
        if n and not re.fullmatch(r'Speaker \d+', n.strip()):
            return n
        # speaker_map 缺失或只有占位名 → 保留原始标签,交给 PREP 去认
        return n or sp

    turns = []
    for s in segs:
        who = name(s.get("speaker") or "SPEAKER_?")
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        pieces = split_sentences(txt) if split else [txt]
        st = float(s.get("start") or 0)
        if turns and turns[-1]["speaker"] == who:
            turns[-1]["sents"].extend(pieces)
        else:
            turns.append({"speaker": who, "start": st, "sents": pieces})

    named = sorted({t["speaker"] for t in turns})
    placeholder = [n for n in named if re.fullmatch(r'(SPEAKER_\d+|Speaker \d+)', n)]
    words = sum(len(x.split()) for t in turns for x in t["sents"])
    meta = {
        "source": "substack",
        "title": p.get("title"),
        "subtitle": p.get("subtitle"),
        "post_date": (p.get("post_date") or "")[:10],
        "canonical_url": p.get("canonical_url"),
        "audience": p.get("audience"),
        "duration": (p.get("podcastUpload") or {}).get("duration"),
        "speakers": named,
        "unnamed_speakers": placeholder,
        "segments": len(segs),
        "turns": len(turns),
        "words": words,
        "sentences": sum(len(t["sents"]) for t in turns),
        "sentence_split": True,
        "transcription_status": tr.get("status"),
    }
    return segs, turns, meta


def hms(x):
    x = int(x)
    return f"{x//3600:02d}:{(x%3600)//60:02d}:{x%60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", help="post URL 或 slug")
    ap.add_argument("--from-youtube", metavar="metadata.json",
                    help="从 fetch_youtube.sh 的 metadata.json 里找 transcript 链接")
    ap.add_argument("--search", help="按标题/嘉宾名在归档里搜 slug(只列候选,不下载)")
    ap.add_argument("--pub", default="www.lennysnewsletter.com", help="Substack 域名")
    ap.add_argument("--workdir", default=".", help="产物输出目录")
    ap.add_argument("--no-split", action="store_true",
                    help="不切句,turns[].sents 保留官方分段原样(默认切句,句级对照需要)")
    a = ap.parse_args()

    if a.search:
        hits = search_archive(a.pub, a.search)
        if not hits:
            print(f"没找到匹配 {a.search!r} 的期次(归档 API 只覆盖较近期次)。"
                  f"\n→ 改用 --from-youtube,或去 https://{a.pub}/podcast/archive 手动找 slug。")
            return 1
        print(f"候选({len(hits)}):")
        for score, slug, title in hits[:10]:
            print(f"  [{score}] https://{a.pub}/p/{slug}   {title[:70]}")
        return 0

    src = None
    if a.from_youtube:
        url, src = find_post_url(a.from_youtube)
        if not url:
            print("[3] YouTube description 里没有 /p/ 链接。"
                  "→ 试 --search '<嘉宾名>',或直接给 post URL。", file=sys.stderr)
            return 3
    elif a.target:
        url = a.target if a.target.startswith("http") else f"https://{a.pub}/p/{a.target}"
        src = "argv"
    else:
        ap.error("需要给 post URL / slug,或 --from-youtube,或 --search")

    print(f"→ post: {url}   (来源: {src})")
    p, tr = extract(url)
    segs, turns, meta = build(p, tr, split=not a.no_split)
    meta["resolved_from"] = src

    os.makedirs(a.workdir, exist_ok=True)
    w = lambda n: os.path.join(a.workdir, n)
    json.dump(segs, open(w("substack_transcript.json"), "w"), ensure_ascii=False)
    json.dump(turns, open(w("substack_turns.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(meta, open(w("substack_meta.json"), "w"), ensure_ascii=False, indent=1)
    with open(w("substack_transcript.txt"), "w", encoding="utf-8") as f:
        for t in turns:
            f.write(f"{t['speaker']} {hms(t['start'])}\n")
            f.write(" ".join(t["sents"]) + "\n\n")

    print(f"  标题     {meta['title']}")
    print(f"  发布     {meta['post_date']}  · audience={meta['audience']}")
    print(f"  说话人   {meta['speakers']}")
    if meta["unnamed_speakers"]:
        print(f"  ⚠ 未命名 {meta['unnamed_speakers']} —— speaker_map 没给名字,"
              f"PREP 需要按 description 认人(别瞎猜,认不出就退化)")
    nsent = sum(len(t["sents"]) for t in turns)
    print(f"  规模     {meta['segments']} 段 → {meta['turns']} turn / {nsent} 句 · {meta['words']:,} 词")
    print(f"✓ 写入 {a.workdir}/substack_{{transcript.json,turns.json,transcript.txt,meta.json}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
