# -*- coding: utf-8 -*-
"""只换背景音乐，不重剪、不动字幕和画面。

work/style_<平台>/subbed_mg.mp4 是「已烧字幕 + MG进度条 + 无音轨」的干净画面。
这个脚本直接拿它，按指定音乐方案裁一段新 BGM 盖上去，几十秒出一条，
选段/转场/字幕/画面全部不变。

用法：
  python rebgm.py --plan energy              # 用"燃爆节奏"方案换全部四条
  python rebgm.py --plan soft --only douyin  # 只换一条
  python rebgm.py --list                     # 列出全部音乐方案
  python rebgm.py --file jy_09.mp3 --start 8 # 直接指定一首曲子（四平台通用）
  python rebgm.py --calendar 5               # 看未来 5 天音乐排期

输出：outbox/styles/rebgm/<方案key>/<平台>_<中文名>_<方案key>.mp4
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from utils import load_config, ensure_dirs, log, run, find_ffmpeg, ffprobe_duration, ROOT
from styles import STYLE_PROFILES, PLATFORM_ORDER
import make_styles as ms
from music_styles import BGM_PLANS, pick_for_date, plan_index, by_key


def list_plans():
    log("可用音乐方案:")
    for i, p in enumerate(BGM_PLANS):
        log(f"  [{i + 1}] {p['name']:<8s} [{p['key']}]  {p['desc']}")
        for plat, (f, s, v) in p["tracks"].items():
            log(f"        {plat:<12s} {f} @{s}s  vol={v}")


def music_calendar(days: int, start: date):
    log(f"未来 {days} 天音乐排期（周期 {len(BGM_PLANS)} 天）:")
    for i in range(days):
        d = start + timedelta(days=i)
        p = pick_for_date(d)
        log(f"  {d.isoformat()}  {p['name']:<8s} [{p['key']}]")


def _find_track(cfg: dict, filename: str) -> Path | None:
    bgm_dir = Path(cfg["paths"].get("bgm", "")) if cfg["paths"].get("bgm") else None
    if not bgm_dir:
        return None
    for cand in (bgm_dir / filename, bgm_dir / "jianying" / filename):
        if cand.exists():
            return cand
    return None


def rebgm_one(platform: str, track_file: str, start: int, vol: float | None,
              cfg: dict, outdir: Path, tag: str) -> dict | None:
    work = ROOT / "work" / f"style_{platform}"
    subbed = work / "subbed_mg.mp4"
    if not subbed.exists():
        log(f"[{platform}] 没有 {subbed.name}，先跑一次 resub.py 生成烧好字幕的画面", "ERR")
        return None

    track = _find_track(cfg, track_file)
    if not track:
        log(f"[{platform}] 找不到曲子 {track_file}", "ERR")
        return None

    ffmpeg = find_ffmpeg(cfg)
    total_dur = ffprobe_duration(str(subbed), ffmpeg)

    # 按方案裁副歌段
    clip = work / f"bgm_{tag}.mp3"
    run([ffmpeg, "-y", "-ss", str(start), "-i", str(track),
         "-t", f"{total_dur + 1.0:.2f}", "-c:a", "libmp3lame", "-q:a", "2", str(clip)])
    log(f"[{platform}] BGM: {track_file} @{start}s")

    style = dict(STYLE_PROFILES[platform])
    if vol is not None:
        style["bgm_volume"] = vol
    audioed = ms.add_audio(ffmpeg, subbed, clip, style, work)

    outdir.mkdir(parents=True, exist_ok=True)
    final = outdir / f"{platform}_{style['platform']}_{tag}.mp4"
    run([ffmpeg, "-y", "-i", str(audioed), "-c", "copy", str(final)])
    cover = ms.make_cover(ffmpeg, final, style, work,
                          outdir / f"{platform}_{style['platform']}_{tag}_cover.jpg")

    dur = ffprobe_duration(str(final), ffmpeg)
    size_mb = final.stat().st_size / 1024 / 1024
    log(f"[{platform}] 完成: {final.name} ({dur:.2f}s / {size_mb:.1f}MB)", "OK")
    return {
        "platform": platform, "label": style["label"], "tag": tag,
        "track": track_file, "start": start, "volume": vol,
        "video": str(final), "cover": str(cover),
        "duration": round(dur, 2),
    }


def main():
    ap = argparse.ArgumentParser(description="只换背景音乐，不重剪不动字幕")
    ap.add_argument("--plan", help="方案 key（见 --list）")
    ap.add_argument("--file", help="直接指定曲子文件名（四平台通用）")
    ap.add_argument("--start", type=int, default=0, help="起始秒（配合 --file）")
    ap.add_argument("--volume", type=float, help="音量覆盖（配合 --file）")
    ap.add_argument("--only", help="只换某平台，逗号分隔")
    ap.add_argument("--list", action="store_true", help="列出全部方案")
    ap.add_argument("--calendar", type=int, metavar="N", help="看未来 N 天音乐排期")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)

    if args.list:
        list_plans()
        return
    if args.calendar:
        music_calendar(args.calendar, date.today())
        return

    if args.file:
        tag = Path(args.file).stem
        plan = {"key": tag, "name": tag, "tracks": {
            p: (args.file, args.start, args.volume) for p in PLATFORM_ORDER}}
    elif args.plan:
        plan = by_key(args.plan)
        if not plan:
            log(f"没有方案 {args.plan}，用 --list 看可用方案", "ERR")
            return
        tag = plan["key"]
    else:
        plan = pick_for_date(date.today())
        tag = plan["key"]
        log(f"未指定方案，用今天的: {plan['name']} [{tag}]")

    outdir = ROOT / "outbox" / "styles" / "rebgm" / tag
    targets = [p.strip() for p in args.only.split(",")] if args.only else list(PLATFORM_ORDER)
    results = []
    for p in targets:
        if p not in PLATFORM_ORDER:
            log(f"未知平台: {p}", "ERR")
            continue
        spec = plan["tracks"].get(p)
        if not spec:
            log(f"[{p}] 方案里没有这一平台的曲子，跳过", "WARN")
            continue
        f, s, v = spec
        r = rebgm_one(p, f, s, v, cfg, outdir, tag)
        if r:
            results.append(r)

    if not results:
        log("一条都没生成", "ERR")
        return

    mf = outdir / "manifest.json"
    mf.write_text(__import__("json").dumps(
        {"tag": tag, "name": plan["name"], "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"全部完成 {len(results)} 条 → {outdir}", "OK")
    for r in results:
        log(f"  [{r['track']}] {r['platform']:<12s} {r['duration']:>6.2f}s  {Path(r['video']).name}", "OK")


if __name__ == "__main__":
    main()
