# -*- coding: utf-8 -*-
"""微信视频号助手 RPA 发布。"""
from __future__ import annotations

from pathlib import Path

from utils import log
from .base import (PublishResult, ensure_login, build_caption, finish,
                   click_publish, click_by_text)
from .douyin import _wait_login, _fill, _shot

UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"

PUBLISH_SELECTORS = [
    'button:has-text("直接发表"):not([disabled])',
    'button:has-text("发表"):not([disabled])',
    'button:has-text("发布"):not([disabled])',
    'div[class*="submit"]:has-text("发表")',
]

SUCCESS_HINTS = ("发表成功", "发布成功", "已提交", "审核中")
FAIL_HINTS = ("请填写", "不能为空", "请上传", "描述不能为空")


def _check_success(page) -> tuple[bool, str]:
    for _ in range(12):
        page.wait_for_timeout(1000)
        u = page.url
        if "/post/list" in u or "/platform/home" in u:
            return True, f"已跳转: {u}"
        try:
            txt = page.evaluate(
                "() => (document.body ? document.body.innerText : '').slice(0, 4000)")
        except Exception:
            txt = ""
        for h in SUCCESS_HINTS:
            if h in txt:
                return True, f"页面提示「{h}」"
        for h in FAIL_HINTS:
            if h in txt:
                return False, f"页面提示「{h}」，发布被拦截"
    return False, "点击后未检测到成功提示"


def publish_shipinhao(video: str, cover: str, plan: dict, cfg: dict,
                      dry_run: bool = False) -> PublishResult:
    platform = "shipinhao"
    result = PublishResult(platform=platform, ok=False)
    if dry_run:
        result.ok = True
        result.message = f"[dry-run] 跳过真实发布: {Path(video).name}"
        return result
    try:
        pw, ctx = ensure_login(platform, cfg)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
        _wait_login(page, platform)

        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(video)
        log("[shipinhao] 视频已上传，等待处理…")
        page.wait_for_timeout(9000)

        caption = build_caption(plan, cfg)
        _fill(page, ['div[contenteditable="true"]', 'textarea',
                     'input[placeholder*="描述"]'], caption)

        if cover and Path(cover).exists():
            try:
                ci = page.locator('input[type="file"]').nth(1)
                if ci.count():
                    ci.set_input_files(cover, timeout=5000)
                    page.wait_for_timeout(1500)
            except Exception:
                pass

        result.screenshot = _shot(page, cfg, platform, "before_publish")

        ok = click_publish(page, PUBLISH_SELECTORS, wait_ms=3000)
        if not ok:
            hit = click_by_text(page, wait_ms=3000)
            ok = bool(hit)
            if hit:
                log(f"[shipinhao] 按文本点到发表按钮: {hit}", "OK")

        if ok:
            result.url = page.url
            success, why = _check_success(page)
            result.ok = success
            result.message = why
            if not success:
                result.screenshot = _shot(page, cfg, platform, "after_publish")
        else:
            result.url = page.url
            result.message = "未找到发表按钮，已停在前置页（截图留证）"
        return finish(pw, ctx, result)
    except Exception as e:
        result.message = f"异常: {e}"
        log(f"[shipinhao] {result.message}", "ERR")
        return result
