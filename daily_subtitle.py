# -*- coding: utf-8 -*-
"""每天自动换一种字幕风格（确定性轮换，不重剪）。

原理：
  style_index = 日期.toordinal() % 风格套数   → 每天一种，相邻两天不重复，重启不丢。
  选中风格后复用 resub.py 的「只换字幕不重剪」链路，几十秒出四条，画面一帧不动。

用法：
  python daily_subtitle.py                  # 出今天（按日期自动选风格）
  python daily_subtitle.py --date 2026-11-22 # 补做/试做指定日期
  python daily_subtitle.py --preview         # 只看今天是什么风格 + 字幕，不出片
  python daily_subtitle.py --calendar 7      # 看未来 7 天排期，确认不重复
  python daily_subtitle.py --only douyin     # 今天只出抖音
  python daily_subtitle.py --force           # 同一天已出过也强制重出

产物：outbox/styles/daily/YYYY-MM-DD/<平台>_<中文名>_v2.mp4 + 封面 + manifest.json
留档：state/daily_subtitle_history.json（每天用了哪套风格，方便回查）
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from utils import load_config, ensure_dirs, log, ROOT
from styles import PLATFORM_ORDER
from subtitle_styles import STYLES, pick_for_date as pick_subtitle_for_date, style_index
from music_styles import BGM_PLANS, pick_for_date as pick_music_for_date
import resub

CFG_KEY = "subtitle_rotation"
HISTORY = ROOT / "state" / "daily_subtitle_history.json"


def _style_for(d: date) -> dict:
    return pick_subtitle_for_date(d)


def _music_for(d: date) -> dict:
    return pick_music_for_date(d)


def lines_for(style: dict) -> dict:
    """把风格里的四平台字幕抽成 resub 能读的 {platform: [lines]}。"""
    return {p: list(style["lines"].get(p, [])) for p in PLATFORM_ORDER}


def preview(d: date):
    s = _style_for(d)
    m = _music_for(d)
    idx = style_index(d)
    log(f"{d.isoformat()} → 字幕第 {idx + 1}/{len(STYLES)} 套: {s['name']}（{s['key']}）")
    log(f"  {s['desc']}")
    for p in PLATFORM_ORDER:
        log(f"  [{p}] " + " / ".join(s["lines"].get(p, [])))
    log(f"音乐: {m['name']}（{m['key']}）— {m['desc']}")
    for p in PLATFORM_ORDER:
        f, sec, vol = m["tracks"].get(p, ("-", 0, None))
        log(f"  [{p}] {f} @{sec}s vol={vol}")


def calendar(days: int, start: date):
    log(f"未来 {days} 天排期（字幕周期 {len(STYLES)} 天 / 音乐周期 {len(BGM_PLANS)} 天）:")
    seen_s, seen_m = {}, {}
    for i in range(days):
        d = start + timedelta(days=i)
        s, m = _style_for(d), _music_for(d)
        sm = "" if s["key"] not in seen_s else f"  ←字幕隔{i - seen_s[s['key']]}天重复"
        mm = "" if m["key"] not in seen_m else f"  ←音乐隔{i - seen_m[m['key']]}天重复"
        log(f"  {d.isoformat()}  字幕:{s['name']:<6s}[{s['key']}]{sm}  音乐:{m['name']:<6s}[{m['key']}]{mm}")
        seen_s.setdefault(s["key"], i)
        seen_m.setdefault(m["key"], i)
    dup_s = [(start + timedelta(days=i)).isoformat()
             for i in range(1, days)
             if style_index(start + timedelta(days=i)) == style_index(start + timedelta(days=i - 1))]
    log("字幕结论: " + ("相邻两天无重复 ✓" if not dup_s else f"发现重复: {dup_s}"), "OK" if not dup_s else "WARN")


def _load_history() -> dict:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    return {}


def _save_history(h: dict):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")


def run_once(cfg: dict, d: date | None = None, only: str | None = None,
             force: bool = False, outdir: Path | None = None) -> list[dict] | None:
    """按日期选风格 → 只换字幕出片。返回本次结果列表。"""
    d = d or date.today()
    style = _style_for(d)
    music = _music_for(d)
    key = d.isoformat()

    hist = _load_history()
    if key in hist and not force and not only:
        log(f"{key} 已出过（字幕 {hist[key].get('style_name')} / 音乐 {hist[key].get('music_name')}），跳过。要重出加 --force", "WARN")
        return None

    log(f"=== {key} 字幕: {style['name']} [{style['key']}] + 音乐: {music['name']} [{music['key']}] ===", "OK")
    lines = lines_for(style)
    # 临时字幕文件落在 state/daily_subtitle/，留档当天用了什么字和曲子
    tmp = ROOT / "state" / "daily_subtitle" / f"{key}.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"date": key, "style": style["key"],
                               "style_name": style["name"], "lines": lines,
                               "music": music["key"], "music_name": music["name"],
                               "tracks": music["tracks"]},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    out = outdir or (ROOT / cfg.get(CFG_KEY, {}).get("outdir",
                                                     "outbox/styles/daily")) / key
    targets = [p.strip() for p in only.split(",")] if only else list(PLATFORM_ORDER)
    results = []
    for p in targets:
        if p not in PLATFORM_ORDER:
            log(f"未知平台: {p}", "ERR")
            continue
        checked = resub.check_lines(lines.get(p, []), p)
        if not checked:
            continue
        # 当天音乐方案里这一平台的 (文件, 起始秒, 音量) → resub 的 music dict
        spec = music["tracks"].get(p)
        music_cfg = None
        if spec:
            f, sec, vol = spec
            music_cfg = {"file": f, "start": sec, "volume": vol}
        r = resub.resub_one(p, checked, cfg, out, music=music_cfg, tag=music["key"])
        if r:
            r["date"] = key
            r["style_key"] = style["key"]
            r["style_name"] = style["name"]
            r["music_key"] = music["key"]
            r["music_name"] = music["name"]
            results.append(r)

    if not results:
        log("一条都没生成（检查 work/style_<平台>/joined.mp4 是否还在）", "ERR")
        return None

    mf = out / "manifest.json"
    mf.write_text(json.dumps({"date": key, "style": style["key"],
                              "style_name": style["name"],
                              "music": music["key"], "music_name": music["name"],
                              "results": results},
                             ensure_ascii=False, indent=2), encoding="utf-8")

    hist[key] = {"style": style["key"], "style_name": style["name"],
                 "music": music["key"], "music_name": music["name"],
                 "count": len(results), "at": datetime.now().isoformat(timespec="seconds")}
    _save_history(hist)
    log(f"{key} 完成 {len(results)} 条 → {out}", "OK")
    for r in results:
        log(f"  [{r['style_name']}+{r['music_name']}] {r['platform']:<12s} {r['duration']:>6.2f}s  {Path(r['video']).name}", "OK")
    return results


def main():
    ap = argparse.ArgumentParser(description="每天自动换字幕风格（确定性轮换）")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--preview", action="store_true", help="只看风格和字幕，不出片")
    ap.add_argument("--calendar", type=int, metavar="N", help="看未来 N 天排期")
    ap.add_argument("--only", help="只出某平台，逗号分隔")
    ap.add_argument("--force", action="store_true", help="同一天已出过也强制重出")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)

    if args.calendar:
        calendar(args.calendar, date.today())
        return
    d = date.fromisoformat(args.date) if args.date else date.today()
    if args.preview:
        preview(d)
        return
    run_once(cfg, d=d, only=args.only, force=args.force)


if __name__ == "__main__":
    main()
