# ASR 后处理三步法 · BPR CLEAN 阶段设计

- **日期**:2026-07-22
- **状态**:已通过 brainstorming,待 writing-plans
- **作者**:Ken + Claude Code
- **影响范围**:bpr 插件(中文模式),`~/.config/volc/`(ASR 偏置反哺)

---

## 1. 问题 / 动机

火山引擎大模型录音识别(`volc.bigasr.auc`)提取的中文播客 transcript 有两类硬伤,单靠现有 `correct_table.json` 字符串替换治不了:

1. **中英混录同音/近音错词**(实测样本,张小珺×Freda 那期):
   - `skating` → 应 `scaling`(scaling law)
   - `constrain 吧` → 应 `constraint`
   - `unprobability` → 应 `unpredictability`
   - `阿帕比` → 大概率 `a paper`(中低置信)
   - `克洛蔻` → 应 `Claude`;`我是小俊` → 应 `小珺`(主持人自己名字)
   - 这些**不是固定错拼**,是"这句话的上下文里才错",字符串精确替换抓不住,**只有带领域上下文的 LLM 能修**。
2. **可读性差**:正文是逐字口语流,口水词密度极高(单期 `就是`×450、`这个`×498、`然后`×252),读 32K 字非常累。

现有 `correct_table.json`(23 行精确映射)只能事后补已知错拼,且同一词堆多种错法(`Hicksfield/Hixfield/Hexfield`)本身就是症状。

## 2. 目标 / 非目标

**目标**
- 在 BPR 中文模式流水线里新增一个 **CLEAN 阶段**,用"analyze / review / polish"三步(翻译四步法去掉 translate)把火山原始 transcript 变成**书面化、纠错后、可读**的正文。
- 保留**逐字口语底档**做对照(可折叠),LLM 重写出错时可回溯。
- 顺手建立**反哺闭环**:每期扒出的专名回写 `~/.config/volc/glossary.txt`,下期 ASR 识别阶段就少错。

**非目标**
- 不改英文双语模式(它走翻译四步法,不重复)。
- 不做实时/流式(仍是录音文件离线转写后处理)。
- 不追求 100% 无错(不可判词标注存疑,交人/音频定夺)。

## 3. 架构总览

```
INGEST → PREP → 【CLEAN ← 新增】 → STRUCTURE → RENDER → VERIFY → PUBLISH
                    │
   火山原始 transcript.txt(逐字底档,只读,永不改)
                    ↓
   Analyze(主代理,全稿 1 次) → 术语表 + 说话人/语气 + 存疑词清单
                    ↓
   按 ~25 turn 切窗 → 子代理 Review+Polish(独立 context) → 书面中文
                    ↓
   RENDER:书面正文为阅读面;原始逐字按章塞进可折叠 <details> 留档
```

- **仅中文模式触发**(CJK ≥ 60%,沿用 `prep-and-modes.md` 现有判定)。
- **`enable_ddc` 保持关闭**:底档要真逐字;口水清洗交给 Polish,DDC 冗余且会污染底档。

## 4. 三步分工

复用 `references/translate.md` 的子代理机制。主代理 verbatim 持有原始窗口,子代理只回书面中文(抗压缩铁律一致)。

| 步 | 谁跑 | 干什么 | 铁律 |
|---|---|---|---|
| **Analyze** | 主代理,全稿 1 次 | ① 领域术语表(专名/高频英文术语,哪些保留英文)② 说话人 + 语气 ③ **存疑词清单**(扫出可疑中英混词) | 产物塞进每个子代理 prompt,保跨窗一致 |
| **Review** | 子代理,按窗 | **纠错**:同音近音词 / 专名 / 断句,用上下文 + 术语表修 | **信**:忠于"说了什么";不可判的**标注 `⟨?猜测⟩` 绝不硬改** |
| **Polish** | 同一子代理接着做 | **书面重写**:去口水、合并重组成通顺段落 | **达/雅**:只改"怎么说";**每个论点/数字/专名/因果必须保下来**,不许为通顺吞信息 |

- **默认**:每窗 1 个子代理,Review→Polish 连做(比翻译省一个 Translate 轮)。
- **极致版**(可选,高密度章/非共识金句):Review、Polish 各一次独立调用(照搬 `translate.md` 极致版)。

## 5. 错词四分类(决定"改还是标")

| 类 | 例 | 处理 |
|---|---|---|
| **1 · 同音/近音** | skating→scaling、constrain→constraint、unprobability→unpredictability | 上下文直接改 |
| **2 · 专名** | 克洛蔻→Claude、阿帕比→a paper | 术语表比对后改 |
| **3 · 断句/标点** | 两句黏成一句 | 重新断句 |
| **4 · 真不可判** | 连人都拿不准的 | **标注 `⟨?a paper⟩` 不硬编**;渲染成可点/可 grep 的 `<mark class="asr-uncertain">`,回音频定夺。confidently wrong 比留错更坏 |

