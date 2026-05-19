# kintai-bot セットアップ手順

所要 30〜60 分。順番通りに進めれば本日中に MVP が動きます。

---

## 1. Notion 側の準備

1. **新しいワークスペースを作成**（既存の叶結びワークスペースとは分離）
   - Notion 左上のワークスペース切替 → 「+ 新しいワークスペースを追加」
   - 名前は例として「勤怠管理」
2. **親ページを 1 枚作る**
   - 例：「勤怠ハブ」というページ
   - URL の末尾 32 文字（ハイフンなしの ID）を控える → これが `NOTION_PARENT_PAGE_ID`
3. **Internal Integration を作る**
   - <https://www.notion.so/profile/integrations> → 「+ New integration」
   - 名前：`kintai-bot`、ワークスペース：勤怠管理
   - 表示されるシークレットを控える → これが `NOTION_TOKEN`
4. **親ページに integration を接続**
   - 親ページ右上「…」→「コネクト」→ `kintai-bot` を追加
   - これをやらないと API から見えません

---

## 2. LINE 側の準備

1. <https://developers.line.biz/> にログイン
2. **プロバイダーを作成**（例：`kintai-bot-provider`）
3. **Messaging API チャネルを作成**
   - チャネル名：勤怠Bot 等
   - アイコン・カテゴリは任意
4. 作成後、「Messaging API」タブで以下を控える
   - **チャネルシークレット**（Basic settings）→ `LINE_CHANNEL_SECRET`
   - **チャネルアクセストークン（長期）**（Messaging API）→ `LINE_CHANNEL_ACCESS_TOKEN`
5. 同タブの **応答設定**
   - 「応答メッセージ」OFF
   - 「あいさつメッセージ」OFF（任意）
   - 「Webhook」ON
6. **Webhook URL は後で設定**（Cloudflare デプロイ後）

---

## 3. ローカルセットアップ

```bash
cd ~/projects/kintai-bot
npm install
cp .env.example .env
# .env に NOTION_TOKEN と NOTION_PARENT_PAGE_ID を入れる
npm run setup:notion
```

出力された 4 つの DB ID を `.env` の `NOTION_DB_*` に転記します。

> Notion 側で 4 つの DB（スタッフ／打刻／業務ログ／日報）が自動生成されます。
> スタッフDB を開いて、自分（ODB）の行を 1 件作っておくと動作確認しやすいです。
> （実際は LINE で「登録 山田太郎」と送れば自動登録されます）

---

## 4. Cloudflare へのデプロイ

```bash
# 初回のみ
npx wrangler login

# シークレットを登録（1つずつ promptが出る）
npx wrangler secret put LINE_CHANNEL_SECRET
npx wrangler secret put LINE_CHANNEL_ACCESS_TOKEN
npx wrangler secret put NOTION_TOKEN
npx wrangler secret put NOTION_DB_STAFF
npx wrangler secret put NOTION_DB_PUNCH
npx wrangler secret put NOTION_DB_WORKLOG
npx wrangler secret put NOTION_DB_REPORT
npx wrangler secret put ADMIN_LINE_USER_IDS   # 管理者（ODB等）のLINE userId、カンマ区切り

# デプロイ
npm run deploy
```

`https://kintai-bot.<your-subdomain>.workers.dev` のような URL が表示されます。

---

## 5. LINE に Webhook URL を登録

1. LINE Developers → Messaging API → **Webhook URL**
   - `https://kintai-bot.<your-subdomain>.workers.dev/webhook`
2. 「Verify」を押して `Success` を確認
3. 「Webhook の利用」ON
4. 公式アカウントを友だち追加（QRコードはチャネル設定にあり）

---

## 6. 動作確認

LINE で Bot に話しかける：

```
登録 林田リカ      ← 初回のみ。あなたの名前を登録
出勤              ← 出勤打刻
報告 開発作業 #叶結び
状況              ← 今の状況を表示
退勤              ← 退勤＋日報生成
```

退勤すると Notion の「日報DB」に1枚増え、本人と `ADMIN_LINE_USER_IDS` 全員に日報が LINE で届きます。

---

## 7. 自分の LINE userId の調べ方

`ADMIN_LINE_USER_IDS` には LINE 内部の userId（`U` で始まる 33 文字）が必要です。

- Bot に何か発言した直後に `npx wrangler tail` を実行するとログに `userId` が出ます
- もしくは Notion のスタッフDB に登録された自分の行から `LINE_UID` をコピー

---

## 8. スタッフ追加運用

新しい外注スタッフを迎える時：

1. ODB から公式アカウントのリンク（or QR）を送る
2. スタッフ側で友だち追加
3. スタッフ側で `登録 田中花子` と送信
4. Notion スタッフDB に行が増えるので、ODB が **時給** と **区分** を埋める

---

## トラブルシュート

- **「invalid signature」が返る** → `LINE_CHANNEL_SECRET` が間違っている
- **Notion 401** → 親ページに integration を接続し忘れ
- **CRON が動かない** → `wrangler.toml` の `[triggers]` を確認し、`npm run deploy` で再反映
- **時刻がズレる** → `TZ_OFFSET_MIN` を確認（JST は 540）
