# INGEST · 输入解析 / URL 处理 / 发布日期 / 抓取流程

> 阶段 1 · INGEST 专用。解析输入(URL→fetch / 粘贴 text·SRT)、判输入类型、提发布日期/标题/作者、定文件名。

---

## 输入模式判定

支持四种输入,渲染逻辑略有不同:

| 模式 | 输入信号 | 是否渲染 speaker / turn / timestamp | Hero kicker 模板 |
|---|---|---|---|
| **SRT** | `.srt` 文件 / `00:00:00,000 -->` 时间码 | ✓(有则渲染) | `{podcast} · Episode · {year}` |
| **Transcript with timestamps** | `[00:12:34]` / `(12:34)` 标记 | ✓ | `{podcast} · Episode · {year}` |
| **Plain transcript** | 段首有 `Lenny:` / `Cat:` 等说话人 + 多说话人交替 | ✓ speaker,无 timestamp | `{podcast} with {Host} · {YYYY-MM-DD} · 双语整理` |
| **Blog / Essay** | URL(claude.com/blog · pmarchive · substack · paulgraham.com 等)/ 单作者长文 markdown | ✗ 全部跳过 | `{publication} · Essay · {YYYY-MM-DD}` |

判定逻辑:
- 有时间码 → SRT 模式
- `Speaker:` 模式 + 多说话人交替 → transcript 模式
- 单作者、有章节标题、无说话人轮换 → **blog / essay 模式**(走 `.body-block` + `.bilingual` 路径,不渲染 `.turn / .speaker / .timestamp`)

## URL 输入处理

`/bpr <URL>` 触发后,先**判定 URL 类型**,走不同分支。

### 分支表

| URL 类型 | 处理 |
|---|---|
| 普通博客 / essay(Anthropic Blog / nav.al / paulgraham.com / 公开 Substack / Medium / Stratechery 公开期等)| **curl 抓**(verbatim 原文,**不要用 WebFetch**——它会把长文压缩成摘要)→ 走正常流程 |
| **YouTube** | 走"YouTube 一站式流程"(下面) |
| **小宇宙 / Xiaoyuzhou**(`xiaoyuzhoufm.com/episode/<id>`)| 走"小宇宙 / Bilibili → 飞书妙记 一站式流程"(下面) |
| **Bilibili / B 站**(`bilibili.com/video/BV<id>` / `b23.tv/<short>`)| 走"小宇宙 / Bilibili → 飞书妙记 一站式流程"(下面),先尝试 yt-dlp 字幕,无字幕则下载音频走妙记 |
| Apple Podcasts / Spotify / Overcast | 不能直接抓,先问用户能不能给 YouTube/小宇宙 URL(同期一般多平台都有) |
| Paywall / 登录墙(WSJ / NYT / 付费 Substack)| curl 失败时**直接告诉用户**抓不到,让 ta 粘 raw text |
| PDF 链接 | 让用户先下载到本地,再 `/bpr <文件路径>` |

### 抓取命令(博客 / essay)

```bash
curl -s -L \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "<URL>" -o /tmp/bpr-raw.html
```

抓完用 Python regex 或 sed 提取 `<article>` / 主正文 div(每个站点不一样,看着 HTML 结构来),然后转成纯文本喂给 BPR 流程。**curl 拿到的是 verbatim HTML,不是 WebFetch 那种摘要**——这是 BPR 翻译质量的硬要求。

> ⚠️ **L4 硬规则**:抓博客 / 长文,一律 curl;`WebFetch` 只用于"我想知道这页面大致讲什么"的摘要场景。详见 `lessons-learned.md` L4。

## 发布日期提取(文件名用)

文件名第一段是发布日期。**绝对不能用今天的日期填占位**,要从内容来源拿真实日期。

