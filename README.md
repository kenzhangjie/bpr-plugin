# BPR · Bilingual Podcast Reader

把英文 podcast、transcript、字幕、博客 essay、长文 article 一键转成**编辑设计风格的双语阅读 HTML**(可选生成可分享的长图海报)。

为想"沉浸式读完一期英文播客 / 一篇 PG essay,但又想要中文对照"的人做的。

## Install

在 Claude Code 里:

```
/plugin marketplace add kenzhangjie/bpr-plugin
/plugin install bpr@bpr-marketplace
```

## Usage

```
/bpr <YouTube URL>
/bpr <博客 URL>
/bpr <粘贴的英文 transcript>
/bpr <上传的 SRT/VTT 字幕> 海报      ← 加 "海报" 修饰词额外出张分享长图
```

## What it does

输入(任一):
- YouTube / Bilibili / 任意带字幕视频 URL → yt-dlp 自动拉字幕
- 博客 URL(Paul Graham / Naval / Anthropic Blog 等)
- 粘贴的 SRT / VTT 字幕
- 粘贴的纯文本 transcript
- 上传的字幕文件

输出:
- 单文件 HTML(无外链依赖,可直接发邮件/上传/归档)
- 包含 Hero / TL;DR / 章节正文(英中双语对照) / 目录 / 深色模式
- 文件名严格规范化(`{date}_{source}_{author}_{topic}.html`)
- 可选海报模式:再额外生成 1080 宽分享长图 PNG

## Why

LLM 默认翻译有几个老问题:

- **直译腔**:中文读起来像翻译软件的输出
- **漏内容**:长文中后段经常被偷工
- **风格漂移**:同一篇里不同段落语气不一致
- **造引文**:URL / 头像 / quote 喜欢编

BPR 用三步法(Translate → Reflect → Improve)+ 模板锁定 + 严格 checklist 解决这四个问题。每章每段都跑三步法,不偷懒;**金句必须能在原文 grep 到**;术语保留原文(`PMF / agent / RAG / IC` 不硬翻);文件结构、CSS、DOM 全部从模板 copy,不重新发明。

## What's inside

```
bpr-plugin/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── .github/
│   ├── workflows/validate.yml         ← CI: JSON / frontmatter / 引用完整性校验
│   ├── ISSUE_TEMPLATE/{bug,feature}.yml
│   └── pull_request_template.md
├── skills/bpr/
│   ├── SKILL.md                       ← 主流程
│   ├── references/
│   │   ├── rules.md                   ← URL 处理 / 双语对照规范
│   │   ├── translation-prompt.md      ← 三步法完整 prompt
│   │   ├── design-system.md           ← 视觉系统说明
│   │   ├── checklist.md               ← 输出前自检
│   │   ├── lessons-learned.md         ← 历史踩坑总结
│   │   ├── poster-template.html       ← 海报模式模板(无水印)
│   │   └── poster-rules.md            ← 海报模式工作流
│   ├── scripts/
│   │   ├── fetch_youtube.sh           ← yt-dlp 字幕抓取
│   │   ├── clean_vtt.py               ← VTT 清洗去重
│   │   └── crop_and_share.py          ← 海报裁剪 + 降采样
│   └── templates/
│       └── base.html                  ← 双语 HTML 骨架
├── examples/                          ← 真实输出样例(社区贡献)
├── tools/release.sh                   ← 一键发版脚本(maintainer 用)
├── README.md
├── CHANGELOG.md                       ← 版本历史
├── CONTRIBUTING.md                    ← 贡献指南
└── LICENSE
```

## Requirements

- Claude Code(任意版本支持 plugin)
- `yt-dlp`(YouTube/Bilibili 输入需要):`brew install yt-dlp` 或 `uv tool install yt-dlp`
- `python3 + Pillow`(海报模式需要):`pip3 install Pillow`
- Google Chrome(海报模式需要,默认路径 `/Applications/Google Chrome.app/`)
- 中文字体(Mac 自带 PingFang SC;Linux 渲染机需要单独装)

## Config

首次使用时,skill 会询问输出目录(`<output_dir>`),默认建议 `~/Documents/Transcript/`。

如果不需要默认值,直接在 `/bpr` 调用里指定路径即可。

## Tips

- **大文件分段**:超过 50K 字会询问要不要拆 part
- **速读模式**:`/bpr <url> 速读` → 折叠英文,默认只显中文
- **学习模式**:`/bpr <url> 学习` → 双语并排两列
- **正式模式**:`/bpr <url> 正式` → 去口语化("uh / um" 等省略)

## Examples

真实输出样例见 [examples/](./examples/) 目录(社区维护;首次使用想看效果可以从这里入手)。

## License

MIT — see [LICENSE](./LICENSE).

## Contributing

欢迎 PR。完整规则见 [CONTRIBUTING.md](./CONTRIBUTING.md):

- ✅ 改进翻译三步法的失败案例(往 `lessons-learned.md` 加 L# 条目)
- ✅ 优化 checklist / 加新触发词 / 新输入源支持
- ⚠️ 改 `templates/base.html` 视觉 / 改触发命令 — 慎重
- ❌ 给 `poster-template.html` 默认版加水印 — 硬规则禁止

发版历史见 [CHANGELOG.md](./CHANGELOG.md)。
