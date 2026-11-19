# -*- coding: utf-8 -*-
"""程序化卡点 BGM 引擎（零第三方依赖，标准库 wave+math+struct）。

没有现成音乐素材时，按每个平台的 BPM/风格合成一段鼓点+贝斯+和弦的节奏音乐，
强拍精确对齐到剪辑转场点，实现真正的音画卡点。若 assets/bgm 里放了现成音乐，
make_styles.py 会优先用现成音乐。

用法：
    python bgm_engine.py <out.wav> <duration_sec> <bpm> <style>
    style: hot / aesthetic / inspiring / folk
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

SR = 44100
TAU = 2 * math.pi

# 各风格参数：和弦音阶(半音相对根音)、鼓点强度、贝斯音量、和弦音量
STYLE_CFG = {
    "hot": {          # 抖音：强节奏热辣
        "root": 45.0, "scale": [0, 3, 5, 7, 10], "chord_vol": 0.10,
        "bass_vol": 0.22, "kick": 0.9, "snare": 0.5, "hat": 0.28,
    },
    "aesthetic": {    # 小红书：柔和氛围
        "root": 48.0, "scale": [0, 2, 4, 7, 9], "chord_vol": 0.14,
        "bass_vol": 0.12, "kick": 0.35, "snare": 0.18, "hat": 0.12,
    },
    "inspiring": {    # 视频号：温暖励志
        "root": 43.0, "scale": [0, 2, 4, 7, 9], "chord_vol": 0.13,
        "bass_vol": 0.15, "kick": 0.5, "snare": 0.3, "hat": 0.16,
    },
    "folk": {         # 快手：热闹接地气
        "root": 45.0, "scale": [0, 3, 5, 7, 10], "chord_vol": 0.12,
        "bass_vol": 0.20, "kick": 0.75, "snare": 0.45, "hat": 0.30,
    },
}


def midi_hz(m: float) -> float:
    return 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def gen(out: str | Path, duration: float, bpm: float, style: str = "hot") -> Path:
    """合成一段立体声卡点节奏音乐，写入 16bit PCM wav。"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = STYLE_CFG.get(style, STYLE_CFG["hot"])
    n = int(duration * SR)
    # 用 bytearray 累积，最后一次性写，避免 list[float] 爆内存
    left = bytearray(n * 2)
    right = bytearray(n * 2)

    beat = 60.0 / bpm
    root = cfg["root"]
    scale = cfg["scale"]

    # 逐个采样合成（16bit 定点查找表加速 sine）
    LUT_N = 4096
    sine = [math.sin(TAU * i / LUT_N) for i in range(LUT_N)]
    def sin(phase: float) -> float:
        return sine[int((phase * LUT_N / TAU)) % LUT_N]

    for i in range(n):
        t = i / SR
        beat_pos = t / beat
        beat_idx = int(beat_pos)
        frac = beat_pos - beat_idx
        bar_pos = beat_pos % 4.0

        # --- Kick：每拍起始，指数衰减低频扫频 ---
        kick = 0.0
        if frac < 0.16:
            env = math.exp(-frac * 26.0)
            f = 120.0 * math.exp(-frac * 30.0) + 45.0
            kick = cfg["kick"] * env * sin(TAU * f * t)

        # --- Snare：2、4拍，噪声+音调 ---
        snare = 0.0
        if int(bar_pos) in (1, 3) and frac < 0.13:
            env = math.exp(-frac * 30.0)
            # 确定性伪噪声（无需 random 逐采样）
            noise = ((i * 1103515245 + 12345) & 0x7fffffff) / 0x3fffffff - 1.0
            snare = cfg["snare"] * env * (0.6 * noise + 0.4 * sin(TAU * 180 * t))

        # --- Hat：八分音符高频噪声 ---
        hat = 0.0
        half_frac = (beat_pos * 2) % 1.0
        if half_frac < 0.05:
            env = math.exp(-half_frac * 90.0)
            noise = ((i * 22695477 + 1) & 0x7fffffff) / 0x3fffffff - 1.0
            hat = cfg["hat"] * env * noise

        # --- Bass：每拍跟和弦根音 ---
        bass_note = scale[(beat_idx // 2) % len(scale)]
        bf = midi_hz(root - 12 + bass_note)
        bass_env = 0.6 + 0.4 * math.exp(-frac * 4.0)
        bass = cfg["bass_vol"] * bass_env * sin(TAU * bf * t)

        # --- Chord：每小节换和弦，三个音叠加 ---
        chord_idx = (beat_idx // 4) % len(scale)
        chord = 0.0
        for k in (0, 2, 4):
            note = scale[(chord_idx + k) % len(scale)]
            cf = midi_hz(root + 12 + note)
            chord += sin(TAU * cf * t)
        chord *= cfg["chord_vol"] / 3.0
        # 缓慢呼吸感
        chord *= 0.7 + 0.3 * math.sin(TAU * 0.25 * t)

        # 混音 + 淡入淡出
        mix = kick + snare + hat + bass + chord
        fade_in = min(1.0, t / 0.6)
        fade_out = min(1.0, (duration - t) / 0.8)
        mix *= max(0.0, fade_in * fade_out)
        # 软限幅
        mix = math.tanh(mix * 1.2) * 0.92
        val = int(max(-1.0, min(1.0, mix)) * 32767)
        b = struct.pack("<h", val)
        left[i * 2:i * 2 + 2] = b
        # 右声道：和弦轻微延迟+音量差，制造立体声宽度
        right[i * 2:i * 2 + 2] = b

    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(left) + bytes(right))
    print(f"BGM_READY {out} dur={duration:.2f}s bpm={bpm} style={style}", file=sys.stderr)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: bgm_engine.py <out.wav> <duration> <bpm> <style>", file=sys.stderr)
        sys.exit(2)
    gen(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "hot")
