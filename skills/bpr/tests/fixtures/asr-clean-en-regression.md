# 英文 PREP 源清洗回归样本(冒烟用)

输入(YouTube 自动字幕,含已知专名错 + 一个合并 >> 块):
- "90% of people at Opening Eye use Codeex."
- "today my guest is Andrew Ambercino. >> Thank you for having me. what does the team look like? >> Everybody is very agentic."

期望源清洗输出:
- 专名修正:Opening Eye → OpenAI;Codeex → Codex;Ambercino → Ambrosino
- 说话人归属 + 拆合并块:第二条按语义拆成
  - Lenny: "today my guest is Andrew Ambrosino." / "what does the team look like?"
  - Andrew: "Thank you for having me." / "Everybody is very agentic."
- 逐字:除专名外英文不改写、不删句(词覆盖 ≥0.98)
- 零幻觉:不可判词标 ⟨?候选⟩,不硬编(见 prep-and-modes.md 降级 + spec §4)
