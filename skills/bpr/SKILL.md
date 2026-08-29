---
name: bpr
description: 把 Transcript 目录里的阅读页发布到 bpr.ken.solar —— 重建 landing index、iCloud 实体化、proxy 直连部署、部署后校验。当用户输入 "/bpr"、"/bpr index"、"/bpr verify",或说"发布到 bpr"/"部署一下"/"重建索引"/"补发某篇"时触发。与 /ddr 分工:DDR 只负责把素材转成本地 HTML,BPR 只负责把 HTML 送上线,两件事分开决定。
---

# BPR · 发布到 bpr.ken.solar

`/ddr` 只出本地 HTML,**不发布**。发布是独立动作,由本 skill 负责。

拆开的理由:转换和发布是两件该分开决定的事 —— 你可能想攒几篇一起发、想改完某篇单独重发、
想只更新 landing 而不加新文章。绑在一条流水线里这三件都做不了。

## 触发条件

| 命令 | 做什么 |
|---|---|
| `/bpr` | **默认**:重建 landing index → 部署 → 校验 |
| `/bpr index` | 只重建 index,**不部署**(想先看看 landing 长什么样) |
| `/bpr verify` | 只跑部署后校验(怀疑线上不对时用) |

自然语言同样触发:"发布到 bpr"、"部署一下"、"重建索引"、"把 xxx 那篇补发一下"。

## 部署根

```
~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/
```

这个目录 **= bpr.ken.solar 的部署根**。DDR 的产物直接写在这里,本 skill 不搬运文件,
只负责重建索引 + 上传。

```
Transcript/
  <stem>.html            阅读页(DDR 产出)
  images/<stem>/         essay 正文自托管图
  index.html             landing(build_index 重建)
```

## 四步

按顺序走,**每步都有对应的坑**,详见 `references/deploy.md`。

| 步 | 做什么 | 坑 |
|---|---|---|
| **1 · 守卫** | 清理遗留的大写 `INDEX.html` | ⚠️ **必须比对真实 dirent**,`[ -f INDEX.html ]` 在 macOS 会误删小写的 |
| **2 · 索引** | 跑 ddr skill 下的 `build_index.py` 重建 landing | 本地这份只是预览,线上那份由 Vercel 端重建 |
| **3 · 部署** | `brctl download .` → proxy 直连 `vercel --prod` | ⚠️ 不 download 会传空文件;不清代理会被掐 |
| **4 · 校验** | curl root + 抽查文章页 | ⚠️ **只对文章页比哈希**,index.html 比不了 |

> `/bpr index` 只跑 1-2 步。`/bpr verify` 只跑第 4 步。

## 四条硬规则

**① INDEX.html 大小写守卫 —— 不能用 `[ -f ]` 判断**

macOS 大小写不敏感 FS 上,只有小写 `index.html` 时 `[ -f INDEX.html ]` 也为真,
照着删会把 landing 删掉。**必须列真实 dirent 再比对**:

```bash
python3 - <<'PY'
import os
T = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript")
names = os.listdir(T)                      # 真实 dirent,保留大小写
if "INDEX.html" in names:                  # 只有真的存在大写才删
    os.remove(os.path.join(T, "INDEX.html"))
    print("已删除大写 INDEX.html")
else:
    print("无遗留大写文件,跳过")
PY
```

不清的后果:Vercel 路由大小写敏感,只认小写 `index.html` 当 root,`/` 返回 404。

**② 部署前必须 `brctl download .`**

源目录在 iCloud。被驱逐(dataless)的文件是占位符,直接部署会**上传空文件**,
线上文章页变白页且不报错。

**③ proxy 必须清干净**

长连接被 GFW / undici 掐会失败。所有代理环境变量都要 `env -u`,走系统 TUN 直连:

```bash
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy \
    -u HTTPS_PROXY -u https_proxy -u NODE_USE_ENV_PROXY \
    vercel --prod --yes
```

**④ 校验时 index.html 不能比哈希**

`vercel.json` 里有 `"buildCommand": "python3 bin/build_index.py . index.html"` ——
**Vercel 每次部署都在自己那边重跑一遍索引生成**,线上那份不是你上传的那份。

- **文章页**:原样上传,可以对哈希 ✅
- **index.html**:只检查语义 —— 条目数、新条目在不在、`entry-h1-link` 的 href 对不对
- 同日期条目在本地和线上**顺序不同是正常的**(`Path.glob()` 在 macOS 和 Linux 返回序不同)

## 常见场景

| 场景 | 怎么做 |
|---|---|
| DDR 刚出了一篇,要发 | `/bpr` |
| 攒了三篇一起发 | `/bpr`(索引会一次扫全目录,三篇同时上线) |
| 改了某篇想重发 | 覆盖那个 `<stem>.html` 后 `/bpr` |
| 删了一篇,要更新 landing | 删文件后 `/bpr` |
| 只想看 landing 效果,先不发 | `/bpr index` |
| 怀疑线上不对 | `/bpr verify` |

## 命名分界(刻意的,别"顺手统一")

- **命令 / 插件 / 仓库 / marketplace** = `ddr`
- **产出侧全部保持 `bpr`** —— 域名 `bpr.ken.solar`、`build_index.py` 的 `BASE_URL`、
  已发布页的 `<title>` / `og:site_name` / 页脚品牌、`localStorage` 的 `bpr-sort` / `bpr-theme`

最后那两个 localStorage 键**尤其别动**:改了会**静默重置**线上站已有的主题和排序偏好,
没有任何报错。

**一句话:命令归 DDR,产出物归 BPR。本 skill 属于产出侧,所以叫 bpr。**

## 完整命令与详细排错

→ `references/deploy.md`
