# 中文字体（不随仓库分发）

本目录**故意不含任何字体文件**。从剪映等软件提取的字体属于该软件/字体厂商的授权资源，
不适合随开源仓库分发。

## 补全方式

```powershell
python import_jianying_assets.py --fonts-only
```

从

```
%LOCALAPPDATA%\JianyingPro\User Data\Resources\Font
```

复制全部 `.ttf/.otf/.ttc` 到本目录。`styles.py` 的 `jy_font` 字段用中文关键词匹配：

| `jy_font` 值 | 期望文件名 |
|---|---|
| `新青年` | `新青年体.ttf` |
| `悠然` | `悠然体.ttf` |
| `后现代` | `后现代体.otf` |

文件名不匹配也不致命——`jianying_fx.font_path()` 匹配不到会返回 `None`，封面回退系统字体。

## 只用于封面，不要交给 ffmpeg drawtext

这条是踩过的坑：把剪映的授权字体通过 `drawtext=fontfile=...` 加载，ffmpeg 会直接
`exit 3221225477 (0xC0000005)` 崩溃，整段 MG 包装失败并静默回退。

**正确用法**：字体只交给 PIL 渲染封面（`make_cover()` 里的 `ImageFont.truetype`）；
花字与计数器用系统字体（`C:\Windows\Fonts\msyhbd.ttc`），稳定且不崩。

## 换成自己的字体

任何 `.ttf/.otf` 放进来，然后改 `styles.py` 里对应平台的 `jy_font` 为文件名关键词即可。
商用字体请自行确认授权范围。