### 提取策略(按优先级)

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | **`scripts/fetch/extract_metadata.py <URL>`**(博客 / essay)| 自动跑 7 种策略:JSON-LD → OG meta → 通用 meta → HTML5 `<time>` → URL `/YYYY/MM/DD/` → WordPress `wp-uploads/YYYY/MM/` → 正文开头 "Month YYYY" |
| 2 | **`scripts/fetch/fetch_youtube.sh` 产出的 metadata.json**(YouTube)| 字段 `upload_date`(YYYYMMDD)→ 转 `YYYY-MM-DD` |
| 3 | **Episode 平台页**(Spotify / Apple / Substack)| 1 + 2 都没拿到 → 看用户能不能给 episode 页面 URL,再走 1 |
| 4 | **WebSearch**(罕见)| 用作者名 + 标题搜,看官方 podcast feed / Wayback / Goodreads / 媒体报道里的发布时间 |
| 5 | **问用户** | 前 4 步全空才走这一步,**绝不静默用今天** |

### 用法

```bash
python3 scripts/fetch/extract_metadata.py "<URL>"
```

输出 JSON,关心的字段:
- `date` — ISO `YYYY-MM-DD`(可能为 null)
- `source_slug` — 文件名第二段(`paul-graham` / `lennys-podcast` / ...)
- `title` / `author` / `publication` — 给 hero 用
- `source` — 调试字段,告诉你是哪条策略命中的(`jsonld:datePublished` / `wp-uploads` / `body:month-year` 等)

### 已知限制

- **SPA / JS-rendered 站点**(anthropic.com 当前版本)— curl 拿到的是 shell,extract_metadata.py 会返回 `date: null`。这种情况退化到优先级 4(WebSearch)或 5(问用户)
- **WordPress wp-uploads 检测要求 ≥3 个 upload 路径**才采用,降低误判
- **Body text "Month YYYY" 只看正文前 1500 字符**,paulgraham 这种顶部纯文本日期会命中;复杂 layout 的现代博客通常用不上(因为 1-3 步已经命中)

### YouTube 一站式流程

bpr 有 `scripts/fetch/fetch_youtube.sh`,用 yt-dlp 拉字幕(uploaded 优先 / auto-subs 兜底),全程**不需要 whisper / ffmpeg**。

**Step A · 检查 yt-dlp**

```bash
which yt-dlp
```

没装 → 告诉用户三选一:
```
brew install yt-dlp        # 推荐
uv tool install yt-dlp
pipx install yt-dlp
```
等用户装完再继续。

**Step B · 一键拉取**

```bash
WORKDIR=$(mktemp -d /tmp/bpr-yt-XXXX)
scripts/fetch/fetch_youtube.sh "<URL>" "$WORKDIR"
```

成功后 `$WORKDIR/` 下有:
- `transcript.txt` — 清理后的纯文本字幕(去时间戳、去 cue 编号、去 `<c>` 标签、相邻重复行去重)
- `metadata.json` — 标题 / uploader(频道)/ 上传日期 / 描述 / 时长 / tags
- `transcript.*.vtt` — 原始 vtt(留作 debug,不动)

**Step C · 用 metadata 识别 host / guest**

```bash
cat "$WORKDIR/metadata.json"
```

提取:
- `title` → 通常含嘉宾名 + 主题
  例:`"20VC: Anton Osika of Lovable on Building a $200M ARR..."` → 嘉宾 = Anton Osika,主题 = Lovable
- `uploader` / `channel` → 主持人 / 节目名
  例:`uploader: "20VC with Harry Stebbings"` → podcast = 20VC,host = Harry Stebbings
- `upload_date`(YYYYMMDD)→ 转 YYYY-MM-DD 给 hero kicker
- `description` 前几段 → 通常有 "Today my guest is X" / "X joins us to discuss Y"

**适用 L1 硬规则**(`lessons-learned.md`):主持人 / 嘉宾**必须从 metadata + transcript 开头确认**,不准默认。

**Step D · 喂给 BPR 正常流程**

