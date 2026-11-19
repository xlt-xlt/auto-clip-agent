# -*- coding: utf-8 -*-
"""定时调度守护进程：把"每天投喂→定时发布"真正自动化。

两种模式：
  daemon   常驻：每 poll_seconds 扫 inbox 自动剪辑；每天 daily_publish_time 自动发队列。
  daily    单次：只发布当前待发布队列（给外部定时器如 dsh schedule / Windows 任务计划调用）。

用法：
  python scheduler.py daemon
  python scheduler.py daily
  python scheduler.py --status
"""
from __future__ import annotations

import argparse
from datetime import datetime, time as dtime
from pathlib import Path

from utils import load_config, ensure_dirs, log
from pipeline import process_inbox, publish_pending, show_queue


def _parse_hhmm(s: str) -> dtime:
    h, m = [int(x) for x in s.strip().split(":")[:2]]
    return dtime(hour=h, minute=m)


def daemon(cfg: dict):
    poll = max(5, int(cfg.get("schedule", {}).get("poll_seconds", 20)))
    daily = cfg.get("schedule", {}).get("daily_publish_time", "20:00")
    pub_time = _parse_hhmm(daily)
    log(f"调度守护启动：每 {poll}s 扫 inbox；每天 {daily} 发布队列。Ctrl+C 停止")
    last_pub_date = None
    while True:
        now = datetime.now()
        try:
            # 1) 处理新素材
            process_inbox(cfg)

            # 2) 到点发布（同一天只触发一次）
            if now.time() >= pub_time and last_pub_date != now.date():
                log(f"到达每日发布时间 {daily}，开始发布待发布队列")
                publish_pending(cfg)
                last_pub_date = now.date()
        except KeyboardInterrupt:
            log("调度守护已停止")
            break
        except Exception as e:
            log(f"调度循环异常: {e}", "ERR")
        # 睡到整点边界，避免漂移
        import time as _t
        _t.sleep(poll)


def daily_once(cfg: dict):
    log(f"每日定时发布触发: {datetime.now().isoformat(timespec='seconds')}")
    publish_pending(cfg)
    show_queue(cfg)


def status(cfg: dict):
    log(f"daily_publish_time = {cfg.get('schedule', {}).get('daily_publish_time')}")
    log(f"poll_seconds = {cfg.get('schedule', {}).get('poll_seconds')}")
    show_queue(cfg)


def main():
    ap = argparse.ArgumentParser(description="定时调度守护进程")
    ap.add_argument("cmd", nargs="?", default="daemon", choices=["daemon", "daily", "status"])
    args = ap.parse_args()
    cfg = load_config()
    ensure_dirs(cfg)
    if args.cmd == "daemon":
        daemon(cfg)
    elif args.cmd == "daily":
        daily_once(cfg)
    else:
        status(cfg)


if __name__ == "__main__":
    main()
