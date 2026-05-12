# BPR · 详细规则

> SKILL.md 已经包含核心步骤、自适应表、翻译简版规则、修饰词、输出规范。
> 本文件只放**详细子规则**——SKILL.md 太琐碎装不下的。

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
| 1 | **`scripts/extract_metadata.py <URL>`**(博客 / essay)| 自动跑 7 种策略:JSON-LD → OG meta → 通用 meta → HTML5 `<time>` → URL `/YYYY/MM/DD/` → WordPress `wp-uploads/YYYY/MM/` → 正文开头 "Month YYYY" |
| 2 | **`scripts/fetch_youtube.sh` 产出的 metadata.json**(YouTube)| 字段 `upload_date`(YYYYMMDD)→ 转 `YYYY-MM-DD` |
| 3 | **Episode 平台页**(Spotify / Apple / Substack)| 1 + 2 都没拿到 → 看用户能不能给 episode 页面 URL,再走 1 |
| 4 | **WebSearch**(罕见)| 用作者名 + 标题搜,看官方 podcast feed / Wayback / Goodreads / 媒体报道里的发布时间 |
| 5 | **问用户** | 前 4 步全空才走这一步,**绝不静默用今天** |

### 用法

```bash
python3 ~/.claude/skills/bpr-skill/scripts/extract_metadata.py "<URL>"
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

bpr 有 `scripts/fetch_youtube.sh`,用 yt-dlp 拉字幕(uploaded 优先 / auto-subs 兜底),全程**不需要 whisper / ffmpeg**。

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
~/.claude/skills/bpr-skill/scripts/fetch_youtube.sh "<URL>" "$WORKDIR"
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
| **auto-subs**(YouTube 自动)| 无 | 无 | 退化模式(见下) | LLM 必须先重断句 + 加标点 |

**auto-subs 预处理(模式退化)**

如果只拿到 auto-subs:

1. **在翻译 Step 1 之前**,先做"重新断句 + 加标点"——把流式无标点文本切成正常英文句子。这步走在三步法之前,不影响"每段都跑三步法"的硬规则
2. **从 metadata 推断 speaker**:`uploader = host` / `description 里的 guest = 嘉宾`,根据语境分 turn(谁在提问 / 谁在回答)
3. **如果不能可靠区分谁在说话**:退化成 **essay 模式渲染**(不写 `.speaker / .turn`),保留章节级时间戳标注。**不要瞎猜 speaker**——猜错比退化更糟

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

#### 小宇宙(xiaoyuzhoufm.com)

**Step A · 拉音频 + 元数据**

```bash
WORKDIR=$(mktemp -d /tmp/bpr-xyz-XXXX)
~/.claude/plugins/cache/bpr-marketplace/bpr/<ver>/skills/bpr/scripts/fetch_xiaoyuzhou.sh "<URL>" "$WORKDIR"
```

成功后 `$WORKDIR/` 下有:
- `audio.m4a` (或 `audio.mp3`) — 原始音频文件
- `metadata.json` — `title` / `podcast` / `publish_date` / `audio_url` / `description`

#### Bilibili(bilibili.com/video/BV...)

**Step A · yt-dlp + 字幕尝试 + 音频回退**

```bash
WORKDIR=$(mktemp -d /tmp/bpr-bili-XXXX)
~/.claude/plugins/cache/bpr-marketplace/bpr/<ver>/skills/bpr/scripts/fetch_bilibili.sh "<URL>" "$WORKDIR"
```

脚本逻辑:
1. 先试 uploaded subs(zh-CN / zh-Hans / zh / ai-zh / en)→ 有则清洗成 `transcript.txt`,跳过妙记
2. 字幕不存在 → 下载 `bestaudio[ext=m4a]` 到 `audio.m4a`,走妙记
3. **需要 Chrome cookie**(私人/会员视频),已默认开启 `--cookies-from-browser chrome`

#### Step B · 飞书妙记转录(小宇宙必跑,B 站无字幕时跑)

```bash
AUDIO="$WORKDIR/audio.m4a"   # 或 audio.mp3

