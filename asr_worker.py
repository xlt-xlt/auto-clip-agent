# -*- coding: utf-8 -*-
"""ASR 子进程 worker：由 .asrenv (Python3.10) 运行，避免主环境版本冲突。
用法：.asrenv/Scripts/python.exe asr_worker.py <音频路径> <模型> <语言> <结果json路径>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 国内镜像端点：faster-whisper 从 HuggingFace Hub 拉模型，国内直连常断线。
# 允许用 ASR_HF_ENDPOINT 覆盖；设为 "none" 则不设置（走官方源）。
_hf = os.getenv("ASR_HF_ENDPOINT", "https://hf-mirror.com")
if _hf and _hf.lower() != "none":
    os.environ.setdefault("HF_ENDPOINT", _hf)

# 缓存目录重定向到工程内：默认的 ~/.cache/huggingface 在部分环境无写权限。
_here = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(_here / ".hf_cache"))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_here / ".hf_cache" / "hub"))
Path(os.environ["HF_HOME"]).mkdir(parents=True, exist_ok=True)


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"error": "usage: asr_worker.py <audio> <model> <lang> <out>"}))
        sys.exit(1)
    audio, model_name, language, out = sys.argv[1:5]
    from faster_whisper import WhisperModel

    device = "cpu"
    compute = "int8"
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments, _info = model.transcribe(
        audio, language=language or None,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
        word_timestamps=True,
    )
    result = []
    for seg in segments:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({"start": float(w.start or 0), "end": float(w.end or 0),
                              "word": w.word})
        result.append({"start": float(seg.start), "end": float(seg.end),
                       "text": seg.text.strip(), "words": words})
    Path(out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": True, "count": len(result)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
