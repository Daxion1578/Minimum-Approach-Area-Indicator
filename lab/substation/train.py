"""公開データ（変電所機器 15 種類、CC BY 4.0）だけで検出器を学習し、確認用の数値を出して ONNX に書き出す（実験ブランチ lab-camera-ar 用）。

GitHub Actions の CPU で動かす。モデル（Ultralytics、AGPL-3.0）はリポジトリにコミットしない。
variant:
  oiv7    = Open Images V7 で学習済みの YOLOv8n から追加学習する（公開元の表示では画像 CC BY 2.0・注釈 CC BY 4.0。
            ただし、その重みを COCO の重みから始めたかは公開元が書いておらず、不明）
  scratch = 事前学習なし。変電所データ（CC BY 4.0）だけでゼロから学習する
使い方: python train.py --variant oiv7 --data /tmp/sub/data.yaml --stats /tmp/sub/stats.json --hours 4.2
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dist"
INIT = {"oiv7": "yolov8n-oiv7.pt", "scratch": "yolov8n.yaml"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=sorted(INIT), required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--hours", type=float, default=4.2)
    a = ap.parse_args()

    from ultralytics import YOLO  # Actions の中でだけ入れる
    import onnx

    t0 = time.time()
    model = YOLO(INIT[a.variant])
    model.train(data=a.data, imgsz=640, epochs=300, time=a.hours, patience=60, batch=16, workers=4, device="cpu",
                cache="ram", seed=0, deterministic=True, pretrained=a.variant == "oiv7", amp=False, plots=False,
                project="/tmp/runs", name=a.variant, exist_ok=True, verbose=True)
    save_dir = Path(model.trainer.save_dir)
    best = save_dir / "weights" / "best.pt"
    epochs_done = int(getattr(model.trainer, "epoch", -1)) + 1
    train_hours = round((time.time() - t0) / 3600, 2)

    m = YOLO(str(best))
    metrics = m.val(data=a.data, imgsz=640, batch=16, device="cpu", plots=False, split="val", verbose=False)
    names = m.names
    stats = json.loads(Path(a.stats).read_text(encoding="utf-8"))
    box = metrics.box
    per_class = []
    for k, ci in enumerate(getattr(box, "ap_class_index", [])):
        n = names[int(ci)]
        per_class.append({"name": n, "ap50": round(float(box.ap50[k]), 3), "ap50_95": round(float(box.ap[k]), 3),
                          "val_instances": stats["instances"]["val"].get(n, 0), "train_instances": stats["instances"]["train"].get(n, 0)})

    path = m.export(format="onnx", imgsz=640, opset=12, simplify=True)
    OUT.mkdir(exist_ok=True)
    dst = OUT / f"substation-{a.variant}.onnx"
    shutil.copy(path, dst)
    g = onnx.load(str(dst)).graph
    dims = lambda v: [d.dim_value or d.dim_param for d in v.type.tensor_type.shape.dim]  # noqa: E731
    meta = {
        "variant": a.variant, "init": INIT[a.variant], "architecture": "YOLOv8n", "classes": [names[i] for i in range(len(names))],
        "epochs_done": epochs_done, "train_hours": train_hours, "imgsz": 640,
        "metrics_val": {"map50": round(float(box.map50), 3), "map50_95": round(float(box.map), 3),
                        "precision": round(float(box.mp), 3), "recall": round(float(box.mr), 3), "per_class": per_class},
        "split": stats["images"], "point_order": stats["point_order"],
        "inputs": [{"name": i.name, "shape": dims(i)} for i in g.input],
        "outputs": [{"name": o.name, "shape": dims(o)} for o in g.output],
        "note": "確認用の画像は学習用と同じ変電所・近い時期の写真を含むので、数値は甘めに出る。実際の当たり外れは別の写真で確かめる",
    }
    (OUT / f"substation-{a.variant}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
