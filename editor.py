# -*- coding: utf-8 -*-
"""合成模块：按剪辑计划裁切→拼接→竖屏适配→烧字幕→混BGM→出封面。
全部基于 ffmpeg（系统自带 9.0）。
关键：保留原声（口播是核心内容），BGM 只做低音量混音叠加，不替换人声。
"""
from __future__ import annotations

import random
from pathlib import Path

from utils import log, run, find_ffmpeg, ffprobe_duration, write_srt


def compose(source: str | Path, plan: dict, segments: list[dict], cfg: dict,
            work_dir: str | Path, out_path: str | Path) -> dict:
    """执行剪辑合成，返回产物路径字典。"""
    source = Path(source)
    work = Path(work_dir)
    out = Path(out_path)
    work.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(cfg)
    keep = plan["keep"]

    log(f"合成开始: {len(keep)} 段 -> {out.name}")
    stem = out.stem

    # 探测源是否有音轨
    has_audio = _has_audio(source, ffmpeg)
    log(f"源音轨: {'有' if has_audio else '无'}")

    # 1) 逐段裁切并重编码（音视频一起，保证精确拼接）
    parts = []
    for i, (st, en) in enumerate(keep):
        part = work / f"{stem}_part{i:03d}.mp4"
        cmd = [
            ffmpeg, "-y", "-ss", f"{st:.3f}", "-to", f"{en:.3f}", "-i", str(source),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1",
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-ar", "44100", "-ac", "2"]
        else:
            cmd += ["-an"]
        cmd.append(str(part))
        run(cmd)
        parts.append(part)
        log(f"  片段 {i+1}/{len(keep)} 完成 ({en-st:.1f}s)", "OK")

    # 2) 拼接（音视频一起 copy）
    concat_list = work / f"{stem}_concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    joined = work / f"{stem}_joined.mp4"
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(joined)])

    # 3) 字幕：按 keep 时间段重新映射转录时间轴
    srt_path = work / f"{stem}.srt"
    remapped = _remap_captions(segments, keep)
    caption_cfg = cfg.get("caption", {})
    if caption_cfg.get("enabled", True) and remapped:
        write_srt(remapped, srt_path, caption_cfg.get("max_chars_per_line", 16))

    current = joined

    # 4) 烧字幕（保留音频）
    if caption_cfg.get("burn_in", True) and srt_path.exists():
        burned = work / f"{stem}_burned.mp4"
        style = (
            f"FontName=Microsoft YaHei,"
            f"FontSize={caption_cfg.get('font_size', 42)},"
            f"PrimaryColour={caption_cfg.get('font_color', '&H00FFFFFF')},"
            f"Outline={caption_cfg.get('outline', 2)},Shadow=0,"
            f"Alignment=2,MarginV=160"
        )
        srt_esc = _escape_ffmpeg_path(srt_path)
        run([ffmpeg, "-y", "-i", str(current),
             "-vf", f"subtitles='{srt_esc}':force_style='{style}'",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-pix_fmt", "yuv420p", "-c:a", "copy", str(burned)])
        current = burned

    # 5) BGM 混音（叠加在原声之上，不替换人声）
    final = out
    bgm_cfg = cfg.get("paths", {}).get("bgm", "")
    bgm_files = list(Path(bgm_cfg).glob("*")) if bgm_cfg and Path(bgm_cfg).exists() else []
    audio_files = [f for f in bgm_files if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}]
    mix_bgm = cfg.get("audio", {}).get("bgm_volume", 0.12) > 0 and audio_files

    if mix_bgm:
        bgm = random.choice(audio_files)
        vol = cfg.get("audio", {}).get("bgm_volume", 0.12)
        if has_audio:
            # 原声 + BGM 混音：BGM 低音量淡入淡出，不盖人声
            fc = (f"[1:a]volume={vol},afade=t=in:st=0:d=1[bg];"
                  f"[0:a]volume=1.0[vo];"
                  f"[vo][bg]amix=inputs=2:duration=first:dropout_transition=0[a]")
            run([ffmpeg, "-y", "-i", str(current), "-stream_loop", "-1", "-i", str(bgm),
                 "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                 "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)])
        else:
            run([ffmpeg, "-y", "-i", str(current), "-stream_loop", "-1", "-i", str(bgm),
                 "-filter_complex", f"[1:a]volume={vol}[a]", "-map", "0:v", "-map", "[a]",
                 "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)])
    else:
        # 无 BGM：直接保留原声；若源本来无声则补静音轨保证平台上传正常
        if has_audio:
            run([ffmpeg, "-y", "-i", str(current), "-c", "copy", str(final)])
        else:
            run([ffmpeg, "-y", "-i", str(current),
                 "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                 "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)])

    # 6) 封面（取第1帧）
    cover_path = out.with_name(f"{stem}_cover.jpg")
    if cfg.get("cover", {}).get("enabled", True):
        run([ffmpeg, "-y", "-i", str(final), "-vframes", "1", "-q:v", "2", str(cover_path)])

    duration = ffprobe_duration(final, ffmpeg)
    log(f"合成完成: {out.name} ({duration:.1f}s), 原声{'保留' if has_audio else '无'}", "OK")
    return {
        "video": str(final), "cover": str(cover_path) if cover_path.exists() else "",
        "srt": str(srt_path) if srt_path.exists() else "", "duration": duration,
        "has_audio": has_audio,
    }


def _has_audio(path: Path, ffmpeg: str) -> bool:
    import subprocess, sys
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    p = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=creationflags)
    return "Audio:" in p.stderr


def _remap_captions(segments: list[dict], keep: list) -> list[dict]:
    """把原时间轴的转录映射成剪辑后相对时间轴的字幕段。"""
    out = []
    offset = 0.0
    for st, en in keep:
        for s in segments:
            ss, se = float(s["start"]), float(s["end"])
            # 与原片段有交集
            a, b = max(ss, st), min(se, en)
            if b > a and s.get("text", "").strip():
                out.append({"start": a - st + offset, "end": b - st + offset,
                            "text": s["text"].strip()})
        offset += en - st
    out.sort(key=lambda x: x["start"])
    return out


def _escape_ffmpeg_path(p: Path) -> str:
    """ffmpeg subtitles filter 的路径转义：Windows 盘符冒号要转义。"""
    s = str(p).replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    return s