把 `$WORKDIR/transcript.txt` 当作 transcript 输入,但注意字幕来源差异:

| 字幕来源 | 标点 | speaker | BPR 渲染模式 | 预处理 |
|---|---|---|---|---|
| **uploaded subs**(节目方上传)| 有 | 有时有 | podcast 模式 | 直接走流程 |
| **auto-subs**(YouTube 自动)| 无 | 无 | 退化模式(见 `prep-and-modes.md`) | LLM 必须先重断句 + 加标点 |

> **auto-subs 预处理(重断句 / 加标点 / speaker 推断 / 退化 essay)→ 见 `prep-and-modes.md`(PREP 阶段)。**

### Step E · WebFetch(普通博客模式)抓取后的 sanity check

- 抓回来内容只有 `<title>` + 几行 description → 抓失败,提示用户粘 raw text
- 字数 < 500 → 多半是简介页或被截断,同样提示
- 抓到完整正文 → 走正常流程

### 小宇宙 / Bilibili → 飞书妙记 一站式流程

YouTube 自带字幕,所以 `fetch_youtube.sh` 一步出 transcript。**小宇宙 / B 站没有公开字幕 API**,所以流程多一步:**下载音频 → 走飞书妙记转录 → 拿逐字稿**。

**前置依赖**:
- `lark-cli`(飞书 CLI 已装好且 `auth login` 完成)
- 飞书账号有妙记上传额度
- `yt-dlp`(只 B 站需要)

#### ⛔ Step 0 · scope 前置检查(必跑,不要跳)

2026-05 实战暴露:lark-cli 的错误提示"run lark-cli auth login --scope X"是**误导** —— 所需 scope 必须**先在 app 开发者后台开通**,才能通过 `auth login --domain` 拉到。**没开就跑 minutes / vc 命令一定 fail**,会浪费大量时间在调认证。

跑流程**第一行命令**就是 scope 验证:

```bash
lark-cli auth scopes | grep -E 'minutes|vc:note' | sort -u
```

期望看到下面 **7+ 行**(缺一不行,缺一就 fail):

```
minutes:minutes.search:read         # 搜妙记列表
minutes:minutes.basic:read          # 获取妙记基础信息
minutes:minutes.upload:write        # 通过 file_token 生成妙记 ← lark-cli minutes +upload
minutes:minutes.media:export        # 下载妙记音视频
minutes:minutes:readonly            # 妙记只读
minutes:minutes.artifacts:read      # 读总结/待办/章节产物 ← lark-cli vc +notes
minutes:minutes.transcript:export   # 导出逐字稿       ← lark-cli vc +notes
vc:note:read                        # 会议纪要(妙记沿用同一权限)
```

**如果缺**:
1. 浏览器打开 https://open.feishu.cn/app → 找到 app(`lark-cli auth status` 里的 `appId`)→ **权限管理** → 搜对应 scope → 勾上 → 提交审核(自己 app 通常秒过)
2. iTerm 跑 `lark-cli auth login --domain minutes,vc` 增量授权
3. 再跑一次 `lark-cli auth scopes | grep minutes` 验证

**未补全 scope 之前,绝对不要进入 Step A,会浪费用户时间**。

#### 兜底方案:Web UI 手动上传

如果 scope 审批一时半会下不来(企业管理员审核可能要小时级),走兜底路:
1. 浏览器开 https://meetings.feishu.cn/minutes/me → 上传按钮 → 选 `$WORKDIR/audio.m4a`
2. 等妙记 AI 转录完(4 小时音频 ~10-30 分钟)
3. 妙记页面右上角 → 导出逐字稿(TXT)
4. 把 TXT 文件路径给 BPR,继续 Step C(语言检测 → 中文模式 / 双语模式)

这条路绕开所有 minutes scope 审核,**今天就能产出**,适合首次跑 / 紧急场景。

#### 小宇宙(xiaoyuzhoufm.com)

**Step A · 拉音频 + 元数据**

