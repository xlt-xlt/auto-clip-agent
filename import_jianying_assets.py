# -*- coding: utf-8 -*-
"""从本机剪映（JianyingPro）导入 BGM 与中文字体到 assets/。

仓库不内置第三方版权音乐/字体，克隆后跑一次本脚本即可补全，效果与本机一致。

用法：
    python import_jianying_assets.py                 # 导入 12 首音乐 + 全部字体
    python import_jianying_assets.py --music 8       # 只导入 8 首音乐
    python import_jianying_assets.py --fonts-only    # 只导入字体
    python import_jianying_assets.py --dry-run       # 只看会复制什么，不动盘

剪映资源位置（Windows 默认）：
    %LOCALAPPDATA%\\JianyingPro\\User Data\\Cache\\music         真实曲目缓存
    %LOCALAPPDATA%\\JianyingPro\\User Data\\Resources\\Font      特色中文字体
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST_MUSIC = ROOT / "assets" / "bgm" / "jianying"
DEST_FONT = ROOT / "assets" / "fonts"

# 音乐时长过滤：太短的是音效，太长的可能是播客
MIN_SEC, MAX_SEC, MIN_BYTES = 40.0, 300.0, 200 * 1024


def _localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def find_music_dir() -> Path | None:
    base = _localappdata() / "JianyingPro"
    for cand in (base / "User Data" / "Cache" / "music",
                 base / "User Data" / "Cache" / "Music"):
        if cand.is_dir():
            return cand
    return None


def find_font_dir() -> Path | None:
    base = _localappdata() / "JianyingPro"
    for cand in (base / "User Data" / "Resources" / "Font",
                 base / "Resources" / "Font"):
        if cand.is_dir():
            return cand
    return None


def duration_of(path: Path) -> float:
    """用 ffprobe 取时长；失败返回 0。"""
    exe = shutil.which("ffprobe") or "ffprobe"
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def pick_music(music_dir: Path, count: int) -> list[Path]:
    """筛出真实曲目：>200KB 且 40s < 时长 < 300s，按体积降序取前 count 首。"""
    cands = [p for p in music_dir.iterdir()
             if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac"}
             and p.stat().st_size >= MIN_BYTES]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    picked: list[Path] = []
    for p in cands:
        if len(picked) >= count:
            break
        d = duration_of(p)
        if MIN_SEC < d < MAX_SEC:
            picked.append(p)
            print(f"  ✓ {p.name}  {d:.0f}s  {p.stat().st_size // 1024}KB")
        else:
            print(f"  · 跳过 {p.name}  {d:.0f}s（不在 {MIN_SEC:.0f}-{MAX_SEC:.0f}s）")
    return picked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从本机剪映导入 BGM 与字体")
    ap.add_argument("--music", type=int, default=12, help="导入音乐首数（默认 12）")
    ap.add_argument("--fonts-only", action="store_true", help="只导入字体")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划")
    args = ap.parse_args(argv)

    done = 0

    if not args.fonts_only:
        print("=== 音乐 ===")
        md = find_music_dir()
        if not md:
            print("  找不到剪映音乐缓存目录。请先在本机剪映里使用/下载一些音乐，或用 --fonts-only 跳过。")
        else:
            print(f"  源: {md}")
            picked = pick_music(md, args.music)
            if not picked:
                print("  没有符合条件（40-300s 真实曲目）的文件。")
            else:
                DEST_MUSIC.mkdir(parents=True, exist_ok=True)
                for i, src in enumerate(picked, 1):
                    dst = DEST_MUSIC / f"jy_{i:02d}{src.suffix.lower()}"
                    if args.dry_run:
                        print(f"  [dry] {src.name} -> {dst.name}")
                    else:
                        shutil.copy2(src, dst)
                        print(f"  已导入 {dst.name}  ←  {src.name}")
                        done += 1
                print(f"  映射：jy_01..jy_{len(picked):02d}，styles.py 的 bgm_file 直接引用这些文件名")

    print("=== 字体 ===")
    fd = find_font_dir()
    if not fd:
        print("  找不到剪映字体目录，跳过（封面会回退系统字体，不影响出片）。")
    else:
        print(f"  源: {fd}")
        fonts = [p for p in fd.iterdir()
                 if p.is_file() and p.suffix.lower() in {".ttf", ".otf", ".ttc"}]
        if not fonts:
            print("  目录里没有字体文件。")
        else:
            DEST_FONT.mkdir(parents=True, exist_ok=True)
            for src in fonts:
                dst = DEST_FONT / src.name
                if args.dry_run:
                    print(f"  [dry] {src.name}")
                else:
                    shutil.copy2(src, dst)
                    print(f"  已导入 {src.name}  {src.stat().st_size // 1024}KB")
                    done += 1

    print()
    if args.dry_run:
        print("dry-run 结束，未修改任何文件。")
    else:
        print(f"完成，共导入 {done} 个文件。下一步：python jianying_test.py 自检。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