## 6. 切窗策略

- CLEAN 在 STRUCTURE(语义切章)**之前**跑,所以不能按章切;按**固定 turn 窗口(~25 条)** 切,避免脏文本进 STRUCTURE(否则章节标题/TL;DR 会带错词)。
- 窗口边界不切碎一个说话人的连续发言时,允许 ±几条弹性对齐到 turn 边界。
- 每窗子代理拿到:该窗逐字原文 + 全局 Analyze brief(术语表 + 存疑清单 + 语气)。

## 7. 底档保留与渲染

- 底档来源:CLEAN 之前的火山原始 `transcript.txt`(不动)。
- RENDER 中文模式:书面正文为默认阅读面;每章末尾 `<details><summary>▸ 展开逐字原稿</summary>…</details>` 放该章原始逐字 turn(带时间戳)。
- `templates/base.html` 加 `<details class="raw-transcript">` 相关 CSS(默认收起、展开为逐字 turn 样式)。

## 8. 反哺闭环(解决"下期更好")

- Analyze 产出的专名清单 → 追加进 `~/.config/volc/glossary.txt`(Ken 过目后合入,半自动)。
- 下期 `volc_asr.py --meta` 拼 context 时自动带上 → ASR 识别阶段就偏向正确专名。**错一次,以后不再错。**

## 9. VERIFY 阶段改造

- **作废**旧的"渲染句数 ÷ 源稿 ≥85%"硬闸(书面重写本就合并句子,句数比失效)。
- **改为信息覆盖闸**:底档里出现的数字 / 专名 / 论点实体,书面版必须都在(实体级覆盖,不是句数级)。
- **回归冒烟样本**:这四个已知错必须在输出里被修对 —— `skating→scaling`、`克洛蔻→Claude`、`constrain→constraint`、`unprobability→unpredictability`。
- **零幻觉检查**:Class 4 必须是"标注"不是"发明";抽查 `<mark class="asr-uncertain">` 处确为存疑而非杜撰。

## 10. 成本

32K 字 / ~13 窗 × 1 子代理 ≈ 一次翻译的一半 token(省了 Translate 轮)。比现在纯逐字渲染贵,换来可读 + 纠错。想省:只对关键章升级独立 Review。

## 11. 要改的文件(全部在**源仓库** `/Users/ken/dev/bpr-plugin`,不是 cache)

> ⚠️ 之前的 `--meta`/context 偏置改动只落到了 cache,源仓库 `ingest.md:230` 仍是旧命令。本次一并在源仓库补齐,改完 reinstall 覆盖 cache。

- `skills/bpr/SKILL.md` — 流水线表加 CLEAN 阶段(7→8 阶段)。
- `skills/bpr/references/prep-and-modes.md` — 中文模式加 CLEAN 说明;修订 2026-07-11「逐字全量」铁律为「书面正文 + 逐字底档可折叠」。
- `skills/bpr/references/clean.md` — **新建**,CLEAN 阶段详细规程(三步、切窗、子代理 prompt 模板、四分类)。
- `skills/bpr/references/ingest.md` — 补齐 `--meta` + context/glossary 说明(把 cache 的改动同步进源)。
- `skills/bpr/references/render.md` — 中文模式渲染书面正文 + `<details>` 底档。
- `skills/bpr/references/verify.md` — 覆盖闸从句数级改实体级 + 回归样本。
- `skills/bpr/templates/base.html` — `<details class="raw-transcript">` CSS。
- `~/.config/volc/volc_asr.py` — 确认 `enable_ddc` 保持 False(已是);无需改。
- 改完:`git commit` 源仓库 → reinstall 插件覆盖 cache。

## 12. 成功标准

1. 中文模式跑一期真实小宇宙,产出书面正文可读(口水词基本清空)。
2. 四个回归错词全部修对。
3. 逐字底档在页面可折叠展开,内容 == 火山原始 transcript。
4. 信息覆盖闸通过(数字/专名/论点无丢失)。
5. Class 4 存疑词以 `<mark>` 标注,无杜撰。

## 13. 主要风险

- **Polish 把"改写"做成"概括"**(丢信息)—— 防线:子代理铁律"保全每个论点" + 实体覆盖闸 + 保留底档对照。**最需盯的点。**
- **切窗跨断上下文**:窗口边界处代词/指代丢失 → 靠全局 Analyze brief + 边界弹性缓解。
- **cache/源漂移**:改源后必须 reinstall,否则跑的还是旧 cache。
