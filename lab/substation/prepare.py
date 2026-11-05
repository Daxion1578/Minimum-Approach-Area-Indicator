"""公開データ「A Semantically Annotated 15-Class Ground Truth Dataset for Substation Equipment」（Zenodo 7884270、CC BY 4.0）を、
YOLO の学習形式（画像ごとの枠のテキスト）に直す（実験ブランチ lab-camera-ar 用）。

GitHub Actions の中でだけ動かす。データ（実在の変電所の写真）はリポジトリにも成果物にも入れない。
- 注釈は LabelMe の多角形（labels_json/ の JSON、画像1枚に1つ）。多角形を囲む長方形を枠にする。
- 種類の名前は、表記の揺れ（大文字・下線など）を吸収して lab/substation/classes.txt の名前に合わせる。合わない名前があれば止める。
- 点の並びが [x, y] か [y, x] かは、画像の大きさからはみ出す数の少ない方を選ぶ（どちらを選んだかを記録する）。
- 学習用と確認用は、ファイル名のハッシュで決めて分ける（毎回同じ分け方になる）。
使い方: python prepare.py <展開したフォルダ> <出力フォルダ>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
VAL_PERCENT = 15


def norm(s: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if w]


def build_mapper(canon: list[str]):
    canon_tokens = [set(norm(c)) for c in canon]

    def to_index(label: str) -> int | None:
        tok = set(norm(label))
        if not tok:
            return None
        hits = [i for i, ct in enumerate(canon_tokens) if tok == ct]
        if not hits:   # 「switch」の有無などの違いだけなら、片方がもう片方を含む候補が一つのときに限って合わせる
            hits = [i for i, ct in enumerate(canon_tokens) if tok <= ct or ct <= tok]
        return hits[0] if len(hits) == 1 else None

    return to_index


def find_dir(root: Path, name: str) -> Path:
    cands = [p for p in root.rglob(name) if p.is_dir()]
    if not cands:
        sys.exit(f"{name}/ が見つからない")
    return min(cands, key=lambda p: len(p.parts))


def main() -> int:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    canon = [s.strip() for s in (HERE / "classes.txt").read_text(encoding="utf-8").splitlines() if s.strip()]
    to_index = build_mapper(canon)
    img_dir, lab_dir = find_dir(root, "images"), find_dir(root, "labels_json")
    for ct in root.rglob("classes.txt"):
        print("データの classes.txt:", ct.relative_to(root), "|", " / ".join(l.strip() for l in ct.read_text(errors="replace").splitlines() if l.strip()))
    images = {p.stem: p for p in img_dir.rglob("*") if p.suffix.lower() in IMG_EXT}
    jsons = sorted(lab_dir.rglob("*.json"))
    print(f"画像 {len(images)} 枚、注釈 {len(jsons)} 件")

    # 1回目: 名前の対応と、点の並びの判定
    raw_labels, unknown, viol = Counter(), Counter(), {"xy": 0, "yx": 0}
    records = []
    for jf in jsons:
        d = json.loads(jf.read_text(encoding="utf-8", errors="replace"))
        stem = Path(d.get("imagePath") or jf.stem).stem
        img = images.get(stem) or images.get(jf.stem)
        if img is None:
            continue
        W, H = int(d.get("imageWidth") or 0), int(d.get("imageHeight") or 0)
        shapes = []
        for sh in d.get("shapes", []):
            lab = str(sh.get("label", ""))
            raw_labels[lab] += 1
            idx = to_index(lab)
            if idx is None:
                if set(norm(lab)) & {"background"}:
                    continue
                unknown[lab] += 1
                continue
            pts = [(float(p[0]), float(p[1])) for p in sh.get("points", []) if len(p) >= 2]
            if len(pts) < 2:
                continue
            if W and H:
                viol["xy"] += sum(1 for a, b in pts if a > W + 1 or b > H + 1)
                viol["yx"] += sum(1 for a, b in pts if b > W + 1 or a > H + 1)
            shapes.append((idx, pts))
        records.append((img, W, H, shapes))
    print("注釈の名前（そのまま）:", dict(raw_labels.most_common()))
    if unknown:
        print("classes.txt に合わせられない名前:", dict(unknown.most_common()), file=sys.stderr)
        return 1
    order = "xy" if viol["xy"] <= viol["yx"] else "yx"
    print(f"点の並び: {order}（はみ出す点の数 [x,y]={viol['xy']}・[y,x]={viol['yx']}）")
    if min(viol.values()) > 0.01 * sum(len(s[1]) for r in records for s in r[3]):
        print("どちらの並びでも画像からはみ出す点が多い", file=sys.stderr)
        return 1

    # 2回目: 枠を書き出す（画像は元の場所を指すリンクにする）
    counts = {"train": Counter(), "val": Counter()}
    nimg = Counter()
    for img, W, H, shapes in records:
        if not (W and H):
            continue
        split = "val" if int(hashlib.md5(img.stem.encode()).hexdigest(), 16) % 100 < VAL_PERCENT else "train"
        lines = []
        for idx, pts in shapes:
            xs = [p[0] if order == "xy" else p[1] for p in pts]
            ys = [p[1] if order == "xy" else p[0] for p in pts]
            x1, x2 = max(0.0, min(xs)), min(float(W), max(xs))
            y1, y2 = max(0.0, min(ys)), min(float(H), max(ys))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            lines.append(f"{idx} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
            counts[split][idx] += 1
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        link = out / "images" / split / img.name
        if not link.exists():
            link.symlink_to(img.resolve())
        (out / "labels" / split / f"{img.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        nimg[split] += 1

    names = "\n".join(f"  {i}: '{n}'" for i, n in enumerate(canon))
    (out / "data.yaml").write_text(f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n", encoding="utf-8")
    stats = {"images": dict(nimg), "point_order": order, "instances": {s: {canon[i]: c[i] for i in range(len(canon))} for s, c in counts.items()}}
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
