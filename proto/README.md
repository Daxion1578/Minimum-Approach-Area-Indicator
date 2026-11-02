# proto/ — 課電判定の試作（契約案B）

11/3 未明に別チャットで作った試作。`docs/spec.md` §6 の契約とは形が違うので、採用を決めるまで `proto/` に置く。

- `schema/substation.schema.json` 構内モデル（電気的接続＋空間を1ファイル。開閉器は辺、区間はノード）
- `tools/gen_model.py` 合成変電所の生成（220/66kV 1・1/2 母線。寸法は全部仮定値、`P` に集約）
- `src/energize.py` 課電判定（live / dead_grounded / dead_ungrounded / FAULT_LIVE_GROUNDED）
- `tests/test_energize.py` 7件。変圧器逆送の FAULT 検出、新設ベイ付近の充電導体の抽出を含む
- `FREEZE.md` 凍結事項（作る／作らない／仮定値／日程）

実行: `python3 proto/tests/test_energize.py` または `python -m pytest proto/tests -q`

採用するなら `engine/energize.py`・`synth/`・`contracts/` へ移し、§6 の契約を書き換える。採用しないなら、テストケース（逆送 FAULT、1・1/2 の運転継続）だけを `tests/` に移植する。
