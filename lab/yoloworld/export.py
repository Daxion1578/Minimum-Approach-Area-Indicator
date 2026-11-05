"""YOLO-World（Ultralytics）を classes.txt の語に固定して ONNX に書き出す（実験ブランチ lab-camera-ar 用）。

GitHub Actions（.github/workflows/lab-yoloworld-export.yml）から動かし、成果物（artifact）として置く。
モデルは AGPL-3.0 なので、Apache-2.0 の MAAI リポジトリにはコミットしない。端末に読み込んで使う。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dist"
WEIGHTS = "yolov8s-worldv2.pt"


def main() -> int:
    from ultralytics import YOLOWorld  # Actions の中でだけ入れる
    import onnx

    classes = [s.strip() for s in (HERE / "classes.txt").read_text(encoding="utf-8").splitlines()
               if s.strip() and not s.lstrip().startswith("#")]
    model = YOLOWorld(WEIGHTS)
    model.set_classes(classes)
    path = model.export(format="onnx", imgsz=640, opset=12, simplify=True)

    OUT.mkdir(exist_ok=True)
    dst = OUT / "yoloworld-s.onnx"
    shutil.copy(path, dst)
    g = onnx.load(str(dst)).graph
    dims = lambda v: [d.dim_value or d.dim_param for d in v.type.tensor_type.shape.dim]  # noqa: E731
    meta = {
        "model": WEIGHTS, "classes": classes, "imgsz": 640,
        "inputs": [{"name": i.name, "shape": dims(i)} for i in g.input],
        "outputs": [{"name": o.name, "shape": dims(o)} for o in g.output],
        "license": "AGPL-3.0（Ultralytics のモデル）。リポジトリにはコミットしない",
    }
    (OUT / "yoloworld-s.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