# 1. 上传到飞书云空间,拿 file_token
FILE_TOKEN=$(lark-cli drive +upload "$AUDIO" --as user 2>&1 | grep -oE 'file_token[: =]+["]?[A-Za-z0-9_-]+' | grep -oE '[A-Za-z0-9_-]{20,}' | tail -1)
echo "file_token: $FILE_TOKEN"

# 2. 用 file_token 生成妙记,拿 minute_url
MINUTE_URL=$(lark-cli minutes +upload --file-token "$FILE_TOKEN" --as user 2>&1 | grep -oE 'https://[^/]+/minutes/[A-Za-z0-9]+' | head -1)
MINUTE_TOKEN="${MINUTE_URL##*/}"
echo "minute_token: $MINUTE_TOKEN"

# 3. 等妙记后台 AI 转录完成(短音频 1-3 分钟,长 30 分钟+ 视情况)
# 妙记后台异步处理,需要轮询 vc +notes 直到返回逐字稿
lark-cli vc +notes --minute-tokens "$MINUTE_TOKEN" --as user > "$WORKDIR/notes.json"

# 4. 从 notes.json 提取逐字稿到 transcript.txt
python3 -c "
import json
data = json.load(open('$WORKDIR/notes.json'))
# 妙记返回结构因版本而异,常见 transcript / sentences / utterances
# 兼容多种:
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
python3 ~/.claude/skills/bpr-skill/scripts/extract_publish_date.py "<URL>"
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

## TL;DR 标题写法

- `tldr-label` 固定写 `TL;DR · 速读`
- `tldr h2` **不写死数字**(❌ "11 条来自 Anthropic 内部的判断")
- `tldr h2` 用**描述性主题**(✓ "Anthropic PM 的工作怎么变了")
- 数字可以提,但不是唯一核心信息

## 每条 TL;DR 格式

每条由 4 个元素组成,顺序固定:

1. **加粗中文论点**(15 字内)— `.tldr-claim`
2. **英文金句**(斜体,原文 ≤ 30 词)— `.tldr-quote`
3. **英文上下文**(原文 1-2 句,40-80 词,提供金句的对话语境)— `.tldr-context`
4. **中文解释**(≤ 60 中文字,1-2 句)— `.tldr-explain`

### 英文上下文 (`.tldr-context`) 写作原则

- 直接从 transcript / 原文复制,不改写、不润色
- 取金句**前后相邻**的 1-2 句话(不是金句本身)
- 让读者看到金句"为什么会出现"——前因或紧接的展开
- 视觉上比金句弱:更小字号 / 普通体(非斜体)/ 颜色更浅
- 如果金句本身已经独立成段、前后没有可补充的自然延伸,**可以省略**这一项
  (省略 > 硬塞低质量上下文)

### 例子

```html
<li>
  <p class="tldr-claim">大厂光环不再加分,可能反而扣分</p>
  <p class="tldr-quote">"Your brands don't matter as much as how modern you are in your ability to deliver product."</p>
  <p class="tldr-context">"What if the established brands are working in a way that's not current? You work there for six years, you come out, and it feels like you're in a totally different world."</p>
  <p class="tldr-explain">在 Meta 干两年把某个算法跑快一点的故事,放进"现在公司怎么造产品"的对话里会显得非常苍白。</p>
</li>
```

CSS 已经写在 `templates/base.html`,不要重复定义。

## 金句优先级

1. 反直觉/反共识(最优先)
2. 有数字/数据支撑
3. 全文重复出现的核心论点
4. 押韵或对称结构(如 "...is dead, ...is alive")

## 翻译补充约束

> 核心方法论 → `translation-prompt.md` 的"翻译三步法"。**每章每段都要跑**,不跳过。

补充约束:
- 数字/单位/公司名:保留原文,不汇率换算
- 引用他人:人名英文 + 中文翻译并存
- Sponsor / Outro 段:翻译保留,但 TL;DR 不体现
- 长复合句:可适度拆短,但不省略信息

## inline link 处理

