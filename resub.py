# -*- coding: utf-8 -*-
"""只换字幕，不重剪。

已经剪好的成片在 work/style_<平台>/joined.mp4（转场拼接完成、还没烧字幕）。
这个脚本直接拿它重新生成 ASS 花字 + 重新烧录 + 复用已有 BGM，几十秒出一条，
不需要重新选段、重新转场、重新裁音乐。

用法：
  python resub.py                        # 用 subtitles.json 换全部四条
  python resub.py --only douyin          # 只换一条
  python resub.py --lines work/new.json  # 指定别的字幕文件
  python resub.py --tag                 # 连右下角角标一起换（default 保留原角标）

subtitles.json 格式（放工程根，用记事本改）：
  {
    "douyin":     ["第一句", "第二句", "第三句", "第四句", "第五句"],
    "xiaohongshu":[...],
    "shipinhao":  [...],
    "kuaishou":   [...]
  }
条数不用和原来一致：给几句就排几句，会自动按片段时长均分。

输出：outbox/styles/resub/<平台>_<中文名>_v2.mp4（不覆盖原片）
      manifest 追加 "resub": true 与新的 beats
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from utils import load_config, ensure_dirs, log, run, find_ffmpeg, ffprobe_duration, ROOT
from styles import STYLE_PROFILES, PLATFORM_ORDER
import make_styles as ms

LINES_FILE = "subtitles.json"
OUT_SUBDIR = Path("outbox") / "styles" / "resub"


def load_lines(path: Path) -> dict:
    if not path.exists():
        log(f"找不到字幕文件: {path}", "ERR")
        log('先建一个 subtitles.json，格式：{"douyin": ["句子1", "句子2"], ...}', "INFO")
        sys.exit(2)
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    out = {}
    for k, v in raw.items():
        if isinstance(v, str):
            v = [x.strip() for x in v.splitlines() if x.strip()]
        out[k] = [str(x).strip() for x in v if str(x).strip()]
    return out


def check_lines(lines: list[str], platform: str) -> list[str]:
    """字幕条数不设死，但给几条提醒：太少撑不满，太长一行读不完。"""
    if not lines:
        log(f"[{platform}] 没有字幕，跳过", "WARN")
        return []
    if len(lines) > 12:
        log(f"[{platform}] 字幕 {len(lines)} 条偏多，单条停留会短于 1 秒", "WARN")
    for i, t in enumerate(lines):
        if len(t) > 18:
            log(f"[{platform}] 第 {i + 1} 条 {len(t)} 字偏长: {t[:12]}…", "WARN")
    return lines


def _find_track(cfg: dict, filename: str) -> Path | None:
    """在 bgm 根目录和 bgm/jianying 子目录找曲子。"""
    bgm_dir = Path(cfg.get("paths", {}).get("bgm", "")) if cfg.get("paths", {}).get("bgm") else None
    if not bgm_dir:
        return None
    for cand in (bgm_dir / filename, bgm_dir / "jianying" / filename):
        if cand.exists():
            return cand
    return None


def resub_one(platform: str, lines: list[str], cfg: dict, outdir: Path,
              music: dict | None = None, tag: str = "") -> dict | None:
    """换字幕重出一条。

    music: 可选 {"file": "jy_09.mp3", "start": 8, "volume": 0.85}。
           给了就按它裁副歌覆盖 BGM（每日音乐轮换用），不给就用原 bgm_clip.mp3。
    """
    work = ROOT / "work" / f"style_{platform}"
    joined = work / "joined.mp4"
    if not joined.exists():
        log(f"[{platform}] 没有 {joined}，这一条得重新剪（make_styles.py --only {platform}）", "ERR")
        return None

    style = dict(STYLE_PROFILES[platform])
    style["beats"] = lines
    ffmpeg = find_ffmpeg(cfg)
    total_dur = ffprobe_duration(str(joined), ffmpeg)

    ass = ms.build_ass(style, work, total_dur)
    log(f"[{platform}] 新 ASS: {len(lines)} 条 / 总时长 {total_dur:.1f}s")

    subbed = ms.burn_subs_mg(ffmpeg, joined, ass, style, work, total_dur)

    music_info = None
    if music:
        track = _find_track(cfg, music["file"])
        if track:
            bgm = work / f"bgm_resub{tag}.mp3"
            run([ffmpeg, "-y", "-ss", str(music.get("start", 0)), "-i", str(track),
                 "-t", f"{total_dur + 1.0:.2f}", "-c:a", "libmp3lame", "-q:a", "2", str(bgm)])
            if music.get("volume") is not None:
                style["bgm_volume"] = music["volume"]
            music_info = {"track": music["file"], "start": music.get("start", 0),
                          "volume": music.get("volume")}
            log(f"[{platform}] 音乐覆盖: {music['file']} @{music.get('start', 0)}s", "OK")
        else:
            log(f"[{platform}] 找不到音乐 {music['file']}，用原BGM", "WARN")
    if not music_info:
        bgm = work / "bgm_clip.mp3"
        if not bgm.exists():
            bgm = ms.get_bgm(cfg, style, platform, total_dur, work, ffmpeg)
    audioed = ms.add_audio(ffmpeg, subbed, bgm, style, work)

    outdir.mkdir(parents=True, exist_ok=True)
    final = outdir / f"{platform}_{style['platform']}_v2.mp4"
    run([ffmpeg, "-y", "-i", str(audioed), "-c", "copy", str(final)])
    cover = ms.make_cover(ffmpeg, final, style, work,
                          outdir / f"{platform}_{style['platform']}_v2_cover.jpg")

    dur = ffprobe_duration(str(final), ffmpeg)
    size_mb = final.stat().st_size / 1024 / 1024
    log(f"[{platform}] 完成: {final.name} ({dur:.2f}s / {size_mb:.1f}MB)", "OK")
    return {
        "platform": platform, "label": style["label"],
        "video": str(final), "cover": str(cover), "duration": round(dur, 2),
        "beats": lines, "tag_text": style.get("tag_text"),
        "resub": True, "music": music_info,
    }


def main():
    ap = argparse.ArgumentParser(description="只换字幕，不重剪")
    ap.add_argument("--only", help="只处理某平台，逗号分隔")
    ap.add_argument("--lines", default=LINES_FILE, help="字幕 JSON 路径")
    ap.add_argument("--out", default=str(OUT_SUBDIR), help="输出目录")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    all_lines = load_lines(ROOT / args.lines)

    targets = ([p.strip() for p in args.only.split(",")] if args.only
               else [p for p in PLATFORM_ORDER if p in all_lines])

    outdir = ROOT / args.out
    results = []
    for p in targets:
        if p not in STYLE_PROFILES:
            log(f"未知平台: {p}", "ERR")
            continue
        lines = check_lines(all_lines.get(p, []), p)
        if not lines:
            continue
        r = resub_one(p, lines, cfg, outdir)
        if r:
            results.append(r)

    if not results:
        log("一条都没生成", "ERR")
        sys.exit(1)

    mf = outdir / "manifest_resub.json"
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"全部完成，清单: {mf}", "OK")
    for r in results:
        log(f"  {r['platform']:12s} {r['duration']:>6.2f}s  {Path(r['video']).name}", "OK")


if __name__ == "__main__":
    main()
