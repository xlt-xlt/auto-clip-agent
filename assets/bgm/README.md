# 背景音乐（不随仓库分发）

本目录**故意不含任何音频文件**。仓库里放的第三方音乐有版权问题，所以只提供导入脚本。

## 补全方式（推荐：从本机剪映导入）

如果你本机装了剪映，且平时在剪映里用过/下载过音乐，跑一条命令即可：

```powershell
python import_jianying_assets.py
```

脚本会从

```
%LOCALAPPDATA%\JianyingPro\User Data\Cache\music
```

筛出真实曲目（>200KB、40 秒至 5 分钟），按体积降序取前 12 首，复制成 `jy_01.mp3 … jy_12.mp3`。
`styles.py` 里的 `bgm_file` 直接引用这些文件名，所以文件名必须保持 `jy_NN` 形式。

想少导几首：`python import_jianying_assets.py --music 6`。

## 用自己的音乐

把任意 mp3/wav 放进本目录或 `jianying/` 子目录，然后让 `styles.py` 的 `bgm_file` 指向该文件名。
`bgm_start` 控制从第几秒开始截取（一般取副歌，例如 8-15 秒）。

## 什么都不放也能跑

`make_styles.py:get_bgm()` 找不到任何音频时会回退到 `bgm_engine.py` 的**程序化合成**——
按平台 BPM 与风格用正弦波+包络生成一条卡点 BGM，零依赖、无版权问题，但听感明显不如真实曲目。

## 选曲参考（按实测能量/速度）

| 场景 | BPM / 能量 | 适合 |
|---|---|---|
| 快节奏爆点 | 107-125 BPM，能量 >800 | 抖音、快手 |
| 中速明亮 | 90-115 BPM | 小红书 |
| 温和叙事 | 85-95 BPM | 视频号 |
| 纯氛围 | 60-75 BPM | 情绪片、慢镜头 |

自己量：跑一遍 `ffprobe` 看时长，或听副歌起点再填 `bgm_start`。
