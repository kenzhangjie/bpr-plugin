# ASR 源头优化 Round 2 · 火山 2.0(裸跑)+ shownote 喂 CLEAN

- **日期**:2026-07-23(spike 后按实测改版)
- **状态**:已通过 brainstorming + spike 实测校正,执行中
- **影响范围**:`~/.config/volc/volc_asr.py`(非版本控制)、`bpr-plugin/skills/bpr/scripts/fetch/fetch_xiaoyuzhou.sh`、`skills/bpr/references/clean.md`、`ingest.md`、`~/.config/volc/glossary.txt`
- **前置**:Round 1(CLEAN 阶段)已上线(v1.6.0)。

---

## 0. Spike 实测结论(推翻了初版设计,记录在案)

拿真 URL(Freda 投资札记第2集,1.5h)实测火山 2.0(`volc.seedasr.auc`):

1. **2.0 不吃 `corpus.context`**:传 context(2429 或 500 字)必在 ~180s 报 `55000001 OperatorWrapper 内部错误`;去掉 context 立即成功(842 句)。→ **ASR 层不能再做 context 偏置**。
2. **2.0 裸跑基础更强但非完美**:`Anthropic/OpenAI/CoWork/Snowflake/Robinhood/Cursor/scaling` 零偏置全对;仍错 `Aultimate Capital`(应 Altimeter)、1 处 `skating`、1 处 `克洛`、`小俊`(应小珺)。
3. **word 级 `confidence` 字段全为 0**(26744 词) → **置信度驱动 flagging 不可行**,放弃。
4. schema 兼容:`utterances[].additions.speaker` + `words[]`(带词级时间戳)在 → `to_transcript` 无需改。

**结论**:shownote 的价值不在 ASR 偏置,而在**喂给下游 CLEAN LLM 做推理纠错**(LLM 能"读 shownote 里的 Altimeter Capital → 改对 Aultimate")。ASR 层改用 **2.0 裸跑**吃其更强基础。

## 1. 目标 / 非目标

**目标**
- 火山 ASR 迁到 **2.0(`volc.seedasr.auc`),裸跑不传 context**;env 可回退 1.0。
- 抓完整 shownote,作为 **CLEAN 阶段的纠错参考**(不是 ASR context)。
- CLEAN 的 Analyze/Review 消费 shownote + glossary,定向纠专名。

**非目标(实测后砍掉)**
- ~~ASR `corpus.context` 偏置~~:2.0 直接崩;biasing 移到 CLEAN LLM。
- ~~置信度驱动 flagging~~:confidence 全 0,不可行。
- ~~控制台热词表~~、~~英文独立模型~~:同初版(单轨、YAGNI)。

## 2. 架构 / 数据流

```
小宇宙 URL → fetch_xiaoyuzhou.sh
   ├─ audio.m4a
   └─ metadata.json { title, podcast, shownote(完整), … }
                    ↓
volc_asr.py  (RESOURCE_ID=$VOLC_ASR_RESOURCE, 默认 volc.seedasr.auc=2.0)
   请求体不含 corpus/context  →  transcript.txt(2.0 裸跑,基础强)
                    ↓
CLEAN 阶段(Round 1)
   Analyze 读入 shownote + glossary.txt 作纠错参考
   Review 用它把残留专名纠对(Aultimate→Altimeter、小俊→小珺、skating→scaling…)
                    ↓
   书面正文 + 可折叠逐字底档(不变)
```

## 3. 组件

### 3.1 volc_asr.py(2.0 裸跑)
- `RESOURCE_ID = os.environ.get("VOLC_ASR_RESOURCE") or "volc.seedasr.auc"`(已改)。
- **移除请求体里的 `corpus`/`context`**(2.0 崩;biasing 已移到 CLEAN)。`build_context()` 及 `--context/--glossary/--boosting` 相关参数一并删除或退役(清理上一轮加的、现已死的代码)。
- 端点、鉴权、`to_transcript`、`correct_table.json` 兜底不变。

### 3.2 fetch_xiaoyuzhou.sh(完整 shownote)
- 从页面 `__NEXT_DATA__` 的 `shownotes` 字段提完整 shownote(HTML→纯文本)→ metadata.json 新增 `shownote` 字段(完整,不截 500)。抓不到回退 og:description,不硬失败。
- 已验证该页面结构:`__NEXT_DATA__` 里有 `shownotes`,含正文 + OUTLINE(全专名 + 时间戳)。

### 3.3 clean.md(CLEAN 消费 shownote)
- Analyze 步骤(Round 1 clean.md Step A)新增:**读入 metadata.json 的 title + podcast + shownote + `~/.config/volc/glossary.txt`**,作为"术语表 + 存疑清单"的权威来源。
  - ⚠️ 必须含 **podcast/series 名字段**:主持人本名(如"张小珺"的"珺")常只在节目名里,不在 shownote 正文——验证时只喂 shownote 正文导致 `小俊` 被误纠成 `小军`(仍错);喂上 podcast 名才有"珺"。
- Review 步骤:遇专名/同音词,**优先对照 shownote 里的写法**纠正(shownote 是嘉宾/主持给的 ground truth)。
- glossary.txt 从"ASR context 底料"**重定位为"CLEAN 纠错词库"**。

### 3.4 ingest.md
- 更新火山命令(去 `--meta/--context`,注明 2.0 裸跑);说明 shownote 抓取 + 它流向 CLEAN 而非 ASR。

## 4. 验证 / 成功标准

- **已完成(spike)**:2.0 裸跑转录成功、schema 兼容、context 会崩已确认。
- **待验(本轮核心)**:把刚跑出的**真实 2.0 transcript 的相关片段 + shownote** 喂 CLEAN Review,确认 `Aultimate→Altimeter`、`小俊→小珺`、`skating→scaling` 被纠对 → **证明 shownote→CLEAN 这条链真有效**。
- 不回退:CLEAN 4 词回归样本仍过。
- e2e:该 URL 跑通 抓取(含 shownote)→2.0 裸跑→CLEAN(用 shownote)→渲染。

## 5. 风险

- **2.0 偶发 55000001**:裸跑那次成功了,但需观察稳定性;env 可秒回退 1.0。
- **shownote 抓取脆**:页面结构变 → 回退 og:description。
- **shownote 与口误冲突**:shownote 偶尔与嘉宾口误不一致 → Review 以"忠于音频说了什么"为准,shownote 仅作专名候选参考(不覆盖内容)。

## 6. 要改的文件

- `~/.config/volc/volc_asr.py`(非版本控制):RESOURCE_ID env(已改)+ 删 corpus/context 及退役 build_context。
- `skills/bpr/scripts/fetch/fetch_xiaoyuzhou.sh`:抓完整 shownote。
- `skills/bpr/references/clean.md`:Analyze/Review 消费 shownote + glossary。
- `skills/bpr/references/ingest.md`:更新说明。
- `~/.config/volc/glossary.txt`:重定位为 CLEAN 纠错词库(内容维护)。
