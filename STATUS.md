# 進み具合

```mermaid
gantt
  dateFormat YYYY-MM-DD
  axisFormat %m/%d
  section 準備
  リポジトリ骨格と文書          :done,   p1, 2026-11-02, 1d
  仕様の確定・試作画面・合成図面  :done,   p2, 2026-11-03, 1d
  section 縦切り
  1 契約・課電判定・3D包絡       :done,   s1, 2026-11-03, 1d
  合成変電所を標準配置に・図面3枚 :done,   s1b, 2026-11-04, 1d
  2 重機・干渉・停止ステップ・ステップ図・承認 :done, s2, 2026-11-04, 1d
  3 PDF取込・Claude層・修正案の説明 :done, s3, 2026-11-04, 1d
  section 提出
  README・台本・通し確認・収録    :active, v1, 2026-11-05, 3d
  提出                           :milestone, m1, 2026-11-08, 0d
```

更新: 2026-11-05 02:21

## 結論

縦切り 1〜3、README、動画台本（3 分の秒割り）、仕様・仕組み図の整合まで `main` に入り、新しい venv でも通しで動くことを確かめた。この環境でできることは終わり。残りは本人の手元でしかできないこと（Claude 接続の確認、禁止語リスト、離隔の出典、収録、提出）。

## 今日できたこと（11/4）

- **縦切り 2**: 線分間距離 → クレーン包絡（旋回掃引）→ 可／条件付き可／不可と根拠（R1/R2/R6）→ 修正案の候補（移動・旋回制限・起伏・追加停止、全部 engine が再判定）→ 承認（不可は拒否、承認ハッシュ、`approved/` に plan/envelope/step-0..3 の塗り分け PDF）
- **縦切り 3**: ベクター PDF の単線結線図を投げ込むと、線と記号と番号から topology の下書き（合成図面で 開閉器番号 136/142、隣接 precision 1.0 / recall 0.953、質問 9）。Claude 層 `agent/`（client・mask・structure・explain）。キー無しでも全画面が規則で動く
- **画面**: 4 タブ（取込・停止条件・重機配置・計画確定）、3D は `equipment.py` の寸法で機器の形、視点ボタン、クレーンの初期値は「段階 3 で不可 → 起伏角 65° で可」になる位置
- 画面写真 `docs/img/ui-1..4-*.png`、判断の記録 `docs/decisions.md`、境界 `docs/claude-boundary.md`
- **README**（問題・使う人・4 タブの流れ・設計判断・任せる／任せない・動かし方・データ・この先）、**台本** `docs/demo-plan.md`（秒割り・切る順・操作メモ）、`docs/spec.md` §7/§8/§15 と `docs/architecture.md` を実装に合わせた

## 確かめた結果

- 新しい venv で `pip install -r requirements.txt` → `python -m pytest -q` → 44 passed。`scripts/run_eval.py` の表も同じ。`python scripts/public_safety_check.py --all` → OK（100 ファイル。禁止語リストは未登録）
- `uvicorn server.app:app` → 取込（PDF 選択 → 取り込む → 質問の無いものを確認済に）→ 2BK を対象に停止ステップ → 段階 3 → 離隔判定「不可」→ 修正案 → 採用「可」→ 承認 → `approved/plan-*/` に PDF 7 枚
- Claude を実際に呼ぶ経路（`.env` にキー）は**未確認**（この環境にキーが無い）。規則の代替経路だけ確認済み

## 判断してほしいこと

| # | 判断 | 選択肢 | 何が変わるか・費用・後戻り |
|---|---|---|---|
| 1 | 動画の見せ場の順 | A. 図面取込から始めて承認で終わる（流れどおり、推奨） ／ B. 「不可 → 可」を冒頭に出してから流れ | A は分かりやすい。B は最初の 30 秒が強い。台本を書き分けるだけで後戻りできる |
| 2 | クレーンの 3D | A. 今のカプセル表示のまま（推奨） ／ B. CC-BY の GLB を探して載せる | B は 1〜2 時間と出典の管理が増える。判定には関係しない |

## 次の一手（本人の手元。順番どおり）

1. `git pull` → `.env` に `MAAI_ANTHROPIC_API_KEY` → `uvicorn server.app:app --reload`。取込タブ右上が「Claude: claude-…」になり、取込の「意味づけ: Claude」と修正案の「説明: Claude」が出ることを確かめる。出なければ `logs/outbound/` の request/response を見て、CLI に `/daily` で直させる
2. `.forbidden-terms.local.txt` を書いて `python scripts/public_safety_check.py --all`
3. 離隔値の公開出典を `data/tables/clearance.csv` の source 列に入れ「要確認」を外す（出典が確かめられなければ「要確認」のまま出す。README にそう書いてある）
4. README と `docs/demo-plan.md` を読んで、言い回しを自分の言葉に直す（CLI でよい）
5. 11/7 収録（台本どおり。初期値は変えない）、11/8 午前に通し確認 → 公開前チェック → push → 提出

## 引き継ぎ（この時点で知っておくこと）

- 起動: `pip install -r requirements.txt` → `uvicorn server.app:app --reload` → http://localhost:8000。取込に使う PDF は `data/sites/SITE-01/drawings/SITE-01_sld.pdf`
- Claude を呼ぶのは `agent/client.py` だけ。`agent/mask.py` で線路名・所名を符号化し、`logs/outbound/` に request/response を残す。`MAAI_OFFLINE=1` で呼ばない
- Claude が返すのは「種別の確認・質問文」（structure）と「修正案の説明」（explain）だけ。種別が規則と食い違っても上書きせず質問にする
- 取込の精度は `python scripts/run_eval.py` が表で出す。見つからない 6 番号は D6（未設、破線）のもので仕様どおり
- 承認の出力は `data/sites/SITE-01/approved/`（git 管理外）
- 機器の寸法を変えるときは `synth/equipment.py` だけ。図面と 3D が一緒に変わる
