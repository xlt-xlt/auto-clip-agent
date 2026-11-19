# -*- coding: utf-8 -*-
"""剪映资源接入自检：音乐、字体、转场特效库是否就绪。"""
from pathlib import Path
import json

ROOT = Path(__file__).parent

print("=== 剪映音乐(导入自 User Data/Cache/music) ===")
musics = list((ROOT / "assets" / "bgm" / "jianying").glob("*.mp3"))
print(f"  数量: {len(musics)}")
for m in musics[:5]:
    print(f"    {m.name} {m.stat().st_size//1024}KB")

print("=== 剪映字体 ===")
fonts = list((ROOT / "assets" / "fonts").glob("*"))
print(f"  数量: {len(fonts)}")
for f in fonts:
    print(f"    {f.name} {f.stat().st_size//1024}KB")

print("=== 剪映转场/特效库 ===")
from jianying_fx import JIANYING_TRANSITIONS, resolve_transition, in_clip_effect, font_path
print(f"  转场映射: {len(JIANYING_TRANSITIONS)} 种: {list(JIANYING_TRANSITIONS)}")
for k in ["闪白", "闪黑", "故障"]:
    print(f"    {k} -> {resolve_transition(k)}")
for k in ["hard", "flash", "soft", "glitch"]:
    fx = in_clip_effect(k)
    print(f"    段内特效 {k}: {'就绪' if fx else '空'} ({len(fx)}字符)")
for k in ["新青年", "悠然", "后现代"]:
    print(f"    字体 {k}: {font_path(k)}")
