# -*- coding: utf-8 -*-
"""把 captions.py 的标题/文案/话题同步到已生成的 manifest.json。

发布脚本 publish_manifest.py 读的是 outbox/styles/manifest.json 里的
title/caption/hashtags，所以改完文案后跑这个脚本，再发就带上新文案，
不用重新剪片（画面/字幕/音乐一帧不动）。

用法：
  python sync_captions.py                          # 同步主 manifest + 所有 daily manifest
  python sync_captions.py --date 2026-11-19        # 只同步指定日期的 daily manifest
  python sync_captions.py --dry-run                # 只预览改动，不写盘
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from utils import ROOT, log
from captions import CAPTIONS

MAIN = ROOT / "outbox" / "styles" / "manifest.json"
DAILY_DIR = ROOT / "outbox" / "styles" / "daily"


def apply(items: list[dict], dry_run: bool = False) -> int:
    """给一批 manifest 条目套上新文案。返回改动条数。"""
    n = 0
    if not isinstance(items, list):
        return 0
    for it in items:
        p = it.get("platform")
        c = CAPTIONS.get(p)
        if not c:
            continue
        changed = (it.get("title") != c["title"] or
                   it.get("caption") != c["caption"] or
                   it.get("hashtags") != c["hashtags"])
        it["title"] = c["title"]
        it["caption"] = c["caption"]
        it["hashtags"] = list(c["hashtags"])
        if changed:
            n += 1
    return n


def sync_file(path: Path, dry_run: bool = False) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        log(f"读取失败 {path.name}: {e}", "WARN")
        return 0

    # 主 manifest 是 list；daily manifest 是 {"results":[...]}
    if isinstance(data, dict) and "results" in data:
        n = apply(data["results"], dry_run)
    elif isinstance(data, list):
        n = apply(data, dry_run)
    else:
        return 0

    if n and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  [+] {path.relative_to(ROOT)}  更新 {n} 条", "OK")
    elif n and dry_run:
        log(f"  [?] {path.relative_to(ROOT)}  将更新 {n} 条（dry-run）")
    return n


def main():
    ap = argparse.ArgumentParser(description="同步新标题文案到 manifest")
    ap.add_argument("--date", help="只同步指定日期的 daily manifest（YYYY-MM-DD）")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写盘")
    args = ap.parse_args()

    log("=== 同步标题文案（来自 captions.py）===", "OK")
    for p, c in CAPTIONS.items():
        log(f"  [{p}] {c['title']}  | 话题 {len(c['hashtags'])} 个")

    total = 0
    total += sync_file(MAIN, args.dry_run)

    if args.date:
        total += sync_file(DAILY_DIR / args.date / "manifest.json", args.dry_run)
    elif DAILY_DIR.exists():
        for d in sorted(DAILY_DIR.iterdir()):
            if d.is_dir():
                total += sync_file(d / "manifest.json", args.dry_run)

    log(f"共更新 {total} 条文案" + ("（dry-run，未写盘）" if args.dry_run else "。发布脚本可直接用新文案。"), "OK")


if __name__ == "__main__":
    main()
