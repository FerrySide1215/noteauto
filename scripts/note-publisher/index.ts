import { chromium, type Page, type BrowserContext } from "playwright";
import { createWriteStream } from "fs";
import { unlink, access } from "fs/promises";
import { pipeline } from "stream/promises";

// ── 環境変数 ───────────────────────────────────────────────
const NOTION_TOKEN   = env("NOTION_TOKEN");
const NOTION_DB      = env("NOTION_DB_ARTICLE"); // 記事アイデア帳 DB ID
const NOTE_EMAIL     = env("NOTE_EMAIL");
const NOTE_PASSWORD  = env("NOTE_PASSWORD");
const DRY_RUN        = process.env.DRY_RUN === "1";
const NOTION_VERSION = "2022-06-28";

function env(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing env: ${key}`);
  return v;
}

// ── 型定義 ────────────────────────────────────────────────
interface Article {
  pageId: string;
  title: string;
  category: string;   // 無料記事 / 有料記事 / マガジン
  price: number | null;
  scheduledAt: Date | null;
  thumbnailUrl: string | null;
}

// ── Notion API ────────────────────────────────────────────
async function notionFetch(path: string, init: RequestInit = {}) {
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

async function fetchPendingArticles(): Promise<Article[]> {
  const data = await notionFetch(`/databases/${NOTION_DB}/query`, {
    method: "POST",
    body: JSON.stringify({
      filter: { property: "ステータス", select: { equals: "note投稿待ち" } },
      sorts: [{ property: "公開予定日", direction: "ascending" }],
    }),
  });

  return data.results.map((page: any) => {
    const p = page.properties;
    const title = (p["タイトル"]?.title ?? []).map((b: any) => b.plain_text).join("");
    const category = p["カテゴリ"]?.select?.name ?? "無料記事";
    const price = p["価格"]?.number ?? null;
    const dateStr = p["公開予定日"]?.date?.start ?? null;
    const thumbnailFiles = p["サムネイル"]?.files ?? [];
    const thumbnailUrl =
      thumbnailFiles[0]?.file?.url ??
      thumbnailFiles[0]?.external?.url ??
      null;

    return {
      pageId: page.id,
      title,
      category,
      price,
      scheduledAt: dateStr ? new Date(dateStr) : null,
      thumbnailUrl,
    };
  });
}

async function fetchBodyText(pageId: string): Promise<string> {
  const data = await notionFetch(`/blocks/${pageId}/children?page_size=100`);
  const lines: string[] = [];

  for (const block of data.results) {
    const rt = block[block.type]?.rich_text ?? [];
    const text = rt.map((b: any) => b.plain_text).join("");

    switch (block.type) {
      case "paragraph":            lines.push(text); break;
      case "heading_1":            lines.push(`# ${text}`); break;
      case "heading_2":            lines.push(`## ${text}`); break;
      case "heading_3":            lines.push(`### ${text}`); break;
      case "bulleted_list_item":   lines.push(`・${text}`); break;
      case "numbered_list_item":   lines.push(`${text}`); break;
      case "quote":                lines.push(`「${text}」`); break;
      case "divider":              lines.push("――――――――――"); break;
      // 画像ブロックはスキップ（サムネイルで対応）
    }
  }

  return lines.filter(Boolean).join("\n\n");
}

async function updateStatus(pageId: string, status: string, noteUrl?: string) {
  const props: any = { ステータス: { select: { name: status } } };
  if (noteUrl) props["note URL"] = { url: noteUrl };
  await notionFetch(`/pages/${pageId}`, {
    method: "PATCH",
    body: JSON.stringify({ properties: props }),
  });
}

// ── サムネイルダウンロード ────────────────────────────────
async function downloadThumbnail(url: string, dest: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`Download failed: ${res.status}`);
  const out = createWriteStream(dest);
  await pipeline(res.body as any, out);
}

async function cleanup(path: string) {
  try { await unlink(path); } catch {}
}

// ── note.com Playwright 自動化 ────────────────────────────
async function loginNote(page: Page) {
  await page.goto("https://note.com/login?redirectPath=%2F");
  await page.waitForLoadState("networkidle");

  // メールアドレス入力
  // 2026-07: note.com ログインUI変更。メール欄は id="email"/type="text"（name無し）、
  // パスワードは id="password"、送信ボタンは type="button" の「ログイン」に変わった。
  // 旧セレクタも OR で残しつつ、現行の #email/#password を優先。
  const emailInput = page.locator('#email, input[name="email"], input[type="email"]').first();
  await emailInput.waitFor({ state: "visible", timeout: 20_000 });
  await emailInput.fill(NOTE_EMAIL);
  await page.locator('#password, input[name="password"], input[type="password"]').first().fill(NOTE_PASSWORD);
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  await page.waitForURL((u) => !u.toString().includes("/login"), { timeout: 20_000 });
  console.log("  ログイン完了");
}

