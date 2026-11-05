"""検出器の点検ページ（web/lab/detector-check.html）を headless Chromium で開き、書き出したモデルで見本画像を検出して、
Ultralytics の結果（check-ultralytics.json）と照合する（実験ブランチ lab-camera-ar 用。GitHub Actions の中で動かす）。

onnxruntime-web は本番と同じく jsDelivr からハッシュ照合つきで取る（ページのワーカーの処理をそのまま通す）。
WASM で照合し、WebGPU（SwiftShader）が使える環境ならそれも照合する。WebGPU が使えないときは飛ばす。
あわせて、ページが外へ出した要求を全部記録し、照合済みの2ファイル以外へ取りに行っていたら失敗にする
（照合していないコードが動く経路が無いことを、実際の要求で確かめる）。モデルの探す語が画面と一致することも確かめる。
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import sys
import threading
from pathlib import Path

PORT = 8799
WEBGPU_ARGS = ["--enable-unsafe-webgpu", "--enable-features=Vulkan", "--use-vulkan=swiftshader",
               "--use-webgpu-adapter=swiftshader", "--disable-vulkan-surface", "--ignore-gpu-blocklist"]


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def ort_files(root: Path) -> list[str]:
    """ワーカー（detector-worker.js）に書いた取得先と照合ファイルを読む（点検側に二重に書かない）"""
    src = (root / "web/lab/detector-worker.js").read_text(encoding="utf-8")
    base = re.search(r"base: '([^']+)'", src).group(1)
    return [base + f for f in re.findall(r"file: '([^']+)'", src)]


def open_page(url: str, args: list[str], timeout_ms: int) -> tuple[dict | None, str | None, list[str], list[str]]:
    from playwright.sync_api import sync_playwright  # Actions の中でだけ入れる

    with sync_playwright() as p:
        browser = p.chromium.launch(args=args)
        ctx = browser.new_context()
        requests: list[str] = []
        ctx.on("request", lambda r: requests.append(r.url))   # ワーカーからの要求も含む
        page = ctx.new_page()
        logs: list[str] = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"[:300]))
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"[:300]))
        try:
            page.goto(url)
            page.wait_for_function("window.__result || window.__error", timeout=timeout_ms)
            return page.evaluate("window.__result || null"), page.evaluate("window.__error || null"), logs, requests
        finally:
            browser.close()


def check_requests(requests: list[str], allowed: list[str]) -> list[str]:
    """外への要求が照合済みのファイルだけか。問題を文字列で返す（空なら問題なし）"""
    local = f"http://127.0.0.1:{PORT}/"
    outside = [u for u in requests if not u.startswith((local, "blob:", "data:"))]
    problems = [f"照合していない外部への要求: {u}" for u in outside if u not in allowed]
    problems += [f"置き換えた場所への要求（ORT が別のファイルを取りに行った）: {u}" for u in requests if "__ort_not_loaded__" in u]
    problems += [f"照合ファイルへの要求が記録されていない（記録の仕組みを確かめる）: {u}" for u in allowed if u not in requests]
    return problems


def compare(res: dict, expect: dict) -> tuple[bool, list[dict]]:
    rows, ok = [], True
    for d in expect["detections"]:
        if d["score"] < 0.5:
            continue
        cands = [g for g in res["boxes"] if g["cls"] == d["cls"]]
        best = max((iou(d["xyxy"], [g["x1"], g["y1"], g["x2"], g["y2"]]) for g in cands), default=0.0)
        rows.append({"name": d["name"], "score": d["score"], "iou": round(best, 3)})
        ok = ok and best >= 0.6
    return ok, rows


def summary(res: dict) -> dict:
    return {k: res.get(k) for k in ("ep", "gpuError", "nc", "warmMs", "ms", "W", "H", "input")} | {"n": len(res["boxes"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--model", required=True, help="root からの相対パス")
    ap.add_argument("--image", required=True, help="root からの相対パス")
    ap.add_argument("--expect", required=True)
    a = ap.parse_args()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args, **kw):  # noqa: D102
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=str(Path(a.root).resolve())))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    expect = json.loads(Path(a.expect).read_text(encoding="utf-8"))
    url = f"http://127.0.0.1:{PORT}/web/lab/detector-check.html?model=/{a.model}&image=/{a.image}&auto=1"

    allowed = ort_files(Path(a.root))
    res, err, logs, reqs = open_page(url + "&prefer=wasm", [], 300_000)
    if err or not res:
        print("WASM: 失敗", err, *logs, sep="\n")
        return 1
    ok, rows = compare(res, expect)
    print("WASM:", json.dumps(summary(res), ensure_ascii=False))
    print("WASM 照合:", json.dumps(rows, ensure_ascii=False))
    problems = check_requests(reqs, allowed)
    print("外への要求:", json.dumps(sorted({u for u in reqs if not u.startswith(f"http://127.0.0.1:{PORT}/")}), ensure_ascii=False))
    if not res.get("namesOk"):
        problems.append(f"モデルの探す語が画面と合わない: {res.get('names')}")
    if problems or not ok:
        print(*problems, sep="\n")
        if not ok:
            print("WASM: Ultralytics の結果と合わない", json.dumps(res["boxes"][:10], ensure_ascii=False), sep="\n")
        return 1

    try:
        res2, err2, logs2, reqs2 = open_page(url, WEBGPU_ARGS, 420_000)
    except Exception as e:  # noqa: BLE001  時間切れなどは飛ばす
        print("WebGPU: 点検を飛ばした（", str(e)[:200], "）")
        return 0
    if err2 or not res2:
        print("WebGPU: 失敗", err2, *logs2[-5:], sep="\n")
        return 1
    print("WebGPU:", json.dumps(summary(res2), ensure_ascii=False))
    if res2["ep"] != "WebGPU":
        print("WebGPU: この環境では使えず WASM で動いた（飛ばす）")
        return 0
    ok2, rows2 = compare(res2, expect)
    print("WebGPU 照合:", json.dumps(rows2, ensure_ascii=False))
    problems2 = check_requests(reqs2, allowed)
    print(*problems2, sep="\n")
    return 0 if ok2 and not problems2 else 1


if __name__ == "__main__":
    sys.exit(main())
