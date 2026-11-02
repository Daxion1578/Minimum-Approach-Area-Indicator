---
name: publish-check
description: push や提出の前に、公開リポジトリとして出してよい状態かを点検するときに使う。「push したい」「公開前」「提出前」と言われたら使う。
---

# 公開前点検

1. `python scripts/public_safety_check.py --all` を実行し、結果をそのまま報告する。禁止語に一致した場合、どの語かを推測・表示しない（行番号だけ伝える）。
2. `safety-reviewer` サブエージェントに、`git diff origin/main...HEAD`（初回は全ファイル）の点検を依頼する。
3. 両方の結果をまとめ、push してよいか・直すべき点を3行以内で示す。
4. push は私が許可してから行う。force push はしない。
