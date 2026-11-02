# 仕組みの図

時間軸が二つある。処理の順番（取込→判定→提案→承認）と、停止ステップの進行（0→3）。この文書は前者を描く。後者はアプリの画面（ステップのスライダー）で見せる。

## データの系譜

左から右へ処理が進む。矢印は「どのデータから作られたか」。図面が正で、JSON はすべて派生物。

```mermaid
flowchart LR
  subgraph IN["入力"]
    DXF["結線図 DXF"]
    TXT["作業指示文"]
    MACH["machine.json"]
  end
  subgraph ST["構造"]
    T0["topology 未確認"] --> T1["topology 承認済み"]
  end
  subgraph JD["判定（エンジン）"]
    EN["energization"] --> EV["envelope"] --> IF["interference"]
  end
  subgraph PR["提案（Claude）"]
    PP["proposal"]
  end
  subgraph OUT["承認済み成果物"]
    AP["envelope.json / .glb"]
  end
  DXF --> T0
  T1 --> EN
  TXT --> EN
  MACH --> IF
  IF -- 干渉あり --> PP -- 再検証 --> EN
  IF -- 干渉なし --> AP
```

## 提案ループ

上から下へ時間が流れる。Claude への送信は必ずマスキング関門を通り、Claude の提案は必ずエンジンが再計算してから人に返る。

```mermaid
sequenceDiagram
  actor U as 担当者
  participant E as エンジン
  participant M as マスキング関門
  participant C as Claude
  U->>E: 重機を配置
  E-->>U: 干渉あり（1.4m < 離隔 2.2m）
  U->>E: 修正案を求める
  loop 干渉が消えるまで（最大5回）
    E->>M: 干渉・開閉器状態・ルール
    M->>C: 許可項目だけ（符号化）
    Note over M: 送信内容を記録
    C-->>E: 提案（追加操作・配置変更・根拠）
    E->>E: 適用→課電→包絡→干渉を再計算
  end
  E-->>U: 提案と検証結果
  U->>E: 採用して承認
```
