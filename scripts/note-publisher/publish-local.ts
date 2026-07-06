/**
 * note.com ローカル自動投稿（確認ゲート付き）
 *
 * 背景: note.com は 1) ログインに reCAPTCHA、2) 公開に reCAPTCHA v3 を要求するため、
 * ヘッドレスCIでは公開できない。そこで「ログイン済みの実ブラウザ(persistent profile)を
 * ローカルで使い、下書き作成・本文セットはAPI直叩き、公開だけ実ブラウザで行う」方式にする。
 *
 * フロー:
 *   Notion「note投稿待ち」記事を取得
 *   → 1本ずつ タイトル/本文をプレビュー → ODBが [y]公開 / [s]スキップ / [q]中断
 *   → 承認: APIで下書き作成+本文保存 → 実ブラウザで「投稿する」クリック(reCAPTCHA通過)
 *   → Notionを「投稿完了」に更新
 *
 * 使い方:
 *   cd scripts/note-publisher
 *   npm install && npx playwright install chromium   # 初回のみ
 *   cp .env.example .env  # NOTION_TOKEN / NOTION_DB_ARTICLE を記入
 *   npx tsx publish-local.ts
 *   初回はブラウザが開くので note にログイン(reCAPTCHA突破)→ ターミナルでEnter。
 *   プロファイルは chrome-profile/ に保存され、次回以降ログイン不要。
 */
import { chromium, type BrowserContext, type Page } from "playwright";
import { randomUUID } from "crypto";
import { readFileSync, existsSync } from "fs";
import { createInterface } from "readline";
import { join } from "path";