- 原文 inline link **必须 preserve**,不能删
- 英文段:写 `<a href="...">link text</a>`(保留原 link text 和原 URL)
- 中文段:在中文翻译对应位置写**同一个 `<a>`**,link text 翻译,URL 保持
- **不要**在中文段重复打印 URL 文本(`(https://...)` 之类)——视觉噪音
- bare link("Learn more in our docs.") → 英文段保留 `<a>`,中文段也保留 `<a>` 同 URL

## 双语对照输出

### 适用条件
- 英文素材(YouTube / Podcast / 英文 article / 英文 transcript / 博客 essay):必须输出双语对照版
- 中文素材:仅输出单一中文版,不需要对照

### 对照颗粒度

- **句级对照**:原文一句英文紧跟一句中文,**不是段落级**
- 一个英文句子包成一个对照单元(`<div class="bilingual">` + `<p class="en">` + `<p class="zh">`)
- 长复合句允许在自然停顿处(分号、连接词)拆成 2 句对照
- 不允许"一段英文 + 一段中文翻译"的段落级对照(信息密度太低,难对位)

### 对照视觉规范

CSS 已经写在 `templates/base.html`(`.bilingual` / `.bilingual .en` / `.bilingual .zh`),
直接用,不要重新定义。

### 对照内容要求

- **保留原文 verbatim**,不省略口头语(you know / I mean / like 等可酌情保留以体现语气)
- 中文翻译以"信达雅"中的"达"为先——准确传递意思 > 字面对照
- 专有名词、公司名、人名保持英文原文(Stripe / DoorDash / Keith Rabois)
- 数字、单位保留原文($10M 不翻成"一千万美元")
- 引用他人:"翻译原则"中"人名英文 + 中文翻译并存"

### 与 TL;DR 的关系

- TL;DR 区域**仍然只用中文**,不做对照(追求最大信息密度)
- TL;DR 中的英文金句保留斜体英文 + 中文解释(按"每条 TL;DR 格式"规则)
- 对照只应用于**正文**(transcript / 博客内容)

### HTML 输出结构示例(blog / essay 模式)

```html
<div class="body-block">
  <div class="bilingual">
    <p class="en">"The idea of a PM makes no sense in the future."</p>
    <p class="zh">"未来'产品经理'这个概念将变得毫无意义。"</p>
  </div>
  <div class="bilingual">
    <p class="en">"The skill is more like being a CEO now — what are we building and why?"</p>
    <p class="zh">"这项技能现在更像是做 CEO — 思考的是:我们在构建什么、为什么要构建它。"</p>
  </div>
</div>
```

(podcast 模式:把 `.bilingual` 包在 `.turn-body` 内,前面有 `.turn-head` 显示 speaker + timestamp。)

### 例外

- 用户明确要求"只排英文" → 跳过中文,仅输出英文版
- 用户明确要求"只要中文" → 跳过英文,仅输出中文版
- 默认行为(无修饰词)= 双语对照

---

## 中文模式 (Chinese-Only Mode)

**触发条件:CJK 字符占 transcript 主体 ≥ 60%** —— 自动检测,**不需要用户加修饰词**。

### 为什么单独一套?

中文 podcast / blog / 访谈不需要翻译,逐句双语对照纯属浪费篇幅。读者真正想从中文内容里拿到的是:
1. **可扫读的摘要**(TL;DR,5-15 条)
2. **非共识的判断**(嘉宾说出来的反直觉 / 反主流的洞见)
3. **章节回顾**(每章 200-400 字浓缩)

——本质是从"逐字稿"压缩到"读书笔记"。

### 语言检测算法

```python
def detect_language(text: str) -> str:
    """Return 'zh' if Chinese-dominant, 'en' otherwise."""
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    total = cjk + latin
    if total < 100: return 'en'  # 太短无法判断,默认双语
    return 'zh' if cjk / total >= 0.6 else 'en'
```

**判定时机**:在预处理(Step 2)之后、章节切分(Step 3)之前。一旦判定中文,**整个流程切到中文分支**。

### 中文模式输出结构

