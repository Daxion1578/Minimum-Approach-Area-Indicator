# 仕組みの図

時間軸が二つある。処理の順番（取込→判定→提案→承認）と、停止ステップの進行（0→3）。この文書は前者を描く。後者はアプリの画面（ステップのスライダー）で見せる。

## データの系譜

左から右へ処理が進む。矢印は「どのデータから作られたか」。図面が正で、JSON はすべて派生物。

```mermaid
flowchart LR
  subgraph IN["入力"]
    PDF["単線結線図（ベクター PDF）"]
    TXT["作業指示文（この先）"]
    MACH["クレーン（画面で置く）"]
  end
  subgraph ST["構造"]
    T0["topology 未確認"] --> T1["topology 承認済み"]
  end
  subgraph JD["判定（エンジン）"]
    EN["energization"] --> EV["envelope"] --> IF["clearance"]
  end
  subgraph PR["提案（Claude）"]
    PP["候補（engine）＋ 説明（Claude）"]
  end
  subgraph OUT["承認済み成果物"]
    AP["plan / envelope / step-N-sld.pdf"]
  end
  PDF --> T0
  T1 --> EN
  TXT --> EN
  MACH --> IF
  IF -- 干渉あり --> PP -- 再検証 --> EN
  IF -- 干渉なし --> AP
```

## 修正案の流れ（11/4 時点の実装）

上から下へ時間が流れる。候補を作って再判定するのはエンジン、Claude は説明だけ。Claude への送信は必ずマスキング関門を通る。

```mermaid
sequenceDiagram
  actor U as 担当者
  participant E as エンジン
  participant M as マスキング関門
  participant C as Claude
  U->>E: 重機を配置
  E-->>U: 不可（最小 3.00m < 必要 5.20m、根拠）
  U->>E: 修正案を出す
  E->>E: 候補（移動・旋回制限・起伏・追加停止）を作り、一つずつ再判定
  E-->>U: 候補と判定値（可 → 条件付き可 → 不可）
  E->>M: 判定値と候補
  M->>C: 線路名・所名を符号化したもの
  Note over M: 送信内容を logs/outbound/ に記録
  C-->>U: 候補ごとの説明と順位づけの理由（数値は作らない）
  U->>E: 採用 → 再判定 → 承認
```
