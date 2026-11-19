"""把当前工作区同步到 GitHub（当 github.com:443 被网络阻断、git push 不可用时使用）。

原理：api.github.com 可通，github.com 主域不通。所以不走 git 协议，
而是用 GitHub Git Data API 把 git 对象直接建出来：blob -> tree -> commit -> ref，
效果等价于一次 push（全量覆盖式提交，非增量）。

首次使用需要一个 token，放在 state/.ghtoken（state/ 已在 .gitignore 里）。

用法：
    python sync_github.py                    # 提交信息自动生成
    python sync_github.py -m "feat: xxx"     # 指定提交信息
    python sync_github.py --dry-run          # 只列要传的文件

环境变量 GH_OWNER / GH_REPO 可覆盖默认仓库。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OWNER = os.environ.get("GH_OWNER", "xlt-xlt")
REPO = os.environ.get("GH_REPO", "auto-clip-agent")
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
TOKEN_FILE = ROOT / "state" / ".ghtoken"


def load_token() -> str:
    if not TOKEN_FILE.exists():
        raise SystemExit(
            f"缺少 token 文件：{TOKEN_FILE}\n"
            "生成一个 fine-grained 或 classic PAT（需 repo 权限），把 token 写进该文件即可。"
        )
    tok = TOKEN_FILE.read_text(encoding="ascii").strip()
    if not tok:
        raise SystemExit(f"token 文件是空的：{TOKEN_FILE}")
    return tok


def api(token: str, method: str, path: str, data=None, timeout: int = 90, retries: int = 4):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "auto-clip-agent-sync")
        if body is not None:
            req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", errors="replace")
            # 5xx 重试，4xx 直接失败
            if e.code >= 500 and attempt < retries:
                last_err = f"HTTP {e.code}"
                time.sleep(1.5 * attempt)
                continue
            print(f"  HTTP {e.code} {method} {path} -> {txt[:400]}")
            raise
        except Exception as e:  # 连接被重置/超时，几乎都是线路抖动
            last_err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                print(f"  网络异常，第 {attempt} 次重试（{last_err[:80]}）")
                time.sleep(1.5 * attempt)
                continue
            raise
    raise SystemExit(f"多次重试仍失败: {last_err}")


def tracked_files() -> list[str]:
    """用 git 索引当白名单，这样 .gitignore 的排除规则自动生效。"""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [n for n in out.decode("utf-8").split("\0") if n]


def ensure_branch(token: str) -> str | None:
    """空仓库不允许直接建 blob，先用 contents API 打一个首提交。"""
    try:
        api(token, "GET", "/branches/main")
        return None
    except Exception:
        print("空仓库，先创建首个提交 ...")
    r = api(token, "PUT", "/contents/.init-placeholder", {
        "message": "chore: bootstrap",
        "content": base64.b64encode(b"bootstrap\n").decode("ascii"),
    })
    print(f"  main 分支已建（{r['commit']['sha'][:8]}）")
    return r["commit"]["sha"]


def main() -> int:
    ap = argparse.ArgumentParser(description="用 GitHub API 同步当前仓库")
    ap.add_argument("-m", "--message", default=None, help="提交信息")
    ap.add_argument("--dry-run", action="store_true", help="只列出文件，不真的上传")
    args = ap.parse_args()

    files = tracked_files()
    if not files:
        print("git 索引里没有文件（先 git add）")
        return 1

    total = sum((ROOT / f).stat().st_size for f in files if (ROOT / f).is_file())
    print(f"待同步 {len(files)} 个文件，共 {total/1024:.1f} KB -> {OWNER}/{REPO}")
    if args.dry_run:
        for f in files:
            print("  " + f)
        return 0

    token = load_token()
    parent = ensure_branch(token)

    tree = []
    for i, name in enumerate(files, 1):
        p = ROOT / name
        if not p.is_file():
            print(f"  跳过（不存在）: {name}")
            continue
        blob = api(token, "POST", "/git/blobs", {
            "content": base64.b64encode(p.read_bytes()).decode("ascii"),
            "encoding": "base64",
        })
        tree.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"  [{i}/{len(files)}] {name}")

    t = api(token, "POST", "/git/trees", {"tree": tree})
    msg = args.message or f"chore: 同步 {len(tree)} 个文件"
    body = {"message": msg, "tree": t["sha"]}
    if parent:
        body["parents"] = [parent]
    c = api(token, "POST", "/git/commits", body)
    print(f"commit {c['sha'][:8]}  tree {t['sha'][:8]}")

    try:
        api(token, "POST", "/git/refs", {"ref": "refs/heads/main", "sha": c["sha"]})
    except Exception:
        api(token, "PATCH", "/git/refs/heads/main", {"sha": c["sha"], "force": True})

    info = api(token, "GET", "")
    print(f"完成: {info['html_url']}")
    print(f"      {msg.splitlines()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
