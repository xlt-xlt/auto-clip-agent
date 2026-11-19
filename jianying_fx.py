# -*- coding: utf-8 -*-
"""剪映风格转场/特效库 —— 用 ffmpeg 复刻剪映爆款转场与特效。

从本机剪映(JianyingPro)探查到的可用资源：
  · 音乐：User Data\\Cache\\music\\*.mp3（用户从剪映音乐库下载过的真实曲目）
  · 字体：新青年体/悠然体/后现代体（已复制到 assets/fonts/）
  · 草稿工程 draft_content.json 为新版加密格式，无法直接读取参数，
    因此转场/特效按剪映常见爆款效果用 ffmpeg 复刻。

提供的转场(供 concat_xfade 使用 xfade 名称)：
  运镜推近 push / 闪白 fadewhite / 闪黑 fadeblack / 故障 glitch
特效(段内)：
  三段闪、RGB色差故障、抖动、缩放冲击、光晕
"""
from __future__ import annotations

# 剪映转场 -> ffmpeg xfade 映射（剪映常见转场名的 ffmpeg 等价实现）
JIANYING_TRANSITIONS = {
    "叠化": "fade",        # 叠化/淡化
    "闪白": "fadewhite",   # 白场过渡
    "闪黑": "fadeblack",   # 黑场过渡
    "推近": "fade",        # 配合段内 push 特效实现运镜推近
    "故障": "fade",        # 配合段内 glitch 特效
    "擦除": "wipeleft",
    "圆形遮罩": "circlecrop",
    "缩放": "fade",        # 配合段内 zoom 冲击
}


def resolve_transition(name: str) -> str:
    """把中文剪映转场名或英文 ffmpeg 名解析为 ffmpeg xfade 名。"""
    return JIANYING_TRANSITIONS.get(name, name if name in {
        "fade", "fadewhite", "fadeblack", "wipeleft", "wiperight",
        "circlecrop", "rectcrop", "slideleft", "slideright", "distance",
        "smoothleft", "smoothright", "radial", "pixelize", "dissolve",
    } else "fade")


def in_clip_effect(kind: str, fps: int = 30) -> str:
    """段内特效滤镜串（拼在 motion 之后）。kind 见 styles.py 的 impact/effect 字段。"""
    if not kind or kind == "none":
        return ""
    if kind == "soft":  # 轻柔白闪
        return "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.32:t=fill:enable='between(t,0.04,0.14)'"
    # RGB 色差故障（剪映"故障"特效核心）
    glitch = "rgbashift=rh=16:bh=-16:gh=6:enable='between(t,0.20,0.42)'"
    if kind == "hard":  # 白-黑-白三连闪（剪映"卡点闪屏"）
        flash = (
            "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t=fill:enable='between(t,0.04,0.11)',"
            "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.88:t=fill:enable='between(t,0.12,0.17)',"
            "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t=fill:enable='between(t,0.18,0.25)'"
        )
        return flash + "," + glitch
    if kind == "flash":  # 单次白闪 + 故障
        return ("drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t=fill:enable='between(t,0.04,0.16)',"
                + glitch)
    if kind == "glitch":  # 纯故障（剪映"故障"）
        return glitch
    return ""


def font_path(key: str) -> str | None:
    """剪映字体键名 -> 工程内字体路径。"""
    from pathlib import Path
    import sys
    base_dir = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                else Path(__file__).parent)
    base = base_dir / "assets" / "fonts"
    names = {
        "新青年": "新青年体.ttf", "youth": "新青年体.ttf",
        "悠然": "悠然体.ttf", "leisure": "悠然体.ttf",
        "后现代": "后现代体.otf", "modern": "后现代体.otf",
    }
    n = names.get(key)
    return str(base / n) if n and (base / n).exists() else None
