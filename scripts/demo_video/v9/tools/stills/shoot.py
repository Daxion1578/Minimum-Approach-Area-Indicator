"""stills.html を Playwright で描いて、assets/r9 に JPEG と points.json を置く（外には何も送らない）。

  python scripts/demo_video/v9/tools/stills/dump9.py                 # 先に stills.json と ground.png
  python scripts/demo_video/v9/tools/stills/shoot.py                 # 1920x1080 の 4 枚 → assets/r9/{gray,live,crane,safe}.jpg ＋ points.json
  python scripts/demo_video/v9/tools/stills/shoot.py --w 640 --h 360 --views gray --outdir /tmp/x --q "gray_eye=-10,60,40"   # 試し撮り
"""
from __future__ import annotations
import argparse, functools, http.server, io, json, threading
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
R9 = HERE.parents[1] / "assets" / "r9"
PAGE = "/scripts/demo_video/v9/tools/stills/stills.html"
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def serve(port: int):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    h.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--views", default="gray,live,crane,safe")
    ap.add_argument("--outdir", default=str(R9))
    ap.add_argument("--q", default="", help="stills.html に足す問い合わせ（gray_eye=..&crane_look=..）")
    ap.add_argument("--port", type=int, default=8201)
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    a = ap.parse_args()
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    srv = serve(a.port)
    pts = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=a.chrome, args=GL)
            pg = b.new_page(viewport={"width": a.w, "height": a.h}, device_scale_factor=1)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
            pg.goto(f"http://127.0.0.1:{a.port}{PAGE}?w={a.w}&h={a.h}" + ("&" + a.q if a.q else ""))
            pg.wait_for_function("window.ready === true", timeout=300000)
            for v in a.views.split(","):
                r = pg.evaluate(f"window.show({json.dumps(v)})")
                pg.wait_for_timeout(300)
                png = pg.screenshot(clip={"x": 0, "y": 0, "width": a.w, "height": a.h})
                Image.open(io.BytesIO(png)).convert("RGB").save(out / f"{v}.jpg", quality=90)
                pts[v] = r["points"]; pts.setdefault("camera", {})[v] = r["camera"]
                print(v, r["points"])
            b.close()
            if errs: print("errors:", errs[:5])
    finally:
        srv.shutdown()
    pf = out / "points.json"
    old = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    for k, v in pts.items():
        if k == "camera": old.setdefault("camera", {}).update(v)
        else: old[k] = v
    old["size"] = [a.w, a.h]
    old["note"] = "画素の位置（左上が原点）。target は 220kV 東線1L の遮断器 20E1-110（220-L1-CB）の中心。crane の構図は閃絡を見せるための絵（計算の結果ではない）"
    pf.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
