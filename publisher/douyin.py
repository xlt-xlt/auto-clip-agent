# -*- coding: utf-8 -*-
"""抖音创作者中心 RPA 发布。首次需手动扫码登录，登录态持久化。"""
from __future__ import annotations

from pathlib import Path

from utils import log
from .base import PublishResult, ensure_login, build_caption, finish

UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"

# 抖音发布页实测结构（probe_douyin.py 输出）：
#   上传后自动跳到 /creator-micro/content/post/video?enter_from=publish_page
#   标题 = <input placeholder="填写作品标题，为作品获得更多流量" class="semi-input">  y≈-324（在视窗上方）
#   简介 = <div contenteditable data-placeholder="添加作品简介" class="zone-container editor-kit-container">  y≈-283
#   发布 = <button class="button-dhlUZE primary-cECiOJ fixed-J9O8Yw">文本「发布」  x354 y788 w120 h32
#   遮罩 = 有「我知道了」按钮(y≈-313)的弹层，需先点掉，否则拦截点击
# 关键坑：标题/简介在视窗上方，loc.is_visible() 返回 False，上一版 _fill 静默跳过 → 发出去是空标题。
TITLE_SELECTORS = ('input[placeholder*="作品标题"]', 'input[placeholder*="标题"]')
BODY_SELECTORS = ('div[data-placeholder="添加作品简介"]',
                  'div.zone-container[contenteditable="true"]',
                  'div[contenteditable="true"]')
DISMISS_SELECTORS = ('button:has-text("我知道了")', 'button:has-text("知道了")')


def _dismiss(page) -> None:
    """点掉「我知道了」等引导弹层，否则会挡住表单与发布按钮。"""
    for sel in DISMISS_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click(timeout=2500, force=True)
                page.wait_for_timeout(600)
                log("[douyin] 已关闭引导弹层")
        except Exception:
            pass


def _fill_verify(page, selectors, text: str, label: str) -> bool:
    """填输入框并回读校验。标题/简介常在视窗上方，必须 scroll_into_view，不能依赖 is_visible。"""
    if not text:
        return False
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if not loc.count():
                continue
            loc.scroll_into_view_if_needed(timeout=4000)
            page.wait_for_timeout(300)
            loc.click(timeout=4000, force=True)
            loc.fill(text, timeout=6000)
            page.wait_for_timeout(400)
            got = ""
            try:
                got = loc.input_value(timeout=1500)
            except Exception:
                try:
                    got = loc.inner_text(timeout=1500)
                except Exception:
                    got = ""
            if got.strip():
                log(f"[douyin] {label} 已填入 {len(got)} 字: {got[:24]!r}", "OK")
                return True
            log(f"[douyin] {label} 回读为空，换下一个 selector", "WARN")
        except Exception as e:
            log(f"[douyin] {label} 填充失败 ({sel}): {str(e)[:80]}", "WARN")
    # JS 兜底：Semi Design 是受控组件，必须用原生 setter + input 事件
    try:
        ok = page.evaluate(
            """([sels, val]) => {
              for (const s of sels) {
                const el = document.querySelector(s);
                if (!el) continue;
                el.scrollIntoView({block: 'center'});
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                  const d = Object.getOwnPropertyDescriptor(
                      window.HTMLInputElement.prototype, 'value');
                  d.set.call(el, val);
                } else {
                  el.focus();
                  document.execCommand('insertText', false, val);
                }
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
              }
              return false;
            }""", [list(selectors), text])
        if ok:
            log(f"[douyin] {label} 已用 JS 兜底写入", "OK")
        return bool(ok)
    except Exception as e:
        log(f"[douyin] {label} JS 兜底失败: {str(e)[:80]}", "ERR")
        return False


