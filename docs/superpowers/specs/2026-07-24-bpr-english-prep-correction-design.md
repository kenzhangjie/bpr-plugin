# BPR · 英文 PREP 源清洗(专名纠错 + 说话人归属)设计

- **日期**:2026-07-24
- **状态**:草案(待 Ken 审阅)
- **实现仓库**:`/Users/ken/dev/bpr-plugin`(skill 1.6.2)
- **相关**:`references/prep-and-modes.md`、`references/ingest.md`、`references/clean.md`(中文 CLEAN,对照)、`references/translate.md`、`references/verify.md`

---

## 1. 问题

英文双语路(YouTube / 带 speaker 的字幕)没有源清洗。2026-07-24 Lenny × Andrew Ambrosino 那期实测暴露两个痛,全靠人肉顶:

1. **专名错词**:YT 自动字幕把 OpenAI 听成 "Opening Eye"、Codex→"Codeex"、ChatGPT→"chatd"、Ambrosino→"Ambercino"。只能渲染前**手写 regex**,用完即弃。
2. **说话人归属**:YT 字幕是扁平流,只有不可靠的 `>>`;谁主持谁嘉宾、哪些 `>>` 把一问一答挤一起,全靠手判 + 手拆(那期拆了 14 处)。

## 2. 决策:放进 PREP,不新开阶段,不碰 TRANSLATE

**不塞进 TRANSLATE 的 Review** —— 时机不对:

```
PREP → STRUCTURE(切章 + 出 TL;DR 英文金句) → TRANSLATE(Analyze→Translate→Review→Polish)
  ↑ 专名 + 说话人必须在这修好
                     ↑ 切章 / TL;DR 金句都要用"干净、分好人"的源
                                                ↑ 太晚:章已切、金句已出
```
- 说话人归属 + 拆 `>>` 必须在 STRUCTURE **之前**(要先有 turn 才切得了章)。
- TL;DR 英文金句在 STRUCTURE 出,专名不能等到 TRANSLATE 才修。
- TRANSLATE.Review 的职责是**校中文译文**(漏译/术语一致),不揽英文源纠错。**TRANSLATE 四步一字不改。**

**也不新开一个"英文 CLEAN 阶段"** —— 太重。中文 CLEAN 重(切窗 / 保真闸 / **书面化**),是因为要把口语书面化。英文**不书面化**(逐字交翻译),不需要那套机器。而 **PREP 本就负责"提取说话人 + auto-subs 重断句"**,英文纠错 + 归属是它的自然延伸。

> 结论:**强化 PREP 的英文子模式**。中文仍走 CLEAN;英文的源清洗归 PREP。

## 3. 目标 / 非目标

**目标**
- PREP 英文子模式自动完成:**专名纠错 + 说话人归属 + 拆合并 `>>`**。
- 用 YouTube `metadata.json.description` 当 ground truth(= 中文的 shownote 玩法)。
- 纠错资产跨期复用:**共用 `~/.config/volc/glossary.txt`** + 双语 `correct_table.json`。
- 失败优雅降级,不幻觉;脱离手写 regex。

**非目标**
- 不引入火山 ASR(已否决;源仍是 YT 字幕)。见 memory `bpr-english-no-volc-asr`。
- 不做书面化(英文逐字交 TRANSLATE)。
- 不动 TRANSLATE 四步、不动中文 CLEAN。
- 纯博客 / essay(无 speaker、curl 干净正文)不触发本流程。

## 4. 流程(PREP 英文子模式,轻量)

触发:PREP 判定 **CJK < 60%** 且输入为 **transcript 类**(有 `>>` / speaker 信号)。essay 跳过。

### Step 1 · Analyze-lite(主代理,全稿 1 次)
读 ground truth,产出小 brief(塞进后续子代理,保跨窗一致):
- 输入:`metadata.json` 的 **description**(嘉宾 "my guest is X"、主持 = uploader/channel、sponsor、产品/链接)+ **title** + **`glossary.txt`**(读专名,忽略 `|` 权重)。
- 产出:① 本期**专名表**(正确英文拼写:OpenAI / Codex / ChatGPT …)② **说话人身份**(host / guest → role 映射)③ 存疑词清单。

### Step 2 · 归属 + 纠错 pass(子代理,可按 ~25 turn 切窗)
主代理 **verbatim 持有原文**(抗压缩铁律)。子代理只做**源清洗 + 结构**,输出结构化 turn 列表 `[{speaker, sents:[...]}]`:
1. **专名纠错**:按 brief 把错听专名改成正确英文拼写。除专名 + 明显拼写外,**英文逐字保留**(含口语水词),不改写、不删句。拿不准标 `⟨?猜测⟩`,不硬编。
2. **说话人归属 + 拆合并块**:用 host/guest 身份判每段给谁;一个 `>>` 块混了问答就在语义拐点拆成多个 turn。

