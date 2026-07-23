"""用 OpenAI 给热词自动分配热度权重(1-10)。

给 `hotword add` 用:你只输入裸词(如 codex 鹅厂),这里调 OpenAI 按档位补 |权重。
默认模型 gpt-5-mini,可用 env VOLC_HOTWORD_WEIGHT_MODEL 覆盖。
"""
import json

RUBRIC = """你是火山引擎豆包语音 ASR 的热词权重助手。给每个词一个"热度权重"整数 1-10,
权重越高 = 识别时越强制把发音相近处掰成这个词。判据 = 多容易被 ASR 听错 × 多重要:
- 8-9:生造词 / 冷门英文品牌,模型基本没见过、谐音多(Higgsfield、TapNow、Flipagram、Dubsmash)
- 7:重要且中等易错的专有名词(Claude、Anthropic、Perplexity、xAI、影视飓风、阶跃星辰、codex)
- 6:较常见但仍需固定(OpenAI、Cursor、DeepSeek、Grok、Snowflake、scaling、agentic、鹅厂)
- 5:常见、偶尔错(Gemini、Sora、豆包)
- 1-4:很常见、几乎不会错的普通词(给低权重)
只按给定的词打分,不要新增或改写词。
只输出 JSON,格式严格为:{"weights":[{"word":"词","weight":整数}]}"""


def assign_weights(words, api_key, model="gpt-5-mini"):
    """返回 {word: weight}。缺 SDK / 网络 / key 时由调用方 try 兜底。"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": "给这些词打权重(输出 JSON):\n" + "\n".join(words)},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    return {item["word"]: int(item["weight"]) for item in data["weights"]}
