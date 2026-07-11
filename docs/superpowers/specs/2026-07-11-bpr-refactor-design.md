# BPR 插件架构重构 · 设计 spec

- **日期**: 2026-07-11
- **类型**: 纯重构(behavior-preserving refactor)——BPR 生成的 HTML / 海报 / 流程能力**完全不变**,只理干净内部结构
- **仓库**: kenzhangjie/bpr-plugin,重构后发布 **v1.5.0**

## 1. 背景与问题

BPR 是个人工具(`/bpr`),把 podcast/字幕/访谈/博客长文转成编辑设计风的双语/中文阅读 HTML。功能强但结构是长年累加出来的,四层"乱"(用户确认全中):

1. **版本/分发漂移**:本地手改的 `cache/1.4.1` vs repo 发布的 `1.4.3` vs 孤儿 `cache/1.4.3` 三方漂移;没人是 source of truth;升级会丢改动。
2. **SKILL.md 步骤臃肿**:11 步 + 2.5/6.2/6.5 半步 + 满屏 🆕,补丁摞补丁。
3. **文件/职责混杂**:`rules.md` 669 行大杂烩;9 个脚本;抓取/翻译/渲染/图/海报/部署全塞一个 skill。
4. **产物散乱**:`Transcript/` 下 html/images/index/海报/部署产物缺约定。

### ⚠️ 基线真身(实现时必知)
**当前功能最全的是被手改过的 `cache/1.4.1`**(含四步翻译法、`extract_images.py`、覆盖率硬闸、`design-system.md`),这些**从未 push 回 repo**。repo 的 `1.4.3` 反而**退化**(无四步法、无 extract_images)。
→ 重构**必须以 cache/1.4.1 为内容基线**,把它的改进对账合并进 repo,**绝不在退化的 repo 1.4.3 上重构**。

## 2. 目标与非目标

**目标**:一次 behavior-preserving 重构,命中上述四层乱。

**非目标(YAGNI)**:
- 不改 BPR 行为/输出(唯一例外见硬约束 2 的"去口语词");
- 不砍功能;
- 不拆多子 skill(各步强耦合,过度设计);
- 不抽 CLI(核心步骤是 LLM 驱动、无法脚本化)。

## 3. 硬约束(重构后必须成立)

### 硬约束 1 · 翻译四步
英文源正文翻译必须走完整四步 **Analyze → Translate → Review → Polish**,一步不省(每篇先 Analyze 定术语表;每章 Translate → 独立 Review → 独立 Polish)。

### 硬约束 2 · 逐字全覆盖 + 中文去口语词(**含一处有意的行为改动**)
- **英文行**:逐字逐句保留原话(含口语水词),**句级全覆盖不压缩**(覆盖率硬闸:渲染句数 ÷ 源稿 < ~85% 判不合格,回 TRANSLATE 补)。
- **中文行**:Polish 步**删掉无意义口语水词**(呃/嗯/you know/I mean/the thing is 之类),让中文读起来干净、书面化。
- **边界**:只去无意义水词,**不去有语义的迟疑/强调**(刻意停顿、honestly 这类带态度的词)。
- ⚠️ **这推翻旧规则"口语感保留 uh/um→呃/嗯"**:新规则 = EN 逐字保留(可学口语)+ ZH 润色去水词(好读),**不对称处理**。这是本次唯一有意的行为改动,其余纯重构。
- 例外:`TL;DR·速读` 和 `Contrarian Takes` 两块本就是浓缩,不受逐字约束。

## 4. 目标架构(方案 A:单 skill 内部重整)

### 4.1 SKILL.md → 7 个干净阶段(替代 11 步 + 半步,清除所有 🆕/半步编号)

