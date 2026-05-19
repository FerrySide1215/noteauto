#!/usr/bin/env node
// Notion ワークスペースに勤怠用 4 DB を一気に作る初期セットアップ。
//
// 前提:
//   1. Notion で新規ワークスペースを作り、適当な「親ページ」を1枚用意
//   2. https://www.notion.so/profile/integrations で internal integration を作る
//   3. その親ページの「コネクト」から、作った integration を接続
//   4. .env を .env.example からコピーし、NOTION_TOKEN と NOTION_PARENT_PAGE_ID を埋める
//   5. `npm run setup:notion`
//
// 出力された 4 つの DB ID を .env の NOTION_DB_* に転記し、wrangler secret put で Workers に渡す。

import "dotenv/config";

const TOKEN = process.env.NOTION_TOKEN;
const PARENT = process.env.NOTION_PARENT_PAGE_ID;

if (!TOKEN || !PARENT) {
  console.error("NOTION_TOKEN と NOTION_PARENT_PAGE_ID を .env に設定してください。");
  process.exit(1);
}

const NOTION_VERSION = "2022-06-28";

async function notion(path, body, method = "POST") {
  const r = await fetch(`https://api.notion.com/v1${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Notion-Version": NOTION_VERSION,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Notion API ${r.status} ${path}\n${text}`);
  }
  return r.json();
}

async function createDb(title, properties) {
  return notion("/databases", {
    parent: { type: "page_id", page_id: PARENT },
    title: [{ type: "text", text: { content: title } }],
    properties,
  });
}

async function main() {
  console.log("▶ スタッフDB を作成中...");
  const staff = await createDb("勤怠｜スタッフ", {
    "名前": { title: {} },
    "LINE_UID": { rich_text: {} },
    "区分": {
      select: {
        options: [
          { name: "自分", color: "blue" },
          { name: "正社員", color: "green" },
          { name: "外注", color: "orange" },
        ],
      },
    },
    "時給": { number: { format: "yen" } },
    "有効": { checkbox: {} },
    "メモ": { rich_text: {} },
  });
  console.log("  ✔ NOTION_DB_STAFF =", staff.id);

  console.log("▶ 打刻DB を作成中...");
  const punch = await createDb("勤怠｜打刻", {
    "名前": { title: {} },
    "スタッフ": { relation: { database_id: staff.id, single_property: {} } },
    "種別": {
      select: {
        options: [
          { name: "出勤", color: "green" },
          { name: "退勤", color: "red" },
          { name: "休憩開始", color: "yellow" },
          { name: "休憩終了", color: "blue" },
        ],
      },
    },
    "時刻": { date: {} },
    "日付": { rich_text: {} },
    "案件": { select: { options: [] } },
  });
  console.log("  ✔ NOTION_DB_PUNCH =", punch.id);

  console.log("▶ 業務ログDB を作成中...");
  const worklog = await createDb("勤怠｜業務ログ", {
    "名前": { title: {} },
    "スタッフ": { relation: { database_id: staff.id, single_property: {} } },
    "時刻": { date: {} },
    "日付": { rich_text: {} },
    "案件": { select: { options: [] } },
    "内容": { rich_text: {} },
  });
  console.log("  ✔ NOTION_DB_WORKLOG =", worklog.id);

  console.log("▶ 日報DB を作成中...");
  const report = await createDb("勤怠｜日報", {
    "名前": { title: {} },
    "スタッフ": { relation: { database_id: staff.id, single_property: {} } },
    "日付": { rich_text: {} },
    "出勤": { date: {} },
    "退勤": { date: {} },
    "休憩分": { number: { format: "number" } },
    "稼働分": { number: { format: "number" } },
    "業務サマリー": { rich_text: {} },
    "報酬概算": { number: { format: "yen" } },
    "承認": {
      select: {
        options: [
          { name: "未承認", color: "gray" },
          { name: "承認済", color: "green" },
        ],
      },
    },
  });
  console.log("  ✔ NOTION_DB_REPORT =", report.id);

  console.log("\n--- 完了 ---");
  console.log("次の値を .env に転記してください：\n");
  console.log(`NOTION_DB_STAFF=${staff.id}`);
  console.log(`NOTION_DB_PUNCH=${punch.id}`);
  console.log(`NOTION_DB_WORKLOG=${worklog.id}`);
  console.log(`NOTION_DB_REPORT=${report.id}`);
  console.log("\nその後、`wrangler secret put NOTION_DB_STAFF` などで Workers に登録してください。");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
