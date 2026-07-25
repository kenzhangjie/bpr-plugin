# CLEAN · ASR 后处理三步法(analyze / review / polish)

> 阶段 3(新增)· 仅中文模式。把火山逐字口语 transcript 纠错并书面化,保留逐字底档。
> 位置:PREP 之后、STRUCTURE 之前。英文双语模式不跑(走 translate.md 四步法)。

---

## 触发条件
- PREP 判定 CJK ≥ 60%(中文模式)→ 跑 CLEAN。
- 英文/双语 → 跳过。

## Step A · Analyze(主代理,全稿 1 次)
先读入**权威参考**,再通读全稿产出 brief(塞进每个子代理 prompt,保跨窗一致)。

**输入参考(小宇宙自带,是纠专名的 ground truth——比 ASR 更可信)**:
- `metadata.json` 的 **title + podcast + shownote**(fetch_xiaoyuzhou.sh 已抓完整 shownote):嘉宾/公司/产品名、OUTLINE 全在里面。
  - shownote **仅小宇宙有**;B站/YouTube 无 `shownote` 字段时跳过它,靠 title + podcast + glossary + 全稿上下文即可(降级,不报错)。
  - ⚠️ **必带 `podcast` 字段**:主持人本名常只在节目名里(如"张小珺Jùn｜商业访谈录"的"珺"),shownote 正文没有——不喂 podcast 名,`小俊/小军` 就纠不对(实测踩过)。
- `~/.config/volc/glossary.txt`:常驻专名词库,**唯一真源**。格式 `正确名|权重|错法1,错法2`(第 3 列可选,只放无歧义错法,供 volc_asr 硬纠)。CLEAN 读第 1 列当参考,忽略权重与错法列。

产出 brief:
1. **领域术语表**:综合 shownote + glossary,列本期专名(标保留英文/固定中文)。AI/科技/投资/growth 优先。
2. **说话人 + 语气**:host / guest(host 名从 `podcast` 字段拿)。
3. **存疑词清单**:扫全稿标可疑中英混词(同音/近音错、拼不成词的英文),供 Review 重点核。
> **为什么 shownote 是关键**:它是 ASR 之外的独立信源。ASR 把基金名转成 Aultimate/Ultimatum,shownote 里白纸黑字 Altimeter Capital → Review 据此一次纠对(2026-07-23 实测有效)。
> 本期新确认的专名由人工加进 glossary.txt(一行一条);热词文件用 `python3 ~/.config/volc/volc_asr.py --dump-boosting` 从 glossary 生成后手动上传火山控制台。最终热词以此 `--dump-boosting` 重生成的 `boosting.txt` 为准,`hotword-candidates.txt` 仅供 Ken 扫噪参考,避免又长出第二个热词真源。

## Step B · 切窗
- CLEAN 在语义切章(STRUCTURE)之前,不能按章切 → 按**固定 turn 窗口(~25 条)**切。
- 窗口边界对齐到 turn 边界(±几条弹性),不切碎一个说话人的连续发言。
- 每窗子代理拿:该窗逐字原文 + 全局 Analyze brief(术语表 + 存疑清单 + 语气)。

## Step C · 子代理 Review+Polish(每窗 1 个,独立 context)
默认每窗一个子代理,先 Review 再 Polish,只回书面中文。主代理 verbatim 持有原窗(抗压缩铁律)。

派发 prompt 模板:
```
你在做中文播客 ASR 逐字稿的纠错 + 书面化。这是第 N 窗逐字原文,和全局 brief。

【全局 brief】
术语表(综合 shownote + glossary):{glossary}
shownote 关键专名(ground truth,优先据此纠专名):{shownote_names}
说话人/语气:{speakers}
存疑词清单:{suspects}

【逐字原文(本窗)】
{raw_window}

分两步做,只输出最终书面中文:
1) Review(纠错,只对原文负责):按上下文 + 术语表修同音/近音错词、专名、断句。
   **专名与 shownote 不一致时,信 shownote 的写法**(如 Aultimate→Altimeter);
   不可判的词绝不硬编,标 ⟨?你的猜测⟩ 留待定夺。
2) Polish(书面化,只改怎么说不改说了什么):去口水词(呃/就是/对吧/然后…)、
   合并重组成通顺书面段落。**每个论点/数字/专名/因果必须保下来**,通顺不许吞信息。

**输出格式(硬约束,render_zh.py 靠它解析,别乱来)**:
- 每个 turn 起始**必须独占一行**:`Speaker N HH:MM:SS`(N 用原窗的说话人号,时间戳照抄原句起始)。
- **禁止 markdown 加粗**(不许写 `**Speaker 2 01:15:43**`)、禁止把正文跟在 header 同一行——正文**另起段**。
- 违反此格式,渲染会把 turn 当成字面文本渲染出来(2026-07-23 ch11 实测踩过)。
不要输出解释,只要正文。
```

高密度章(非共识金句)可升级:Review、Polish 各一次独立调用(见 translate.md 极致版)。

## Step C.5 · 保真闸(每窗 Polish 后自动对账)
书面重写是"软"操作,子代理可能悄悄吞数字/漏论点/改因果。每窗 Polish 完,派一个**廉价对账子代理(haiku 级)**只做一件事:

```
拿【原始窗】和【书面窗】逐条核对:数字、专名、论点实体、因果方向 —— 有没有丢或被改?
只输出 JSON:{"missing":[...], "altered":[...]}(各列具体项;都没有则空数组)。
```

- 清单**非空** → 把该窗**打回 Polish 重做一次**(把 missing/altered 塞进重做 prompt 让它补回)。
- 重做仍不过 → 该窗把丢失项标 `⟨?丢失:xxx⟩` 留人,不无限重试。
- 成本比 Polish 低一个数量级,但把"软护栏"变硬闸。

## Step D · 错词四分类
| 类 | 例 | 处理 |
|---|---|---|
| 1 同音/近音 | skating→scaling、constrain→constraint、unprobability→unpredictability | 上下文直接改 |
| 2 专名 | 克洛蔻→Claude、阿帕比→Anthropic、Aultimate→Altimeter、小俊→小珺 | 术语表/shownote 比对后改 |
| 3 断句/标点 | 两句黏一句 | 重新断句 |
| 4 真不可判 | 连人都拿不准 | 标 ⟨?猜测⟩ 不硬编;confidently wrong 比留错更坏 |

## Step E · 存疑标注约定
- Review 阶段不可判词写 `⟨?候选词⟩`(如 `⟨?a paper⟩`)。
- RENDER 阶段(render.md)把 `⟨?X⟩` 转成 `<mark class="asr-uncertain" title="ASR存疑">X?</mark>`,可点可 grep。
