# -*- coding: utf-8 -*-
"""按 manifest.json 把四条风格化成片发布到四个平台。
每个平台使用 manifest 中各自独立的标题/文案/话题（不是同一套搬运）。
每个平台在独立子进程中发布，避免同进程多次 Playwright 的 asyncio 污染。
用法:
  python publish_manifest.py                 # 真实发布全部四条
  python publish_manifest.py --dry-run       # 仅校验标题/文案/话题构造，不上传
  python publish_manifest.py --only douyin   # 只发布指定平台（内部也用得到）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from utils import ROOT, load_config, ensure_dirs, log
from publisher import PLATFORMS

MANIFEST = ROOT / "outbox" / "styles" / "manifest.json"
LOG_FILE = "publish_log.json"


def publish_one(platform: str, dry_run: bool) -> dict:
    """发布单个平台（在当前进程内，均由 --only 子进程调用）。"""
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    it = next((x for x in items if x["platform"] == platform), None)
    if not it:
        return {"platform": platform, "ok": False, "message": "manifest 无此平台"}

    fn = PLATFORMS.get(platform)
    if not fn:
        return {"platform": platform, "ok": False, "message": "无发布适配器"}

    video = it.get("video", "")
    cover = it.get("cover", "")
    plan = {
        "title": it.get("title", ""),
        "caption": it.get("caption", ""),
        "hashtags": it.get("hashtags", []),
    }
    if not Path(video).exists():
        return {"platform": platform, "ok": False, "message": "视频文件不存在",
                "title": plan["title"]}

    log(f"===== 发布 [{platform}] {it.get('label', '')} =====", "OK")
    log(f"  标题: {plan['title']}")
    log(f"  文案: {plan['caption']}")
    log(f"  话题: {' '.join(plan['hashtags'])}")
    try:
        r = fn(video, cover, plan, load_config(), dry_run=dry_run)
        return {
            "platform": platform, "ok": r.ok, "message": r.message,
            "url": r.url, "screenshot": r.screenshot,
            "title": plan["title"], "caption": plan["caption"],
            "at": datetime.now().isoformat(timespec="seconds"),
        }
    except Exception as e:
        log(f"[{platform}] 发布异常: {e}", "ERR")
        return {"platform": platform, "ok": False, "message": f"异常: {e}",
                "title": plan["title"]}


def main():
    ap = argparse.ArgumentParser(description="按 manifest 发布四平台风格化成片")
    ap.add_argument("--dry-run", action="store_true", help="仅校验，不真实上传")
    ap.add_argument("--only", default="", help="只发布指定平台")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    targets = [args.only] if args.only else [x["platform"] for x in items]

    # 单平台模式：直接发布并把结果落盘（父进程通过文件读取）
    if args.only:
        r = publish_one(args.only, args.dry_run)
        out = ROOT / "state" / f"publish_result_{args.only}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"[{args.only}] {'成功' if r['ok'] else '未成功'}: {r['message']}",
            "OK" if r["ok"] else "WARN")
        return

    # 多平台模式：逐平台起独立子进程，彻底隔离 Playwright 事件循环
    results = []
    for p in targets:
        cmd = [sys.executable, str(ROOT / "publish_manifest.py"), "--only", p]
        if args.dry_run:
            cmd.append("--dry-run")
        log(f">>>> 启动独立进程发布 [{p}] ...", "OK")
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        # 回显子进程输出（关键行）
        for line in proc.stdout.splitlines():
            if any(k in line for k in ("=====", "标题:", "文案:", "话题:", "上传", "发布", "异常", "成功", "[!]", "[-]")):
                log("    " + line)
        rf = ROOT / "state" / f"publish_result_{p}.json"
        if rf.exists():
            try:
                results.append(json.loads(rf.read_text(encoding="utf-8")))
            except Exception:
                pass
        else:
            results.append({"platform": p, "ok": False,
                            "message": f"子进程退出码 {proc.returncode}，无结果文件: {proc.stderr[-300:]}"})

    # 追加到总日志
    logpath = ROOT / "state" / LOG_FILE
    existing = []
    if logpath.exists():
        try:
            existing = json.loads(logpath.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.extend(results)
    logpath.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    log("===== 发布汇总 =====", "OK")
    for r in results:
        log(f"  [{r['platform']}] {'成功' if r['ok'] else '未成功'}: "
            f"{r.get('message', '')}" + (f" | {r.get('url')}" if r.get("url") else ""))


if __name__ == "__main__":
    main()