```bash
WORKDIR=$(mktemp -d /tmp/bpr-xyz-XXXX)
scripts/fetch/fetch_xiaoyuzhou.sh "<URL>" "$WORKDIR"
```

成功后 `$WORKDIR/` 下有:
- `audio.m4a` (或 `audio.mp3`) — 原始音频文件
- `metadata.json` — `title` / `podcast` / `publish_date` / `audio_url` / `description`

#### Bilibili(bilibili.com/video/BV...)

**Step A · yt-dlp + 字幕尝试 + 音频回退**

```bash
WORKDIR=$(mktemp -d /tmp/bpr-bili-XXXX)
scripts/fetch/fetch_bilibili.sh "<URL>" "$WORKDIR"
```

脚本逻辑:
1. 先试 uploaded subs(zh-CN / zh-Hans / zh / ai-zh / en)→ 有则清洗成 `transcript.txt`,跳过妙记
2. 字幕不存在 → 下载 `bestaudio[ext=m4a]` 到 `audio.m4a`,走妙记
3. **需要 Chrome cookie**(私人/会员视频),已默认开启 `--cookies-from-browser chrome`

#### Step B(推荐)· 火山引擎大模型录音识别(优先于妙记)

**Ken 专用**:有 `~/.config/volc/asr.env` 的 `VOLC_API_KEY` 时,**优先走火山,不走妙记**——纯 API 无人值守(无妙记的交互授权 / scope 摩擦)、中英混说质量更高、自带词级时间戳 + 说话人分离。妙记降级为 fallback(火山报错或无密钥时)。

```bash
# fetch_xiaoyuzhou.sh / fetch_bilibili.sh 已给出音频直链(metadata.json 的 audio_url),
# 火山可直接吃 URL,省掉重新上传那一步。
AUDIO_URL=$(python3 -c "import json;print(json.load(open('$WORKDIR/metadata.json'))['audio_url'])")
# --meta 把本期标题/简介 + ~/.config/volc/glossary.txt 常驻专名表拼成 context 偏置喂给模型,
# 中英混录的英文品牌名/术语在识别阶段就转对,别再靠事后 correct_table 替换。
python3 ~/.config/volc/volc_asr.py "$AUDIO_URL" "$WORKDIR/transcript.txt" --meta "$WORKDIR/metadata.json"
```

**质量偏置三层(强→弱)**:

1. `corpus.context`(--meta 自动 + glossary.txt):本期元数据(标题/简介) + 常驻专名表,在识别时直接偏置模型,转录准确度最高。
2. `corpus.boosting_table_name`(--boosting 控制台表):云端管理的特定领域术语表,精度次于上层。
3. `correct_table.json`(事后替换,兜底):本地硬映射表,仅修正遗漏,不影响上游两层的转录结果。

输出 `transcript.txt` 是 `Speaker N HH:MM:SS.mmm` 格式(与妙记导出一致,下游无需改),
并自动套用 `~/.config/volc/correct_table.json` 的专名硬映射(Higgsfield / Hockey Stick Growth / Midjourney …)。
鉴权要点:火山 v3 大模型端点用 **X-Api-Key**(= `VOLC_API_KEY`),**不是** App-Key/Access-Key(后者会 401 `grant not found`)。

> 转录质量仍可能有专名错词(中英混录里英文品牌名最易错)→ BPR 翻译 / 渲染阶段按上下文修正,
> 新踩坑的无歧义专名顺手加进 `correct_table.json`,下次自动生效。

#### Step B(fallback)· 飞书妙记转录(无火山密钥时;小宇宙必跑,B 站无字幕时跑)

⚠️ **`lark-cli drive +upload` 拒绝绝对路径**(2026-05 实战发现),必须 `cd` 到 WORKDIR 用 `./filename` 相对路径:

