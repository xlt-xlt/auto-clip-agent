# -*- coding: utf-8 -*-
"""真人录音处理：把手机录的旁白做成成片可用的干净人声。

用法：
  python prep_voiceover_real.py "inbox\我的旁白.m4a"

做三件事：
1. 降噪 + 去低频嗡嗡声（highpass 80Hz + afftdn）
2. 响度归一化到短视频标准（I=-16 LUFS, TP=-2dB）
3. 输出 work/voiceover_real_norm.wav，并打印前后响度对比

手机录的原始素材通常合格，不要用 TTS 那种过度平滑的声音——
平台音频指纹主要抓的就是神经 TTS 的规律性。
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "voiceover_real_norm.wav"


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-800:])
    return p.stderr


def probe_mean(path: Path) -> str:
    err = run(["ffmpeg", "-hide_banner", "-i", str(path),
               "-af", "volumedetect", "-f", "null", "NUL"])
    for line in err.splitlines():
        if "mean_volume" in line or "max_volume" in line:
            return line.strip()
    return ""


def main():
    if len(sys.argv) < 2:
        print("用法: python prep_voiceover_real.py <录音文件>")
        raise SystemExit(1)
    src = Path(sys.argv[1])
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        print(f"[ERR] 找不到文件: {src}")
        raise SystemExit(1)

    print(f"[*] 源文件: {src}")
    print(f"[*] 处理前: {probe_mean(src)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    af = (
        "highpass=f=80,"                    # 去掉桌面/空调低频嗡嗡声
        "afftdn=nf=-25,"                    # 频域降噪
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=120,"
        "loudnorm=I=-16:TP=-2:LRA=11"       # 短视频平台响度标准
    )
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(src),
         "-af", af, "-ar", "44100", "-ac", "2", str(OUT)])
    print(f"[+] 已输出: {OUT}")
    print(f"[+] 处理后: {probe_mean(OUT)}")
    print("\n下一步：把 work/voiceover_real_norm.wav 替换进 ChatCut 成片的 A2 音轨，重新导出。")


if __name__ == "__main__":
    main()