```
Hero
  - kicker:{podcast} with {host} · {YYYY-MM-DD} · 中文整理
  - h1:中文标题(直接用原标题,不需翻译)
  - hero-zh:一句话概括(20-40 字)
  - hero-lede:最核心金句(选一条) + 一段背景(80-120 字)
─────────────────
TL;DR · 速读 (5-15 条)
  - 每条:加粗中文论点 + 一句解释(不需要英文 quote / context 双语三明治结构)
─────────────────
🔥 非共识 · Contrarian Takes (3-8 条)
  - 每条:嘉宾原话引用(中文 verbatim,带 .pull 样式)
  - 配一个 "为什么非共识" 短解释 (中文,1-2 句)
  - 可选:多数人怎么想(对比锚点)
─────────────────
章节回顾 (8-12 章,可选)
  - 每章 200-400 字中文摘要(不是 verbatim)
  - 保留章节级时间戳(如有)
  - 不再有 .bilingual 双语对照块
─────────────────
Footer(来源 + 元信息)
```

### 中文模式与 podcast / essay 模式的区别

| 维度 | 英文双语模式 | 中文模式 |
|---|---|---|
| 翻译三步法 | ✓ 每段都跑 | ✗ 不跑 |
| `.bilingual` 双语对照块 | ✓ 句级 | ✗ 不渲染 |
| `.turn-head` speaker / timestamp | 视情况渲染 | 视情况渲染(可保留) |
| TL;DR 4 元素结构 | 中文论点 + 英文金句 + 英文上下文 + 中文解释 | **仅 2 元素**:中文论点 + 中文解释 |
| **非共识 section** | ✗ 不渲染 | ✓ **必须有** |
| 章节正文 | 逐句双语对照 | 浓缩中文摘要 |

### 非共识 section 写作原则

这是中文模式的灵魂。**做不好,整篇就是简陋摘要器**。

**什么算非共识**:
- 嘉宾说出来跟**主流认知不一样**的判断(例:"AGI 5 年内"在 2020 是非共识,2026 是共识)
- **反直觉**的因果(例:"做更少的事才能做更多")
- **嘉宾独有的判断**,你在别处听不到(例:Naval 的 specific knowledge、PG 的 live in the future)
- **行业内部人才知道的内幕逻辑**(例:"国内 AI 创业 80% 资源花在合规上")

**什么不算非共识**:
- 复述主流观点(❌ "AI 会改变所有行业")
- 数据陈述(❌ "我们这个季度增长了 30%"——这是事实不是判断)
- 老生常谈的鸡汤(❌ "保持初心很重要")

**格式**:
```html
<section class="contrarian">
  <div class="contrarian-label">🔥 非共识 · Contrarian Takes</div>
  <div class="contrarian-item">
    <p class="contrarian-quote">"原话引用,verbatim 中文"</p>
    <p class="contrarian-why"><strong>为什么非共识 · </strong>多数人觉得 X,他说 Y,因为 Z。</p>
  </div>
  ...
</section>
```

CSS 写在 `templates/base.html` 的"中文模式扩展样式"section。

### 章节回顾(中文模式专属)

跟英文双语模式的 `.bilingual` 句级对照完全不同——这里是**浓缩摘要**,200-400 字一章。

```html
<section class="chapter zh-only" id="chN">
  <div class="ch-num">Chapter 0N</div>
  <h2>章节中文标题</h2>
  <div class="ch-range">15:30 — 28:45 · 关键词概括</div>
  <div class="ch-summary">
    <p>本章 200-400 字的中文浓缩,抓住核心论点 + 关键证据 + 嘉宾态度。
    不是 verbatim,允许编辑取舍。但**不能编造嘉宾没说的话**。</p>
    <p>(如有金句)<span class="ch-pull">"verbatim 嘉宾原话"</span></p>
  </div>
</section>
```

### 文件名约定(中文模式)

文件名跟双语模式一样,**但日期、source slug、嘉宾名等元数据要从中文 metadata 抓**:
- 小宇宙:`{date}_{podcast}_{host}_{topic}.html`(host slug 用拼音)
- B 站:`{date}_{uploader}_{topic}.html`

例:`2026-05-13_kechuang-50-ren_zhang-yiming_AI-and-bytedance.html`(科创 50 人:张一鸣谈 AI 与字节)
