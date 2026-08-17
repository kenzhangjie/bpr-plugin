# PUBLISH · 产物约定 / landing index / 部署

> 阶段 8 · PUBLISH 专用。重建 landing index → 部署 bpr.ken.solar(proxy 直连)。

---

## 输出路径

所有 reader 产物落到:

```
~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript/
```

这个目录 **= bpr.ken.solar 的部署根**。

## 产物约定

```
Transcript/(= bpr.ken.solar 部署根)固定结构:
  <stem>.html            阅读器
  images/<stem>/         essay 正文自托管图
  index.html             landing(build_index 重建)
  (<stem>-poster.png 已废:海报分支 1.7.3 移除,0 篇用过)
部署:cd 到 Transcript 目录 → brctl download . → 用 proxy 直连跑 vercel --prod --yes
(proxy 直连指:env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy -u NODE_USE_ENV_PROXY vercel --prod --yes;长连接被 GFW/undici 掐会失败)
```

## landing index 重建

新 reader 写完后,用 `scripts/publish/build_index.py` 重建 landing `index.html`(扫描 Transcript 目录下所有 `<stem>.html`,生成卡片列表)。

> ⚠️ **INDEX.html 大小写坑(L5)**:Transcript 目录若有遗留的大写 `INDEX.html`,macOS 大小写不敏感 FS 会让 `open("index.html","w")` 匹配到它、只改内容不改名,而 Vercel 路由大小写敏感,只认小写 `index.html` 当 root → `/` 返回 404。
> 跑 build_index 之前先清。**必须比对真实 dirent,不能用 `[ -f INDEX.html ]`** ——
> macOS 大小写不敏感 FS 上,只有小写 `index.html` 时那个判断也为真,会把 landing 删掉:
> ```bash
> python3 - <<'PY'
> import os
> T = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript")
> names = os.listdir(T)                      # 真实 dirent,保留大小写
> print("INDEX.html:", "INDEX.html" in names, " index.html:", "index.html" in names)
> if "INDEX.html" in names:                  # 只有真的存在大写才删
>     os.remove(os.path.join(T, "INDEX.html"))
>     print("已删除大写 INDEX.html")
> PY
> ```
> 详见 `lessons-learned.md` L5。

## 部署 bpr.ken.solar

```bash
cd "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Claude/Transcript"
brctl download .   # 把 iCloud 占位符实体化,避免部署上传空文件
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy \
    -u HTTPS_PROXY -u https_proxy -u NODE_USE_ENV_PROXY \
    vercel --prod --yes
```

- **proxy 直连**:长连接被 GFW / undici 掐会失败,必须 `env -u ...` 清掉所有代理变量走系统 TUN 直连。
- 部署后 **curl 测 root**,不是 200 立刻查磁盘文件名(见 L5):
  ```bash
  curl -s -o /dev/null -w "HTTP %{http_code}\n" https://bpr.ken.solar/
  ```
