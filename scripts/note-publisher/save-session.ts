/**
 * note.com のログインセッションを手元で1回だけ取得して保存するヘルパー。
 *
 * note.com はログインに reCAPTCHA を要求するため、ヘッドレスCIでは自動ログインできない。
 * そこで「人間が1回ログイン → セッション(storageState)を保存 → CIはそれを使い回す」方式にする。
 *
 * 使い方（ローカルのMacで実行）:
 *   cd scripts/note-publisher
 *   npm install            # 未インストールなら
 *   npx playwright install chromium
 *   npx tsx save-session.ts
 *   → 開いたブラウザで note.com にログイン（reCAPTCHAも突破）
 *   → 自分のホームが見えたら、このターミナルで Enter
 *   → note-state.json が保存される
 *
 * 保存後、その中身を GitHub secret `NOTE_STORAGE_STATE` に登録する。
 * （アオイに「保存した」と伝えれば gh secret set まで代行可能）
 */
import { chromium } from "playwright";
import { writeFileSync } from "fs";
import { createInterface } from "readline";

const OUT = "note-state.json";

function waitForEnter(prompt: string): Promise<void> {
  return new Promise((resolve) => {
    const rl = createInterface({ input: process.stdin, output: process.stdout });
    rl.question(prompt, () => {
      rl.close();
      resolve();
    });
  });
}

async function main() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ locale: "ja-JP" });
  const page = await context.newPage();
  await page.goto("https://note.com/login");

  console.log("\n▶ 開いたブラウザで note.com にログインしてください（reCAPTCHAも突破）。");
  console.log("  ログインが完了して自分のホームが見えたら、このターミナルで Enter を押してください。\n");
  await waitForEnter("ログインが完了したら Enter ▶ ");

  const state = await context.storageState();
  writeFileSync(OUT, JSON.stringify(state));
  await browser.close();

  console.log(`\n✅ セッションを ${OUT} に保存しました。`);
  console.log("\n--- 次の手順 ---");
  console.log(`1) ${OUT} の中身を GitHub secret 'NOTE_STORAGE_STATE' に登録する`);
  console.log("   （アオイに戻って「保存した」と言えば、gh secret set まで代行します）");
  console.log("2) note-state.json は絶対にコミットしない（.gitignore 済み）");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
