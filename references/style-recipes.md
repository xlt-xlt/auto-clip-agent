# 配方与精修（styles.py + 卡点 + 配音）

## 四平台配方（当前生效值）

| 字段 | 抖音 | 小红书 | 视频号 | 快手 |
|---|---|---|---|---|
| target_duration | 22s | 28.6s | 39.8s | 27s |
| n_clips / clip_len | 多段短切 | 中速 | 多段慢叙 | 中快 |
| bpm | 140 | 96 | 108 | 128 |
| bgm_file / start | jy_01 @8s | jy_05 @12s | jy_04 @10s | jy_11 @6s |
| jy_transition | 闪白 | 叠化 | 叠化 | 闪黑 |
| jy_font | 新青年体 | 悠然体 | 后现代体 | 新青年体 |
| impact | flash | soft | soft | hard |
| counter_label | 抖音计数 | 小红书计数 | 转发 | 老铁在看 |

改配方只改 `styles.py` 的 `STYLE_PROFILES`，`make_styles.py` 不用动。

## 换 BGM

可用曲库（`assets/bgm/jianying/jy_01..12.mp3`，来自本机剪映缓存，全是真曲目）：

| 文件 | 特性（onset-flux + 自相关实测） |
|---|---|
| jy_11 | 107BPM / 能量1226 —— **最燃最快**，快节奏/爆点首选 |
| jy_09 | 125BPM / 858 —— 快，偏电子 |
| jy_05 | 115BPM / 526 —— 中速明亮 |
| jy_03 / jy_02 | 53 / 52BPM / 能量 704 / 650 —— 慢、层次厚（自相关可能倍频，实际听感更快） |
| jy_10 | 100BPM / 251 —— 安静，适合叙事 |
| jy_04 / jy_08 / jy_06 | 94 / 94 / 91BPM —— 温和 |
| kalimba | 60BPM / 847 —— 卡林巴，治愈 |
| soundhelix_05 | 71BPM / 116 —— **最柔**，纯氛围 |

换法：改 `STYLE_PROFILES[p]["bgm_file"]` 与 `bgm_start`（换一个 8-20s 的入点避免前奏太空），`bgm_volume` 保持 0.12（人声优先）。
自相关对慢曲有倍频误差，**真要卡点以实际强拍检测为准**，别信 BPM 数字。

## 字幕卡点（关键：不要按固定时长平均切）

早期错误做法：12 张花字每张固定 105 帧（3.5s），与音乐完全脱节。

正确做法：先拿到 BGM 的**强拍时间表**，再按强拍排卡片的 `startFrame`。

拿强拍两条路：
- ChatCut `detect_beats`（有 ChatCut 时最准）：`detect_beats(assetId)` 返回 beats 列表。
  实测 jy_01 每小节 1.85s；jy_11 强拍落在 1.79 / 4.78 / 7.79 / 10.76 / 13.72 / 16.73 / 19.69 / 22.67 / 25.65 / 28.63 / 31.61 / 34.59 / 37.57 / 40.57s（间隔≈2.97s）。
- 自写 onset-flux + 自相关（无 ChatCut 时）：见 `_debug` 里 `probe.py` 思路——短时傅里叶 → 谱通量 → 自相关求周期 → 取峰值。

排卡片：`startFrame = round(强拍秒数 * fps)`，`durationFrames = 下一张 startFrame - 本张 startFrame`。
30fps 下 jy_11 的实测结果：

```python
STARTS = [0, 143, 234, 323, 412, 502, 591, 680, 770, 859, 948, 1038]
# 对应 0 / 4.77 / 7.8 / 10.77 / 13.73 / 16.73 / 19.7 / 22.67 / 25.67 / 28.63 / 31.63 / 34.6 / 37.6s
DUR    = [143, 89, 89, 89, 90, 89, 89, 90, 89, 89, 90, 222]   # 末张拉长到结尾
```

注意：音频轨（`edit_item`）一改，`read_captions` 的 revision 就失效，会报 `Caption inputs changed` → 重新 `read_captions` 取新 revision 再 `edit_captions`。

## 真人播音

### 首选：edge-tts 神经音色（免费、无限量）

```powershell
pip install edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m edge_tts --list-voices      # 看可用音色
python -m edge_tts --voice zh-CN-XiaoxiaoNeural --text "文案" --write-media out.mp3
```

zh-CN 可用音色：

| voice | 感觉 | 适合 |
|---|---|---|
| `zh-CN-XiaoxiaoNeural` | 温暖女声（新闻感） | **默认推荐**，口播/旁白 |
| `zh-CN-XiaoyiNeural` | 活泼卡通女声 | 轻快种草 |
| `zh-CN-YunjianNeural` | 运动激情男声 | 体育/炸场 |
| `zh-CN-YunxiNeural` | 阳光活泼男声 | 日常 vlog |
| `zh-CN-YunyangNeural` | 专业新闻男声 | 正经解说 |
| `zh-CN-liaoning-XiaobeiNeural` | 东北幽默女声 | 搞笑 |
| `zh-CN-shaanxi-XiaoniNeural` | 陕西明快女声 | 地方特色 |

生成后必须做响度归一，否则和 BGM 电平打架：

```
loudnorm=I=-16:TP=-2:LRA=11
```
实测归一后 mean ≈ -19dB / max ≈ -5dB，混音整体 -14.3 LUFS / peak -0.6dBFS 为佳。

**关键：逐句 TTS + 按字幕卡时间摆放，不要整段连读。**
整段连读会让口播和卡点花字完全错位（v3 的问题）。正确做法：

```python
for i, (text, start_ms) in enumerate(zip(SENTENCES, STARTS_MS)):
    subprocess.run(["edge-tts", "--voice", VOICE, "--text", text, "--write-media", f"seg{i}.mp3"])
    # 每段用 adelay 推到对应时间，最后 amix
filters = "".join(f"[{i}:a]adelay={ms}|{ms}[a{i}];" for i, ms in enumerate(STARTS_MS))
```

### 用户自己录音（最自然）

```powershell
python prep_voiceover_real.py "inbox\我的旁白.m4a"
```

链路：`highpass=f=80`（去低频轰鸣）→ `afftdn=nf=-25`（降噪）→ `acompressor=threshold=-18dB:ratio=3:attack=5:release=120`（压平手机录音的动态）→ `loudnorm=I=-16:TP=-2:LRA=11`。
产物 `work/voiceover_real_norm.wav`，含处理前后 volumedetect 对比，直接替换成片音轨。

### 不要用
本机 `System.Speech` 的 `Microsoft Huihui Desktop`——机械感重，用户明确说"机器合成的有点恐怖"。

## 平台文案差异（不是复制粘贴同一段）

- **抖音**：钩子在前 3 字，疑问句/惊叹句开头，话题 5-6 个
- **小红书**：第一人称场景叙事（"下班路上偶遇"），emoji 适度，话题 3-7 个，带"姐妹可以冲"式建议
- **视频号**：正式、价值导向（"非遗有了新玩法"），适合转发，话题 4-5 个
- **快手**：老铁口吻（"开眼了""双击666"），话题**最多 4 个**

封面文字（`cover_text`）与标题不要雷同，封面负责 3 秒抓眼，标题负责搜索关键词。
