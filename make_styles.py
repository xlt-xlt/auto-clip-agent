# -*- coding: utf-8 -*-
"""一键把 inbox 素材剪辑成四条【成片级】不同平台风格的视频。

区别于旧版"素材串烧"，本引擎做了真正的成片包装：
  · 每片段：卡点推近(zoompan) + 抖动(shake)，画面不再是死板平移
  · 片段间：xfade 转场（抖音闪白/小红书叠化/视频号淡入/快手闪黑）
  · 字幕：ASS 花字动画（弹出/放大强调/淡入），不是静态贴字
  · MG 包装：动态进度条 + 实时递增计数器（drawbox/drawtext 表达式驱动）
  · 声音：纯 BGM 覆盖、去掉现场原声；BGM 强拍对齐剪辑点（程序化合成或现成音乐）
  · 每个平台：独立选段/色调/字幕样式/营销文案/封面/节奏

用法：
  python make_styles.py                 # 用 inbox 全部素材生成四平台四条
  python make_styles.py --only douyin   # 只生成某平台
  python make_styles.py --src DIR       # 指定素材目录
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from utils import load_config, ensure_dirs, log, run, find_ffmpeg, ffprobe_duration, ROOT
from styles import STYLE_PROFILES, PLATFORM_ORDER
from bgm_engine import gen as gen_bgm
from jianying_fx import resolve_transition, font_path as jy_font_path

ROOT = ROOT  # 由 utils 统一解析（源码=脚本目录，exe=exe 所在目录）
FONT_REG = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def ffprobe(path: Path) -> dict:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=creationflags)
    parts = (p.stdout.strip().split("x") or ["0", "0", "0"])
    try:
        w, h = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        w, h = 0, 0
    dur = 0.0
    try:
        dur = float(parts[2])
    except (ValueError, IndexError):
        dur = 0.0
    if dur <= 0:
        dur = ffprobe_duration(str(path), "ffmpeg")
    return {"path": path, "w": w, "h": h, "dur": dur, "landscape": w > h}


SEC_SEED = {"douyin": 11, "xiaohongshu": 23, "shipinhao": 37, "kuaishou": 53}
POS_FACTOR = {"douyin": 0.12, "xiaohongshu": 0.42, "shipinhao": 0.58, "kuaishou": 0.30}


def pick_segments(sources: list[dict], platform: str, style: dict) -> list[tuple[Path, float, float]]:
    rnd = random.Random(SEC_SEED[platform])
    need = style["clip_len"]
    cands = [s for s in sources if s["dur"] >= need + 2.0]
    if len(cands) < 2:
        cands = [s for s in sources if s["dur"] >= need + 0.5]
    rnd.shuffle(cands)
    segs = []
    for i in range(style["n_clips"]):
        it = cands[i % len(cands)]
        max_start = max(0.0, it["dur"] - need - 0.2)
        factor = POS_FACTOR[platform]
        start = max_start * factor * rnd.uniform(0.8, 1.25)
        start = min(max(0.3, start), max_start)
        segs.append((it["path"], round(start, 2), float(need)))
    return segs


def vf_base(style: dict) -> str:
    """阶段1：竖屏适配（模糊背景填充）+ 平台色调。"""
    color = style.get("color_filter", "")
    return (
        "split[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bgb];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2:shortest=1[canv];"
        f"[canv]{color},setsar=1,format=yuv420p"
    )


def vf_motion(style: dict) -> str:
    """阶段2：动态 crop 窗口实现推近+抖动（比 zoompan 稳定，逐帧表达式不触发重初始化）。"""
    shake = int(style.get("shake", 0))
    zoom = float(style.get("zoom_step", 0.001))
    # zoom_step 映射为放大倍率：抖音/快手 ~1.15，小红书/视频号 ~1.05
    scale_factor = 1.0 + min(0.20, zoom * 130)
    cw, ch = round(1080 * scale_factor), round(1920 * scale_factor)
    if shake > 0:
        x = f"(iw-ow)/2+sin(n*0.4)*{shake}"
        y = f"(ih-oh)/2+cos(n*0.32)*{shake}"
    else:
        x, y = "(iw-ow)/2", "(ih-oh)/2"
    return (f"scale={cw}:{ch},crop=w=1080:h=1920:x='{x}':y='{y}',setsar=1,format=yuv420p")


def vf_impact(style: dict, seg_dur: float) -> str:
    """爆点特效：段首快闪(白/黑/白) + RGB色差故障，制造视觉冲击。
    用 drawbox 闪屏（实测可靠）而非 eq brightness（crop 后不生效）。
    hard   : 白闪→黑闪→白闪 三连快闪 + RGB故障（抖音/快手爆点）
    flash  : 白闪 + RGB故障
    soft   : 单次轻柔白闪（氛围感平台，不破坏调性）
    """
    kind = style.get("impact", "none")
    if kind == "none":
        return ""
    if kind == "soft":
        return "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.32:t=fill:enable='between(t,0.04,0.14)'"
    # RGB色差故障（穿插在闪屏之间）
    glitch = "rgbashift=rh=16:bh=-16:gh=6:enable='between(t,0.20,0.42)'"
    if kind == "hard":
        # 三连快闪：白(0.04-0.11) 黑(0.12-0.17) 白(0.18-0.25)，制造强节奏爆点
        flash = (
            "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t=fill:enable='between(t,0.04,0.11)',"
            "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.88:t=fill:enable='between(t,0.12,0.17)',"
            "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t=fill:enable='between(t,0.18,0.25)'"
        )
    else:  # flash
        flash = "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.95:t=fill:enable='between(t,0.04,0.16)'"
    return flash + "," + glitch


def build_clips(ffmpeg: str, segs, style: dict, work: Path) -> list[Path]:
    """两阶段：先竖屏适配，再对成片做推近抖动+爆点特效，规避 zoompan 在 filter_complex 中重初始化崩溃。"""
    parts = []
    base = vf_base(style)
    motion = vf_motion(style)
    impact = vf_impact(style, style["clip_len"])
    for i, (src, start, dur) in enumerate(segs):
        stage1 = work / f"base_{i:02d}.mp4"
        out = work / f"clip_{i:02d}.mp4"
        # 阶段1：竖屏适配+色调
        run([ffmpeg, "-y", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src),
             "-filter_complex", base, "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "21", "-r", str(style["fps"]), "-t", f"{dur:.2f}", str(stage1)])
        # 阶段2：推近+抖动+爆点特效；失败则退到阶段1的静止画面
        vf2 = motion + ("," + impact if impact else "")
        try:
            run([ffmpeg, "-y", "-i", str(stage1), "-vf", vf2, "-an",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                 "-r", str(style["fps"]), "-t", f"{dur:.2f}", str(out)])
        except Exception as e:
            log(f"  片段{i+1} 爆点/动效失败({e}),回退纯动效", "WARN")
            try:
                run([ffmpeg, "-y", "-i", str(stage1), "-vf", motion, "-an",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                     "-r", str(style["fps"]), "-t", f"{dur:.2f}", str(out)])
            except Exception:
                run([ffmpeg, "-y", "-i", str(stage1), "-c", "copy", str(out)])
        parts.append(out)
        log(f"  片段 {i+1}/{len(segs)} [{src.name[:10]}@{start}s] 爆点={style.get('impact')}", "OK")
    return parts


def concat_xfade(ffmpeg: str, parts: list[Path], style: dict, work: Path) -> tuple[Path, float]:
    """用 xfade 串联片段，返回(成片, 总时长)。转场类型按平台区分。"""
    td = float(style.get("transition_dur", 0.25))
    # 剪映中文转场名 -> ffmpeg xfade 名（如"闪白"->fadewhite）
    jy_name = style.get("jy_transition")
    trans = resolve_transition(jy_name) if jy_name else style.get("transition", "fade")
    dur = float(style["clip_len"])
    n = len(parts)
    if n == 1:
        return parts[0], dur

    fc_parts = []
    # 重置每段时间戳，保证 xfade 对齐
    for i in range(n):
        fc_parts.append(f"[{i}:v]setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]")
    cur = "v0"
    for i in range(1, n):
        # 第 i 次转场起点：前 i 段总时长 - i 个已用转场重叠
        offset = i * dur - i * td
        out_lbl = f"x{i}"
        fc_parts.append(
            f"[{cur}][v{i}]xfade=transition={trans}:duration={td:.3f}:offset={offset:.3f}[{out_lbl}]"
        )
        cur = out_lbl
    fc = ";".join(fc_parts)
    out = work / "joined.mp4"
    cmd = [ffmpeg, "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", fc, "-map", f"[{cur}]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-r", str(style["fps"]), "-an", str(out)]
    try:
        run(cmd)
        total = ffprobe_duration(str(out), ffmpeg)
        log(f"转场串联完成: {n}段 / {trans} / 总时长{total:.1f}s", "OK")
        return out, total
    except Exception as e:
        # 回退： concat copy 硬拼
        log(f"xfade失败({e}),回退硬拼", "WARN")
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        out2 = work / "joined_plain.mp4"
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out2)])
        return out2, n * dur


def ass_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(style: dict, work: Path, total_dur: float) -> Path:
    """花字动画字幕：每段弹出(t\fscx放大) + 淡入(fad)，按转场后时间轴排布。"""
    st = style["sub_style"]
    accent = style.get("mg_accent", "0xFFD700")
    # ASS 主样式
    style_line = (
        f"Style: Main,{st['font']},{st['size']},{st['primary']},&H000000FF,"
        f"{st['outline']},{st['back']},"
        f"{'-1' if st['bold'] else '0'},0,0,0,100,100,0,0,1,"
        f"{st['outline_w']},{st['shadow']},{st['alignment']},10,10,{st['margin_v']},1"
    )
    # 角标样式（平台水印式强调条）
    tag_size = int(st["size"] * 0.5)
    tag_line = (
        f"Style: Tag,{st['font']},{tag_size},{accent},&H000000FF,"
        f"&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,1.5,0,8,20,20,40,1"
    )
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n{tag_line}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    beats = style["beats"]
    td = float(style.get("transition_dur", 0.25))
    seg_span = float(style["clip_len"]) - td  # 转场后每段的有效时长
    for i, text in enumerate(beats):
        st_t = i * seg_span + 0.10
        en_t = min((i + 1) * seg_span - 0.10, st_t + seg_span - 0.2)
        safe = text.replace("{", r"\{").replace("}", r"\}")
        # 花字：0.25s 从 70% 放大到 108% 再回落到 100%，配合淡入淡出
        anim = r"{\fad(180,150)\t(0,250,\fscx108\fscy108)\fscx70\fscy70\t(250,400,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{ass_ts(st_t)},{ass_ts(en_t)},Main,,0,0,0,,{anim}{safe}")
        # 角标：每段右下角出现平台名（tag_text 可覆盖，避免"精选"这类营销词）
        tag_text = style.get("tag_text") or f"{style['platform']} · 精选"
        tag = f"Dialogue: 1,{ass_ts(st_t)},{ass_ts(en_t)},Tag,,0,0,0,,{tag_text}"
        events.append(tag)
    ass = work / "sub.ass"
    ass.write_text(head + "\n".join(events) + "\n", encoding="utf-8-sig")
    return ass


def esc(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def burn_subs_mg(ffmpeg: str, video: Path, ass: Path, style: dict,
                 work: Path, total_dur: float) -> Path:
    """烧花字字幕 + 动态进度条 + 实时递增计数器（MG包装）。"""
    out = work / "subbed_mg.mp4"
    accent = style.get("mg_accent", "0xFFD700")
    label = style.get("counter_label", "播放量")
    cstart = int(style.get("counter_start", 10000))
    crate = int(style.get("counter_rate", 1000))

    # drawtext 字体：必须用系统微软雅黑。剪映特色字体(新青年/后现代)是授权字体，
    # ffmpeg 的 freetype 加载会触发 0xC0000005 崩溃，实测 MG 包装整段报废。
    # 剪映字体改在封面(PIL渲染)上使用，稳定且可见。
    fp = str(FONT_BOLD).replace("\\", "/").replace(":", r"\:")
    # 计数器：eif 表达式用帧号 n 实时计算 = start + n*rate/fps
    fps = style["fps"]
    counter_txt = f"%{{eif\\:({cstart}+n*{crate}/{fps})\\:d}}"
    # 进度条：drawbox 宽度随 t 增长
    bar_w = f"(iw-80)*t/{total_dur:.3f}"

    vf = (
        f"ass='{esc(ass)}',"
        # 顶部计数器：标签 + 实时数字
        f"drawtext=fontfile='{fp}':text='{label} ':x=60:y=70:fontsize=40:"
        f"fontcolor=white:box=1:boxcolor=black@0.45:boxborderw=12,"
        f"drawtext=fontfile='{fp}':text='{counter_txt}':x=60+{label.__len__()*40}:y=70:"
        f"fontsize=44:fontcolor={accent}:box=1:boxcolor=black@0.45:boxborderw=12,"
        # 底部进度条：底槽 + 动态填充
        f"drawbox=x=40:y=1850:w=iw-80:h=6:color=white@0.25:t=fill,"
        f"drawbox=x=40:y=1850:w='{bar_w}':h=6:color={accent}@0.95:t=fill"
    )
    try:
        run([ffmpeg, "-y", "-i", str(video), "-vf", vf,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", "-an", str(out)])
    except Exception as e:
        # 回退：只烧花字字幕，放弃 MG 进度条/计数器
        log(f"MG包装失败({e}),回退仅花字字幕", "WARN")
        run([ffmpeg, "-y", "-i", str(video), "-vf", f"ass='{esc(ass)}'",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


def get_bgm(cfg: dict, style: dict, platform: str, total_dur: float, work: Path,
            ffmpeg: str) -> Path:
    """选真实热门风格曲目：按 style.bgm_file 固定映射，从 bgm_start 裁副歌段；无则程序化兜底。"""
    bgm_dir = Path(cfg["paths"].get("bgm", "")) if cfg["paths"].get("bgm") else None
    if bgm_dir and bgm_dir.exists():
        wanted = style.get("bgm_file")
        chosen = None
        if wanted:
            cand = bgm_dir / wanted
            if not cand.exists():  # 剪映音乐放在 bgm/jianying/ 子目录
                cand = bgm_dir / "jianying" / wanted
            if cand.exists():
                chosen = cand
        if chosen is None:
            bgms = [f for f in bgm_dir.rglob("*")
                    if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}]
            if bgms:
                rnd = random.Random(SEC_SEED.get(platform, 7))
                chosen = rnd.choice(bgms)
        if chosen is not None:
            start = int(style.get("bgm_start", 0))
            seg = work / "bgm_clip.mp3"
            try:
                run([ffmpeg, "-y", "-ss", str(start), "-i", str(chosen),
                     "-t", f"{total_dur + 1.0:.2f}", "-c:a", "libmp3lame", "-q:a", "2", str(seg)])
                log(f"使用真实BGM: {chosen.name} (从{start}s副歌截取)", "OK")
                return seg
            except Exception as e:
                log(f"BGM裁剪失败({e}),直接用原曲", "WARN")
                return chosen
    # 程序化合成：强拍对齐转场点
    wav = work / "bgm_gen.wav"
    gen_bgm(wav, total_dur + 0.5, float(style["bpm"]), style["bgm_style"])
    log(f"程序化生成BGM: {style['bpm']}BPM / {style['bgm_style']}", "OK")
    return wav


def add_audio(ffmpeg: str, video: Path, bgm: Path, style: dict, work: Path) -> Path:
    """纯 BGM 覆盖，去掉现场原声。音量按平台设定，淡入淡出。"""
    out = work / "with_audio.mp4"
    vol = float(style.get("bgm_volume", 0.85))
    # 尾部 1 秒淡出；时长从视频探测，避免 st=0 导致整段静音
    tail = max(0.1, ffprobe_duration(str(video), ffmpeg) - 1.0)
    fc = (f"[1:a]volume={vol},afade=t=in:st=0:d=0.8,"
          f"afade=t=out:st={tail:.2f}:d=1.0[a]")
    run([ffmpeg, "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(bgm),
         "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-shortest",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(out)])
    return out


def make_cover(ffmpeg: str, video: Path, style: dict, work: Path, out: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    frame = work / "cover_raw.jpg"
    run([ffmpeg, "-y", "-ss", "1.0", "-i", str(video), "-vframes", "1", "-q:v", "2", str(frame)])
    im = Image.open(frame).convert("RGB")
    W, H = im.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(int(H * 0.55), H):
        alpha = int(200 * (y - H * 0.55) / (H * 0.45))
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    dr = ImageDraw.Draw(im)

    # 封面主字体用剪映特色字体（新青年/悠然/后现代），失败回退微软雅黑
    jy_font = jy_font_path(style.get("jy_font", "")) if style.get("jy_font") else None

    def font(sz, bold=True):
        if jy_font and Path(jy_font).exists():
            try:
                return ImageFont.truetype(jy_font, sz)
            except Exception:
                pass
        p = FONT_BOLD if (bold and FONT_BOLD.exists()) else FONT_REG
        try:
            return ImageFont.truetype(str(p), sz)
        except Exception:
            return ImageFont.load_default()

    main_txt = style["cover_text"]
    sub_txt = style.get("cover_sub", "")
    f1 = font(int(W * 0.085), True)
    f2 = font(int(W * 0.048), False)

    def wrap(text, f, maxw):
        lines, cur = [], ""
        for ch in text:
            if dr.textlength(cur + ch, font=f) > maxw and cur:
                lines.append(cur); cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines

    lines = wrap(main_txt, f1, W * 0.86)
    y = H * 0.72
    for ln in lines:
        dr.text((W / 2, y), ln, font=f1, fill=(255, 255, 255), anchor="mm",
                stroke_width=3, stroke_fill=(0, 0, 0))
        y += int(W * 0.10)
    if sub_txt:
        dr.text((W / 2, min(y + 12, H * 0.92)), sub_txt, font=f2,
                fill=(255, 235, 120), anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
    im.save(out, quality=90)
    return out


def make_one(platform: str, sources: list[dict], cfg: dict, outdir: Path) -> dict:
    style = STYLE_PROFILES[platform]
    log(f"===== 生成 {style['label']} =====")
    work = ROOT / "work" / f"style_{platform}"
    work.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(cfg)

    segs = pick_segments(sources, platform, style)
    log(f"选段: {len(segs)} 个片段, 目标时长 {style['target_duration']}s")
    parts = build_clips(ffmpeg, segs, style, work)
    joined, total_dur = concat_xfade(ffmpeg, parts, style, work)
    ass = build_ass(style, work, total_dur)
    subbed = burn_subs_mg(ffmpeg, joined, ass, style, work, total_dur)
    bgm = get_bgm(cfg, style, platform, total_dur, work, ffmpeg)
    audioed = add_audio(ffmpeg, subbed, bgm, style, work)

    final = outdir / f"{platform}_{style['platform']}.mp4"
    run([ffmpeg, "-y", "-i", str(audioed), "-c", "copy", str(final)])
    cover = make_cover(ffmpeg, final, style, work, outdir / f"{platform}_{style['platform']}_cover.jpg")

    dur = ffprobe_duration(str(final), ffmpeg)
    log(f"完成: {final.name} ({dur:.1f}s)", "OK")
    return {
        "platform": platform, "label": style["label"], "video": str(final),
        "cover": str(cover), "duration": round(dur, 1),
        "title": style["title"], "caption": style["caption"],
        "hashtags": style["hashtags"],
        "transition": style.get("transition"), "bpm": style.get("bpm"),
        "bgm": "generated" if "bgm_gen" in str(bgm) else "provided",
        "bgm_file": style.get("bgm_file"),
        # 剪映音乐以 jy_ 命名且存于 assets/bgm/jianying/；裁剪后路径不含 jianying，
        # 故按 bgm_file 前缀与其实际落点判断来源
        "bgm_source": "剪映音乐库" if (
            str(style.get("bgm_file", "")).startswith("jy_")
            and (ROOT / "assets" / "bgm" / "jianying" / str(style.get("bgm_file", ""))).exists()
        ) else "本地",
        "jy_transition": style.get("jy_transition"), "jy_font": style.get("jy_font"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=PLATFORM_ORDER, help="只生成某个平台")
    ap.add_argument("--src", help="素材目录（默认 inbox）")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    src_dir = Path(args.src) if args.src else ROOT / cfg["paths"]["inbox"]
    outdir = ROOT / "outbox" / "styles"
    outdir.mkdir(parents=True, exist_ok=True)

    files = sorted([p for p in src_dir.glob("*.mp4")])
    if not files:
        log(f"素材目录无 mp4: {src_dir}", "ERR")
        return
    log(f"发现 {len(files)} 个素材，开始逐平台探测…")
    sources = [ffprobe(p) for p in files]
    sources = [s for s in sources if s["dur"] > 3]
    log(f"有效素材 {len(sources)} 个")

    targets = [args.only] if args.only else PLATFORM_ORDER
    results = []
    for p in targets:
        try:
            results.append(make_one(p, sources, cfg, outdir))
        except Exception as e:
            log(f"{p} 生成失败: {e}", "ERR")

    manifest = outdir / "manifest.json"
    merged = {}
    if manifest.exists():
        try:
            for item in json.loads(manifest.read_text(encoding="utf-8")):
                merged[item["platform"]] = item
        except Exception:
            pass
    for r in results:
        merged[r["platform"]] = r
    ordered = [merged[p] for p in PLATFORM_ORDER if p in merged]
    manifest.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"全部完成，清单: {manifest} (共 {len(ordered)} 条)", "OK")
    for r in results:
        log(f"  {r['label']}: {r['video']} ({r['duration']}s)")


if __name__ == "__main__":
    main()