async function publishArticle(
  page: Page,
  article: Article,
  body: string,
  thumbnailPath: string | null
): Promise<string> {

  await page.goto("https://note.com/notes/new");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);

  // ── タイトル入力 ──
  const titleEl = page.locator(
    '[data-placeholder="タイトル"], .o-articleEditTitle__title, h1[contenteditable]'
  ).first();
  await titleEl.click();
  await page.keyboard.type(article.title);
  console.log("  タイトル入力完了");

  // ── 本文入力（クリップボード経由）──
  const bodyEl = page.locator(
    '.o-editable[contenteditable], [data-placeholder="本文を書く"][contenteditable]'
  ).first();
  await bodyEl.click();

  // クリップボードにセットしてペースト
  await page.evaluate((text) => navigator.clipboard.writeText(text), body);
  const modifier = process.platform === "darwin" ? "Meta" : "Control";
  await page.keyboard.press(`${modifier}+v`);
  await page.waitForTimeout(1000);
  console.log("  本文入力完了");

  // ── サムネイル（アイキャッチ）アップロード ──
  if (thumbnailPath) {
    // 「アイキャッチ」ボタンを探す
    const eyecatchBtn = page.locator(
      '[class*="eyecatch"] button, button:has-text("アイキャッチ"), [aria-label*="サムネイル"]'
    ).first();
    if (await eyecatchBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      const [chooser] = await Promise.all([
        page.waitForEvent("filechooser"),
        eyecatchBtn.click(),
      ]);
      await chooser.setFiles(thumbnailPath);
      await page.waitForTimeout(3000);
      console.log("  サムネイルアップロード完了");
    } else {
      console.warn("  サムネイルボタンが見つかりませんでした（スキップ）");
    }
  }

  // ── 公開設定ダイアログを開く ──
  const publishBtn = page.locator(
    'button:has-text("公開設定"), button:has-text("投稿設定"), button:has-text("公開する")'
  ).first();
  await publishBtn.click();
  await page.waitForTimeout(1500);

  // ── 有料設定 ──
  if (article.category === "有料記事" && article.price) {
    const paidLabel = page.locator('label:has-text("有料"), input[value="paid"]').first();
    if (await paidLabel.isVisible({ timeout: 3000 }).catch(() => false)) {
      await paidLabel.click();
      const priceInput = page.locator(
        'input[name*="price"], input[placeholder*="価格"], input[placeholder*="金額"]'
      ).first();
      await priceInput.fill(String(article.price));
      console.log(`  有料設定: ¥${article.price}`);
    }
  }

  // ── 予約投稿 ──
  if (article.scheduledAt) {
    const scheduleLabel = page.locator('label:has-text("予約投稿"), button:has-text("予約")').first();
    if (await scheduleLabel.isVisible({ timeout: 3000 }).catch(() => false)) {
      await scheduleLabel.click();
      await page.waitForTimeout(500);

      const d = article.scheduledAt;
      const pad = (n: number) => String(n).padStart(2, "0");
      const dateValue = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
      const timeValue = `${pad(d.getHours())}:${pad(d.getMinutes())}`;

      const dateInput = page.locator('input[type="date"]').first();
      const timeInput = page.locator('input[type="time"]').first();
      if (await dateInput.isVisible({ timeout: 2000 }).catch(() => false)) {
        await dateInput.fill(dateValue);
        await timeInput.fill(timeValue);
      }
      console.log(`  予約投稿: ${dateValue} ${timeValue}`);
    }
  }

  // ── 投稿実行 ──
  const submitBtn = page.locator(
    'button:has-text("投稿する"), button:has-text("公開する"), button:has-text("予約する")'
  ).first();

  if (DRY_RUN) {
    console.log("  [DRY RUN] 投稿はスキップします");
    await page.screenshot({ path: `/tmp/note-dryrun-${Date.now()}.png` });
    return "dry-run";
  }

  await submitBtn.click();
  await page.waitForLoadState("networkidle", { timeout: 20_000 });
  await page.waitForTimeout(2000);

  return page.url();
}

// ── メイン ────────────────────────────────────────────────
async function main() {
  if (DRY_RUN) console.log("=== DRY RUN モード ===");

  console.log("Notionから投稿待ち記事を取得中...");
  const articles = await fetchPendingArticles();

  if (articles.length === 0) {
    console.log("note投稿待ちの記事はありません。終了。");
    return;
  }

  console.log(`${articles.length}件を処理します\n`);

  const browser = await chromium.launch({ headless: true });
  const context: BrowserContext = await browser.newContext({
    permissions: ["clipboard-read", "clipboard-write"],
    locale: "ja-JP",
  });
  const page = await context.newPage();

  try {
    await loginNote(page);

    for (const article of articles) {
      console.log(`\n▸ ${article.title}`);

      const body = await fetchBodyText(article.pageId);

      let thumbPath: string | null = null;
      if (article.thumbnailUrl) {
        thumbPath = `/tmp/thumb-${article.pageId.replace(/-/g, "")}.jpg`;
        try {
          await downloadThumbnail(article.thumbnailUrl, thumbPath);
          console.log("  サムネイルDL完了");
        } catch (e) {
          console.warn("  サムネイルDL失敗（スキップ）:", e);
          thumbPath = null;
        }
      }

      try {
        const noteUrl = await publishArticle(page, article, body, thumbPath);
        console.log(`  投稿URL: ${noteUrl}`);

        if (!DRY_RUN) {
          await updateStatus(article.pageId, "投稿完了", noteUrl);
        }
      } catch (err) {
        console.error(`  投稿失敗:`, err);
        // エラースクリーンショット保存
        await page.screenshot({ path: `/tmp/note-error-${Date.now()}.png` });
        if (!DRY_RUN) {
          await updateStatus(article.pageId, "投稿エラー");
        }
      } finally {
        if (thumbPath) await cleanup(thumbPath);
      }

      // 連続投稿の間隔
      await page.waitForTimeout(5000);
    }
  } finally {
    await browser.close();
  }

  console.log("\n完了。");
}

main().catch((e) => { console.error(e); process.exit(1); });
