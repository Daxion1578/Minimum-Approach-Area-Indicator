"""書き出した ONNX を Ultralytics で読み、見本画像で検出できるかを確かめる（実験ブランチ lab-camera-ar 用）。

結果の JSON は、端末側の前処理・後処理（web/lab/detector.js）を同じ画像で照合するときの答えに使う。
見本画像は Actions の中でだけ取得し、リポジトリには置かない。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    from ultralytics import YOLO  # Actions の中でだけ入れる

    img, out = sys.argv[1], Path(sys.argv[2])
    model = YOLO(str(HERE / "dist" / "yoloworld-s.onnx"), task="detect")
    r = model.predict(img, imgsz=640, conf=0.25, verbose=False)[0]
    dets = [
        {"cls": int(c), "name": r.names[int(c)], "score": round(float(s), 4), "xyxy": [round(float(v), 1) for v in b]}
        for b, s, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())
    ]
    out.write_text(json.dumps({"image": Path(img).name, "shape": list(r.orig_shape), "detections": dets},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dets, ensure_ascii=False))
    if not any(d["name"] == "person" for d in dets):
        print("見本画像で person を検出できなかった", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
