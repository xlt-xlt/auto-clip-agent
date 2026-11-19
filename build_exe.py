# -*- coding: utf-8 -*-
r"""把 gui.py 打包成可双击的「自动剪辑工坊」工具包。

用法：
    python build_exe.py

产物：dist\自动剪辑工坊\
    自动剪辑工坊.exe     主程序（双击即用）
    _internal\           程序依赖
    assets\              音乐库 + 剪映字体
    config.json          配置
    使用说明.txt
    inbox\ outbox\ work\ logs\ state\

改完 gui.py / styles.py / make_styles.py 后重跑本脚本即可更新工具包。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "自动剪辑工坊"
APP_DIR = ROOT / "dist" / NAME

# 只保留 styles.py 实际用到的剪映音乐库；soundhelix 早期素材不打包
KEEP_BGM_SUBDIR = "jianying"


def run(cmd: list[str]) -> None:
    print("[*] " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[-] 缺少 PyInstaller：python -m pip install pyinstaller")
        return 1

    print("[*] 打包 exe …")
    run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFont",
        "--hidden-import", "dotenv",
        "--hidden-import", "styles",
        "--hidden-import", "make_styles",
        "--hidden-import", "jianying_fx",
        "--hidden-import", "bgm_engine",
        "--exclude-module", "numpy",
        "--exclude-module", "cv2",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        str(ROOT / "gui.py"),
    ])

    print("[*] 布置运行环境 …")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config.json", APP_DIR / "config.json")

    assets = APP_DIR / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    (assets / "bgm" / KEEP_BGM_SUBDIR).mkdir(parents=True)
    for f in (ROOT / "assets" / "bgm" / KEEP_BGM_SUBDIR).glob("*.mp3"):
        shutil.copy2(f, assets / "bgm" / KEEP_BGM_SUBDIR / f.name)
    if (ROOT / "assets" / "fonts").exists():
        shutil.copytree(ROOT / "assets" / "fonts", assets / "fonts")

    for d in ("inbox", "outbox/styles", "work", "logs", "state"):
        (APP_DIR / d).mkdir(parents=True, exist_ok=True)

    doc = ROOT / "dist" / "使用说明.txt"
    if doc.exists():
        shutil.copy2(doc, APP_DIR / "使用说明.txt")

    size = sum(f.stat().st_size for f in APP_DIR.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"[+] 完成：{APP_DIR}  ({size:.0f} MB)")
    print(f"[+] 双击运行：{APP_DIR / (NAME + '.exe')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
