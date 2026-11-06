"""現地表示（AR）の構想の動画を、index.html を 1 コマずつ撮って作る（Playwright + ffmpeg）。

    python scripts/ar_concept/dump.py                       # 先に concept.json を作る
    python scripts/ar_concept/render.py --out OUT.mp4       # 30 秒・30 コマ/秒・1920x1080
    python scripts/ar_concept/render.py --sample 1,5,9 --outdir DIR   # 見本のコマだけ PNG で
    python scripts/ar_concept/render.py --card title --out title.png   # 題と締めの札（cards.html）

リポジトリ直下を 127.0.0.1 で配信して描く。外には何も送らない。
"""
from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = "/scripts/ar_concept/index.html"
CARDS = "/scripts/ar_concept/cards.html"


def serve(root: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ar-concept.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--sample", help="見本のコマの秒（カンマ区切り）。指定すると動画は作らず PNG だけ")
    ap.add_argument("--outdir", help="--sample の PNG の置き場")
    ap.add_argument("--card", choices=["title", "closing"], help="題・締めの札を 1 枚の PNG にする")
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    srv, port = serve(ROOT)
    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
            page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

            if a.card:
                page.goto(f"{base}{CARDS}?card={a.card}")
                page.wait_for_function("window.__ready === true", timeout=60000)
                page.screenshot(path=a.out, clip={"x": 0, "y": 0, "width": 1920, "height": 1080})
                print("札:", a.out)
                return 0

            page.goto(f"{base}{PAGE}?t=0")
            page.wait_for_function("window.__ready === true", timeout=120000)
            if errors:
                print("ページのエラー:", *errors, sep="\n  ", file=sys.stderr)
                return 1
            duration = page.evaluate("window.DURATION")

            if a.sample:
                outdir = Path(a.outdir or ".")
                outdir.mkdir(parents=True, exist_ok=True)
                for t in (float(x) for x in a.sample.split(",")):
                    page.evaluate(f"renderAt({t})")
                    page.screenshot(path=str(outdir / f"t{t:05.1f}.png"), clip={"x": 0, "y": 0, "width": 1920, "height": 1080})
                print("見本:", outdir)
                return 0

            n = int(round(duration * a.fps))
            tmp = Path(tempfile.mkdtemp(prefix="arc-"))
            try:
                for i in range(n):
                    page.evaluate(f"renderAt({i / a.fps})")
                    page.screenshot(path=str(tmp / f"f{i:05d}.png"), clip={"x": 0, "y": 0, "width": 1920, "height": 1080})
                    if i % 60 == 0:
                        print(f"  {i}/{n}", flush=True)
                if errors:
                    print("ページのエラー:", *errors, sep="\n  ", file=sys.stderr)
                    return 1
                cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", str(tmp / "f%05d.png"),
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
                subprocess.run(cmd, check=True)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            print("動画:", a.out, f"{duration:.0f} 秒 {a.fps} コマ/秒")
            browser.close()
    finally:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
