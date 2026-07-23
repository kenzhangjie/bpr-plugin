# ASR 源头优化 Round 2 · 火山 2.0 + shownote context

- **日期**:2026-07-23
- **状态**:已通过 brainstorming,待 writing-plans
- **影响范围**:`~/.config/volc/volc_asr.py`(非版本控制)、`bpr-plugin/skills/bpr/scripts/fetch/fetch_xiaoyuzhou.sh`(版本控制)、`~/.config/volc/glossary.txt`
- **前置**:Round 1(CLEAN 阶段)已上线(v1.6.0)。本轮是它上游的源头质量提升。

---

## 1. 问题 / 动机

Round 1 用 LLM 后处理(CLEAN)兜底 ASR 错词。本轮从**源头**再压一层,让火山少犯错:

1. **模型仍是 1.0**:`volc_asr.py` 的 `RESOURCE_ID = "volc.bigasr.auc"` 是豆包录音识别 **1.0**。2.0(`volc.seedasr.auc`)准确率更高、**上下文关键词召回 +20%**、中英混录更强。
2. **shownote 没吃到**:`fetch_xiaoyuzhou.sh` 只抓 `og:description` 且截断 500 字,**完整 shownote(嘉宾/公司/专题名的金矿)没抓**。2.0 强上下文,shownote 喂进 `corpus.context` 正中其长处。

## 2. 目标 / 非目标

**目标**
- 火山 ASR 从 1.0 迁移到 2.0(`volc.seedasr.auc`),可 env 配置、可回退 1.0。
- 抓取完整 shownote,拼进 `corpus.context` 偏置(叠加 glossary.txt)。
- 先跑 2.0 实测 spike,确认契约再铺开。

**非目标(明确砍掉)**
- **控制台热词表(boosting_table_name)**:火山无管理 API 无法自动同步;与 context 装同一批词、context 还自动新鲜 → 冗余。**单轨 context**。
- **英文独立 ASR 模型**:2.0 支持英文;英文内容多走 YouTube 字幕不过 ASR。真撞上"英文音频+无字幕"再单开 spec。
- 不动 CLEAN 阶段本身(Round 1 已上线)。

## 3. 架构 / 数据流

```
小宇宙 URL → fetch_xiaoyuzhou.sh
   ├─ audio.m4a
   └─ metadata.json { title, podcast, shownote(完整), publish_date, audio_url, … }
                    ↓
volc_asr.py --meta metadata.json
   RESOURCE_ID = $VOLC_ASR_RESOURCE(默认 volc.seedasr.auc = 2.0)
   build_context() = title + shownote + glossary.txt  → corpus.context
                    ↓
   transcript.txt(2.0 转录,专名召回 ↑)→ 进 CLEAN 阶段(不变)
```

## 4. 组件

### 4.1 2.0 迁移(volc_asr.py)
- `RESOURCE_ID` 改为读 env `VOLC_ASR_RESOURCE`,缺省 `volc.seedasr.auc`;设 `volc.bigasr.auc` 即回退 1.0。
- 端点不变(标准版 2.0 复用 `/api/v3/auc/bigmodel/submit` + `/query`)。
- `--boosting` flag 保留但默认不用(单轨 context;留着不碍事)。

### 4.2 完整 shownote 抓取(fetch_xiaoyuzhou.sh)
- 现状:`desc = og:description`,截断 `desc[:500]`。
- 改:从 episode 页面正文提取**完整 shownote**(小宇宙页面有 shownote 区块;JSON-LD 或正文 DOM),存 metadata.json 的新字段 `shownote`(完整,不截断或放宽到合理上限如 4000 字)。`description` 字段保留兼容。
- 抓不到完整 shownote 时,回退用 `og:description`(不硬失败)。

### 4.3 context 升级(volc_asr.py build_context)
- `build_context()` 已读 metadata 的 title/podcast/description;新增读 `shownote` 字段。
- 拼接顺序:title + shownote + glossary.txt;总长按 2.0 的 context 上限截断(spike 确认上限;暂定沿用 ~1000,若 2.0 允许更长则放宽)。

### 4.4 spike(先跑,gate 后续)
拿真 URL `https://www.xiaoyuzhoufm.com/episode/6a09d58b1b7bd502955258ab` 实测 2.0,确认 3 件事:
1. 请求体 `model_name` 是否仍 `"bigmodel"`(换错 submit 报错)。
2. 响应结构是否变(`to_transcript()` 靠 `result.utterances[].additions.speaker` + `.text` + `.start_time`;变了要改解析)。
3. 响应带不带 word 级 `confidence`(定后续"置信度驱动 flagging"可行性;本轮只记录不实现)。
- **spike 通过 → 铺开 4.1-4.3;spike 挂 → env 回退 1.0,修解析后再切。**

## 5. 验证 / 成功标准

- **spike**:同一期音频 1.0 vs 2.0 转录并排,专名错词(克洛蔻/阿帕比类)肉眼变少;记录 2.0 是否带 confidence。
- **shownote**:metadata.json 的 `shownote` 字段含完整正文(非 500 截断);build_context stderr 日志可见 shownote 内容进了 context。
- **不回退**:CLEAN 的 4 词回归样本仍过。
- **e2e**:该 URL 跑通 抓取→2.0→CLEAN→渲染 全链路。

## 6. 同步策略(单轨的好处)

- 词库单一源 = `~/.config/volc/glossary.txt`(我维护)。
- context 直传每次现读 glossary.txt + 现抓 shownote → **永远新鲜、零漂移、零手工**。
- 无控制台表 = 无需人工重传、无 hash 漂移检测。

## 7. 风险

- **2.0 契约漂移**:model_name/响应结构与 1.0 不同 → spike 先验,env 可秒回退 1.0,`to_transcript` 按需改。
- **shownote 抓取脆**:小宇宙页面结构变 → 回退 og:description,不硬失败。
- **context 超长**:shownote 可能很长 → 按上限截断,优先保 glossary + shownote 头部专名密集段。

## 8. 要改的文件

- `~/.config/volc/volc_asr.py`(**非版本控制**):RESOURCE_ID env 化 + build_context 读 shownote。
- `bpr-plugin/skills/bpr/scripts/fetch/fetch_xiaoyuzhou.sh`(版本控制):抓完整 shownote。
- `bpr-plugin/skills/bpr/references/ingest.md`:补 2.0 / shownote / env 说明。
- `~/.config/volc/glossary.txt`:按需补词(内容维护,非结构改动)。
