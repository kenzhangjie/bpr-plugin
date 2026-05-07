# Changelog

All notable changes to this plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this plugin adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/kenzhangjie/bpr-plugin/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/kenzhangjie/bpr-plugin/releases/tag/v1.0.0
