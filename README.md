# 自动剪辑工坊 · auto-clip-agent

> 一份素材，剪成四条不同风格的竖屏成片，逐条适配抖音 / 小红书 / 视频号 / 快手的生态，再按各平台文案自动发布。

每天把手机拍的素材扔进 `inbox/`，剩下的事它做完：
**语音转写 → AI 决定剪哪几段 → ffmpeg 成片级包装（转场/动效/花字/卡点/BGM/封面）→ 排队 → 定时发到四个平台。**

不是"同一条视频加字幕后搬运"——每个平台都是从同一批素材**重新剪一条**：不同时长、不同选段、不同转场、不同字体、不同色调、不同文案。

![status](https://img.shields.io/badge/platform-Windows-blue) ![python](https://img.shields.io/badge/python-3.10%2B-yellow) ![license](https://img.shields.io/badge/license-MIT-green)

---

## 为什么做这个

一个人运营四个平台，真实痛点不是"剪视频"，是**同一批素材要按四种完全不同的语言再讲四遍**：

- 抖音前 3 秒定生死，要快切、要高对比、要爆点
- 小红书封面标题决定点击，要暖调、要人味、要"姐妹可以冲"
- 视频号靠社交转发，要完整叙事、要正能量、不能太吵
- 快手讲老铁文化，要烟火气、要接地气、要"双击 666"

手工剪四条 = 一整天。这个项目的答案是把"平台语感"固化进配置表（`styles.py`），一条命令批量出片。

---

## 四平台配方（可改）

| | 抖音 | 小红书 | 视频号 | 快手 |
|---|---|---|---|---|
| **策略** | 算法赛马·前 3 秒定生死 | 封面决定点击·种草氛围 | 社交推荐·易转发 | 老铁文化·真实接地气 |
| **时长** | 22s | 28.6s | 39.8s | 27s |
| **节奏 BPM** | 140 | 96 | 108 | 128 |
| **转场** | 闪白 | 柔和叠化 | 淡入淡出 | 闪黑 |
| **爆点强度** | 强（三连闪+RGB 故障） | 轻（单次白闪） | 轻 | 强 |
| **花字** | 白字亮黄描边 68px | 细黑描边无底 46px | 白字黑描边半透底 | 亮黄字黑粗描边 62px |
| **MG 计数** | 播放量 | 点赞 | 转发 | 老铁在看 |
| **封面字体** | 新青年体 | 悠然体 | 后现代体 | 新青年体 |
| **话题数** | 6 | 7 | 5 | 4（平台硬上限） |

全部集中在 [`styles.py`](styles.py) 的 `STYLE_PROFILES`，改一个字就换风格，不用碰剪辑引擎。

## 成片级包装做了什么

| 元素 | 实现 | 平台差异 |
|---|---|---|
| 转场 | `xfade` 串联各段 | 闪白 / 叠化 / 淡入淡出 / 闪黑 |
| 画面动效 | 动态 `crop` 推近 + 逐帧正弦抖动 | 抖音快手推拉明显，小红书视频号极缓 |
| 花字字幕 | ASS 弹出动画（70%→108%→回落）+ 淡入淡出 | 字号/配色/描边/角标逐平台独立 |
| MG 包装 | 顶部递增计数器 + 底部动态进度条 | 标签与主色按平台定制 |
| 爆点快闪 | 段首闪白→黑→白 + `rgbashift` 色差 | 强/轻两档 |
| 声音 | 真实曲目按副歌截取 + 淡入淡出 | 每平台一首，音量压到 0.12 不盖人声 |
| 封面 | ffmpeg 抽帧 + PIL 带字封面 | 字体/配色/标题逐平台不同 |

---

## 快速开始（Windows）

### 1. 环境

```powershell
# Python 3.10+ 与 ffmpeg 是硬依赖
winget install Gyan.FFmpeg
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
```

语音转写可选（不装则跳过转录，直接按规则选段）：

```powershell
pip install faster-whisper
```

### 2. 补全素材资源

仓库不含任何音乐/字体（版权原因），从你本机剪映导入：

```powershell
python import_jianying_assets.py            # 12 首 BGM + 全部字体
python jianying_test.py                     # 自检
```

没有剪映也能跑——缺音乐时自动回退 `bgm_engine.py` 的程序化合成，缺字体时封面回退系统字体。

### 3. 出片

```powershell
# 素材放进 inbox
python make_styles.py                       # 四条全出
python make_styles.py --only douyin         # 只出一条
```

产物在 `outbox/styles/`：四条 `.mp4` + 各自 `_cover.jpg` + `manifest.json`（含标题/文案/话题）。

合格线自检：

```powershell
ffprobe -v error -show_entries format=duration -show_entries stream=codec_name,width,height -of default=nw=1 "outbox\styles\douyin_抖音.mp4"
# 期望 h264 / 1080x1920 / aac
```

---

## 三种用法

### A. 图形界面（给不想敲命令的人）

```powershell
python gui.py            # 或双击 启动工具.bat
```

勾平台 → 选素材目录 → 开始生成，日志实时滚，跑完自动打开输出目录。

### B. 打包成独立 exe（分发给别人，不需要装 Python）

```powershell
python build_exe.py      # 约 3 分钟
```

产物 `dist/自动剪辑工坊/`（约 159 MB），双击 `自动剪辑工坊.exe` 即用。
支持无界面批处理：

```powershell
自动剪辑工坊.exe --cli --only douyin
自动剪辑工坊.exe --cli --src "D:\素材" --only douyin,kuaishou
```

> 必须用 PyInstaller `--onedir`；`--onefile` 在 Windows 会报 `Could not create temporary directory!`。
> 打包后 `ROOT` 取 exe 所在目录，`assets/` 与 `config.json` 要放在 exe 旁边。

### C. 全自动守护（每天投喂）

```powershell
python scheduler.py daemon      # 或双击 run.bat 选 [1]
```

每 20 秒扫一次 `inbox/` 自动剪辑并进待发布队列；每天 20:00 自动发布队列，同一天只触发一次。

---

## 流水线架构

```
inbox/*.mp4
   │
   ├─ transcriber.py ──► faster-whisper（子进程，独立环境）──► 带时间轴文本
   │
   ├─ brain.py ────────► LLM 输出 JSON 剪辑计划（keep: [[起,止],...]）
   │                     无 API key 时走规则引擎（去口癖/压缩静音/按时长截取）
   │
   └─ make_styles.py ──► 逐平台：选段 → 动态 crop → xfade 转场 → 爆点闪
                          → ASS 花字 + MG 计数 → BGM 混音 → PIL 封面
                          │
                          └─► outbox/styles/<platform>_<名>.mp4 + manifest.json
                                 │
                                 └─ publish_manifest.py ──► 四平台 RPA 发布
```

**三层解耦**：ASR（听懂）→ LLM（决定剪哪）→ ffmpeg（真的剪）。
任一环缺失都能降级运行，不会整条流水线停摆。

---

## 自动发布

```powershell
python publish_manifest.py --dry-run          # 看会发什么
python publish_manifest.py --only xiaohongshu # 单平台
python publish_manifest.py                    # 全部启用平台
```

| 平台 | 入口 | 备注 |
|---|---|---|
| 抖音 | creator.douyin.com | Playwright RPA，扫码登录 |
| 小红书 | creator.xiaohongshu.com | 发布按钮是自定义元素，只能坐标点击 |
| 视频号 | channels.weixin.qq.com | 必须微信扫码，登录态最容易掉 |
| 快手 | cp.kuaishou.com | 话题硬上限 4 个 |

### 三条血泪经验（不看会浪费一整晚）

1. **扫码成功后不要关浏览器**。登录态在"关窗口 → 重开"之间必定被平台风控清掉，正确做法是在同一个 Playwright 上下文里直接发布。
2. **每平台单独一个子进程**。同一进程连续跑两个平台会撞 `Sync API inside the asyncio loop`。
3. **"已点击发布"不等于发布成功**。必须打开作品管理页数一遍，实测出现过点击成功但内容没落库。

完整踩坑记录见 [`references/publishing.md`](references/publishing.md)。

### 合规提醒

- 平台对 AIGC 内容普遍**要求标识**而非禁止。被识别未标识通常是限流不是封号；可在创作中心编辑补「内容由 AI 生成」声明。
- 建议把 `config.json` 的 `publish.auto_publish` 保持 `false`，成片先进待发布队列人工复核，稳定后再开。
- 自动化发布需遵守各平台用户协议；高频发布、批量注册账号等行为风险自负。

---

## 目录结构

```
auto-clip-agent/
├── make_styles.py            ★ 四平台成片级剪辑引擎
├── styles.py                 ★ 四平台风格档案（改这里就换风格）
├── jianying_fx.py            剪映转场/特效中文名 → ffmpeg 映射
├── bgm_engine.py             程序化 BGM 兜底（零依赖）
├── gui.py                    图形界面（tkinter）
├── build_exe.py              PyInstaller 打包脚本
├── import_jianying_assets.py 从本机剪映导入 BGM/字体
├── pipeline.py               主编排 + 待发布队列
├── scheduler.py              定时调度守护
├── brain.py                  LLM 剪辑决策（含规则兜底）
├── editor.py                 ffmpeg 合成（保留原声 + BGM 混音）
├── transcriber.py / asr_worker.py   转写调度与 ASR 子进程
├── publish_manifest.py       按 manifest 批量发布
├── publisher/                四平台 RPA 适配器
├── prep_voiceover_real.py    手机录音降噪归一
├── sync_github.py            网络阻断 git push 时用 API 同步到 GitHub
├── utils.py                  配置/日志/ffprobe/状态
├── config.json               全部配置
├── run.bat                   交互菜单
├── references/               ffmpeg 坑位 / 发布经验 / 配方手册
├── assets/                   资源目录（音乐字体需自行导入）
├── inbox/  outbox/  work/  state/  logs/     运行时目录
└── _debug/                   本地一次性诊断脚本（不入库）
```

## 配置要点（`config.json`）

| 键 | 作用 |
|---|---|
| `brain.llm` | 不填走规则引擎；填了（OpenAI/DeepSeek/通义兼容协议）走 LLM 决策 |
| `brain.target.duration_min/max` | 成片时长区间 |
| `audio.keep_original` / `bgm_volume` | 保留原声 / BGM 音量（0.12 不盖人声） |
| `publish.platforms` | 四平台开关 |
| `publish.auto_publish` | **首次务必 false** |
| `schedule.daily_publish_time` | 每日发布时间 |
| `asr.model` | tiny/base/small/medium/large-v3 |

密钥放 `.env`（见 `.env.example`），不要写进 `config.json`。

## 常见问题

**Q: 成片没声音？**
检查源素材是否本身无声；有声源会按 `-c:a aac` 保留，烧字幕与拼接阶段用 `-c:a copy`。

**Q: 封面字体没生效？**
字体文件名要能被 `jianying_fx.font_path()` 的中文关键词匹配（`新青年`/`悠然`/`后现代`）；匹配不到回退系统字体，不影响出片。

**Q: 剪映草稿里的转场能不能直接读？**
不能。新版 `draft_content.json` 是加密格式。项目改为用 ffmpeg 复刻剪映的爆款效果（闪白/闪黑/叠化/故障三连闪）。

**Q: 转写很慢？**
`config.json` 里 `asr.model` 调成 `base` 或 `tiny`；首次会下载模型，之后离线。

**Q: 只想剪一条平台？**
`python make_styles.py --only douyin`。

---

## 技术笔记

踩过的坑都写在 [`references/`](references/) 里，改代码前建议先看一眼，能省半天：

- [`references/ffmpeg-traps.md`](references/ffmpeg-traps.md) — zoompan 崩、eq 失效、afade 静音、路径转义、ASS 大写标签、剪映字体崩溃等 10 个坑
- [`references/publishing.md`](references/publishing.md) — 登录态病根、反自动化检测、各平台专属坑
- [`references/style-recipes.md`](references/style-recipes.md) — 配方改动、按强拍卡字幕、edge-tts 真人音色、逐句 TTS 对齐

仓库也自带一份 agent 可读的技能描述 [`skills/auto-clip-agent/SKILL.md`](skills/auto-clip-agent/SKILL.md)，放进 DSH / Claude 的 skills 目录后，说"自动剪辑"就能被正确调用。

## 环境说明

本项目是在 Windows 上长出来的，已在 Windows 11 + Python 3.15 + ffmpeg 9.0 验证。
macOS/Linux 理论上可行（都是 ffmpeg 调用），但 `run.bat`、字体路径、剪映导入、PyInstaller 打包需要自行适配。

双环境设计：主环境跑编排/剪辑/发布，ASR 单独一个环境跑 faster-whisper（Python 3.15 上 PyAV 编译不了），两者通过子进程解耦。

## 维护：把改动同步回 GitHub

正常情况下 `git push` 就够了。但如果所在网络只放通 `api.github.com`、`github.com:443` 被重置（部分线路会遇到），
可以用仓库自带的 `sync_github.py` 绕过 git 协议，直接走 Git Data API 提交：

```powershell
python sync_github.py --dry-run              # 看会传哪些文件（白名单来自 git 索引，.gitignore 自动生效）
python sync_github.py -m "feat: 新增 XX"     # 真正提交
```

token 放在 `state/.ghtoken`（`state/` 已在 `.gitignore` 里，不会误传），需要一个有 `repo` 权限的 PAT。
`GH_OWNER` / `GH_REPO` 环境变量可覆盖默认仓库。这是全量覆盖式提交（每次重建 tree），适合单人维护的仓库。


## License

[MIT](LICENSE) © YG (xlt-xlt)

仓库不含任何第三方音乐、字体或素材文件，需由使用者自行导入并遵守相应授权；
详见 [THIRD_PARTY.md](THIRD_PARTY.md)。
