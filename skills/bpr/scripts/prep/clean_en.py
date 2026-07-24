#!/usr/bin/env python3
"""英文 PREP 源清洗 —— 确定性部分(agent 派子代理做纠错/归属,本脚本做拼装与闸门)。

见 references/prep-and-modes.md「英文子模式源清洗」与
docs/superpowers/specs/2026-07-24-bpr-english-prep-correction-design.md。
"""
from __future__ import annotations
import html, re, json


def parse_blocks(raw: str) -> list[str]:
    """把扁平字幕流按 >> 切成块(html 反转义、去空白、丢空块)。"""
    text = html.unescape(raw)
    parts = re.split(r">>\s*", text)
    return [p.strip() for p in parts if p.strip()]


def split_windows(blocks: list, size: int = 25) -> list[list]:
    """按固定大小切窗,供逐窗派子代理。"""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]


def load_mappings(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def apply_correct_table(text: str, mappings: dict) -> str:
    """套用无歧义硬映射。长键优先,避免短键抢先命中长专名。"""
    sorted_keys = sorted(mappings.keys(), key=len, reverse=True)

    i = 0
    result = []
    while i < len(text):
        matched = False
        for key in sorted_keys:
            if text[i:i+len(key)] == key:
                result.append(mappings[key])
                i += len(key)
                matched = True
                break
        if not matched:
            result.append(text[i])
            i += 1

    return ''.join(result)
