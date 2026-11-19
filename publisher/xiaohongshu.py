# -*- coding: utf-8 -*-
"""小红书创作者中心 RPA 发布。"""
from __future__ import annotations

from pathlib import Path

from utils import log
from .base import (PublishResult, ensure_login, build_caption, finish,
                   click_publish, scroll_to_bottom)
from .douyin import _wait_login, _fill, _shot

UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"

# 小红书发布按钮是自定义元素 <xhs-publish-btn submit-text="发布" save-text="暂存离开">，
# 内部 DOM 是【空的】（innerHTML=""），子节点由 Vue 运行时异步挂载、且不在 querySelectorAll('button')
# 的结果里（页面 button 总数仅 9 个），也没有 shadowRoot。
# 因此 selector / innerText 全都抓不到它 —— 唯一可靠的路径是：
#   1) 找到 <xhs-publish-btn>，取它的 bounding box；
#   2) 用真实鼠标坐标点它【右侧】的「发布」按钮（左侧是「暂存离开」）。
# 实测该元素 box = x331 y810 w680 h90，红「发布」在相对 x≈0.60、垂直居中处。
FIND_PUBLISH_BTN = r"""() => {
  const el = document.querySelector('xhs-publish-btn');
  if (!el) return null;
  el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  return {
    x: r.x, y: r.y, w: r.width, h: r.height,
    publish: el.getAttribute('is-publish'),
    disabled: el.getAttribute('submit-disabled'),
    submitText: el.getAttribute('submit-text'),
  };
}"""

SUCCESS_HINTS = ("发布成功", "提交成功", "笔记发布成功", "审核中", "已发布")
FAIL_HINTS = ("请填写", "不能为空", "请上传", "图片不能为空", "标题不能为空")

# 小红书真实表单结构（probe 实测）：
#   标题 = <input placeholder="填写标题会有更多赞哦" class="d-text">  (x355 y632 w500 h24)
#   正文 = <div class="tiptap ProseMirror" contenteditable="true">  (x355 y676 w632 h140)
# 注意：_fill 里 loc.is_visible() 对标题 input 常返回 False（在视窗滚动区外），
# 上一版因此静默跳过 → 发出去的笔记「无笔记标题」。这里不判可见性，直接填+回读校验。
TITLE_SELECTORS = ('input[placeholder*="标题"]', 'input[placeholder*="赞"]',
                   'input[placeholder*="填写标题"]')
BODY_SELECTORS = ('div.tiptap.ProseMirror', 'div[contenteditable="true"]')