// ── .env ロード（NODE標準にはJS用ローダが無いので簡易パース）──
function loadEnv() {
  const p = join(process.cwd(), ".env");
  if (!existsSync(p)) return;
  for (const line of readFileSync(p, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
loadEnv();

const NOTION_TOKEN = requireEnv("NOTION_TOKEN");
const NOTION_DB = requireEnv("NOTION_DB_ARTICLE");
const NOTION_VERSION = "2022-06-28";
const PROFILE_DIR = join(process.cwd(), "chrome-profile");

function requireEnv(k: string): string {
  const v = process.env[k];
  if (!v) {
    console.error(`環境変数 ${k} がありません。.env に設定してください（.env.example 参照）。`);
    process.exit(1);
  }
  return v;
}

// ── 端末プロンプト ──
const rl = createInterface({ input: process.stdin, output: process.stdout });
const ask = (q: string) => new Promise<string>((res) => rl.question(q, (a) => res(a.trim())));

// ── Notion ──
async function notion(path: string, init: RequestInit = {}) {
  const res = await fetch(`https://api.notion.com/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${NOTION_TOKEN}`,
      "Notion-Version": NOTION_VERSION,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`Notion ${res.status}: ${await res.text()}`);
  return res.json() as Promise<any>;
}

interface Article { pageId: string; title: string; blocks: string[]; }

async function fetchPending(): Promise<Article[]> {
  const data = await notion(`/databases/${NOTION_DB}/query`, {
    method: "POST",
    body: JSON.stringify({
      filter: { property: "ステータス", select: { equals: "note投稿待ち" } },
      sorts: [{ property: "公開予定日", direction: "ascending" }],
    }),
  });
  const arts: Article[] = [];
  for (const page of data.results) {
    const title = (page.properties["タイトル"]?.title ?? []).map((b: any) => b.plain_text).join("");
    arts.push({ pageId: page.id, title, blocks: await fetchBlocks(page.id) });
  }
  return arts;
}

async function fetchBlocks(pageId: string): Promise<string[]> {
  const data = await notion(`/blocks/${pageId}/children?page_size=100`);
  const lines: string[] = [];
  for (const block of data.results) {
    const rt = block[block.type]?.rich_text ?? [];
    const text = rt.map((b: any) => b.plain_text).join("");
    switch (block.type) {
      case "paragraph": lines.push(text); break;
      case "heading_1": case "heading_2": case "heading_3": lines.push(text); break;
      case "bulleted_list_item": lines.push(`・${text}`); break;
      case "numbered_list_item": lines.push(text); break;
      case "quote": lines.push(`「${text}」`); break;
      case "divider": lines.push("――――――――――"); break;
    }
  }
  return lines.filter(Boolean);
}

async function updateStatus(pageId: string, status: string, noteUrl?: string) {
  const props: any = { ステータス: { select: { name: status } } };
  if (noteUrl) props["note URL"] = { url: noteUrl };
  await notion(`/pages/${pageId}`, { method: "PATCH", body: JSON.stringify({ properties: props }) });
}

// ── note API（Cookieはブラウザprofileが持つのでcontext.request経由で叩く）──
function esc(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function toNoteHtml(blocks: string[]): { html: string; length: number } {
  const html = blocks.map((t) => {
    const u = randomUUID();
    return `<p name="${u}" id="${u}">${esc(t)}</p>`;
  }).join("");
  const length = blocks.join("").length;
  return { html, length };
}

async function noteApi(ctx: BrowserContext, method: string, url: string, body?: any) {
  const res = await ctx.request.fetch(url, {
    method,
    headers: { "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
    data: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json: any = null; try { json = JSON.parse(text); } catch {}
  return { status: res.status(), json, text };
}

// ── ログイン確認（必要なら手動ログインを促す）──
async function ensureLoggedIn(ctx: BrowserContext, page: Page) {
  const cu = await noteApi(ctx, "GET", "https://note.com/api/v2/current_user");
  if (cu.status === 200 && cu.json?.data?.id) {
    console.log(`✓ note ログイン済み: ${cu.json.data.nickname} (@${cu.json.data.urlname})`);
    return cu.json.data.urlname as string;
  }
  await page.goto("https://note.com/login");
  console.log("\n▶ 開いたブラウザで note にログインしてください（reCAPTCHAも突破）。");
  await ask("ログインが完了したら Enter ▶ ");
  const cu2 = await noteApi(ctx, "GET", "https://note.com/api/v2/current_user");
  if (cu2.status !== 200 || !cu2.json?.data?.id) {
    console.error("ログインを確認できませんでした。中断します。");
    process.exit(1);
  }
  console.log(`✓ ログイン確認: @${cu2.json.data.urlname}`);
  return cu2.json.data.urlname as string;
}

// ── 1記事を下書き化して公開 ──
async function publishOne(ctx: BrowserContext, page: Page, art: Article, urlname: string): Promise<string> {
  // 1) 下書き作成
  const create = await noteApi(ctx, "POST", "https://note.com/api/v1/text_notes", {});
  if (create.status !== 201) throw new Error(`下書き作成失敗: ${create.status} ${create.text.slice(0, 120)}`);
  const id = create.json.data.id;
  const key = create.json.data.key;

  // 2) タイトル・本文を保存
  const { html, length } = toNoteHtml(art.blocks);
  const save = await noteApi(ctx, "POST", `https://note.com/api/v1/text_notes/draft_save?id=${id}&is_temp_saved=true`, {
    name: art.title, body: html, body_length: length, index: false, is_lead_form: false,
  });
  if (save.status !== 201) throw new Error(`本文保存失敗: ${save.status} ${save.text.slice(0, 120)}`);

  // 3) 実ブラウザで公開設定ページを開いて「投稿する」（reCAPTCHA v3 は実ブラウザが自動処理）
  await page.goto(`https://editor.note.com/notes/${key}/publish/`, { waitUntil: "domcontentloaded" });
  const btn = page.getByRole("button", { name: "投稿する", exact: true });
  await btn.waitFor({ state: "visible", timeout: 30_000 });
  await btn.click();

  // 4) 公開完了を待つ（「記事が公開されました」モーダル）
  await page.getByText("記事が公開されました", { exact: false }).waitFor({ state: "visible", timeout: 30_000 });
  return `https://note.com/${urlname}/n/${key}`;
}

async function main() {
  console.log("Notion から「note投稿待ち」記事を取得中...");
  const articles = await fetchPending();
  if (articles.length === 0) {
    console.log("投稿待ちの記事はありません。終了。");
    rl.close();
    return;
  }
  console.log(`${articles.length} 件の投稿待ち記事があります。\n`);

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: false,
    channel: "chrome",
    viewport: { width: 1280, height: 900 },
    locale: "ja-JP",
  });
  const page = ctx.pages()[0] ?? (await ctx.newPage());

  try {
    const urlname = await ensureLoggedIn(ctx, page);

    for (const art of articles) {
      const bodyPreview = art.blocks.join("\n").slice(0, 500);
      console.log("\n" + "=".repeat(60));
      console.log(`📝 タイトル: ${art.title}`);
      console.log("-".repeat(60));
      console.log(bodyPreview + (art.blocks.join("\n").length > 500 ? "\n…(以下略)" : ""));
      console.log("=".repeat(60));
      const ans = (await ask("この記事を公開しますか？ [y=公開 / s=スキップ / q=中断] ▶ ")).toLowerCase();

      if (ans === "q") { console.log("中断しました。"); break; }
      if (ans !== "y") { console.log("→ スキップしました。"); continue; }

      try {
        console.log("→ 下書き作成・本文保存・公開中...");
        const url = await publishOne(ctx, page, art, urlname);
        await updateStatus(art.pageId, "投稿完了", url);
        console.log(`✅ 公開しました: ${url}`);
      } catch (e) {
        console.error(`❌ 公開失敗: ${(e as Error).message}`);
        await updateStatus(art.pageId, "投稿エラー").catch(() => {});
      }
    }
  } finally {
    await ctx.close();
    rl.close();
  }
  console.log("\n完了。");
}

main().catch((e) => { console.error(e); rl.close(); process.exit(1); });
