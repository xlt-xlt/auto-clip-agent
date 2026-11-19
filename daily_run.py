# -*- coding: utf-8 -*-
"""每日全自动闭环：扫 inbox 新素材 → 剪四条 → 换当天的字幕风格 + 音乐方案。

被定时调度（dsh schedule / Windows 任务计划）每天调用一次。
一天只跑一次，靠 state/daily_run_history.json 去重；--force 可强制重跑。

流程：
  1. 扫 inbox 的 mp4。有新素材 → 复制到 work/src_YYYYMMDD/ → 调 make_styles.py 剪片。
  2. 没有新素材但 work/style_<平台>/joined.mp4 还在 → 直接用它换字幕。
  3. 调 daily_subtitle.run_once()：按今天日期确定性选一套字幕风格，只换字幕重出四条。
  4. 产物 outbox/styles/daily/YYYY-MM-DD/ + 历史留档。

用法：
  python daily_run.py                 # 今天：有新素材就剪+换字幕，没有就只换字幕
  python daily_run.py --force         # 今天已跑过也重跑
  python daily_run.py --no-cut        # 跳过剪片，只用现有 joined.mp4 换字幕
  python daily_run.py --date 2026-11-22
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from utils import load_config, ensure_dirs, log, ROOT, VIDEO_EXT
import daily_subtitle

HISTORY = ROOT / "state" / "daily_run_history.json"


def _load_hist() -> dict:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    return {}


def _save_hist(h: dict):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")


def _inbox_new_videos(cfg: dict, since: date) -> list[Path]:
    inbox = ROOT / cfg.get("paths", {}).get("inbox", "inbox")
    if not inbox.exists():
        return []
    out = []
    for f in sorted(inbox.iterdir()):
        if f.suffix.lower() in VIDEO_EXT:
            out.append(f)
    return out


def _joined_exists() -> bool:
    from styles import PLATFORM_ORDER
    return all((ROOT / "work" / f"style_{p}" / "joined.mp4").exists()
               for p in PLATFORM_ORDER[:1])  # 有一条就说明剪过片


def cut_today(d: date, videos: list[Path]) -> bool:
    """把 inbox 素材隔离到 work/src_YYYYMMDD 并调 make_styles 剪片。"""
    src = ROOT / "work" / f"src_{d.strftime('%Y%m%d')}"
    src.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in videos:
        dst = src / f.name
        if not dst.exists():
            shutil.copy2(f, dst)
            n += 1
    log(f"隔离今日素材 {n} 个到 {src}")
    cmd = [sys.executable, "make_styles.py", "--src", str(src.relative_to(ROOT))]
    log(f"剪片: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        log("剪片失败（make_styles 退出码非 0）", "ERR")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="每日全自动：剪片 + 换当天风格字幕")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--force", action="store_true", help="今天已跑过也重跑")
    ap.add_argument("--no-cut", action="store_true", help="跳过剪片，只用现有 joined.mp4 换字幕")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    d = date.fromisoformat(args.date) if args.date else date.today()
    key = d.isoformat()

    hist = _load_hist()
    if key in hist and not args.force:
        log(f"{key} 今日闭环已跑过（{hist[key].get('style_name')}, {hist[key].get('at')}），跳过。--force 可重跑", "WARN")
        return

    videos = _inbox_new_videos(cfg, d)
    log(f"=== 每日闭环 {key}：inbox 素材 {len(videos)} 个 ===")

    if videos and not args.no_cut:
        if not cut_today(d, videos):
            log("剪片失败，本次终止", "ERR")
            sys.exit(1)
    elif not _joined_exists():
        log("inbox 无新素材，且 work/style_*/joined.mp4 不存在；今天没片可换字幕。先发素材或跑 make_styles.py", "ERR")
        sys.exit(2)
    else:
        log("无新素材，使用现有 joined.mp4 直接换当天风格字幕")

    results = daily_subtitle.run_once(cfg, d=d, force=args.force)
    if not results:
        log("字幕轮换没产出成片", "ERR")
        sys.exit(3)

    hist[key] = {
        "style_name": results[0].get("style_name"),
        "style_key": results[0].get("style_key"),
        "music_name": results[0].get("music_name"),
        "music_key": results[0].get("music_key"),
        "count": len(results), "videos": len(videos),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_hist(hist)
    log(f"每日闭环 {key} 全部完成：{len(results)} 条 → outbox/styles/daily/{key}/", "OK")


if __name__ == "__main__":
    main()
