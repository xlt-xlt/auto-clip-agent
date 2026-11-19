# -*- coding: utf-8 -*-
"""公共工具：配置加载、路径、日志、ffmpeg 调用、SRT 生成。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

def _app_root() -> Path:
    """源码运行取脚本目录；打包成 exe 后取 exe 所在目录（config/assets 放它旁边）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = _app_root()
load_dotenv(ROOT / ".env")

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def load_config(path: str | Path | None = None) -> dict:
    """加载 JSON 配置（标准库，无需 pyyaml）。兼容旧 config.yaml 路径。"""
    import json
    path = Path(path) if path else (ROOT / "config.json")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f) or {}
    # 把相对路径解析为基于工程根
    for k, v in cfg.get("paths", {}).items():
        cfg["paths"][k] = str((ROOT / v).resolve())
    return cfg


def ensure_dirs(cfg: dict):
    for v in cfg.get("paths", {}).values():
        if str(v).endswith((".mp3", ".wav", ".ttf", ".otf", ".ttc")):
            continue
        Path(v).mkdir(parents=True, exist_ok=True)


def log(msg: str, level: str = "INFO"):
    tag = {"INFO": "[*]", "OK": "[+]", "WARN": "[!]", "ERR": "[-]"}.get(level, "[*]")
    print(f"{tag} {msg}", flush=True)


def run(cmd: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """统一 subprocess 调用，Windows 下隐藏窗口。"""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log("$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    return subprocess.run(
        cmd, check=check, capture_output=capture, text=True,
        encoding="utf-8", errors="replace", creationflags=creationflags,
    )


def find_ffmpeg(cfg: dict | None = None) -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("未找到 ffmpeg：请安装系统 ffmpeg 或 pip install imageio-ffmpeg")


def ffprobe_duration(path: str | Path, ffmpeg: str | None = None) -> float:
    """用 ffmpeg -i 解析时长（不依赖 ffprobe）。"""
    ff = ffmpeg or find_ffmpeg()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    p = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=creationflags)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
    if not m:
        return 0.0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def is_media(path: Path) -> bool:
    return path.suffix.lower() in (VIDEO_EXT | AUDIO_EXT)


def srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[dict], out: str | Path, max_chars: int = 16) -> Path:
    """segments: [{'start':s,'end':s,'text':str}]，按标点/长度切行。"""
    out = Path(out)
    lines = []
    for i, seg in enumerate(segments, 1):
        text = re.sub(r"\s+", " ", seg["text"]).strip()
        if not text:
            continue
        # 长句按长度切两行
        if len(text) > max_chars * 2:
            cut = text.rfind("，", 0, max_chars * 2)
            if cut == -1:
                cut = text.rfind(" ", 0, max_chars * 2)
            if cut == -1:
                cut = max_chars * 2
            text = text[:cut] + "\n" + text[cut:].lstrip("， ")
        lines += [str(i), f"{srt_time(seg['start'])} --> {srt_time(seg['end'])}", text, ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def state_key(path: str | Path) -> str:
    import hashlib
    p = Path(path)
    stat = p.stat()
    raw = f"{p.name}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_state(state_dir: str | Path) -> set:
    f = Path(state_dir) / "processed.json"
    if f.exists():
        try:
            return set(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_state(state_dir: str | Path, keys: set):
    f = Path(state_dir) / "processed.json"
    f.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=2), encoding="utf-8")