### Step 3 · 词覆盖硬闸(主代理,确定性)
返回的 en 词(剔除已知专名替换)concat vs 原文词流,**覆盖 < ~98% = 丢句** → 打回重做一次;仍不过标 `⟨?丢失⟩` 留人。把"英文 verbatim"从软约束变硬闸(对应 L6)。

### Step 4 · 确定性后处理
套用**双语 `correct_table.json`** 无歧义硬映射(补遗漏)。中文由 `volc_asr.py` 套用;**英文由本步套用**(英文不跑 volc_asr.py)。

### Step 5 · 专名飞轮
本期专名清单结束时 append 进**共用** `~/.config/volc/glossary.txt`(去重,`专名|权重` 默认权重)。跑越多越准。

### 降级(不幻觉)
- description 缺失/无用 → 专名靠 glossary + 上下文;说话人靠启发式(提问者 = host)。
- 说话人**真分不出** → 退 **essay 模式渲染**(不写 speaker/turn),保留章节级时间戳。不瞎猜(L1)。

## 5. 输出契约
PREP 英文子模式产出**扁平说话人 turn 列表**(章节未知,STRUCTURE 才切):
```json
[{ "speaker": "Lenny" | "Andrew" | "SpeakerN",
   "sents": ["verbatim corrected english sentence", "..."] }, ...]
```
- 无时间戳(RENDER 阶段 `add_timestamps.py` 反查 VTT 注入,不变)。
- STRUCTURE 消费它切章 + 出 TL;DR;TRANSLATE 消费英文句做四步法(**输入已是干净、分好人的英文**)。

## 6. 边界(谁干什么,防撞车)

| | PREP 英文子模式(新) | TRANSLATE.Review(不变) | 中文 CLEAN(不变) |
|---|---|---|---|
| 对象 | 英文**源** | 中文**译文** vs 英文 | 中文**源** |
| 干什么 | 专名拼对 + 谁说的 + 拆 turn | 漏译/误译/术语一致 | 纠错 + 书面化 |
| 抓的错 | "Opening Eye"→OpenAI;拆一问一答 | 中文漏了从句;agency 忽译忽留 | 同音错;口语→书面 |
| 书面化 | 否(逐字交翻译) | —— | 是 |

## 7. 改动清单

| 文件 | 改动 |
|---|---|
| `references/prep-and-modes.md` | 加"英文子模式源清洗"全节(本 spec §4–§5);essay 跳过说明 |
| `SKILL.md` | PREP 行注明英文子模式做专名纠错 + 说话人归属;流水线图不变(不新增阶段) |
| `scripts/`(新) | `prep_en.py` 或子代理编排:切窗 + 归属/纠错子代理 + 词覆盖闸 + correct_table 后处理 + glossary 回写 → 产出 §5 JSON |
| `~/.config/volc/correct_table.json` | 升双语:保留中文 mappings,加英文段;`_note` 注明英文路由 prep_en 套用 |
| `~/.config/volc/glossary.txt` | 共用(格式不变),英文专名 append |
| `references/verify.md` | 英文覆盖闸加:PREP 词覆盖 ≥98%;加英文纠错冒烟 fixture |
| `references/ingest.md` | YouTube 段注明产出交 PREP 英文子模式(description 作 ground truth) |
| `tests/` | 英文 ASR 纠错回归 fixture(Opening Eye→OpenAI 等全修对)+ 合并 `>>` 拆分样例 |

## 8. 验证(完成判据)
1. **纠错回归**:fixture 里英文错专名(Opening Eye / Codeex / chatd / Ambercino / Versell …)全修对。
2. **说话人**:合并 `>>` 样例被正确拆成不同 speaker;host/guest 映射对。
3. **保真**:PREP 输出词覆盖 ≥98%(不丢句);抽查无 confidently-wrong 硬编(存疑走 `⟨?⟩`)。
4. **端到端**:重跑 Lenny × Andrew 那期,不手写任何 regex,质量 ≥ 本次;新专名进 glossary.txt。
5. **降级**:构造无 description 输入,退启发式/essay 而非报错/幻觉。

## 9. 风险
- **说话人判错**:短插话 / 无 description 时易错 → 词覆盖闸只保不丢句(不保 speaker 对);缓解靠明确 host/guest + 启发式 + 分不出就退 essay。
- **专名过度纠正**:把对的普通词"纠"错 → brief 只列确证专名 + `⟨?⟩` 留疑 + correct_table 只放无歧义项。
- **glossary 噪声累积**:飞轮自动 append → 沿用中文做法,Ken 偶尔扫一眼去噪。