```bash
cd "$WORKDIR"   # ← 关键!不 cd 直接传 --file /tmp/... 会被 validation 拒掉
AUDIO_BASENAME="audio.m4a"   # 或 audio.mp3

# 1. 上传到飞书云空间,拿 file_token
FILE_TOKEN=$(lark-cli drive +upload --file "./$AUDIO_BASENAME" --as user 2>&1 \
  | /usr/bin/python3 -c "import json,sys;d=json.loads(''.join(l for l in sys.stdin if l.startswith('{') or not l.startswith('[')));print(d.get('data',{}).get('file_token',''))")
echo "file_token: $FILE_TOKEN"

# 2. 用 file_token 生成妙记,拿 minute_url
MINUTE_URL=$(lark-cli minutes +upload --file-token "$FILE_TOKEN" --as user 2>&1 \
  | grep -oE 'https://[^/]+/minutes/[A-Za-z0-9]+' | head -1)
MINUTE_TOKEN="${MINUTE_URL##*/}"
echo "minute_token: $MINUTE_TOKEN"

# 3. 等妙记后台 AI 转录完成(短音频 1-3 分钟,长 30 分钟+ 视情况)
# 妙记后台异步处理,需要轮询 vc +notes 直到返回逐字稿
lark-cli vc +notes --minute-tokens "$MINUTE_TOKEN" --as user > "$WORKDIR/notes.json"

# 4. 从 notes.json 提取逐字稿到 transcript.txt
/usr/bin/python3 -c "
import json
data = json.load(open('$WORKDIR/notes.json'))
# 妙记返回结构因版本而异,常见 transcript / sentences / utterances
text = data.get('transcript') or data.get('text', '')
if not text and 'sentences' in data:
    text = '\n'.join(s.get('content', s.get('text', '')) for s in data['sentences'])
print(text)
" > "$WORKDIR/transcript.txt"
```

**轮询妙记完成**:妙记 AI 异步处理。第一次 `vc +notes` 可能返回"processing"。建议:
```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  RESULT=$(lark-cli vc +notes --minute-tokens "$MINUTE_TOKEN" --as user 2>&1)
  if echo "$RESULT" | grep -qE 'transcript|sentences|utterances'; then
    echo "$RESULT" > "$WORKDIR/notes.json"
    break
  fi
  echo "  still processing... wait 30s (attempt $i/10)"
  sleep 30
done
```

#### Step C · 喂给 BPR 正常流程

把 `$WORKDIR/transcript.txt` + `$WORKDIR/metadata.json` 当作 transcript 输入。
注意 metadata 字段命名跟 YouTube 略不同:
- 小宇宙:`title` / `podcast` / `publish_date`
- B 站:`title` / `uploader` / `upload_date`

→ 在 SKILL.md hero kicker 渲染时按 source 字段(`xiaoyuzhou` / `bilibili` / `youtube`)选不同模板。

#### 妙记常见问题

| 问题 | 修法 |
|---|---|
| `lark-cli` 未认证 | `lark-cli auth login` |
| 妙记说还在处理 | 增加轮询次数或拉长间隔(长音频 > 60min 可能要 5-10 分钟) |
| 转录质量差(说话人多 / 杂音多) | 妙记本身限制,接受。可在 BPR 翻译阶段适度修正明显错词 |
| `--as user` vs `--as bot` | 妙记功能必须 `--as user`(bot 拿不到个人空间妙记) |
| 文件超大上传失败 | `drive +upload` 默认支持分片;失败时检查 lark 上传额度 |

---

## 发布日期提取(必跑,不能跳)

**前置**:文件名日期必须是**内容发布日期**,不是处理日期。**绝不静默用今天**。

按下表的优先级**逐级试**,前一级拿到就停,跳到 Step Z 应用日期。

### Step P1 · YouTube → yt-dlp metadata(最准)

