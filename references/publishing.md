# 四平台发布（publisher/ 目录）

## 总原则：登录态是唯一真难题

发布流程本身不难（上传→填标题→填正文→点发布→看结果）。真正的坑**全在登录态**：

> 扫码登录成功 → 脚本关掉浏览器 → 下次发布重新打开 → 登录态已被平台风控清掉。

实测抖音/视频号/快手都这样反复掉。**唯一稳定解法：扫码成功后不要关 ctx，在同一个 Playwright 上下文里直接发。**

对应脚本：`_debug\login_and_publish_v4.py`（`--only` 化之前的一次性版本，改造成正式版直接复制它的 `publish_in_ctx()`）。流程：

1. `launch_persistent_context` 用真实 Chrome + STEALTH 打开平台首页
2. 轮询 `is_logged(platform, url)`——**必须遍历 `ctx.pages` 所有标签页**（扫码会开新标签，只盯 `pages[0]` 会误判成"没登录"）
3. 一检测到登录，立刻在同 ctx 里 `goto` 上传页并发
4. 发完才关

`is_logged` 判据：

| 平台 | 已登录 | 未登录 |
|---|---|---|
| douyin | url 含 `creator.douyin.com/creator-micro` 且不含 `login` | 含 `login` |
| xiaohongshu | 含 `creator.xiaohongshu.com` 且不含 `login` / `401` | 含 `login` |
| shipinhao | 含 `channels.weixin.qq.com/platform` 且不含 `login` | 含 `login.html` |
| kuaishou | 含 `cp.kuaishou.com` 且不含 `passport` / `login` | 含 `passport.kuaishou.com` |

## 反自动化检测

平台的 passport 会检测 Playwright 特征，报「跳转地址不合法 为保障账号安全，已停止访问该链接」。必须：

```python
p.chromium.launch_persistent_context(
    profile_dir,
    executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",  # 真实 Chrome，不是 bundled chromium
    ignore_default_args=["--enable-automation", "--enable-blink-features=AutomationControlled"],
    locale="zh-CN",
    timezone_id="Asia/Shanghai",
    viewport={"width": 1440, "height": 900},
    headless=False,
)
ctx.add_init_script(STEALTH_JS)   # 覆写 navigator.webdriver / languages / plugins / platform + window.chrome + WebGL vendor
```

## 进程隔离

`publish_manifest.py` 必须**每平台起一个子进程**（`subprocess.run([sys.executable, __file__, "--only", p])`）。同进程连续跑两个平台会报：

```
It looks like you are using Playwright Sync API inside the asyncio loop. Please use the Async API instead.
```

## 各平台专属坑

### 抖音
- 上传页：`creator.douyin.com/creator-micro/content/upload`
- 成功判据不能只看 URL 含 `publish`——成功跳的是 `/content/post/video?enter_from=publish_page`，也含 publish。
  正确：`("upload" not in u) and any(k in u for k in ("post","manage","video","success","creator-micro/home"))`
- 扫码后常报「上传页无 fileInput」，重试一次通常就好。

### 小红书
- 上传页：`creator.xiaohongshu.com/publish/publish`
- **发布按钮是自定义元素 `<xhs-publish-btn>`**：`innerHTML` 为空、无 `shadowRoot`、不出现在 `querySelectorAll('button')` 结果里（全页 button 只有 9 个）。
  做法：JS 取它的 `getBoundingClientRect()`，再 `page.mouse.click(x + w*0.62, y + h*0.5)` 坐标点击。
- 表单在内部容器 `.publish-page` 里滚动，滚 `window` 没用 → 用 `scroll_to_bottom()` 遍历所有 `scrollHeight > clientHeight` 的元素。
- 别点左侧导航的「发布笔记」（y≈90），会把整页重置回空白上传页。
- **AIGC 标识**：平台要求标注不禁止 AI 内容。被识别后是限流不是封号。处理：① 不要删（重发触发新审核 + 判重复）② 创作中心编辑笔记补「内容由 AI 生成/AI 辅助创作」③ 换更人味的文案（少话题、长短句不齐、第一人称口语）。
- 长期建议：小红书优先手机 App 手动发，设备指纹最干净。

### 视频号
- 上传页：`channels.weixin.qq.com/platform/post/create`，必须微信扫码
- 上传页经常 SPA 白屏（body 只有「视频号 · 助手」、fileInputs=0），但 profile 页正常 → 先 `goto` 首页预热再进上传页
- 扫码窗口 10 分钟超时是常态，用户不在电脑前就发不出去；报错 `BrowserContext.close: Target page, context or browser has been closed`

### 快手
- 上传页：`cp.kuaishou.com/article/publish/video`
- **话题硬上限 4 个**，超过报「内容发布失败: 话题标签数量超过上限：4」。代码里 `MAX_TOPICS=4` + `_trim_topics()` 截断。
- 发布按钮在内部滚动容器里，初始 `y≈1189` 在视窗外；`scrollY` 恒为 0（不是 window 滚动）。必须先 `el.scrollIntoView({block:'center'})` 再回读 rect 才点得到。
- 成功判据：离开上传页到 `/article/manage/video`，或页面 toast 含「发布成功」；toast 含「失败/错误」判 fail。
- 必须 headless + 先访问 profile 页预热，headful 反而掉登录（2026-11 实测）。

## 复核（别信"已点击发布"）

发布脚本报 ok 不等于落库。必须打开作品管理页数一遍：

- 抖音：`creator.douyin.com/creator-micro/content/manage` → 找标题关键词 + 时长
- 快手：`cp.kuaishou.com/article/manage/video` → 数作品数、看最新一条时间
- 小红书：`creator.xiaohongshu.com/new/home`

实测踩过：快手报「已点击发布」，管理页仍只有 2 条 11-17 的旧稿 —— 根本没落库。
