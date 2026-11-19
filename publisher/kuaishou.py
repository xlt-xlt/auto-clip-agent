# -*- coding: utf-8 -*-
"""快手创作者中心 RPA 发布。"""
from __future__ import annotations

from pathlib import Path

from utils import log
from .base import (PublishResult, ensure_login, build_caption, finish,
                   click_publish, click_by_text, scroll_to_bottom)
from .douyin import _wait_login, _fill, _shot

UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video"

# 快手发布页实测（probe_kuaishou.py）：
#   发布按钮是 <div class="_button_3a3lq_1 _button-primary_3a3lq_60">文本「发布」</div>
#   —— 不是 <button>，所以 button:has-text 全抓不到；CSS Modules 类名带 hash 会变。
#   位置 x376 y683 w96 h36（滚到底后可见）。
#   「立即发布」SPAN 在 y575 是【发布时间】选项，不是提交按钮，别点错。
PUBLISH_SELECTORS = [
    'div[class*="_button-primary"]:has-text("发布")',
    'div[class*="button"][class*="primary"]:has-text("发布")',
    'div[class*="submit"]:has-text("发布")',
    'button:has-text("发布"):not([disabled])',
]

CLICK_PUBLISH_DIV = r"""() => {
  // 注意：发布页整页在内部容器里滚动（bodyH=900、scrollY 恒为 0），
  // 发布按钮初始在 y≈1189（视窗只有 900 高）→ 不能按"是否在视窗内"过滤，
  // 必须先 scrollIntoView 再回读坐标。
  let best = null;
  for (const e of document.querySelectorAll('div,span,a,button')) {
    const t = (e.innerText || '').trim();
    if (t !== '发布') continue;                    // 「发布作品」「发布视频」「发布设置」都不算
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (r.width < 50 || r.height < 26 || r.height > 70) continue;  // 排除内层 w=24 的文字节点
    if (r.x < 200) continue;                       // 排除左侧栏
    // 优先带 primary 类名的真按钮
    const prim = /primary/.test((e.className || '').toString());
    const score = (prim ? 10000 : 0) + r.y;
    if (!best || score > best.score) {
      best = {el: e, score: score, x: r.x, y: r.y,
              w: Math.round(r.width), h: Math.round(r.height),
              cls: (e.className || '').toString().slice(0, 50)};
    }
  }
  if (!best) return null;
  best.el.scrollIntoView({block: 'center', behavior: 'instant'});
  const r2 = best.el.getBoundingClientRect();
  return {x: r2.x + r2.width / 2, y: r2.y + r2.height / 2,
          w: Math.round(r2.width), h: Math.round(r2.height),
          beforeY: Math.round(best.y), afterY: Math.round(r2.y),
          inView: r2.y >= 0 && r2.y + r2.height <= window.innerHeight,
          cls: best.cls};
}"""

TOASTS = r"""() => [...document.querySelectorAll(
    '[class*=toast],[class*=message],[class*=notice],[class*=ant-message],[role=alert]')]
  .map(e => (e.innerText || '').trim()).filter(t => t && t.length < 150).slice(0, 8)"""

# 快手硬限制：话题标签数量上限 4 个，超了整条发布失败
# （实测报错「内容发布失败: 话题标签数量超过上限：4」）
MAX_TOPICS = 4


def _trim_topics(plan: dict) -> dict:
    """把 hashtags 截到平台上限，避免「话题标签数量超过上限」整条失败。"""
    tags = plan.get("hashtags") or ""
    if isinstance(tags, str):
        items = tags.split()
    else:
        items = list(tags)
    if len(items) <= MAX_TOPICS:
        return plan
    kept = items[:MAX_TOPICS]
    log(f"[kuaishou] 话题 {len(items)} 个超过上限 {MAX_TOPICS}，截断为: {' '.join(kept)}", "WARN")
    p = dict(plan)
    p["hashtags"] = " ".join(kept)
    return p


