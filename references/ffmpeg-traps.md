# ffmpeg 踩过的坑（都已修在 make_styles.py 里，改代码前必读）

## 1. zoompan 会炸，别用

想把画面做"推近"效果时用 `zoompan`，在 filter_complex + 尺寸变化场景下必报：

```
[fc#0] Error reinitializing filters!
Task finished with error code: -22 (Invalid argument)
```

改用**动态 crop**（每帧偏移由 n 驱动），实测两帧 MD5 不同，证明真在动：

```
scale={cw}:{ch},crop=w=1080:h=1920:x='(iw-ow)/2+sin(n*0.4)*{shake}':y='(ih-oh)/2+cos(n*0.32)*{shake}'
```

`{shake}` 是平台配方里的 `shake` 字段（像素），`n` 是帧号。

## 2. eq 的 brightness 在 crop 之后不生效

`eq=brightness=...` 放在 crop 后面，实测亮度几乎不变（76.0 vs 76.7）。要"爆点闪白"就用 `drawbox` 全屏覆盖：

```
drawbox=x=0:y=0:w=iw:h=ih:color=white@0.85:t=fill:enable='between(t,0.04,0.11)'
drawbox=...color=black@0.9...:enable='between(t,0.12,0.17)'
drawbox=...color=white@0.85...:enable='between(t,0.18,0.25)'
rgbashift=rh=16:bh=-16:gh=6:enable='between(t,0.20,0.42)'
```

`hard` 型就是上面这套三连闪白+黑+白 + rgbashift 故障感；`flash` 只留一次白闪；`soft` 轻闪。

## 3. drawbox enable 里的 t 是片段内相对时间

分段处理时每段的 `start_time=0`，所以 `between(t,0.04,...)` 恒指**该段开头** 0.04s 处，不是全片时间轴。要放在全片绝对时间上，得在 concat 之后再加一层 filter。

## 4. add_audio 的 afade out 起点写 0 会整段静音

```python
# 错：st=0 从 0 秒开始淡出 → 全程被 attenuate 到 0
afade=t=out:st=0:d=2
# 对：用真实时长减 1 秒
tail = ffprobe_duration(path) - 1.0
afade=t=out:st={tail}:d=1
```

## 5. BGM 叠加不能替换人声

早期版本直接 `-map 1:a` 只剩 BGM，人声没了。正确写法是 amix 双输入，人声保持 1.0、BGM 压到 0.12：

```
[1:a]volume={vol},afade=t=in:st=0:d=1[bg];
[0:a]volume=1.0[vo];
[vo][bg]amix=inputs=2:duration=first:dropout_transition=0[a]
```

注意 `afade` 参数名是 `d`（duration），不是 `dur`——写错会静默失败。

## 6. 分段与音轨

- 源有音轨：`-c:a aac -ar 44100 -ac 2`
- 烧字幕阶段用 `-c:a copy`
- 最终 concat 用 `-c copy`
- 源**无**音轨时才补 `anullsrc` 静音轨，否则成片在部分平台被判"无音频"

## 7. Windows 路径在 filter 里的转义

盘符冒号必须转义，否则被当成 filter 参数分隔符：

```python
def _escape_ffmpeg_path(p): return str(p).replace("\\", "/").replace(":", "\\:")
```

## 8. ASS 花字动画标签是小写

`\fscx` / `\fscy` / `\fad` / `\t` 必须小写。写成 `\Fscx` 不会报错，但字号动画完全不生效。参考：

```
{\fad(180,150)\t(0,250,\fscx108\fscy108)\fscx70\fscy70\t(250,400,\fscx100\fscy100)}
```

## 9. 剪映授权字体喂给 drawtext 会崩进程

`drawtext=fontfile=新青年体.ttf` 触发 `exit 3221225477 (0xC0000005)`，整段 MG 包装失败并回退成纯花字字幕。**结论：剪映字体只给 PIL 封面用**，drawtext 计数器/数字固定用系统字体 `C:\Windows\Fonts\msyhbd.ttc`。

## 10. ffprobe 解析别用 JSON

用 csv 更稳，避免中文路径与不规范 metadata 干扰：

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -show_entries format=duration -of csv=p=0 file.mp4
```
