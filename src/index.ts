import type { Env } from "./types";
import { type LineEvent, type LineMessageEvent, type LineWebhookBody, push, verifySignature } from "./line";
import { handleText } from "./commands";
import { dateStr, diffMinutes, hhmm } from "./time";
import { listActiveStaff, listPunchesOfDay } from "./notion";
import { summarizeDay } from "./reports";

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === "GET" && url.pathname === "/") {
      return new Response("kintai-bot OK", { status: 200 });
    }

    if (req.method === "POST" && url.pathname === "/webhook") {
      const raw = await req.text();
      const sig = req.headers.get("x-line-signature") ?? "";
      if (!(await verifySignature(env, raw, sig))) {
        return new Response("invalid signature", { status: 401 });
      }
      let body: LineWebhookBody;
      try {
        body = JSON.parse(raw) as LineWebhookBody;
      } catch {
        return new Response("bad json", { status: 400 });
      }

      // LINE には即 200 を返し、処理は非同期で
      ctx.waitUntil(processEvents(env, body.events ?? []));
      return new Response("ok", { status: 200 });
    }

    return new Response("not found", { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runCron(env));
  },
};

async function processEvents(env: Env, events: LineEvent[]): Promise<void> {
  await Promise.all(events.map(async (ev) => {
    if (!isMessageEvent(ev)) return;
    if (ev.message.type !== "text") return;
    const text = ev.message.text ?? "";
    const userId = ev.source.userId;
    if (!userId) return;
    try {
      await handleText(env, userId, ev.replyToken, text);
    } catch (e) {
      console.error("handleText failed", e);
    }
  }));
}

function isMessageEvent(ev: LineEvent): ev is LineMessageEvent {
  return ev.type === "message" && "replyToken" in ev && "message" in ev;
}

// CRON: 5分おき。
//  - 出勤から12時間超で退勤打刻がない → 本人に注意、管理者に通知
//  - 出勤から2時間ごとに業務内容ナッジ（最後の業務ログ or 出勤から2h以上空いていたら）
async function runCron(env: Env): Promise<void> {
  const now = new Date();
  const nowIso = now.toISOString();
  const day = dateStr(env, now);
  const staffs = await listActiveStaff(env, day);
  if (staffs.length === 0) return;

  const admins = (env.ADMIN_LINE_USER_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean);

  for (const s of staffs) {
    if (!s.lineUserId) continue;
    const punches = await listPunchesOfDay(env, s, day);
    const state = summarizeDay(punches, nowIso);
    if (!state.clockIn || state.clockOut) continue;

    const sinceIn = diffMinutes(state.clockIn.timestamp, nowIso);

    // 12時間超で退勤忘れ疑い（5分の枠内なら1回だけ通知）
    if (sinceIn >= 12 * 60 && sinceIn < 12 * 60 + 5) {
      await push(env, s.lineUserId,
        `⏰ ${hhmm(env, state.clockIn.timestamp)} の出勤から12時間が経過しました。退勤打刻を忘れていませんか？`);
      await Promise.all(admins.map((to) => push(env, to,
        `⚠️ ${s.name} さんが12時間以上、退勤未打刻です。`)));
    }

    // 業務内容ナッジ：休憩中はスキップ。直近の打刻 or ログから1時間空いていたら1回ナッジ
    if (!state.onBreakSince) {
      // 最後のイベント時刻（出勤含む全打刻）
      const lastTs = punches.length > 0
        ? punches[punches.length - 1]!.timestamp
        : state.clockIn.timestamp;
      const gap = diffMinutes(lastTs, nowIso);
      if (gap >= 60 && gap < 65) {
        await push(env, s.lineUserId,
          "📝 今、何の作業をしていますか？ そのまま本文で送ってください。\n例) 動画編集 #脳育×知育");
      }
    }
  }
}
