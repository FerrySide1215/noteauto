import type { Env } from "./types";

const API = "https://api.line.me/v2/bot";

export async function verifySignature(env: Env, rawBody: string, signature: string): Promise<boolean> {
  if (!signature) return false;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.LINE_CHANNEL_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(rawBody));
  const expected = btoa(String.fromCharCode(...new Uint8Array(mac)));
  // タイミングセーフ比較
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  return diff === 0;
}

// クイックリプライ：返信メッセージの下に最大13個のボタンを並べる
const QUICK_REPLY_ITEMS = [
  { label: "出勤", text: "おはようございます" },
  { label: "退勤", text: "お疲れ様でした" },
  { label: "休憩", text: "休憩" },
  { label: "再開", text: "再開" },
  { label: "業務報告", text: "報告" },
  { label: "状況", text: "状況" },
  { label: "日報", text: "日報" },
  { label: "ヘルプ", text: "ヘルプ" },
];

function buildQuickReply() {
  return {
    items: QUICK_REPLY_ITEMS.map((q) => ({
      type: "action" as const,
      action: { type: "message" as const, label: q.label, text: q.text },
    })),
  };
}

export async function reply(env: Env, replyToken: string, text: string): Promise<void> {
  await fetch(`${API}/message/reply`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text: trimText(text), quickReply: buildQuickReply() }],
    }),
  });
}

export async function push(env: Env, to: string, text: string): Promise<void> {
  await fetch(`${API}/message/push`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      to,
      messages: [{ type: "text", text: trimText(text), quickReply: buildQuickReply() }],
    }),
  });
}

export async function getProfile(env: Env, userId: string): Promise<{ displayName: string } | null> {
  const r = await fetch(`${API}/profile/${userId}`, {
    headers: { Authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}` },
  });
  if (!r.ok) return null;
  return (await r.json()) as { displayName: string };
}

function trimText(s: string): string {
  // LINE のテキスト 1 通あたり 5000 文字制限を超えないよう保険
  return s.length > 4900 ? s.slice(0, 4900) + "\n…(省略)" : s;
}

// LINE Webhook イベントの最小型
export interface LineMessageEvent {
  type: "message";
  replyToken: string;
  source: { userId: string; type: string };
  message: { type: string; text?: string };
  timestamp: number;
}
export type LineEvent = LineMessageEvent | { type: string; [k: string]: unknown };

export interface LineWebhookBody {
  events: LineEvent[];
}
