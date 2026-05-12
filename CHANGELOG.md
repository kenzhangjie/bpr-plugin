# Changelog

All notable changes to this plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this plugin adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-05-13

### Added
- **`scripts/fetch_xiaoyuzhou.sh`** — 小宇宙(xiaoyuzhoufm.com)episode 抓取脚本。
  curl 拿 og:audio meta → 下载 mp3/m4a → 写 metadata.json(title / podcast /
  publish_date / audio_url)。**不内置转录**——由调用方走飞书妙记
  (lark-minutes skill: drive +upload → minutes +upload → vc +notes)。
- **`scripts/fetch_bilibili.sh`** — Bilibili 抓取脚本。yt-dlp 包装,先尝试
  uploaded subs(zh-CN / zh-Hans / zh / ai-zh / en)→ 没字幕则下载
  bestaudio[m4a] 给妙记转录。默认带 `--cookies-from-browser chrome` 应对
  会员/私人视频。
- **中文模式 (Chinese-Only Mode)** — CJK 字符 ≥ 60% 自动判定为中文素材,
  **跳过翻译三步法**,改走 TL;DR + 🔥 非共识 takes + 章节回顾 的浓缩结构。
  - 新 CSS:`.contrarian` / `.contrarian-quote` / `.contrarian-why` /
    `.ch-summary` / `.ch-pull` / `body[data-mode="zh-only"]` 等
  - 完整规范见 `references/rules.md` "中文模式 (Chinese-Only Mode)" section
  - 非共识 section 是中文模式的灵魂——做不好就是简陋摘要器,
    严格按 rules 里的写作原则执行

### Changed
- **SKILL.md 核心步骤表** — 新增 step 2.5 "语言检测",在预处理之后、章节切分
  之前判定语言;中文素材绕开 step 5 翻译。
- **`references/rules.md` URL 分支表** — 加 xiaoyuzhou.fm + bilibili.com 两行,
  新增"小宇宙 / Bilibili → 飞书妙记 一站式流程" section 详细列出 lark-cli
  drive +upload → minutes +upload → vc +notes 的完整 pipeline。
- **`templates/base.html` 底部说明区** — 加 CHINESE-ONLY MODE 模板示例
  (TL;DR + contrarian + ch-summary 怎么写)。

### Notes
- 中文模式判定**完全自动**,不接受用户修饰词覆盖——保持判定单一来源。
- 飞书妙记转录依赖 lark-cli + 个人空间额度。**首次使用**前需
  `lark-cli auth login`(详见 lark-shared skill)。

## [1.3.0] - 2026-05-11

### Removed
- Optional `/private/` link in index meta-bar(v1.2.0 加的功能)。
  原本的意图是 "让你给私有内容留个入口",但实际使用中发现:
  既然有内容,通常会单独绑子域名(`private.example.com`)再 rewrite,
  在公开主站 surface 一个 `/private/` 链接反而泄露了私域存在。
  把这逻辑彻底移除,private 内容由用户自己决定怎么链。

## [1.2.0] - 2026-05-11

### Added
- `scripts/build_index.py` major upgrade (synced from production-vendored version,
  37 KB ↑ from 12 KB):
  - `infer_tags()` — auto-detect format / topic tags from h1 + zh + eyebrow content
  - Tag filter UI (`tag-chip` buttons, JS filter, count badges)
  - Separate `posters.html` page — visual gallery for entries with `-poster.png`
  - Image lightbox modal for poster preview
  - OpenGraph meta tags (`og:title` / `og:image` / `og:url`) for social sharing
  - "Latest card" URL detection — surfaces newest poster as OG image
  - Top-nav link to posters page from index
- Optional `private/` link in index meta-bar — renders only when
  `~/Documents/Transcript/private/` exists locally. Lets you surface a
  password-protected section (e.g. staticrypt-encrypted page) without forcing
  other users to have one.

### Changed
- `collect_entries()` now skips both `index.html` and `posters.html`
- Build output now includes both `index.html` and `posters.html` in one run

## [1.1.0] - 2026-05-09

### Added
- `scripts/build_index.py` — 扫 Transcript 目录重建 landing `index.html`
- `scripts/extract_metadata.py` — 从博客 URL 抓发布日期 + source slug(7 种策略)
- SKILL.md step 0:发布日期提取要求(博客调 `extract_metadata.py`,YouTube 用 metadata.json)
- SKILL.md step 9:每次跑完重建 landing index
- SKILL.md step 10:每次跑完 vercel 部署到 bpr.ken.solar

### Changed
- 海报触发从修饰词 (`海报` / `分享版` / `poster`) 改为子命令前缀 `/bpr all <内容>`
- `templates/poster-template.html` 从 `references/` 移到 `templates/`(对齐 base.html 的位置)
- 文件名规则强化:日期 = 内容发布日期(必跑 extract_metadata.py),拿不到必须问用户,不再静默用今天

### Removed
- 修饰词 `海报` / `分享版` / `poster` 的支持(被 `/bpr all` 取代)

## [1.0.0] - 2026-05-07

### Added
- Initial release
- Plugin scaffold (`.claude-plugin/plugin.json` + `marketplace.json`)
- Skill `bpr` — 双语阅读器,覆盖 podcast / essay / 字幕 / 长文 四种输入
  - `SKILL.md` 主流程(0-7 步:URL 处理 → 类型识别 → 预处理 → 章节切分 → TL;DR → 三步法翻译 → HTML 渲染 → 自检)
  - `references/rules.md` — URL 输入处理 / 双语对照 / inline link 规范
  - `references/translation-prompt.md` — Translate → Reflect → Improve 三步法完整 prompt
  - `references/design-system.md` — 编辑设计风格视觉系统说明
  - `references/checklist.md` — 输出前自检清单
  - `references/lessons-learned.md` — 历史踩坑总结(L1 主持人识别 / L2 桌面布局 / L3 分块写入)
  - `references/poster-template.html` — 海报模式模板(无水印,1080 宽深色)
  - `references/poster-rules.md` — 海报模式工作流(9-section 框架 + Chrome 渲染 + crop)
- Scripts
  - `scripts/fetch_youtube.sh` — yt-dlp 字幕抓取
  - `scripts/clean_vtt.py` — VTT 去时间戳 / 去重清洗
  - `scripts/crop_and_share.py` — 海报自动裁剪 + 降采样(hidpi + share 双输出)
- `templates/base.html` — 双语 HTML 骨架(深色模式、目录、章节锚点)
- 修饰词支持:`只英文` / `深色` / `简洁` / `正式` / `速读` / `学习` / `带批注` / `海报`
- 文件名四种 pattern:single-host podcast / multi-host podcast / single-author essay / multi-author publication
- MIT license

[Unreleased]: https://github.com/kenzhangjie/bpr-plugin/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.3.0
[1.2.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.2.0
[1.1.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.1.0
[1.0.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.0.0
