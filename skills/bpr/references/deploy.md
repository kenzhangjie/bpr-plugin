# DEPLOY · 完整命令 / 排错

> `/bpr` 专用。四步:守卫 → 索引 → 部署 → 校验。
> 概览与硬规则见 `../SKILL.md`,本文件给可直接跑的命令和排错路径。

---

## 部署根

```
~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/
```

= bpr.ken.solar 的部署根。固定结构:

```
Transcript/
  <stem>.html            阅读页(DDR 产出)
  images/<stem>/         essay 正文自托管图
  index.html             landing(build_index 重建)
  (<stem>-poster.png 已废:海报分支 1.7.3 移除,0 篇用过)
```

本 skill **不搬运文件** —— DDR 直接写在这里,BPR 只负责重建索引 + 上传。

---

## 步骤 1 · INDEX.html 大小写守卫

**先跑这个,再跑 build_index。**

```bash
python3 - <<'PY'
import os
T = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript")
names = os.listdir(T)                      # 真实 dirent,保留大小写
print("INDEX.html:", "INDEX.html" in names, " index.html:", "index.html" in names)
if "INDEX.html" in names:                  # 只有真的存在大写才删
    os.remove(os.path.join(T, "INDEX.html"))
    print("已删除大写 INDEX.html")
else:
    print("无遗留大写文件,跳过")
PY
```

**为什么不能写 `[ -f INDEX.html ] && rm INDEX.html`**(L5,踩过):

macOS 的 APFS 默认大小写**不敏感**。目录里只有小写 `index.html` 时,
`[ -f INDEX.html ]` 依然为真 → 那条命令会**把 landing 删掉**。
必须 `os.listdir()` 拿真实 dirent 做精确字符串比对。

**不清大写文件的后果**:`open("index.html","w")` 在大小写不敏感 FS 上会匹配到
`INDEX.html`,**只改内容不改名**;而 Vercel 路由**大小写敏感**,只认小写
`index.html` 当 root → `https://bpr.ken.solar/` 返回 404。

---

## 步骤 2 · 重建 landing index

```bash
cd "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript"
python3 "$DDR_SKILL"/scripts/publish/build_index.py . index.html
```

扫描目录下所有 `<stem>.html`,生成卡片列表。

`$DDR_SKILL` = 同一 plugin 下的 ddr skill 目录,通常是:

```bash
DDR_SKILL=$(dirname "$(dirname "$BPR_SKILL")")/ddr    # 兄弟目录
# 或直接:
DDR_SKILL=~/.claude/plugins/cache/ddr-marketplace/ddr/<version>/skills/ddr
```


> 脚本在 **ddr skill** 下,两个 skill
> 共用同一份,**不要复制第二份** —— 历史上模板改动漏同步过(2026-07-11,reader
> 模板漏了整整三周)。

⚠️ **本地跑出来的 index.html 只是预览。** 线上那份由 Vercel 端重建,见步骤 4。

⚠️ **本地条目数可能比实际少**:源目录在 iCloud,被驱逐(dataless)的文件在
`Path.glob()` 时读不到,会被 `parse_entry` **静默跳过**。条目数对不上先看这个,
别急着改脚本 —— 先跑步骤 3 的 `brctl download .` 再重建就正常了。

---

## 步骤 3 · 部署

```bash
cd "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript"

# ① iCloud 占位符实体化 —— 不做会上传空文件
brctl download .

# ② proxy 直连部署
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy \
    -u HTTPS_PROXY -u https_proxy -u NODE_USE_ENV_PROXY \
    vercel --prod --yes
```

**`brctl download .`** —— 源目录在 iCloud,dataless 文件是占位符。
不实体化就部署 = **上传空文件**,线上文章页白屏且**不报错**。

⚠️ 如果 iCloud 同步被暂停过(`killall -STOP bird`),**按需下载会失效**,
`brctl download` 静默无效,照样传空。部署前确认 bird 在跑:

```bash
pgrep -x bird >/dev/null && echo "bird 运行中 ✅" || echo "⚠️ bird 没在跑,先 killall -CONT bird"
```

**`env -u ...`** —— 长连接被 GFW / undici 掐会失败,必须清掉**所有**代理变量
走系统 TUN 直连。漏一个都可能挂。

---

## 步骤 4 · 部署后校验

```bash
# ① root 必须 200
curl -s -o /dev/null -w "root  HTTP %{http_code}\n" https://bpr.ken.solar/

# ② 新发的文章页必须 200
curl -s -o /dev/null -w "article  HTTP %{http_code}\n" "https://bpr.ken.solar/<stem>.html"

# ③ 文章页可以对哈希(原样上传)
LOCAL=$(shasum -a 256 "<stem>.html" | cut -d' ' -f1)
REMOTE=$(curl -s "https://bpr.ken.solar/<stem>.html" | shasum -a 256 | cut -d' ' -f1)
[ "$LOCAL" = "$REMOTE" ] && echo "文章页一致 ✅" || echo "⚠️ 文章页不一致"

# ④ index.html 只查语义,不比哈希
curl -s https://bpr.ken.solar/ | grep -c 'entry-h1-link'      # 条目数
curl -s https://bpr.ken.solar/ | grep -o '<stem>.html'        # 新条目在不在
```

### ⚠️ index.html 为什么不能比哈希

`vercel.json` 里有:

```json
"buildCommand": "python3 bin/build_index.py . index.html"
```

**Vercel 每次部署都在自己那边重跑一遍索引生成** —— 线上那份根本不是你上传的那份。

2026-08-06 踩过:拿本地 index.html 跟线上对 sha256 对不上、条目数也差一条,
花了十几分钟怀疑部署没生效 / iCloud 回滚 / CDN 缓存。

**同日期条目在本地和线上顺序不同是正常的**:`Path.glob()` 在 macOS 和 Vercel 的
Linux 上返回序不一样,不是 bug。

---

## 排错

| 症状 | 先查 |
|---|---|
| root 返回 404 | 遗留大写 `INDEX.html`(步骤 1) |
| 文章页白屏 / 内容为空 | iCloud 占位符没实体化(`brctl download` + bird 是否在跑) |
| `vercel` 卡住 / 超时 | 代理变量没清干净(步骤 3 的 `env -u`) |
| 线上条目比本地少 | **正常**,先 `brctl download .` 再重建索引 |
| index.html 哈希对不上 | **正常**,Vercel 端重建的,只查语义 |
| 线上主题 / 排序被重置 | 有人改了 `localStorage` 的 `bpr-sort` / `bpr-theme` 键 → 回滚 |
| 部署 BLOCKED / 状态 UNKNOWN | git author 邮箱不在 Vercel 团队名下 |

---

## 相关记忆

| 记忆 | 讲什么 |
|---|---|
| `ddr-l5-index-guard-bug` | INDEX.html 守卫的 `[ -f ]` 陷阱 |
| `bpr-index-rebuilt-on-vercel` | index.html 由 Vercel 端重建,别比哈希 |
| `icloud-sync-traffic-and-pause` | 暂停同步会让按需下载失效 → 传空文件 |
| `git-proxy-dead-gh-works` | 代理相关诊断顺序 |
| `vercel-git-author-blocked` | 部署被按 git author 拦 |
