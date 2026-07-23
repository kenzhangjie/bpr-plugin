#!/usr/bin/env python3
"""中文模式 RENDER —— 确定性脚本(取代 agent 手写,消灭 L2/L3 render 回归)。

把 CLEAN 产出的书面正文 + STRUCTURE 的 JSON + 原始逐字底档,机械填进 base.html
占位符,输出成品 HTML。渲染是纯机械填空——不需要 LLM"思考",故用脚本保证字节级
一致、零布局回归、可单测。agent 只负责 STRUCTURE(想),拼装交给本脚本。

用法:
  render_zh.py --clean clean.txt --structure struct.json --raw raw.txt \
               --base base.html --meta metadata.json --out out.html

输入:
  --clean      CLEAN 后的书面正文(turn 头 = "Speaker N HH:MM:SS" 独占行)
  --structure  STRUCTURE 的 JSON:{hero,tldr,contrarian,chapters,speakers?}
  --raw        火山原始逐字稿(同格式,进可折叠 <details> 底档)
  --base       templates/base.html
  --meta       metadata.json(podcast/title 等;可选)
  --out        输出 HTML 路径
"""
import argparse, json, re, html, sys
from pathlib import Path

# 兼容两种子代理输出:独占行 "Speaker N ts" 和 markdown 内联 "**Speaker N ts** 正文"
HEADER = re.compile(r'^\**\s*Speaker\s+(\d+)\s+(\d{1,2}:\d{2}:\d{2})(?:\.\d+)?\s*\**\s*(.*)$')

def ts2sec(t):
    p = [int(x) for x in t.split(":")]
    while len(p) < 3: p = [0] + p
    return p[0]*3600 + p[1]*60 + p[2]

def parse_turns(text):
    turns, cur = [], None
    for line in text.splitlines():
        m = HEADER.match(line.strip())
        if m:
            if cur: turns.append(cur)
            cur = [m.group(1), m.group(2), ts2sec(m.group(2)), []]
            rest = m.group(3).strip()
            if rest: cur[3].append(rest)          # 内联格式的首段正文
        elif cur is not None:
            cur[3].append(line)
    if cur: turns.append(cur)
    out = []
    for spk, ts, sec, lines in turns:
        blob = "\n".join(lines).strip()
        paras = [p.strip().replace('**', '') for p in re.split(r'\n\s*\n', blob) if p.strip()]
        out.append((spk, ts, sec, paras))
    return out

def esc(s): return html.escape(s, quote=False)
UNCERTAIN = re.compile(r'⟨\?([^⟩]*)⟩')
def mark_uncertain(s):
    return UNCERTAIN.sub(lambda m: f'<mark class="asr-uncertain" title="ASR存疑">{esc(m.group(1))}?</mark>', s)

def turn_html(spk, ts, paras, spk_map, host_id, uncertain=True):
    role = 'host' if spk == host_id else 'guest'
    name = esc(spk_map.get(spk, f"Speaker {spk}"))
    ps = "".join(f'<p class="zh">{mark_uncertain(esc(p)) if uncertain else esc(p)}</p>' for p in paras)
    return (f'<div class="turn"><div class="turn-head">'
            f'<span class="speaker" data-role="{role}">{name}</span>'
            f'<span class="timestamp">{ts}</span></div>'
            f'<div class="turn-body">{ps}</div></div>')

