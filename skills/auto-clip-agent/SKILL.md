---
name: auto-clip-agent
description: "自动剪辑工坊：把手机素材剪成抖音/小红书/视频号/快手四条差异化成片（转场/花字/卡点/进度条/BGM/封面），并可打包成双击即用的 Windows 工具、发布到四平台。Use on: 自动剪辑, 剪成四条, 四平台成片, 出片, 再做一版, 换个风格, 换BGM, 卡点字幕, 加花字, 打包成工具, 发到抖音小红书视频号快手, auto-clip, 一键剪辑. 工程根即本技能所在仓库根目录。"
metadata:
  author: "YG"
  version: "1.2.0"
---

# 自动剪辑工坊（auto-clip-agent）

你是这套剪辑流水线的操作员。目标永远是**出成片**或**出工具**，不是写文档、不是解释参数。
工程根 = 本仓库根目录（克隆后 `cd` 进去即可，下文命令都在此目录执行）：

一句话结构：`素材(inbox) → make_styles.py 按平台配方重剪 → outbox\styles\<platform>_<中文名>.mp4 + _cover.jpg + manifest.json →（可选）publish_manifest.py 发四平台`。

## 先判断用户要哪一种

| 用户说的 | 走哪条 |
|---|---|
| 剪一下 / 出片 / 做成四条 / 换个风格 | **A. 源码生成**（make_styles.py） |
| 双击就能用 / 封装成工具 / 打包 exe | **B. 打包工具**（build_exe.py） |
| 发出去 / 发到平台 / 加上文案 | **C. 发布**（publish_manifest.py；登录态问题见 references/publishing.md） |
| 字幕不跟画面 / 真人播音 | **D. 精修**（见 references/style-recipes.md） |
| 换字幕 / 只改字 / 不动画面 | **D2. 换字幕**：改 `subtitles.json` → `python resub.py`（几十秒，不重剪） |
| 换音乐 / 只换BGM / 换曲子 | **D3. 换音乐**：`python rebgm.py --plan <key>` 或 `--file X.mp3 --start 秒`（复用字幕+画面，几十秒） |
| 每天自动换字幕风格 / 每日轮换 | **E. 每日轮换**：`python daily_run.py`（剪片+按日期同时换字幕风格+音乐方案，配定时调度） |
| 生成标题/文案/话题 / 换发布文案 | **文案档**：改 `captions.py` → `python sync_captions.py`（同步到 manifest，不重剪） |
| 只有素材、还没进 inbox | 先把素材放（或复制）到 `inbox\`，或在 GUI 里选素材目录 |

不要反问"你想要什么风格"——四套配方已经定义好了，直接跑，跑完让用户看片再调。

## A. 源码生成（最常用）

```powershell
cd <仓库根目录>
python make_styles.py                          # inbox 全部素材 → 四平台四条
python make_styles.py --only douyin            # 只出一条
python make_styles.py --src "work\src_today"   # 指定素材目录
```

产物：`outbox\styles\douyin_抖音.mp4 / xiaohongshu_小红书.mp4 / shipinhao_视频号.mp4 / kuaishou_快手.mp4`，各带 `_cover.jpg`，`manifest.json` 汇总标题/文案/话题（按 platform 合并写入，不会互相覆盖）。

核心函数签名（要自己调时用这个，别重写）：

```python
import make_styles as ms
ms.ffprobe(path) -> {"path","w","h","dur"}          # 只用 ffprobe 的 csv 输出解析
ms.make_one(platform: str, sources: list[dict], cfg: dict, outdir: Path) -> dict
# 返回 {"platform","label","video","cover","duration","title","caption","hashtags",...}
```

`STYLE_PROFILES`（在 `styles.py`）每个平台一套：`target_duration / clip_len / n_clips / bpm / bgm_file / bgm_start / bgm_volume / transition / transition_dur / zoom_step / shake / impact / jy_transition / jy_font / counter_label / cover_text / title / caption / hashtags`。改视觉配方就改这里。

**标题/文案/话题的单一事实来源是 `captions.py`**（`CAPTIONS` 字典），`styles.py` 末尾会把它覆盖进 `STYLE_PROFILES`。要生成或换文案就改 `captions.py`，然后同步到已生成的 manifest：

```powershell
python sync_captions.py                          # 同步主 manifest + 所有 daily manifest
python sync_captions.py --date 2026-11-19        # 只同步某天
python sync_captions.py --dry-run                # 只预览
```

`publish_manifest.py` 读 manifest 的 title/caption/hashtags，同步后直接发就带新文案，不重剪。各平台文案按生态差异化写：抖音提问钩子+反转、小红书口语种草+emoji（话题少而精避 AIGC 风控）、视频号稳重可转发、快手接地气（话题硬上限 4 个）。

## B. 打包成工具

```powershell
python build_exe.py      # 约 3 分钟
```

产物 `dist\自动剪辑工坊\`（约 159 MB）：`自动剪辑工坊.exe`(windowed) + `_internal\` + `assets\`(12 首剪映音乐 + 3 字体) + `config.json` + `使用说明.txt` + `inbox/outbox/work/logs/state`。

**硬约束**：
- 必须 `--onedir`。`--onefile` 在 Windows 上报 `Could not create temporary directory!`，别试。
- 打包后 `ROOT` 走 `sys.executable` 目录（`utils._app_root()`）；`assets/`、`config.json` 必须**复制到 exe 旁边**，不要指望打进 exe 内部。
- 打包只带 `assets/bgm/jianying/`（styles.py 的 bgm_file 全部是 `jy_*.mp3`）；根目录 `assets/bgm/*.mp3` 是早期 soundhelix 素材，不带。
- 工具仍依赖系统 `ffmpeg`（需在 PATH 里）。

GUI 源码 `gui.py`（tkinter，零依赖）也可直接跑：`python gui.py` 或双击 `启动工具.bat`。
GUI 支持 `--cli` 无界面批处理：

```powershell
自动剪辑工坊.exe --cli --only douyin
自动剪辑工坊.exe --cli --src "D:\素材" --only douyin,kuaishou
```

日志落 `logs\cli_run.log`（打包成 windowed 后 `sys.stdout` 是 None，所有输出必须走文件）。

## C. 发布

```powershell
python publish_manifest.py                    # 按 manifest 发全部启用平台
python publish_manifest.py --only xiaohongshu
python publish_manifest.py --dry-run
```

**发布是个坑场，动手前必读 `references/publishing.md`**。一句话版本：
逐平台**子进程隔离**（同进程多次 Playwright 会 `Sync API inside the asyncio loop`）；用真实 Chrome + STEALTH 抹自动化痕迹；**扫码成功后不要关 ctx**，在同一个会话里直接发（关掉重开必掉登录态）；快手话题**最多 4 个**；小红书发布按钮是自定义元素 `<xhs-publish-btn>`，只能坐标点击。

## D. 精修（字幕卡点 / 换音乐 / 真人配音）

见 `references/style-recipes.md`。要点：字幕卡点要按 BGM 强拍排 startFrame，不要按固定时长平均切；真人播音优先 edge-tts 的 `zh-CN-XiaoxiaoNeural`（温暖女声）替本机 Huihui；手机自录旁白走 `prep_voiceover_real.py` 降噪。

## D2. 只换字幕（不重剪，几十秒）

改 `subtitles.json`（四平台各一组字符串数组）后：

```powershell
python resub.py                       # 四条全换
python resub.py --only douyin         # 只换一条
```

原理：`work/style_<平台>/joined.mp4` 已是转场拼好的干净视频，`resub.py` 只重新生成 ASS 花字 + 烧录 + 复用 `bgm_clip.mp3`，画面一帧不动。条数不限（自动按 `clip_len - transition_dur` 均分），单条 >18 字会告警。输出 `outbox/styles/resub/`，不覆盖原片。

## D3. 只换音乐（不重剪，几十秒）

```powershell
python rebgm.py --list                       # 列出 5 套音乐方案
python rebgm.py --calendar 7                 # 看未来 7 天音乐排期
python rebgm.py --plan energy                # 用"燃爆节奏"换全部四条
python rebgm.py --plan soft --only douyin    # 只换一条
python rebgm.py --file jy_09.mp3 --start 8   # 直接指定曲子（四平台通用）
```

原理：`work/style_<平台>/subbed_mg.mp4` 是「已烧字幕 + MG进度条 + 无音轨」的干净画面，`rebgm.py` 拿它裁一段新 BGM（从指定秒数起）盖上去，字幕/画面/选段/转场全不动。方案库在 `music_styles.py` 的 `BGM_PLANS`（5 套：燃爆节奏/温柔治愈/科技未来/轻快活泼/大气开阔），每套四平台各指定 `(文件, 起始秒, 音量)`。输出 `outbox/styles/rebgm/<方案key>/`，不覆盖原片。没有指定 `--plan/--file` 时按当天日期自动选。

## E. 每天自动换字幕风格 + 音乐

```powershell
python daily_run.py                        # 每日闭环：扫 inbox 新素材→剪片→按今天同时换字幕风格+音乐
python daily_run.py --no-cut               # 不剪片，只用现有 joined.mp4 换当天字幕+音乐
python daily_subtitle.py --calendar 7      # 看未来 7 天字幕+音乐排期
python daily_subtitle.py --preview         # 看今天是什么字幕风格+音乐+字幕，不出片
python daily_subtitle.py --date 2026-11-22 --force   # 补做/重做某天
```

- 字幕库在 `subtitle_styles.py` 的 `STYLES`（6 套：现场口吻/技术视角/悬念提问/幽默段子/情绪种草/数据硬核）；音乐库在 `music_styles.py` 的 `BGM_PLANS`（5 套：燃爆节奏/温柔治愈/科技未来/轻快活泼/大气开阔），每套四平台各一组。
- **确定性轮换**：`index = 日期.toordinal() % len(库)`，重启/换机器结果一致，字幕相邻两天必不同（6 天周期）、音乐 5 天周期。加新风格/音乐只需往对应列表 append。
- `daily_subtitle.run_once(cfg, d, ...)` 会同时选中当天字幕风格 + 音乐方案，把音乐的 `(文件,起始秒,音量)` 经 `resub.resub_one(..., music=..., tag=...)` 覆盖 BGM。
- 产物 `outbox/styles/daily/YYYY-MM-DD/`，历史留档 `state/daily_subtitle_history.json` 与 `state/daily_run_history.json`（记当天字幕+音乐，同日不重复跑，除非 `--force`）。
- 定时用 dsh `schedule_create`（每天 08:00 触发 `python daily_run.py`）或 Windows 任务计划；已建任务 id `schedule-b0b267bb-4dfc-4db0-8b67-826b3960a029`。

## 验收（必须做，不能只看日志）

```powershell
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_type,codec_name,width,height -of default=noprint_wrappers=1 "outbox\styles\douyin_抖音.mp4"
```

合格线：`h264` + `1080x1920` + `aac` + 时长与 `target_duration` 差 < 1s + 文件 > 5 MB。
封面用 PIL 统计主色/亮度确认不是黑图；**不要用 read_image 做视觉核验**（本机模型 `hy4flash-free` 不支持图像输入，`modlens_read_image` 常 180s 超时），改用 `PIL.ImageStat` 客观统计或 ffprobe。

## 环境事实

- 需要 Python 3.10+ 与 ffmpeg（Windows 可用 `winget install Gyan.FFmpeg`）
- 剪映资源在 `%LOCALAPPDATA%\JianyingPro`：音乐缓存 `User Data\Cache\music\`、字体 `User Data\Resources\Font\`；用 `python import_jianying_assets.py` 导入到 `assets/`（仓库不分发这些版权资源）
- 剪映草稿 `draft_content.json` 是加密格式，读不出转场参数 → 剪映效果只能 ffmpeg 复刻，别浪费时间解密
- 成片默认文案围绕用户实际业务（机器人表演/四足机器人），换标题/文案/话题改 `captions.py`（不是 styles.py），再跑 `python sync_captions.py` 同步到 manifest；换视觉配方才改 `styles.py`

## 不要做的事

- 不要重写 `make_styles.py` 的分段/转场/音频链路，先读 `references/ffmpeg-traps.md`，那些坑都已经踩过并修好了。
- 不要用 `config.yaml`（工程读的是 `config.json`）。
- 不要在 `run.bat` 里加 `chcp 65001`、不要用 LF 换行（必须 CRLF + GBK）。
- 不要把剪映授权字体交给 ffmpeg `drawtext`（会 0xC0000005 崩溃）；它只能给 PIL 封面用。
- 不要在同一个 Python 进程里连续跑两个平台的 Playwright 发布。
