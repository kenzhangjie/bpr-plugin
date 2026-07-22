# CLEAN · ASR 后处理三步法(analyze / review / polish)

> 阶段 3(新增)· 仅中文模式。把火山逐字口语 transcript 纠错并书面化,保留逐字底档。
> 位置:PREP 之后、STRUCTURE 之前。英文双语模式不跑(走 translate.md 四步法)。

## 触发条件
- PREP 判定 CJK ≥ 60%(中文模式)→ 跑 CLEAN。
- 英文/双语 → 跳过。

## Step A · Analyze(主代理,全稿 1 次)
在切窗分派前,通读全稿产出一份 brief,塞进每个子代理 prompt(保跨窗一致):
1. **领域术语表**:本期专名(人/公司/产品/模型名)+ 高频英文术语,标注哪些保留英文、哪些固定中文。AI/科技/投资/growth 领域优先。
2. **说话人 + 语气**:host / guest 分别的语气。
3. **存疑词清单**:扫全稿标出可疑中英混词(疑似同音/近音错、拼写不成词的英文),供 Review 重点核。
> Analyze 产出的专名清单,完成后回写 `~/.config/volc/glossary.txt`(Ken 过目合入),反哺下期 ASR 偏置。

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
术语表:{glossary}
说话人/语气:{speakers}
存疑词清单:{suspects}

【逐字原文(本窗)】
{raw_window}

分两步做,只输出最终书面中文:
1) Review(纠错,只对原文负责):按上下文 + 术语表修同音/近音错词、专名、断句。
   不可判的词绝不硬编,标 ⟨?你的猜测⟩ 留待定夺。
2) Polish(书面化,只改怎么说不改说了什么):去口水词(呃/就是/对吧/然后…)、
   合并重组成通顺书面段落。**每个论点/数字/专名/因果必须保下来**,通顺不许吞信息。

按说话人分段输出,保留时间戳锚点。不要输出解释,只要正文。
```

高密度章(非共识金句)可升级:Review、Polish 各一次独立调用(见 translate.md 极致版)。

## Step D · 错词四分类
| 类 | 例 | 处理 |
|---|---|---|
| 1 同音/近音 | skating→scaling、constrain→constraint、unprobability→unpredictability | 上下文直接改 |
| 2 专名 | 克洛蔻→Claude、阿帕比→a paper、小俊→小珺 | 术语表比对后改 |
| 3 断句/标点 | 两句黏一句 | 重新断句 |
| 4 真不可判 | 连人都拿不准 | 标 ⟨?猜测⟩ 不硬编;confidently wrong 比留错更坏 |

## Step E · 存疑标注约定
- Review 阶段不可判词写 `⟨?候选词⟩`(如 `⟨?a paper⟩`)。
- RENDER 阶段(render.md)把 `⟨?X⟩` 转成 `<mark class="asr-uncertain" title="ASR存疑">X?</mark>`,可点可 grep。
