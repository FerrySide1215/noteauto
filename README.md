# kintai-bot

LINE Bot で外注スタッフを含む勤怠を管理する MVP。
バックエンドは Notion、ホストは Cloudflare Workers。15 人規模を想定。

## できること（MVP）

| 機能 | 操作 |
|---|---|
| 出勤打刻 | LINE で「出勤」または「おはよう」 |
| 退勤打刻＋日報自動生成 | 「退勤」または「おつかれ」 |
| 休憩 / 再開 | 「休憩」「再開」 |
| 業務内容の記録 | 「報告 動画編集 30分 #叶結び」 など |
| 案件タグ | 本文に `#案件名` を含める |
| 現在の打刻状況 | 「状況」 |
| 日報の再表示 | 「日報」 |
| ヘルプ | 「ヘルプ」 |
| 打刻忘れアラート | 出勤から 12 時間経過で本人＋管理者に通知（CRON） |
| 業務内容ナッジ | 直近イベントから 2 時間空くと本人に問いかけ（CRON） |

退勤打刻時に、その日の打刻と業務ログを集計して Notion 日報DB に1枚作り、
本人と管理者（`ADMIN_LINE_USER_IDS`）に LINE で送ります。

## アーキテクチャ

```
LINE Messaging API
        │  webhook (HTTPS)
        ▼
Cloudflare Workers ── 5分おき CRON
        │
        ▼
Notion API ── 4つのDB（スタッフ／打刻／業務ログ／日報）
```

- 認証情報はすべて `wrangler secret` で Workers に保管（リポジトリには入らない）
- Notion ワークスペースは既存ブランド（叶結び等）と分離した「勤怠専用」を推奨
- Workers の無料枠で 15 人規模なら十分まかなえる

## ファイル構成

```
kintai-bot/
├── src/
│   ├── index.ts       # Webhook / CRON エントリ
│   ├── commands.ts    # 出勤・退勤・休憩・報告などのコマンドルーター
│   ├── reports.ts     # 日報の集計と Notion 書き込み
│   ├── notion.ts      # Notion API ラッパー
│   ├── line.ts        # LINE API ラッパー＋署名検証
│   ├── time.ts        # JST 時刻ヘルパ
│   └── types.ts
├── scripts/
│   └── setup-notion.mjs   # 勤怠用 4 DB を一括作成
├── wrangler.toml
├── package.json
├── tsconfig.json
├── .env.example
└── SETUP.md           # 初回セットアップ手順
```

## セットアップ

[SETUP.md](./SETUP.md) を参照。

## 今後の拡張（第2弾以降の候補）

- 月次 CSV エクスポート（給与・請求書用）
- 見積もり工数 vs 実工数の差分集計（案件別）
- 承認フロー（管理者の 👍 で「承認済」に変更）
- Rich Menu / Quick Reply でボタン操作
- 複数案件の同時稼働対応（時間配分）
- マイナンバー・契約書管理（労務側）
