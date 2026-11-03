# proto/ — 図面生成の試作（移植待ち）

11/3 未明の試作のうち、まだ `synth/` に移していないものだけが残っている。

- `tools/gen_model.py` と `data/substation_fictional.json` 旧契約の構内モデル（`tools/gen_drawings.py` がこれを読む）
- `tools/gen_drawings.py` 合成図面 3 枚（配置図・断面図・単線結線図、ベクター PDF）→ `data/drawings/`
- `FREEZE.md` 試作時の凍結事項（11/3 の判断で一部は変わっている。正は `docs/decisions.md`）

移植済み（11/3）: 課電判定とテストは `engine/energize.py` と `tests/`、合成変電所の構成は `synth/gen_site.py`（契約 §6 の形で `data/sites/SITE-01/truth/` に出す）。

図面生成を `synth/` に移し、描き方のルール（本人から受け取る）に合わせて書き直したら、`proto/` は消す。
