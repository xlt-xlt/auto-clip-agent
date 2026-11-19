# -*- coding: utf-8 -*-
"""主编排：素材 → 转写 → AI决策 → 合成 → 发布 → 归档。
用法：
  python pipeline.py once <素材路径> [--dry-run]   # 处理单个文件
  python pipeline.py process-inbox [--dry-run]      # 处理 inbox 里所有未处理文件
  python pipeline.py watch [--dry-run]              # 监听 inbox 目录（常驻）
  python pipeline.py publish <成片mp4> <plan.json>  # 只发布单个已有成片
  python pipeline.py publish-pending [--dry-run]    # 发布待发布队列（定时用）
  python pipeline.py queue                          # 查看待发布队列
  python pipeline.py login <platform>               # 预登录某平台（首次扫码）
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from utils import (load_config, ensure_dirs, log, is_media, state_key,
                   load_state, save_state, ffprobe_duration, find_ffmpeg)
from transcriber import transcribe_to_json
from brain import decide
from editor import compose
from publisher import PLATFORMS
from publisher.base import ensure_login, finish, PublishResult


PENDING_FILE = "pending_publish.json"


# ---------------- 待发布队列 ----------------

def _pending_path(cfg: dict) -> Path:
    return Path(cfg["paths"]["state"]) / PENDING_FILE


def load_pending(cfg: dict) -> list:
    f = _pending_path(cfg)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_pending(cfg: dict, items: list):
    _pending_path(cfg).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue_pending(cfg: dict, entry: dict):
    """把成片加入待发布队列；按 video 路径去重。"""
    items = load_pending(cfg)
    items = [x for x in items if x.get("video") != entry["video"]]
    items.append(entry)
    save_pending(cfg, items)
    log(f"已加入待发布队列: {Path(entry['video']).name} -> {','.join(entry['platforms'])}")


def publish_pending(cfg: dict, *, dry_run: bool = False):
    """发布队列里的成片；任一平台失败则保留该项以便下次重试。"""
    items = load_pending(cfg)
    if not items:
        log("待发布队列为空")
        return
    remain = []
    for it in items:
        video = it.get("video", "")
        plan_path = it.get("plan_path", "")
        if not Path(video).exists() or not Path(plan_path).exists():
            log(f"队列项产物缺失，丢弃: {video}", "WARN")
            continue
        try:
            plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        except Exception as e:
            log(f"队列项 plan 读取失败，丢弃: {e}", "ERR")
            continue
        failed = []
        for p in it.get("platforms", []):
            fn = PLATFORMS.get(p)
            if not fn:
                continue
            log(f"---- 队列发布 [{p}]: {Path(video).name} ----")
            try:
                r = fn(video, it.get("cover", ""), plan, cfg, dry_run=dry_run)
                log(f"[{p}] ok={r.ok} {r.message}")
                if not r.ok:
                    failed.append(p)
            except Exception as e:
                log(f"[{p}] 发布异常: {e}", "ERR")
                failed.append(p)
        it["failed_platforms"] = failed
        it["last_attempt"] = datetime.now().isoformat(timespec="seconds")
        if failed:
            remain.append(it)  # 保留重试
        else:
            log(f"队列项全部完成，移除: {Path(video).name}", "OK")
    save_pending(cfg, remain)


def show_queue(cfg: dict):
    items = load_pending(cfg)
    if not items:
        log("待发布队列为空")
        return
    log(f"待发布队列（{len(items)} 项）:")
    for i, it in enumerate(items, 1):
        log(f"  {i}. {Path(it.get('video','')).name} "
            f"平台={','.join(it.get('platforms', []))} "
            f"失败={','.join(it.get('failed_platforms', [])) or '无'} "
            f"创建={it.get('created_at','')}")


# ---------------- 主流程 ----------------

def process_one(path: str | Path, cfg: dict, *, dry_run: bool = False) -> dict:
    path = Path(path).resolve()
    if not path.exists():
        log(f"文件不存在: {path}", "ERR")
        return {}
    key = state_key(path)
    processed = load_state(cfg["paths"]["state"])
    if key in processed:
        log(f"已处理过，跳过: {path.name}", "WARN")
        return {}

    log(f"===== 开始处理: {path.name} =====")
    stem = path.stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = Path(cfg["paths"]["work"]) / f"{stem}_{timestamp}"
    work.mkdir(parents=True, exist_ok=True)

    # 1) 转写
    segs_json = work / "transcript.json"
    segments = transcribe_to_json(path, cfg, segs_json)

    # 2) AI 决策
    duration = ffprobe_duration(path, find_ffmpeg(cfg))
    plan = decide(segments, cfg, duration_hint=duration)
    (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"剪辑计划: {len(plan['keep'])} 段, 标题《{plan.get('title')}》")

    # 3) 合成
    out_name = f"{timestamp}_{stem}.mp4"
    out_path = Path(cfg["paths"]["outbox"]) / out_name
    assets = compose(path, plan, segments, cfg, work, out_path)

    # 4) 发布
    pcfg = cfg.get("publish", {})
    results = []
    enabled = [p for p, on in pcfg.get("platforms", {}).items() if on]
    auto = pcfg.get("auto_publish", False)
    if enabled and (auto or dry_run):
        for p in enabled:
            fn = PLATFORMS.get(p)
            if not fn:
                continue
            log(f"---- 发布到 {p} ----")
            r = fn(assets["video"], assets["cover"], plan, cfg, dry_run=dry_run)
            results.append({"platform": p, "ok": r.ok, "message": r.message, "url": r.url})
    elif enabled:
        # 未开自动发布：加入队列，等 daily_publish_time 统一发
        enqueue_pending(cfg, {
            "id": out_name,
            "video": str(assets["video"]),
            "cover": str(assets["cover"]),
            "plan_path": str(work / "plan.json"),
            "platforms": enabled,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

    # 5) 归档
    processed.add(key)
    save_state(cfg["paths"]["state"], processed)
    summary = {
        "source": str(path), "work": str(work), "assets": assets,
        "plan": plan, "publish": results,
    }
    (work / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"===== 处理完成: {out_path.name} =====", "OK")
    return summary


def process_inbox(cfg: dict, *, dry_run: bool = False):
    inbox = Path(cfg["paths"]["inbox"])
    files = [p for p in sorted(inbox.iterdir()) if p.is_file() and is_media(p)]
    if not files:
        log(f"inbox 为空: {inbox}")
        return
    for f in files:
        try:
            process_one(f, cfg, dry_run=dry_run)
        except Exception as e:
            log(f"处理失败 {f.name}: {e}", "ERR")


def watch_inbox(cfg: dict, *, dry_run: bool = False):
    interval = cfg.get("schedule", {}).get("poll_seconds", 20)
    log(f"开始监听 inbox，每 {interval}s 轮询，Ctrl+C 停止")
    while True:
        try:
            process_inbox(cfg, dry_run=dry_run)
        except Exception as e:
            log(f"轮询异常: {e}", "ERR")
        time.sleep(interval)


def publish_only(video: str, plan_path: str, cfg: dict, *, dry_run: bool = False):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    cover = str(Path(video).with_name(Path(video).stem + "_cover.jpg"))
    pcfg = cfg.get("publish", {})
    enabled = [p for p, on in pcfg.get("platforms", {}).items() if on]
    if not enabled:
        log("config.json 中未启用任何平台", "WARN")
        return
    for p in enabled:
        fn = PLATFORMS.get(p)
        if fn:
            r = fn(video, cover, plan, cfg, dry_run=dry_run)
            log(f"[{p}] ok={r.ok} {r.message}")


def login_platform(platform: str, cfg: dict):
    log(f"预登录平台: {platform}（首次需扫码，登录态会持久化）")
    pw, ctx = ensure_login(platform, cfg)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    urls = {
        "douyin": "https://creator.douyin.com/",
        "xiaohongshu": "https://creator.xiaohongshu.com/",
        "shipinhao": "https://channels.weixin.qq.com/",
        "kuaishou": "https://cp.kuaishou.com/",
    }
    page.goto(urls.get(platform, "about:blank"), wait_until="domcontentloaded")
    input("请在浏览器中完成登录，完成后按回车键继续…")
    finish(pw, ctx, PublishResult(platform, True, "登录态已保存"))


def main():
    ap = argparse.ArgumentParser(description="自动剪辑+自动发布智能体")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("process-inbox").add_argument("--dry-run", action="store_true")
    sub.add_parser("watch").add_argument("--dry-run", action="store_true")
    sub.add_parser("publish-pending").add_argument("--dry-run", action="store_true")
    sub.add_parser("queue")
    p_once = sub.add_parser("once")
    p_once.add_argument("path")
    p_once.add_argument("--dry-run", action="store_true")
    p_pub = sub.add_parser("publish")
    p_pub.add_argument("video")
    p_pub.add_argument("plan")
    p_pub.add_argument("--dry-run", action="store_true")
    p_login = sub.add_parser("login")
    p_login.add_argument("platform", choices=list(PLATFORMS.keys()))

    args = ap.parse_args()
    cfg = load_config()
    ensure_dirs(cfg)

    if args.cmd == "once":
        process_one(args.path, cfg, dry_run=args.dry_run)
    elif args.cmd == "process-inbox":
        process_inbox(cfg, dry_run=args.dry_run)
    elif args.cmd == "watch":
        watch_inbox(cfg, dry_run=args.dry_run)
    elif args.cmd == "publish":
        publish_only(args.video, args.plan, cfg, dry_run=args.dry_run)
    elif args.cmd == "publish-pending":
        publish_pending(cfg, dry_run=args.dry_run)
    elif args.cmd == "queue":
        show_queue(cfg)
    elif args.cmd == "login":
        login_platform(args.platform, cfg)


if __name__ == "__main__":
    main()
