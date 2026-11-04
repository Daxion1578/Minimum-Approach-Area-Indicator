# CLAUDE.md — MAAI（Minimum Approach Area Indicator）

変わりにくい約束だけをここに書く。仕様は `docs/spec.md`、判断の記録は `docs/decisions.md` を正とする。

## 対話方針
- 技術的な判断は、私の意見に迎合せず、根拠に基づいて評価すること。私の提案に問題があれば同意せず、理由と代替案を示す。
- 回答は簡潔に。結論を先に書き、必要な根拠だけを添える。冗長な前置き・言い換え・過剰な箇条書きは避ける。
- 私はソフトウェア開発の経験が浅い。専門用語は初出で一言説明し、確認手順はコピーして実行できる形で示す。

## 報告の型
- 普段の返答は「結論1行 → 要点3つまで → 次の一手（私の判断が要るならその選択肢と推奨）」。経過の実況はしない。
- 区切り（縦切りの完了、1日の終わり、私の判断が必要なとき）は `/report` でリポジトリ直下の `STATUS.md` を上書きする（私はスマホの GitHub で読む）。ターミナルには結論1行だけを出す。
- 私が見るのは `STATUS.md` だけ。私が打つのは朝 `/daily`、夜 `/wrap` の2つだけ。判断は `STATUS.md` の「判断してほしいこと」の番号で答える。私に判断を求めるときは1枚1判断のカードにし、何が変わるか・費用・後戻りできるかを織り込む（複数を総合して決める必要があるときだけまとめてよい）。残りの作業は `TASKS.md` にタスク係（`task-keeper`）が持ち、私は読まなくてよい。

## 書き方（作品の文章）
- README・動画台本・画面・検討書・`docs/` に「審査」「評価基準」「ハッカソン向け」という語を使わない。作品の文章は、ハッカソンが無くても同じ文章になるように書く。問題、使う人、道具、設計判断、次の段階、それだけ。
- 外部の目での批評は `docs/critique/` にだけ置く（`/critique`）。批評の語彙を作品の文章に持ち込まない。

## 公開リポジトリの制約（違反は失格・事故につながる）
- 実在の会社名・事業所名・設備名・社内システム名・人名を書かない。データはすべて合成。
- 実際の現場写真・図面・社内資料を置かない。実物の DWG・ドキュワークス・PDF 図面を持ち込まない（合成変電所から生成した図面は可）。
- 暦日の停止時期、住所・緯度経度、容量・潮流・整定などの値を書かない（`docs/spec.md` §12）。
- APIキーは `.env` だけに置く。`.env` と `*.local.*` は読まない・コミットしない。
- 環境変数 `ANTHROPIC_API_KEY` をシェルに設定しない（Claude Code が API 課金に切り替わる）。アプリはキーを `.env` から読む。
- 既存プロジェクトのコードを持ち込まない。すべてこのリポジトリで新しく書く。

## 安全上の設計原則（崩さない）
- 課電判定・距離計算・干渉判定・ステップ適用は `engine/` の決定論コードだけが行う。Claude（`agent/`）はこれらの値を決めない。
- Claude の提案は必ず `engine/` で再検証してから表示する。採否は人が決める。
- 外部 API への送信は `agent/client.py` の一箇所からだけ行い、必ず `agent/mask.py` を通す。送信内容は `logs/outbound/` に記録する。
- 迷ったら保守側に倒す（未接地の停止区間は課電扱いが既定）。

## 作業の進め方
- 1回の作業は1つの縦切り（`docs/spec.md` §14・§15）か、その一部に限る。一度に大きな変更をしない。
- 後戻りしにくい判断（契約の形、ライブラリ追加、ディレクトリ構成の変更）は、実装前に選択肢と推奨を短く示して確認を取る。
- 前提が曖昧なら勝手に補完せず質問する。仕様と食い違う実装が必要になったら、先に `docs/spec.md` §0 または §16 の修正案を出す。
- `engine/` を変えたらテストを書く・直す。テストが通らない状態で作業を終えない。
- 縦切りの最後に、私が手元で確認する手順（コマンドと、画面で何が見えれば合格か）を示す。
- 判断をしたら `docs/decisions.md` に日付つきで1〜3行残す（後から読み返すと試行錯誤の跡になる）。

## コマンド
- テスト: `python -m pytest -q`
- サーバ: `uvicorn server.app:app --reload`（http://localhost:8000）
- 公開前チェック: `python scripts/public_safety_check.py --all`
- 環境の点検: `python scripts/doctor.py`
- 通しの確認（サーバなし・Claude なし）: `python scripts/check_demo.py`。GitHub Actions（`.github/workflows/check.yml`）が push のたびに同じものを回し、Summary に表を出す（本人はスマホでこれを見る）

## ディレクトリ（予定）
```
contracts/   データ契約（JSON Schema）
engine/      決定論エンジン（課電・幾何・包絡・重機・干渉・ステップ・ルール・書き出し）
ingest/      DXF 抽出
agent/       Claude 層（client, mask, audit, structure, propose, tools）
synth/       合成変電所の生成器
server/      FastAPI
web/         単一HTMLアプリ（three.js）と ar.html
data/        tables/, rules/, sites/<SITE>/{truth,approved}/, eval/
scripts/     評価・安全チェック・点検
tests/       pytest
docs/        仕様・判断記録・導入手順・台本
logs/        outbound/, proposals/（コミットしない）
```

## このリポジトリの Claude Code 設定
- フック: `git commit` / `git push` の前に公開安全チェック、`engine/` 編集後に pytest。
- スキル: `/daily`（朝の手順）、`/wrap`（夜の手順）、`/critique`（外部批評）、`/slice`（縦切りの進め方）、`/verify`（手元確認の手順を出す）、`/report`（STATUS.md の更新）、`/publish-check`（公開前点検）。
- サブエージェント: `safety-reviewer`（読み取り専用の公開前点検係、Sonnet・medium）、`task-keeper`（`TASKS.md` だけを保守するタスク係、Haiku・low）。軽い係ほど安いモデルにする。
- テストは常に `MAAI_OFFLINE=1`（`tests/conftest.py`）。本物の Claude を呼ぶ確認は手で 1 回だけ。
- Claude に任せること・任せないことの一覧は `docs/claude-boundary.md`。使い方を増やしたら1行足す。
