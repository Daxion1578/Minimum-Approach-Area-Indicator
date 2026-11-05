"""書き出した ONNX を Ultralytics で読み、見本画像で検出できるかを確かめる（実験ブランチ lab-camera-ar 用）。

結果の JSON は、端末側の前処理・後処理（web/lab/detector.js）を同じ画像で照合するときの答えに使う。
見本画像は Actions の中でだけ取得し、リポジトリには置かない。
使い方: python check_ultralytics.py <画像> <結果.json> [--model モデル.onnx] [--require 必ず見つかるはずの種類（空なら問わない）]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    from ultralytics import YOLO  # Actions の中でだけ入れる

    ap = argparse.ArgumentParser()
    ap.add_argument("img"); ap.add_argument("out")
    ap.add_argument("--model", default=str(HERE / "dist" / "yoloworld-s.onnx"))
    ap.add_argument("--require", default="person")
    a = ap.parse_args()
    img, out = a.img, Path(a.out)
    model = YOLO(a.model, task="detect")
    r = model.predict(img, imgsz=640, conf=0.25, verbose=False)[0]
    dets = [
        {"cls": int(c), "name": r.names[int(c)], "score": round(float(s), 4), "xyxy": [round(float(v), 1) for v in b]}
        for b, s, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())
    ]
    out.write_text(json.dumps({"image": Path(img).name, "shape": list(r.orig_shape), "detections": dets},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dets, ensure_ascii=False))
    if a.require and not any(d["name"] == a.require for d in dets):
        print(f"見本画像で {a.require} を検出できなかった", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
