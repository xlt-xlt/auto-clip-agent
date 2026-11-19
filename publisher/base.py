# -*- coding: utf-8 -*-
"""发布基类：共享的浏览器上下文、登录态、文案拼装、截图留证。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

from utils import log


@dataclass
class PublishResult:
    platform: str
    ok: bool
    message: str = ""
    url: str = ""
    screenshot: str = ""


def build_caption(plan: dict, cfg: dict) -> str:
    ccfg = cfg.get("copywriting", {})
    caption = plan.get("caption", "") or ""
    tags = plan.get("hashtags") or ccfg.get("default_hashtags", [])
    template = ccfg.get("caption_template", "{caption}\n{hashtags}")
    return template.format(caption=caption, hashtags=" ".join(tags)).strip()


CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 抹除 Playwright 自动化指纹，避免快手等平台风控拦"跳转地址不合法"
STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
window.chrome = window.chrome || {runtime:{}};
"""

# 逐 selector 找按钮时，视为"发布"类按钮的文本（各平台不一致）
PUBLISH_TEXTS = ("发布", "发表", "立即发布", "发布笔记", "直接发表", "提交")


def ensure_login(platform: str, cfg: dict):
    """返回 (playwright, context)。使用持久化 profile 保留扫码登录态。
    用真实 Chrome 内核 + 抹除自动化痕迹，绕开平台风控。
    """
    pcfg = cfg.get("publish", {}).get("browser", {})
    state = Path(cfg["paths"]["state"])
    profile = state / pcfg.get("profile_dir", "browser_profiles") / platform
    profile.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    kw = dict(
        user_data_dir=str(profile),
        headless=pcfg.get("headless", False),
        slow_mo=pcfg.get("slow_mo_ms", 80),
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        args=["--disable-blink-features=AutomationControlled",
              "--no-first-run", "--no-default-browser-check"],
        ignore_default_args=["--enable-automation",
                             "--enable-blink-features=AutomationControlled"],
    )
    if Path(CHROME_EXE).exists():
        kw["executable_path"] = CHROME_EXE
    ctx = pw.chromium.launch_persistent_context(**kw)
    try:
        ctx.add_init_script(STEALTH_JS)
    except Exception:
        pass
    return pw, ctx


def scroll_to_bottom(page, rounds: int = 6, step_ms: int = 400) -> None:
    """把页面滚到底：发布按钮常在视窗之外，不滚动 Playwright 会报 not visible。

    关键：小红书等站点表单在内部容器（.publish-page）里滚动，光滚 window 没用，
    必须遍历所有 scrollHeight > clientHeight 的元素逐个滚到底，按钮才会被渲染进 DOM。
    """
    SCROLL_ALL = r"""() => {
      const done = [];
      const els = [document.scrollingElement, document.documentElement,
                   document.body, ...document.querySelectorAll('*')];
      for (const e of els) {
        if (!e || !e.scrollHeight) continue;
        if (e.scrollHeight > e.clientHeight + 20) {
          try {
            e.scrollTop = e.scrollHeight;
            done.push(((e.className || e.tagName || '') + '').slice(0, 40));
          } catch (err) {}
        }
      }
      return done;
    }"""
    for _ in range(rounds):
        try:
            page.evaluate("window.scrollBy(0, Math.max(400, window.innerHeight*0.8))")
            page.evaluate(SCROLL_ALL)
        except Exception:
            break
        page.wait_for_timeout(step_ms)
    try:
        page.evaluate("() => { const d=document.scrollingElement||document.documentElement; "
                      "if(d) window.scrollTo(0, d.scrollHeight); }")
        page.evaluate(SCROLL_ALL)
    except Exception:
        pass
    page.wait_for_timeout(800)


def click_publish(page, selectors: list[str], *, wait_ms: int = 6000,
                  scroll: bool = True) -> bool:
    """多重 selector 尝试点击发布按钮：滚动到底 → 可见点击 → force → JS 点击。
    视频号/小红书/快手的发布按钮常在折叠区外或被浮动层遮挡，
    因此先滚动、再用 force / JS 兜底。
    """
    if scroll:
        scroll_to_bottom(page)
    for sel in selectors:
        loc = page.locator(sel).last
        if not loc.count():
            continue
        # 先滚到该元素
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            loc.click(timeout=5000)
            page.wait_for_timeout(wait_ms)
            return True
        except Exception:
            pass
        try:
            loc.click(force=True, timeout=3000)
            page.wait_for_timeout(wait_ms)
            return True
        except Exception:
            pass
        try:
            page.evaluate(
                "sel => { const els=[...document.querySelectorAll(sel)]; "
                "const el=els[els.length-1]; if(el){el.click();} }", sel)
            page.wait_for_timeout(wait_ms)
            return True
        except Exception:
            pass
    return False


def click_by_text(page, texts=PUBLISH_TEXTS, *, wait_ms: int = 6000,
                  scroll: bool = True) -> str:
    """按可见文本兜底点击发布按钮（button / div / span 都可能承载）。
    返回命中的文本，未命中返回空串。
    """
    if scroll:
        scroll_to_bottom(page)
    for t in texts:
        js = (
            "t => { const cand=[...document.querySelectorAll('button,div,span,a')]"
            ".filter(e => { const s=(e.innerText||'').trim(); "
            "  if (s !== t) return false; "
            "  const r=e.getBoundingClientRect(); "
            "  return r.width>0 && r.height>0; }); "
            "  const el=cand[cand.length-1]; if(!el) return false; "
            "  el.scrollIntoView({block:'center'}); el.click(); return true; }"
        )
        try:
            if page.evaluate(js, t):
                page.wait_for_timeout(wait_ms)
                return t
        except Exception:
            pass
    return ""


def finish(pw, ctx, result: PublishResult, *, wait_seconds: int = 0) -> PublishResult:
    if wait_seconds:
        time.sleep(wait_seconds)
    try:
        ctx.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass
    log(f"[{result.platform}] {'发布成功' if result.ok else '发布未完成'}: {result.message}",
        "OK" if result.ok else "WARN")
    return result