`fetch_youtube.sh` 已经把 `upload_date` 存到 `$WORKDIR/metadata.json`,直接读:
```bash
cat "$WORKDIR/metadata.json" | python3 -c "import json,sys;d=json.load(sys.stdin);u=d['upload_date'];print(f'{u[:4]}-{u[4:6]}-{u[6:8]}')"
```
→ 输出 `YYYY-MM-DD`,直接用。**这是最可靠的来源**(YouTube 自己记录的,不是页面解析)。

### Step P2 · 博客 / Essay → 先跑脚本,失败再 WebFetch

#### P2a · 跑脚本(优先,~70% 场景秒级解决)

```bash
python3 scripts/fetch/extract_metadata.py "<URL>"
```

返回:
- `YYYY-MM-DD`(exit 0)→ 直接用,跳到 Step Z
- `not_found`(exit 1)→ 脚本兜不住,继续 P2b

脚本检查的来源(按优先级):
1. `<meta property="article:published_time">`
2. `<meta name="date">` / `<meta name="dc.date">`
3. JSON-LD `<script type="application/ld+json">` 里的 `datePublished`
4. `<time datetime="YYYY-MM-DD">`
5. `<meta property="og:updated_time">`(末位,updated 不如 published 准)

**已验证好用的站**:nav.al / Lenny's Substack / 大部分 WordPress / 新闻站 / Medium。
**脚本搞不定的站**(JS-rendered SPA):claude.com/blog / 部分 Vercel 部署的 Next.js 站 / 很多现代静态生成博客。这些走 P2b。

#### P2b · 脚本失败 → WebFetch + 显式 prompt

WebFetch 时**显式 prompt 抓发布日期**(不是只抓正文):

> "Extract the publish date of this article. Look for `<time>` tags, `<meta property='article:published_time'>`, JSON-LD `datePublished`, og:updated_time, or visible date in the byline. Reply with just the date in YYYY-MM-DD format, or `not found`."

LLM 模型可能能推断出 JS-rendered 页面的内容(它看到的是 markdown 化版本,有时包含元数据)。失败再继续 P3。

### Step P3 · Podcast(非 YouTube)→ 平台页 + WebSearch

Podcast episode 通常 YouTube 之外还有 Spotify / Apple Podcasts / Substack(Lenny's)/ libsyn(20VC),WebSearch 找到 episode 页:
- Spotify episode URL → 页面有 release date
- Apple Podcasts URL → 页面有发布日期
- Substack post(Lenny / Stratechery)→ URL 通常含日期或页面有
- Twitter/X 主持人发布通告 post → status ID 编码时间

WebSearch query 模板:
```
"<podcast name>" "<guest name>" "<topic keyword>" episode date
```
要求模型从结果中**只挑有具体日期的来源**(Spotify / Apple Podcasts / Substack / 官方 newsletter),不要相信博客文章的"发布于 X 周前"这种相对描述。

### Step P4 · Transcript 内部线索(辅助)

读 transcript 头几段或尾几段,有时主持人会说:
- "Recording this on April 23"
- "Last week the Anthropic team launched X..."(可推断录制时间)
这是**次要参考**,只在前 3 步都失败时用。

### Step P5 · 实在拿不到 → 明确问用户

```
"我没法可靠拿到这期的发布日期。你知道吗?或者给我一个 Spotify/Apple Podcasts/YouTube URL 我去抓?"
```

**绝不静默用今天**。文件名日期错位会让时间线乱掉,后续整理代价更大。

### Step Z · 应用日期到文件名 + Hero kicker

拿到 `YYYY-MM-DD` 后:
- **文件名前缀** = 这个日期
- **Hero kicker** 也用这个日期(`{Podcast} with {Host} · YYYY-MM-DD · 双语整理`),不要用今天

### 不要做的事

- 不要"猜"博客内容补全(哪怕有先验知识)
- 不要根据 URL slug 自己编正文
- 不要静默 fallback——抓不到必须告诉用户
- **不要假装能直接抓 YouTube transcript**:除非走了上面 Step A-D,否则只能拿到页面标题和描述