def publish_kuaishou(video: str, cover: str, plan: dict, cfg: dict,
                     dry_run: bool = False) -> PublishResult:
    platform = "kuaishou"
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
        log("[kuaishou] 视频已上传，等待处理…")
        page.wait_for_timeout(22000)

        caption = build_caption(_trim_topics(plan), cfg)
        _fill(page, ['div[contenteditable="true"]', 'textarea[placeholder*="描述"]',
                     'textarea'], caption)
        page.wait_for_timeout(1000)

        # 必须先滚到底：发布按钮在页面下方，不滚用 Playwright 会报 not visible
        scroll_to_bottom(page, rounds=10)
        page.wait_for_timeout(2000)

        result.screenshot = _shot(page, cfg, platform, "before_publish")

        # 主路径：坐标点击 div 版的「发布」按钮
        target = None
        try:
            target = page.evaluate(CLICK_PUBLISH_DIV)
        except Exception as e:
            log(f"[kuaishou] 定位发布按钮异常: {e}", "WARN")

        clicked = False
        if target:
            log(f"[kuaishou] 定位到发布按钮 cls={target.get('cls')} "
                f"y {target.get('beforeY')}→{target.get('afterY')} "
                f"inView={target.get('inView')}")
            page.wait_for_timeout(600)          # 等 scrollIntoView 落稳
            for attempt in range(3):
                try:
                    page.mouse.click(target["x"], target["y"])
                except Exception as e:
                    log(f"[kuaishou] 鼠标点击异常: {e}", "WARN")
                    break
                page.wait_for_timeout(3500)
                # 点完检查是否已离开发布页；未离开就重定位再点一次
                if "/publish/video" not in page.url:
                    clicked = True
                    break
                try:
                    t2 = page.evaluate(CLICK_PUBLISH_DIV)
                except Exception:
                    t2 = None
                if t2:
                    target = t2
                    page.wait_for_timeout(500)
                else:
                    clicked = attempt == 0   # 按钮消失通常也意味着已提交
                    break
            if not clicked and "/publish/video" in page.url:
                clicked = True   # 已点过，交给后面的成功判据

        if not clicked:
            clicked = click_publish(page, PUBLISH_SELECTORS, wait_ms=8000, scroll=True)
            if not clicked:
                hit = click_by_text(page, wait_ms=6000)
                clicked = bool(hit)
                if hit:
                    log(f"[kuaishou] 按文本点到发布: {hit}", "OK")

        if not clicked:
            result.message = "未找到发布按钮，已停在前置页（截图留证）"
            return finish(pw, ctx, result)

        page.wait_for_timeout(10000)
        # 二次确认弹窗（部分账号/时段会弹）
        for t in ("确认发布", "确定", "确认"):
            try:
                box = page.evaluate(
                    """(txt) => {
                      for (const e of document.querySelectorAll('div,span,button')) {
                        if ((e.innerText||'').trim() !== txt) continue;
                        const r = e.getBoundingClientRect();
                        if (r.width < 40 || r.height < 20) continue;
                        if (r.y < 0 || r.y > window.innerHeight) continue;
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                      }
                      return null;
                    }""", t)
                if box:
                    log(f"[kuaishou] 发现二次确认，点「{t}」")
                    page.mouse.click(box["x"], box["y"])
                    page.wait_for_timeout(9000)
                    break
            except Exception:
                pass

        result.url = page.url
        toasts = []
        for _ in range(4):            # 失败提示可能延迟出现，多抓几轮
            try:
                got = page.evaluate(TOASTS)
                for t in got:
                    if t not in toasts:
                        toasts.append(t)
            except Exception:
                pass
            if any("失败" in t for t in toasts):
                break
            page.wait_for_timeout(2000)

        u = result.url.lower()
        fail_toast = [t for t in toasts if "失败" in t or "错误" in t]
        ok_toast = [t for t in toasts if "成功" in t and "失败" not in t]
        left_page = "/publish/video" not in u

        if fail_toast:
            result.ok = False
            result.message = f"发布被平台拒绝: {'；'.join(fail_toast[:2])}"
        elif ok_toast or left_page:
            result.ok = True
            result.message = (f"发布成功（提示：{ok_toast[:2]}）" if ok_toast
                              else f"已离开发布页: {result.url}")
        else:
            result.ok = False
            result.message = "已点击发布，未捕获成功提示，需人工复核"
        result.screenshot = _shot(page, cfg, platform, "after_publish")
        return finish(pw, ctx, result)
    except Exception as e:
        result.message = f"异常: {e}"
        log(f"[kuaishou] {result.message}", "ERR")
        return result
