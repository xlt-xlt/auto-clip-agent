# -*- coding: utf-8 -*-
"""AI 剪辑大脑：把逐句转录变成剪辑计划（保留哪些时间段 + 文案 + 标题）。
有 LLM key 走 LLM，否则用规则引擎兜底，保证系统永远可跑。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from utils import log

SYSTEM_PROMPT = """你是资深短视频剪辑导演。输入是视频的逐句转录（含起止秒数）。
请输出严格的 JSON，不要任何解释文字，格式：
{
  "keep": [[start_sec, end_sec], ...],
  "title": "标题（不超过20字，制造悬念或痛点）",
  "caption": "发布文案（不超过100字，口语化，有互动引导）",
  "hashtags": ["#标签1", "#标签2", "#标签3"]
}
剪辑规则：
1. 删除口头禅、重复、冷场、说错重来的部分；保留完整句子边界。
2. 开头 3 秒必须放最强钩子（最有争议/最反常识/最有价值的一句），可把它挪到开头。
3. 成片总时长严格控制在 {dmin}-{dmax} 秒之间。
4. keep 里的时间段必须来自原文起止时间，可微调边界到句子首尾，不能凭空捏造。
5. 保留片段按播放顺序排列。
6. 如果转录为空，返回 keep 为等长的 3 个片段。
"""


FILLER_WORDS = re.compile(
    r"^(嗯+|啊+|呃+|额+|那个|这个|就是|然后|所以说|那么|OK|okay|well|um+|uh+|er+|ah+)[，。,.!！ ]*$",
    re.IGNORECASE,
)


def decide(segments: list[dict], cfg: dict, duration_hint: float = 0) -> dict:
    bcfg = cfg.get("brain", {})
    backend = bcfg.get("backend", "auto")
    api_key = os.getenv(bcfg.get("llm", {}).get("api_key_env", "LLM_API_KEY"), "")

    if backend in ("auto", "llm") and api_key:
        try:
            plan = _llm_decide(segments, cfg, api_key)
            _validate_plan(plan, segments, cfg)
            log(f"LLM 剪辑决策完成: {len(plan['keep'])} 段", "OK")
            return plan
        except Exception as e:
            if backend == "llm":
                raise
            log(f"LLM 决策失败，降级规则引擎: {e}", "WARN")

    log("使用规则引擎生成剪辑计划", "INFO")
    plan = _rule_decide(segments, cfg, duration_hint)
    return plan


def _llm_decide(segments: list[dict], cfg: dict, api_key: str) -> dict:
    from openai import OpenAI
    bcfg = cfg["brain"]
    llm = bcfg["llm"]
    client = OpenAI(api_key=api_key, base_url=llm.get("base_url") or None)
    target = bcfg.get("target", {})
    system = SYSTEM_PROMPT.format(
        dmin=target.get("duration_min", 30), dmax=target.get("duration_max", 90))
    # 压缩转录，只保留必要字段
    payload = [{"start": round(s["start"], 2), "end": round(s["end"], 2),
                "text": s["text"]} for s in segments]
    r = client.chat.completions.create(
        model=llm.get("model", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.5,
    )
    content = r.choices[0].message.content or "{}"
    return json.loads(content)


def _rule_decide(segments: list[dict], cfg: dict, duration_hint: float) -> dict:
    """规则引擎：去纯口癖行、按目标时长截取，保留完整句子。"""
    target = cfg.get("brain", {}).get("target", {})
    dmin = target.get("duration_min", 30)
    dmax = target.get("duration_max", 90)

    if not segments:
        dur = duration_hint if duration_hint > 0 else 60
        n = 3
        step = dur / n
        return {
            "keep": [[round(i * step, 2), round((i + 1) * step, 2)] for i in range(n)],
            "title": "精彩片段", "caption": "仅供参考，欢迎互动～",
            "hashtags": ["#短视频", "#日常分享"],
        }

    cleaned = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text or FILLER_WORDS.match(text):
            continue
        start, end = float(s["start"]), float(s["end"])
        if end <= start:
            continue
        cleaned.append([round(start, 2), round(end, 2)])

    keep = cleaned
    total = sum(e - st for st, e in keep)
    if total <= 0:
        keep = [[round(segments[0]["start"], 2), round(segments[-1]["end"], 2)]]
        total = keep[0][1] - keep[0][0]

    # 按时长裁剪（从开头累计到 dmax）
    if total > dmax:
        acc, trimmed = 0.0, []
        for st, e in keep:
            segdur = e - st
            if acc + segdur > dmax:
                remain = dmax - acc
                if remain > 1:
                    trimmed.append([st, round(st + remain, 2)])
                break
            trimmed.append([st, e])
            acc += segdur
        keep = trimmed

    # 用首句做标题
    first_text = next((s["text"] for s in segments if s.get("text", "").strip()), "精彩片段")
    title = re.sub(r"[，。,.!！?？]", "", first_text)[:20] or "精彩片段"
    caption = first_text[:80]
    return {
        "keep": keep,
        "title": title,
        "caption": caption,
        "hashtags": ["#短视频", "#日常分享", "#推荐"],
    }


def _validate_plan(plan: dict, segments: list[dict], cfg: dict):
    """校验 LLM 输出，修正越界/非法时间段。"""
    if not isinstance(plan.get("keep"), list) or not plan["keep"]:
        raise ValueError("LLM 未输出 keep 片段")
    if not segments:
        return
    lo = float(segments[0]["start"])
    hi = float(segments[-1]["end"])
    fixed = []
    for pair in plan["keep"]:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        st, en = float(pair[0]), float(pair[1])
        if en <= st:
            continue
        st, en = max(lo, st), min(hi, en)
        if en > st:
            fixed.append([round(st, 2), round(en, 2)])
    if not fixed:
        raise ValueError("所有 keep 片段越界")
    plan["keep"] = fixed
    plan.setdefault("title", "精彩片段")
    plan.setdefault("caption", "")
    plan.setdefault("hashtags", ["#短视频"])