def publish_douyin(video: str, cover: str, plan: dict, cfg: dict,
                   dry_run: bool = False) -> PublishResult:
    platform = "douyin"
    result = PublishResult(platform=platform, ok=False)
    if dry_run:
        result.message = f"[dry-run] 跳过真实发布: {Path(video).name}"
        result.ok = True
        return result
    try:
        pw, ctx = ensure_login(platform, cfg)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
        _wait_login(page, platform)

        # 上传视频
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(video)
        log("[douyin] 视频已上传，等待处理…")
        page.wait_for_timeout(12000)

        # 先关掉「我知道了」等弹层
        _dismiss(page)

        # 填标题/文案（标题/简介在视窗上方，必须 force 填 + 回读校验）
        title = plan.get("title", "")[:30]
        caption = build_caption(plan, cfg)
        ok_title = _fill_verify(page, TITLE_SELECTORS, title, "标题")
        page.wait_for_timeout(600)
        ok_body = _fill_verify(page, BODY_SELECTORS, caption, "简介")
        page.wait_for_timeout(800)
        if not ok_title:
            log("[douyin] 标题未填成功，作品将无标题", "WARN")
        if not ok_body:
            log("[douyin] 简介未填成功", "WARN")

        # 定时/立即发布：默认立即
        result.screenshot = _shot(page, cfg, platform, "before_publish")

        # 发布按钮：class 含 primary 且文本「发布」的那个（不要点到左上角「作品发布」）
        btn = page.locator('button.button-dhlUZE.primary-cECiOJ').last
        if not btn.count():
            btn = page.locator('button:has-text("发布")').last
        if btn.count():
            btn.scroll_into_view_if_needed(timeout=4000)
            page.wait_for_timeout(500)
            try:
                btn.click(timeout=8000)
            except Exception:
                btn.click(timeout=8000, force=True)
            log("[douyin] 已点击发布，等待跳转（15s）…")
            page.wait_for_timeout(15000)
            result.url = page.url
            u = result.url.lower()
            # 成功判据：离开 post/video 编辑页，或落在 manage/作品页
            still_editing = "/post/video" in u or "/content/upload" in u
            result.ok = (not still_editing) and any(
                k in u for k in ("manage", "success", "creator-micro/home"))
            if still_editing:
                # 仍在编辑页：读页面提示，多半是校验拦截
                try:
                    tips = page.evaluate(
                        "() => [...document.querySelectorAll('[class*=error],[class*=tip],[class*=warn]')]"
                        ".map(e => (e.innerText||'').trim()).filter(t => t && t.length < 120).slice(0,6)")
                except Exception:
                    tips = []
                result.message = ("点击发布后仍停留编辑页，可能是上传未完成或被校验拦截"
                                  + (f"：{tips}" if tips else ""))
                result.screenshot = _shot(page, cfg, platform, "after_publish")
            else:
                result.message = "已提交发布，跳转至作品页"
                result.screenshot = _shot(page, cfg, platform, "after_publish")
        else:
            result.message = "未找到发布按钮，已停在前置页（截图留证）"
        return finish(pw, ctx, result)
    except Exception as e:
        result.message = f"异常: {e}"
        log(f"[douyin] {result.message}", "ERR")
        return result


def _wait_login(page, platform: str, timeout_ms: int = 300000):
    """若仍在登录/扫码页，等待人工扫码（有头模式）。"""
    page.wait_for_timeout(3000)
    url = page.url.lower()
    if "login" in url or "passport" in url:
        log(f"[{platform}] 检测到未登录，请在打开的浏览器窗口扫码，等待最多 {timeout_ms//1000}s…", "WARN")
        page.wait_for_url(lambda u: "login" not in u.lower() and "passport" not in u.lower(),
                          timeout=timeout_ms)


def _fill(page, selectors: list[str], text: str):
    if not text:
        return
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            try:
                loc.fill(text)
                return
            except Exception:
                pass


def _shot(page, cfg: dict, platform: str, tag: str) -> str:
    try:
        d = Path(cfg["paths"]["logs"]) / "screenshots" / platform
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{tag}_{int(__import__('time').time())}.png"
        page.screenshot(path=str(p), full_page=False)
        return str(p)
    except Exception:
        return ""
