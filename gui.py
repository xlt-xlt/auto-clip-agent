# -*- coding: utf-8 -*-
"""自动剪辑工坊 —— 图形界面版（零额外依赖，Python 自带 tkinter）。

双击「启动工具.bat」或 `python gui.py` 打开。
流程：选素材文件夹 → 勾平台 → 点开始 → 实时看日志 → 生成完自动打开输出目录。
"""
from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
    else Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from utils import load_config, ensure_dirs, VIDEO_EXT          # noqa: E402
import make_styles as ms                                       # noqa: E402
from styles import PLATFORM_ORDER, STYLE_PROFILES              # noqa: E402


class QueueWriter:
    """把后台线程的 print 重定向进队列，供界面消费。"""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s: str):
        if s:
            self.q.put(("log", s))

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自动剪辑工坊 · 四平台成片")
        self.geometry("960x700")
        self.minsize(820, 560)
        self.configure(bg="#11151c")

        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.vars: dict[str, tk.BooleanVar] = {}
        self.last_outdir = ROOT / "outbox" / "styles"

        self._build_style()
        self._build_ui()
        self._env_check()
        self.after(120, self._drain_queue)

    def _env_check(self):
        """启动时自检：ffmpeg、素材数、BGM 库、字体，直接写进日志区。"""
        from utils import find_ffmpeg
        lines = ["自动剪辑工坊 已就绪。把素材丢进 inbox，勾平台，点开始。", ""]
        try:
            lines.append(f"ffmpeg  ：{find_ffmpeg()}")
        except Exception as e:
            lines.append(f"ffmpeg  ：未找到（{e}）—— 需要先安装 ffmpeg 并加入 PATH")
        src = Path(self.src_var.get())
        n = len([p for p in src.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]) if src.exists() else 0
        lines.append(f"素材    ：{src}（{n} 个视频）")
        bgm = ROOT / "assets" / "bgm" / "jianying"
        lines.append(f"BGM 库  ：{len(list(bgm.glob('*.mp3'))) if bgm.exists() else 0} 首剪映音乐")
        fonts = ROOT / "assets" / "fonts"
        lines.append(f"字体    ：{len(list(fonts.glob('*'))) if fonts.exists() else 0} 个剪映字体")
        lines.append(f"输出    ：{self.last_outdir}")
        lines.append("-" * 58)
        self._append("\n".join(lines) + "\n")

    # ---------- 样式 ----------
    def _build_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background="#11151c", foreground="#e6edf5",
                     font=("Microsoft YaHei UI", 10))
        st.configure("TFrame", background="#11151c")
        st.configure("TLabel", background="#11151c", foreground="#e6edf5")
        st.configure("Hint.TLabel", foreground="#7d8b9c")
        st.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"),
                     foreground="#4cc2ff")
        st.configure("TCheckbutton", background="#11151c", foreground="#e6edf5")
        st.configure("TButton", padding=(14, 8),
                     background="#1d2532", foreground="#e6edf5")
        st.map("TButton", background=[("active", "#2a3547")])
        st.configure("Go.TButton", padding=(20, 10),
                     background="#1f6feb", foreground="#ffffff",
                     font=("Microsoft YaHei UI", 11, "bold"))
        st.map("Go.TButton", background=[("active", "#2f7ffb")])
        st.configure("TEntry", fieldbackground="#1a2130", foreground="#e6edf5")

    # ---------- 界面 ----------
    def _build_ui(self):
        pad = {"padx": 18, "pady": 8}

        head = ttk.Frame(self)
        head.pack(fill="x", **pad)
        ttk.Label(head, text="自动剪辑工坊", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="  素材进 → 四条成片出", style="Hint.TLabel").pack(side="left", pady=(6, 0))

        # 素材目录
        src = ttk.Frame(self)
        src.pack(fill="x", **pad)
        ttk.Label(src, text="素材文件夹").pack(side="left")
        self.src_var = tk.StringVar(value=str(ROOT / "inbox"))
        e = ttk.Entry(src, textvariable=self.src_var, width=64)
        e.pack(side="left", padx=8, fill="x", expand=True)
        ttk.Button(src, text="浏览…", command=self._pick_dir).pack(side="left")
        ttk.Button(src, text="打开", command=lambda: self._open(self.src_var.get())).pack(side="left", padx=6)

        # 平台选择
        box = ttk.LabelFrame(self, text=" 生成哪些平台 ")
        box.pack(fill="x", **pad)
        grid = ttk.Frame(box)
        grid.pack(fill="x", padx=10, pady=10)
        for i, p in enumerate(PLATFORM_ORDER):
            st = STYLE_PROFILES[p]
            v = tk.BooleanVar(value=True)
            self.vars[p] = v
            cb = ttk.Checkbutton(grid, text=f"{st['label']}", variable=v)
            cb.grid(row=0, column=i * 2, sticky="w", padx=(8, 2), pady=4)
            ttk.Label(grid, text=f"{int(st['target_duration'])}s",
                      style="Hint.TLabel").grid(row=0, column=i * 2 + 1, sticky="w", padx=(0, 18))

        # 操作按钮
        ops = ttk.Frame(self)
        ops.pack(fill="x", **pad)
        self.go_btn = ttk.Button(ops, text="开始生成", style="Go.TButton", command=self._start)
        self.go_btn.pack(side="left")
        self.out_btn = ttk.Button(ops, text="打开输出目录",
                                  command=lambda: self._open(str(self.last_outdir)))
        self.out_btn.pack(side="left", padx=10)
        ttk.Button(ops, text="清空日志", command=self._clear).pack(side="left")
        self.status = ttk.Label(ops, text="就绪", style="Hint.TLabel")
        self.status.pack(side="right")

        self.pbar = ttk.Progressbar(self, mode="indeterminate")
        self.pbar.pack(fill="x", padx=18, pady=(0, 6))

        # 日志
        self.log = scrolledtext.ScrolledText(
            self, bg="#0b0f15", fg="#c9d6e3", insertbackground="#c9d6e3",
            font=("Consolas", 10), relief="flat", wrap="word", height=20)
        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.log.configure(state="disabled")

    # ---------- 动作 ----------
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.src_var.get() or str(ROOT))
        if d:
            self.src_var.set(d)

    def _open(self, path: str):
        p = Path(path)
        if not p.exists():
            messagebox.showinfo("提示", f"目录还不存在：\n{p}")
            return
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _append(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        if self.busy:
            return
        src = Path(self.src_var.get())
        targets = [p for p in PLATFORM_ORDER if self.vars[p].get()]
        if not src.exists():
            messagebox.showwarning("路径不对", f"素材文件夹不存在：\n{src}")
            return
        files = sorted([p for p in src.iterdir()
                        if p.is_file() and p.suffix.lower() in VIDEO_EXT])
        if not files:
            messagebox.showwarning("没有素材", f"这个文件夹里没有视频文件：\n{src}")
            return
        if not targets:
            messagebox.showwarning("没选平台", "至少勾选一个平台。")
            return

        self.busy = True
        self.go_btn.state(["disabled"])
        self.pbar.start(12)
        self.status.configure(text=f"正在处理 {len(files)} 个素材…")
        self._append(f"\n{'='*60}\n开始：{len(files)} 个素材 → "
                     f"{len(targets)} 个平台\n{'='*60}\n")

        t = threading.Thread(target=self._worker, args=(src, files, targets), daemon=True)
        t.start()

    def _worker(self, src: Path, files: list[Path], targets: list[str]):
        writer = QueueWriter(self.q)
        try:
            with contextlib.redirect_stdout(writer):
                cfg = load_config()
                ensure_dirs(cfg)
                outdir = ROOT / "outbox" / "styles"
                outdir.mkdir(parents=True, exist_ok=True)

                print(f"[*] 探测 {len(files)} 个素材规格…")
                sources = []
                for p in files:
                    info = ms.ffprobe(p)
                    if info["dur"] > 3:
                        sources.append(info)
                        print(f"    {p.name}  {info['w']}x{info['h']}  {info['dur']:.1f}s")
                    else:
                        print(f"    {p.name}  跳过（时长 {info['dur']:.1f}s 太短）")
                if len(sources) < 2:
                    print("[-] 有效素材不足 2 个，无法生成")
                    self.q.put(("error", "有效素材不足，至少需要 2 个 3 秒以上的视频"))
                    return

                print(f"[+] 有效素材 {len(sources)} 个\n")
                results = []
                for i, p in enumerate(targets, 1):
                    self.q.put(("status", f"[{i}/{len(targets)}] 正在生成 {STYLE_PROFILES[p]['label']}…"))
                    try:
                        r = ms.make_one(p, sources, cfg, outdir)
                        results.append(r)
                        print(f"[+] {r['label']} 完成：{r['duration']}s → {Path(r['video']).name}\n")
                    except Exception as e:
                        print(f"[-] {p} 生成失败：{e}")
                        traceback.print_exc()

                if results:
                    manifest = outdir / "manifest.json"
                    merged = {}
                    if manifest.exists():
                        try:
                            for item in __import__("json").loads(
                                    manifest.read_text(encoding="utf-8")):
                                merged[item["platform"]] = item
                        except Exception:
                            pass
                    for r in results:
                        merged[r["platform"]] = r
                    ordered = [merged[p] for p in PLATFORM_ORDER if p in merged]
                    manifest.write_text(__import__("json").dumps(
                        ordered, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"[+] 全部完成，共 {len(ordered)} 条，清单：{manifest}")
                    self.q.put(("done", len(results)))
                else:
                    self.q.put(("error", "全部平台生成失败，看日志里的报错"))
        except Exception:
            self.q.put(("error", traceback.format_exc()))
        finally:
            self.q.put(("finish", None))

    # ---------- 队列消费 ----------
    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "status":
                    self.status.configure(text=payload)
                elif kind == "done":
                    self._append(f"\n[+] 成功生成 {payload} 条成片。\n")
                elif kind == "error":
                    self._append(f"\n[-] {payload}\n")
                    messagebox.showerror("出错了", str(payload)[:600])
                elif kind == "finish":
                    self.busy = False
                    self.go_btn.state(["!disabled"])
                    self.pbar.stop()
                    self.status.configure(text="完成")
                    self._open(str(self.last_outdir))
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)


def cli_mode(argv: list[str]) -> int:
    """无界面跑一次生成，用于自检/自动化：--cli --src DIR --only p1,p2

    打包成无控制台 exe 后 sys.stdout 为 None，所以一律写 logs/cli_run.log。
    """
    import argparse
    ap = argparse.ArgumentParser(prog="自动剪辑工坊")
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--src", default=None)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)

    logdir = ROOT / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = (logdir / "cli_run.log").open("w", encoding="utf-8")

    def say(msg: str):
        print(msg)          # 已重定向到 logfile
        logfile.flush()

    with contextlib.redirect_stdout(logfile):
        try:
            src = Path(a.src) if a.src else ROOT / "inbox"
            targets = [p.strip() for p in a.only.split(",") if p.strip()] or list(PLATFORM_ORDER)
            cfg = load_config()
            ensure_dirs(cfg)
            outdir = ROOT / "outbox" / "styles"
            outdir.mkdir(parents=True, exist_ok=True)

            files = sorted(p for p in src.iterdir()
                           if p.is_file() and p.suffix.lower() in VIDEO_EXT)
            say(f"[*] 素材目录 {src}：{len(files)} 个文件")
            sources = []
            for p in files:
                info = ms.ffprobe(p)
                if info["dur"] > 3:
                    sources.append(info)
                    say(f"    {p.name} {info['w']}x{info['h']} {info['dur']:.1f}s")
            if len(sources) < 2:
                say("[-] 有效素材不足 2 个")
                return 2

            ok = 0
            for p in targets:
                try:
                    r = ms.make_one(p, sources, cfg, outdir)
                    ok += 1
                    say(f"[+] {r['label']} {r['duration']}s -> {Path(r['video']).name}")
                except Exception as e:
                    say(f"[-] {p} 失败：{e}")
            say(f"[+] 完成 {ok}/{len(targets)}")
            return 0 if ok else 1
        finally:
            logfile.close()


def main():
    if any(x == "--cli" for x in sys.argv[1:]):
        raise SystemExit(cli_mode(sys.argv[1:]))
    try:
        app = App()
        app.mainloop()
    except Exception:
        # pythonw 启动时没有控制台，异常必须落盘，否则窗口一闪就没痕迹
        logdir = ROOT / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        (logdir / "gui_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror("启动失败", (logdir / "gui_error.log").read_text(encoding="utf-8")[:800])
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