def main():
    ap = argparse.ArgumentParser()
    for a in ("clean", "structure", "raw", "base", "out"):
        ap.add_argument(f"--{a}", required=True)
    ap.add_argument("--meta", default="")
    A = ap.parse_args()

    struct = json.loads(Path(A.structure).read_text(encoding="utf-8"))
    clean_turns = parse_turns(Path(A.clean).read_text(encoding="utf-8"))
    raw_turns = parse_turns(Path(A.raw).read_text(encoding="utf-8"))
    meta = json.loads(Path(A.meta).read_text(encoding="utf-8")) if A.meta and Path(A.meta).exists() else {}

    # 说话人映射:structure.speakers {id:name} 优先,否则回退 "Speaker N"
    spk_map = {str(k): v for k, v in (struct.get("speakers") or {}).items()}
    host_id = str(struct.get("host_id", "1"))
    podcast = meta.get("podcast", "") or struct.get("hero", {}).get("podcast", "")

    chapters = sorted(struct["chapters"], key=lambda c: ts2sec(c["start_ts"]))
    bounds = [ts2sec(c["start_ts"]) for c in chapters] + [10**9]
    in_chap = lambda turns, i: [t for t in turns if bounds[i] <= t[2] < bounds[i+1]]

    chap_html = []
    con = "".join(
        f'<div class="contrarian-item"><p class="contrarian-quote">“{esc(c["quote"])}”</p>'
        f'<p class="contrarian-why"><strong>为什么非共识 · </strong>{esc(c["why"])}</p></div>'
        for c in struct.get("contrarian", []))
    if con:
        chap_html.append(f'<section class="contrarian"><div class="contrarian-label">🔥 非共识 · Contrarian Takes</div>{con}</section>')
    for i, c in enumerate(chapters):
        cl, rw = in_chap(clean_turns, i), in_chap(raw_turns, i)
        end_ts = chapters[i+1]["start_ts"] if i+1 < len(chapters) else (cl[-1][1] if cl else c["start_ts"])
        body = "".join(turn_html(s, ts, ps, spk_map, host_id, True) for s, ts, _, ps in cl)
        raw_body = "".join(turn_html(s, ts, ps, spk_map, host_id, False) for s, ts, _, ps in rw)
        details = (f'<details class="raw-transcript"><summary>展开逐字原稿（{len(rw)} 段）</summary>{raw_body}</details>') if rw else ""
        kw = " · ".join(c.get("keywords", []))
        chap_html.append(
            f'<section class="chapter" id="ch{c["num"]}"><div class="ch-num">Chapter {c["num"]:02d}</div>'
            f'<h2>{esc(c["en_title"])}</h2><div class="ch-zh">{esc(c["zh_title"])}</div>'
            f'<div class="ch-range">{c["start_ts"][3:]} — {end_ts[3:]} · {esc(kw)}</div>{body}{details}</section>')

    toc = "".join(f'<li><a href="#ch{c["num"]}">{c["num"]:02d} · {esc(c["zh_title"])}</a></li>' for c in chapters)
    h = struct["hero"]
    hero = (f'<div class="hero-eyebrow">{esc(podcast)} · {esc(meta.get("publish_date",""))} · 中文整理</div>'
            f'<h1>{esc(h["en_title"])}</h1><div class="hero-zh">{esc(h["zh_summary"])}</div>'
            f'<div class="hero-lede">“{esc(h["lede_quote"])}”<br><br>{esc(h["lede_bg"])}</div>'
            f'<div class="hero-meta">火山 2.0+热词 转录 · CLEAN 书面整理 · 逐字底档可展开</div>')
    strip = lambda s: re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    tldr = "".join(f'<li><p class="tldr-claim">{esc(strip(t["claim"]))}</p><p class="tldr-explain">{esc(t["explain"])}</p></li>'
                   for t in struct.get("tldr", []))

    tpl = Path(A.base).read_text(encoding="utf-8")
    tpl = tpl[tpl.index("<!DOCTYPE html>"):]          # 去顶部占位符文档注释(否则 {{}} 被重复填)
    for k, v in {"{{LANG}}": "zh-CN", "{{TITLE}}": esc(h["en_title"]),
                 "{{TOC_ITEMS}}": toc, "{{HERO}}": hero, "{{TLDR_LABEL}}": "TL;DR · 速读",
                 "{{TLDR_H2}}": esc(h["zh_summary"]), "{{TLDR_ITEMS}}": tldr,
                 "{{CHAPTERS}}": "\n".join(chap_html),
                 "{{FOOTER}}": f'来源:{esc(podcast)} · 火山 2.0 转录 → CLEAN 书面整理 · 逐字底档保真可对照'}.items():
        tpl = tpl.replace(k, v)
    tpl = tpl.replace("<body>", '<body data-mode="zh-only">').replace('<section class="tldr">', '<section class="tldr zh-only">')
    tpl = tpl.split("</html>")[0] + "</html>\n"        # 去 base.html 末尾模板文档注释

    left = re.findall(r'\{\{[A-Z_]+\}\}', tpl)
    if left:
        print(f"ERROR: 未填占位符 {set(left)}", file=sys.stderr); sys.exit(1)
    Path(A.out).write_text(tpl, encoding="utf-8")
    print(f"✓ {A.out}  {len(tpl):,} bytes · {len(chapters)} 章 · 书面 {len(clean_turns)} turn · 底档 {len(raw_turns)} turn", file=sys.stderr)

if __name__ == "__main__":
    main()