def _fill_xhs(page, selectors, text: str, label: str) -> bool:
    """填一个输入框并回读校验；contenteditable 走 fill（Playwright 支持）。"""
    if not text:
        return False
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if not loc.count():
                continue
            loc.scroll_into_view_if_needed(timeout=3000)
            loc.click(timeout=3000)
            loc.fill(text, timeout=5000)
            page.wait_for_timeout(400)
            # 回读校验：input 用 input_value，contenteditable 用 innerText
            got = ""
            try:
                got = loc.input_value(timeout=1500)
            except Exception:
                try:
                    got = loc.inner_text(timeout=1500)
                except Exception:
                    got = ""
            if got.strip():
                log(f"[xiaohongshu] {label} 已填入 {len(got)} 字: {got[:24]!r}", "OK")
                return True
            log(f"[xiaohongshu] {label} 填入后回读为空，换下一个 selector", "WARN")
        except Exception as e:
            log(f"[xiaohongshu] {label} 填充失败 ({sel}): {str(e)[:90]}", "WARN")
    # 最后兜底：JS 直接写值并派发 input 事件（Vue 受控组件需要）
    try:
        ok = page.evaluate(
            """([sels, val]) => {
              for (const s of sels) {
                const el = document.querySelector(s);
                if (!el) continue;
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                  const setter = Object.getOwnPropertyDescriptor(
                      window.HTMLInputElement.prototype, 'value').set;
                  setter.call(el, val);
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
            log(f"[xiaohongshu] {label} 已用 JS 兜底写入", "OK")
        return bool(ok)
    except Exception as e:
        log(f"[xiaohongshu] {label} JS 兜底失败: {str(e)[:90]}", "ERR")
        return False


def _check_success(page) -> tuple[bool, str]:
    """点完发布后等跳转或提示，判断是否真的成功。"""
    for _ in range(15):
        page.wait_for_timeout(1000)
        u = page.url
        if "/publish/success" in u or "published" in u.lower():
            return True, f"已跳转成功页: {u}"
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
        if "/new/home" in u or "/note/manage" in u:
            return True, f"已跳转到管理页: {u}"
    return False, "点击后未检测到成功提示"


def publish_xiaohongshu(video: str, cover: str, plan: dict, cfg: dict,
                        dry_run: bool = False) -> PublishResult:
    platform = "xiaohongshu"
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
        log("[xiaohongshu] 视频已上传，等待处理…")
        page.wait_for_timeout(12000)

        title = plan.get("title", "")[:20]
        caption = build_caption(plan, cfg)
        # 先填标题（input），再填正文（tiptap）；两者 selector 不重叠
        ok_title = _fill_xhs(page, TITLE_SELECTORS, title, "标题")
        page.wait_for_timeout(600)
        ok_body = _fill_xhs(page, BODY_SELECTORS, caption, "正文")
        page.wait_for_timeout(800)
        if not ok_title:
            log("[xiaohongshu] 标题未填成功，笔记将无标题", "WARN")
        if not ok_body:
            log("[xiaohongshu] 正文未填成功", "WARN")

        if cover and Path(cover).exists():
            try:
                cover_input = page.locator('input[type="file"]').nth(1)
                if cover_input.count():
                    cover_input.set_input_files(cover, timeout=5000)
                    page.wait_for_timeout(2000)
            except Exception as e:
                log(f"[xiaohongshu] 封面设置跳过: {e}", "WARN")

        result.screenshot = _shot(page, cfg, platform, "before_publish")

        # 小红书发布表单内部滚动，必须先把内部容器滚到底，底部「发布」按钮才进入视窗
        scroll_to_bottom(page, rounds=8)
        page.wait_for_timeout(1500)

        btn = None
        try:
            btn = page.evaluate(FIND_PUBLISH_BTN)
        except Exception as e:
            log(f"[xiaohongshu] 定位 xhs-publish-btn 异常: {e}", "WARN")

        if btn:
            log(f"[xiaohongshu] 找到 xhs-publish-btn box={btn} ", "OK")
            if btn.get("disabled") == "true":
                result.message = "发布按钮处于 disabled 状态（表单可能未填完整）"
                result.screenshot = _shot(page, cfg, platform, "btn_disabled")
                return finish(pw, ctx, result)

            # 该元素内部 DOM 为空、子按钮不可查询，只能按坐标点。
            # 红「发布」在右侧；从左到右试几个相对位置，命中即跳出。
            hit = False
            for ratio in (0.62, 0.72, 0.55, 0.80):
                cx = btn["x"] + btn["w"] * ratio
                cy = btn["y"] + btn["h"] * 0.5
                log(f"[xiaohongshu] 坐标点击发布 x={cx:.0f} y={cy:.0f} (ratio={ratio})")
                page.mouse.click(cx, cy)
                page.wait_for_timeout(6000)
                if "published" in page.url.lower() or "success" in page.url.lower():
                    hit = True
                    break
            result.url = page.url
            success, why = _check_success(page)
            result.ok = success
            result.message = why if success else (
                f"已点击发布（{why}），需人工复核")
            if not success:
                result.screenshot = _shot(page, cfg, platform, "after_publish")
            if hit:
                log("[xiaohongshu] 已跳转成功标记页", "OK")
        else:
            # 兜底：按 selector 点（不用文本兜底，避免点到侧栏「发布笔记」）
            ok = click_publish(page, [
                'xhs-publish-btn',
                'button:has-text("发布"):not([disabled])',
                'div[class*="footer"] button:has-text("发布")',
            ], wait_ms=3000, scroll=False)
            result.url = page.url
            result.ok = False
            result.message = ("已按 selector 点击发布，需人工复核" if ok
                              else "未找到发布按钮（截图留证）")
            if not ok:
                result.screenshot = _shot(page, cfg, platform, "no_button")
        return finish(pw, ctx, result)
    except Exception as e:
        result.message = f"异常: {e}"
        log(f"[xiaohongshu] {result.message}", "ERR")
        return result
