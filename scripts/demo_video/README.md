# 3 分デモ動画の下書き（人手なし）

1. `MAAI_OFFLINE=1 uvicorn server.app:app --port 8000`（別の端末）→ `python scripts/demo_video/record.py --out OUT`（約 4 分。OUT/segments.json と録画）
2. `python scripts/ar_concept/dump.py && python scripts/ar_concept/render.py --out OUT/ar-concept.mp4`（構想映像。compose.py が 30 秒すべて使う）
3. `python scripts/demo_video/compose.py --dir OUT --concept OUT/ar-concept.mp4`（約 5 分。札は自動で作る）
- 出力: `maai-demo-draft.mp4`（字幕入り）、`maai-demo-draft-nosub.mp4`、`narration.srt`、`narration.json`（語りの区切りと開始・終了秒）
- キーがあるとき（`.env`）は取込タブ右上が「Claude: …」になり、質問文も Claude のものに変わる。操作は同じ。
- 字幕を外す: nosub 版を使う。または `compose.py --no-sub`（字幕入りを作らない）
- ソフトウェア描画（約 2 コマ/秒）では操作ごとに約 1 秒かかり、録画が台本より長くなる。compose が、長い静止（1.2 秒超）を 1.2 秒に縮め、なお長ければ最大 1.5 倍まで早送りして台本の秒数に合わせる。短ければ最後のコマを止めて埋める。GPU のある機械で撮ると自然な速さになる。
