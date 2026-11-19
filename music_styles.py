# -*- coding: utf-8 -*-
"""音乐方案库。

每套方案给四平台各指定：曲子文件、从几秒开始裁副歌、音量覆盖（可选）。
选曲依据（本机实测 BPM/能量，来自 work/bgm_probe）：
  jy_11=107BPM/能量1226（最燃）  jy_09=125/858（最快）  jy_05=115/525
  jy_07=103/386  jy_08=94/516  jy_06=91/568  jy_04=94/377
  jy_03=53/704  jy_02=52/650  jy_01=65/532  jy_12=64/440  jy_10=100/251（安静）
  soundhelix_02=200/210（最快） soundhelix_05=71/116（最柔） soundhelix_01=67/629
  soundhelix_08=71/396  kalimba=60/847

按日期确定性轮换：plan_index = 日期.toordinal() % len(BGM_PLANS)
加新方案只需 append 一个 dict，周期自动+1。
"""
from __future__ import annotations

# 每套方案：key / name / desc / tracks{平台:(文件, 起始秒, 音量或None)}
BGM_PLANS = [
    {
        "key": "energy",
        "name": "燃爆节奏",
        "desc": "最快最燃的曲子，卡点猛、适合炸场",
        "tracks": {
            "douyin":     ("jy_11.mp3", 6, 0.82),
            "xiaohongshu": ("jy_09.mp3", 8, 0.85),
            "shipinhao":  ("soundhelix_02.mp3", 10, 0.70),
            "kuaishou":   ("jy_11.mp3", 6, 0.85),
        },
    },
    {
        "key": "soft",
        "name": "温柔治愈",
        "desc": "最柔的曲子，安静、适合走心",
        "tracks": {
            "douyin":     ("soundhelix_05.mp3", 5, 0.90),
            "xiaohongshu": ("kalimba.mp3", 6, 0.80),
            "shipinhao":  ("soundhelix_05.mp3", 5, 0.92),
            "kuaishou":   ("jy_10.mp3", 4, 0.90),
        },
    },
    {
        "key": "tech",
        "name": "科技未来",
        "desc": "节奏干净带电子感，适合讲技术/机器人",
        "tracks": {
            "douyin":     ("jy_09.mp3", 8, 0.82),
            "xiaohongshu": ("jy_07.mp3", 10, 0.88),
            "shipinhao":  ("jy_08.mp3", 6, 0.88),
            "kuaishou":   ("jy_06.mp3", 8, 0.88),
        },
    },
    {
        "key": "lively",
        "name": "轻快活泼",
        "desc": "明亮跳跃，适合亲子/日常",
        "tracks": {
            "douyin":     ("jy_05.mp3", 12, 0.85),
            "xiaohongshu": ("jy_06.mp3", 10, 0.88),
            "shipinhao":  ("jy_05.mp3", 12, 0.88),
            "kuaishou":   ("jy_05.mp3", 12, 0.88),
        },
    },
    {
        "key": "epic",
        "name": "大气开阔",
        "desc": "铺陈感强，适合非遗/传承/记录",
        "tracks": {
            "douyin":     ("soundhelix_01.mp3", 10, 0.72),
            "xiaohongshu": ("jy_02.mp3", 12, 0.88),
            "shipinhao":  ("soundhelix_08.mp3", 8, 0.80),
            "kuaishou":   ("jy_03.mp3", 10, 0.88),
        },
    },
]


def plan_index(d) -> int:
    return d.toordinal() % len(BGM_PLANS)


def pick_for_date(d) -> dict:
    return BGM_PLANS[plan_index(d)]


def by_key(key: str) -> dict | None:
    for p in BGM_PLANS:
        if p["key"] == key:
            return p
    return None
