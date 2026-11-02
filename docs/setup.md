# 開発環境の導入手順（Windows）

## 1. 必要なもの

- Git for Windows（Git Bash を含む。Claude Code のフックもこれで動く）
- Python 3.11 以上（インストール時に「Add python.exe to PATH」にチェック）
- Claude Code（公式クイックスタートの手順で入れる: https://code.claude.com/docs/ja/quickstart ）

## 2. 取得と依存の導入

PowerShell で:

```powershell
git clone https://github.com/Daxion1578/Minimum-Approach-Area-Indicator.git
cd Minimum-Approach-Area-Indicator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`Activate.ps1` が実行ポリシーで止められたら、一度だけ `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` を実行する。

## 3. 鍵と禁止語（自分の手元でだけ行う）

```powershell
copy .env.example .env
notepad .env
notepad .forbidden-terms.local.txt
```

- `.env` にはアプリ用の API キーを書く。**PowerShell やシステムの環境変数に `ANTHROPIC_API_KEY` を設定しない**（設定すると Claude Code が Max のログインではなく API 課金で動く）。
- `.forbidden-terms.local.txt` には、公開してはいけない語を1行1語で書く（勤務先の社名・略称、事業所名、設備名、社内システム名、協力会社名など）。`#` で始まる行はコメント。このファイルはコミットされず、Claude Code の Read も禁止してある。中身を Claude に貼らないこと。

## 4. git フックの登録と点検

```powershell
python scripts/install_git_hooks.py
python scripts/doctor.py
```

`doctor.py` がすべて OK になれば準備完了。NG の項目には直し方が出る。

## 5. Claude Code の起動と確認

仮想環境を有効にした PowerShell で `claude` を起動する（フックが仮想環境の Python を使うため）。

最初に次を打って確認する。
- `/status` — 認証が Max のアカウントになっていること（API キーになっていないこと）。
- `/hooks` — PreToolUse（公開前チェック）と PostToolUse（engine 編集後のテスト）の2本が見えること。

## 6. 日々の回し方

1. `claude` を起動し、`/slice` で今日の縦切りを確認してから着手させる。
2. 縦切りが終わったら `/verify` で手元確認の手順を出させ、自分で画面を見て確かめる。
3. 判断をしたら `docs/decisions.md` に1〜3行残させる。
4. push の前に `/publish-check`（中で `safety-reviewer` が点検する）。push は毎回確認が出るので、差分を見てから許可する。

## 7. 最初の指示（11/2 夜）

```
docs/spec.md の §6 に沿って、contracts/ に JSON Schema の雛形を作ってください。
対象は topology, layout, state, energization, envelope, machine, plan, interference, proposal の9つです。
あわせて data/sites/SITE-01/site.json（§10 の SITE-01 のサイト定義）を合成データで作ってください。
エンジンやサーバのコードはまだ書かないでください。
最後に、スキーマでサイト定義を検証するテストを1本だけ書き、python -m pytest -q が通ることを確認して、私が手元で確認する手順を示してください。
```
