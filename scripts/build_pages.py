"""ブラウザ版（サーバ無し）を GitHub Pages 用のフォルダに組む。

    python scripts/build_pages.py                       # _site/ に組む
    python scripts/build_pages.py --keep-web DIR        # 先に DIR の中身を _site/web/ に置く（AR の試作を残す。lab/ は載せない）

中身: index.html（ブラウザ版の印つき）、web/（画面と three.js）、web/py.zip（Python のコードと合成データ）、
web/sample/SITE-01_sld.pdf（取込の見本）。Pyodide 本体は配信サイトから読む。
承認の書き出し（approved/）と .env・*.local.* は入れない。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_DIRS = ["engine", "synth", "ingest", "agent", "server", "contracts"]
PY_FILES = ["scripts/__init__.py", "scripts/run_eval.py", "scripts/eval_layout.py"]
DATA = ["data/tables", "data/rules"]
SKIP_PARTS = {"__pycache__", "approved", "drawings"}


def _ok(p: Path) -> bool:
    return p.is_file() and not (SKIP_PARTS & set(p.parts)) and ".local." not in p.name and p.name != ".env"


def build(out: Path, keep_web: Path | None = None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    for p in out.iterdir():          # フォルダ自体は消さない（手元で配信中でも組み直せるように）
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    (out / "web").mkdir()
    if keep_web and keep_web.is_dir():
        # 別ブランチの web/ は AR（計算済みの包絡を重ねるだけ）を残す。lab/（カメラ映像から充電部の候補を探す実験）は
        # 設計原則を外した実験なので、作品と同じ公開 URL には載せない
        shutil.copytree(keep_web, out / "web", dirs_exist_ok=True, ignore=shutil.ignore_patterns("lab", "*.local.*"))
    shutil.copytree(ROOT / "web", out / "web", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.local.*", "__pycache__"))
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    marker = 'src="./web/browser-api.js" data-mode="server"'
    if marker not in html:
        raise SystemExit("web/index.html に browser-api.js の読み込みが無い")
    (out / "index.html").write_text(html.replace(marker, marker.replace("server", "browser")), encoding="utf-8")
    (out / "web" / "sample").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "data" / "sites" / "SITE-01" / "drawings" / "SITE-01_sld.pdf", out / "web" / "sample" / "SITE-01_sld.pdf")

    files: list[Path] = []
    for d in PY_DIRS + DATA:
        files += [p for p in sorted((ROOT / d).rglob("*")) if _ok(p.relative_to(ROOT))]
    for site in sorted((ROOT / "data" / "sites").iterdir()):
        files += [p for p in sorted((site / "truth").rglob("*")) if _ok(p.relative_to(ROOT))]
    files += [ROOT / f for f in PY_FILES if (ROOT / f).exists()]
    with zipfile.ZipFile(out / "web" / "py.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
        lp = ROOT / "data" / "sites" / "SITE-01" / "drawings" / "SITE-01_layout.pdf"   # 装置図のサンプル（ブラウザ版の下書き用）
        if lp.is_file():
            z.write(lp, lp.relative_to(ROOT).as_posix())
        if not (ROOT / "scripts" / "__init__.py").exists():
            z.writestr("scripts/__init__.py", "")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_site"))
    ap.add_argument("--keep-web", help="先に置く既存の公開ページ（別ブランチの web/）")
    a = ap.parse_args()
    out = build(Path(a.out), Path(a.keep_web) if a.keep_web else None)
    n = len(zipfile.ZipFile(out / "web" / "py.zip").namelist())
    print(f"組んだ: {out}（py.zip {n} ファイル、{(out / 'web' / 'py.zip').stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
