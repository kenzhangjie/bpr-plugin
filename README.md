# BPR · Bilingual Podcast Reader

把英文 podcast、transcript、字幕、博客 essay、长文 article 一键转成**编辑设计风格的双语阅读 HTML**。中文素材自动切到「TL;DR + 非共识 + 书面正文 + 折叠逐字底档」模式。

为想"沉浸式读完一期英文播客 / 一篇 PG essay,但又想要中文对照"的人做的。

## Install

在 Claude Code 里:

```
/plugin marketplace add kenzhangjie/bpr-plugin
/plugin install ddr@bpr-marketplace
```

## Usage

```
/ddr <YouTube URL>
/ddr <博客 URL>
/ddr <粘贴的英文 transcript>
/ddr <上传的 SRT/VTT 字幕>
/ddr <本地 PDF 路径>                 ← 研报 / 白皮书 / 书籍章节
/ddr <小宇宙 / Bilibili URL>         ← 中文播客,走 ASR 转录
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
├── skills/ddr/
│   ├── SKILL.md                       ← 8 阶段主流程(只做路由,到站才读 reference)
│   ├── references/                    ← 按阶段一份
│   │   ├── ingest.md                  ← 1 URL 处理 / 抓取 / 发布日期
│   │   ├── prep-and-modes.md          ← 2 断句 / 说话人 / 中英模式判定
│   │   ├── clean.md                   ← 3 中文 ASR 后处理三步法
│   │   ├── render.md                  ← 6 版型 / 设计系统
│   │   ├── translate.md               ← 5 翻译四步法
│   │   ├── verify.md                  ← 7 输出前自检清单
│   │   ├── publish.md                 ← 8 产物约定 / 部署
│   │   └── lessons-learned.md         ← 历史踩坑总结(只增不改)
│   ├── scripts/
│   │   ├── fetch/                     ← yt-dlp / 小宇宙 / B站 / PDF / 元数据
│   │   ├── prep/clean_en.py           ← 英文源清洗 + 覆盖率闸
│   │   ├── lib/glossary_lib.py        ← glossary 单一实现(volc_asr.py 也用这份)
│   │   ├── enrich/                    ← 时间戳注入 / 正文图自托管
│   │   ├── verify/entity_coverage.py  ← 中文实体覆盖闸
│   │   └── publish/                   ← landing 重建 / 中文模式渲染
│   ├── templates/
│   │   └── base.html                  ← 双语 HTML 骨架
│   └── tests/                         ← pytest(152 例)
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
- `python3`(脚本全部标准库,无第三方依赖)
- 中文字体(Mac 自带 PingFang SC;Linux 渲染机需要单独装)

## Config

首次使用时,skill 会询问输出目录(`<output_dir>`),默认建议 `~/Documents/Transcript/`。

如果不需要默认值,直接在 `/ddr` 调用里指定路径即可。

## Tips

- **大文件分段**:超过 50K 字会询问要不要拆 part
- **速读模式**:`/ddr <url> 速读` → 折叠英文,默认只显中文
- **学习模式**:`/ddr <url> 学习` → 双语并排两列
- **正式模式**:`/ddr <url> 正式` → 去口语化("uh / um" 等省略)

## Examples

真实输出样例见 [examples/](./examples/) 目录(社区维护;首次使用想看效果可以从这里入手)。

## License

MIT — see [LICENSE](./LICENSE).

## Contributing

欢迎 PR。完整规则见 [CONTRIBUTING.md](./CONTRIBUTING.md):

- ✅ 改进翻译三步法的失败案例(往 `lessons-learned.md` 加 L# 条目)
- ✅ 优化 checklist / 加新触发词 / 新输入源支持
- ⚠️ 改 `templates/base.html` 视觉 / 改触发命令 — 慎重
- ❌ 往 `glossary.txt` 第 3 列加短错法(CJK <3 字 / 拉丁 <4 字)— 会误伤常用词,`--check-glossary` 会拦

发版历史见 [CHANGELOG.md](./CHANGELOG.md)。
