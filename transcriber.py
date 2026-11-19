# -*- coding: utf-8 -*-
"""转写模块：主程序通过子进程调用 .asrenv(Python3.10) 的 faster-whisper，
彻底绕开 Python 3.15 上 PyAV 无法编译的问题。失败可降级到等长分段。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from utils import log, is_media, ROOT


def transcribe(path: str | Path, cfg: dict) -> list[dict]:
    """返回 [{'start':float,'end':float,'text':str,'words':[...]}]，源时间秒。"""
    acfg = cfg.get("asr", {})
    backend = acfg.get("backend", "auto")
    path = Path(path)
    if not is_media(path):
        log(f"非媒体文件，跳过转写: {path.name}", "WARN")
        return []

    log(f"开始转写: {path.name} (model={acfg.get('model')})")

    if backend in ("auto", "faster-whisper"):
        try:
            return _subprocess_whisper(path, acfg)
        except Exception as e:
            if backend == "faster-whisper":
                raise
            log(f"本地 ASR 失败，降级等长分段: {e}", "WARN")

    log("无可用语音转写结果，剪辑将退化为按等长分段", "WARN")
    return []


def _subprocess_whisper(path: Path, acfg: dict) -> list[dict]:
    """调用 .asrenv 中的 asr_worker.py。"""
    asr_py = ROOT / ".asrenv" / "Scripts" / "python.exe"
    if not asr_py.exists():
        # 兼容非 Windows 或自定义路径
        asr_py = Path(os.getenv("ASR_PYTHON", str(asr_py)))
    worker = ROOT / "asr_worker.py"
    if not asr_py.exists():
        raise RuntimeError(f"ASR 环境不存在: {asr_py}（请先建 .asrenv）")

    out_json = path.parent / f".{path.stem}_asr.json"
    cmd = [str(asr_py), str(worker), str(path),
           acfg.get("model", "small"), acfg.get("language", "zh"), str(out_json)]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    log(f"  调用 ASR worker（首次会下载模型，可能较慢）…")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600, creationflags=creationflags)
    stdout = (p.stdout or "").strip()
    if p.returncode != 0:
        raise RuntimeError(f"ASR worker 退出 {p.returncode}: {stdout[-500:]} {(p.stderr or '')[-500:]}")
    try:
        info = json.loads(stdout.splitlines()[-1])
    except Exception:
        info = {}
    if info.get("error"):
        raise RuntimeError(f"ASR worker 报错: {info['error']}")
    if not out_json.exists():
        raise RuntimeError("ASR worker 未产出结果文件")
    segs = json.loads(out_json.read_text(encoding="utf-8"))
    try:
        out_json.unlink()
    except Exception:
        pass
    log(f"faster-whisper 完成: {len(segs)} 段", "OK")
    return segs


def transcribe_to_json(path: str | Path, cfg: dict, out_json: str | Path) -> list[dict]:
    segs = transcribe(path, cfg)
    Path(out_json).write_text(json.dumps(segs, ensure_ascii=False, indent=2), encoding="utf-8")
    return segs
