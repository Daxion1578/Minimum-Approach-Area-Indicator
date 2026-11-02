# Claude の使い方（審査向けの対応表）

審査基準「モデルや機能（Skills、サブエージェント、MCP、フックなど）を目的に応じて選び、使い分けているか」に、ファイルとコミットで答えるための表。使ったら1行足す。「なぜそれか」が書けない行は、使う理由が無いということなので消す。

## 開発側（Claude Code）

| 機能 | 何に使う | なぜその機能か（他では駄目な理由） | 証拠 | 動画で触れる |
|---|---|---|---|---|
| `CLAUDE.md` | 変わらない約束（公開制約、安全設計の原則、報告の型） | 毎回のセッションで必ず読まれる唯一の場所 | `CLAUDE.md` | 一言 |
| Skill `/slice` | 縦切り1つ分の計画→実装→確認を同じ型で回す | 手順を人が毎回言い直すと抜ける。型を Skill に固定 | `.claude/skills/slice/` | — |
| Skill `/verify` | 縦切りの最後に「手元で何を見れば合格か」を出させる | 作りかけを「できた」と言わせない | `.claude/skills/verify/` | — |
| Skill `/report` | `STATUS.md` を所定の型で上書き | スマホで30秒で読める報告を毎回同じ形にする | `.claude/skills/report/`, `STATUS.md` の履歴 | — |
| Skill `/publish-check` | 公開前点検 | 社内情報の混入は失格。人の記憶に頼らない | `.claude/skills/publish-check/` | 一言 |
| Skill `/judge-review` | 審査員の目で4基準を採点し、足りないものを残す | 自分では自分の作品を客観視できない。採点結果をコミットすれば試行錯誤の跡になる | `.claude/skills/judge-review/`, `docs/reviews/` | 一言 |
| サブエージェント `safety-reviewer` | push・提出前の点検係（読み取り専用） | 書いた本人と同じコンテキストでは見落とす。別コンテキストで独立に読ませる | `.claude/agents/safety-reviewer.md` | 一言 |
| フック `pre_git_safety` | commit/push 前に禁止語・秘密情報・緯度経度・実図面形式を検出 | 人が忘れる作業は機械に。`--no-verify` も拒否 | `.claude/hooks/pre_git_safety.py`, `scripts/public_safety_check.py` | 一言 |
| フック `post_edit_tests` | `engine/` `contracts/` `tests/` 編集後に pytest を自動実行 | テストが落ちた状態で先に進ませない | `.claude/hooks/post_edit_tests.py` | — |
| worktree 並列 | 幾何／3D／エージェント層を別 worktree で同時に進める | 1人開発で「2人分」を出す唯一の方法 | コミットのブランチ名・時刻 | 30秒 |

## 製品側（MAAI 本体）

| 機能 | 何に使う | なぜその機能か | 証拠 | 動画で触れる |
|---|---|---|---|---|
| ツール呼び出しループ（`agent/propose.py`） | 干渉時の修正提案→エンジン再検証→通るまで | 提案は Claude、採否は決定論。Claude に安全判定をさせない設計の中心 | `agent/`, `logs/proposals/`（画面表示） | 主役 |
| 図面構造化（`agent/structure.py`） | 候補グラフ＋文字→トポロジJSON＋質問 | 図面の意味づけは人の読み方の再現で、LLM が一番効く場所 | `agent/structure.py`, 評価表 | 採用なら主役 |
| モデルの使い分け（`agent/client.py`） | 構造化は軽いモデル、提案は上位モデル | 遅延・精度・コストが用途で違う。`.env` で差替え | `agent/client.py`, README の一段落 | 一言 |
| マスキング関門（`agent/mask.py`） | 外に出してよい項目だけ通す | 社外 AI に社内情報を出せない現場で「使える」の前提条件 | `agent/mask.py`, `logs/outbound/` | 一言 |
| MCP サーバ（`agent/tools.py` を公開） | 開発中の Claude Code と製品の提案ループが**同じ道具**を使う | 「機能の使い分け」の最も分かりやすい例。採否は `docs/spec.md` §16 | 未採用（11/3 判断） | 採用なら一言 |

## 動画の「Claude の使い方」パート（30秒）で言うこと
1. 安全判定は決定論、Claude は意味づけと提案。提案はエンジンで再検証（主役）
2. 開発は Claude Code を中心に、Skill・フック・点検係で「社内情報を出さない」「作りかけを通さない」を仕組みにした
3. （採用なら）同じエンジンを MCP で公開し、開発中も製品も同じ道具を使った