| 阶段 | 吸收原步骤 | 内容 |
|---|---|---|
| **1 INGEST** | 0,1 | 解析输入(URL→fetch yt/xyz/bili/blog;或粘贴 text/SRT)、提发布日期/标题/作者、判类型 |
| **2 PREP** | 2,2.5 | 清洗断句/说话人/VTT 重建;CJK≥60% 判定 → 选模式(英双语 / 中文浓缩) |
| **3 STRUCTURE** | 3,4 | 章节切分 + TL;DR(+ 中文模式 Contrarian Takes) |
| **4 TRANSLATE** | 5 | 仅英双语;**四步法(硬约束1)+ 逐字 + Polish 去口语词(硬约束2)** |
| **5 RENDER** | 6,6.2,6.5 | base.html 建页;`enrich` 子动作 = 正文图自托管(essay)+ 时间戳(podcast) |
| **6 VERIFY** | 7 | 覆盖率硬闸 + checklist(不止查 en=zh 配对) |
| **7 PUBLISH** | 9,10 | 重建 index + 部署 bpr.ken.solar(proxy 直连) |
| *(海报)* | 8 | `/bpr all` 触发的可选分支,不进主线编号 |

### 4.2 references/ 按阶段拆(散掉 669 行 rules.md)
`ingest.md` · `prep-and-modes.md`(断句 + 中文模式规范)· `translate.md`(四步法 + 逐字 + 去口语词=两条硬约束落这)· `render.md`(三版型 + inline link + 图自托管 + design-system 并入)· `verify.md`(checklist + 覆盖闸)· `publish.md`(index + 部署)· `poster.md` · `lessons-learned.md`(保留作"为什么"附录,逐条注明已固化到哪个阶段文档)

### 4.3 scripts/ 按职责分组
`fetch/`(fetch_youtube.sh / fetch_xiaoyuzhou.sh / fetch_bilibili.sh / extract_metadata.py / clean_vtt.py)· `enrich/`(add_timestamps.py / extract_images.py)· `publish/`(build_index.py)· `poster/`(crop_and_share.py)· `templates/`(base.html / poster-template.html 不动内容)
→ SKILL.md 与各 reference 里的脚本路径同步更新。

### 4.4 版本 / source-of-truth 流程(治漂移)
1. **对账合并**:把 cache/1.4.1 的改进(四步法、extract_images、覆盖闸、design-system…)+ 本次重构,一起进 repo,发布 **v1.5.0**;清孤儿 cache/1.4.3。
2. **铁律**:此后**只在 `~/dev/bpr-plugin` 改** → bump `plugin.json` 版本 + CHANGELOG → commit/push → `/plugin` 更新 → `installed_plugins.json` 重指新版本。**绝不手改 cache**(手改 = 制造下一个漂移)。

### 4.5 产物结构(治散乱)
`Transcript/`(= bpr.ken.solar 部署根)固定约定,写进 `publish.md`:
```
Transcript/
  <stem>.html            # 阅读器
  <stem>-poster.png      # 海报(/bpr all 时)
  images/<stem>/         # essay 正文自托管图
  index.html             # landing(build_index 重建)
```

## 5. 实现阶段(细节由 writing-plans 展开)
1. 对账:diff cache/1.4.1 ↔ repo,把 1.4.1 独有改进搬进 clone(四步法/extract_images/design-system/覆盖闸)。
2. 重构 SKILL.md → 7 阶段。
3. 拆 references(rules.md → 按阶段的 7 个文件),两条硬约束写进 translate.md。
4. scripts 分组 + 全局路径更新。
5. 写 publish.md 产物约定。
6. bump v1.5.0 + CHANGELOG + push;`/plugin` 更新;repoint pin;删孤儿。
7. 验证:跑一篇英文 essay + 一篇中文 + 一个 podcast,确认 HTML 与旧版一致、四步法与去口语词生效、覆盖闸通过。

## 6. 成功标准
- SKILL.md 无半步编号、无 🆕,7 阶段线性可读。
- `rules.md` 消失,内容按阶段落到 7 个 reference。
- 脚本按 fetch/enrich/publish/poster 分组,所有引用路径可用。
- 两条硬约束在 translate.md 明文化并在实测中生效。
- repo v1.5.0 = 唯一 source of truth;cache 与 repo 不再漂移;pin 指 1.5.0。
- 抽样重跑:输出与重构前行为一致(除 ZH 去口语词这一有意改动)。
