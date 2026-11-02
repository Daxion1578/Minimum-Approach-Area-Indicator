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

## 6. 日々の回し方（打つのは2つだけ）

1. 朝: `claude` を起動し `/daily` と打つ。批評 → `TASKS.md` の更新 → 「今日の一つ」の提案で止まるので、「やって」で着手させる。
2. 途中で判断を求められたら、`STATUS.md` の表の番号で答える（1枚1判断のカードで来る）。
3. 夜: `/wrap` と打つ。テスト → 公開前点検 → 判断の記録 → `STATUS.md` の更新 → コミットまで進み、最後に「push してよいか」と聞いてくるので、差分を見て許可する。
4. 自分で確かめたいときは `/verify`（手元確認の手順）。それ以外のコマンドは覚えなくてよい。

## 7. 既に clone 済みの場合（11/3 以降）

PowerShell で:

```powershell
cd F:\Dev\Minimum-Approach-Area-Indicator
git pull
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/doctor.py
claude
```

`.venv` がまだ無ければ §2 の `python -m venv .venv` から。`claude` が立ち上がったら `/status` で Max のログインであることを確かめ、`/daily` と打つ。
