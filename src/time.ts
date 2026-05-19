// JST 中心の時刻ヘルパ。Workers は UTC で動くので必ずここを経由する。

export function tzOffsetMin(env: { TZ_OFFSET_MIN: string }): number {
  const n = Number(env.TZ_OFFSET_MIN);
  return Number.isFinite(n) ? n : 540;
}

export function nowInTz(env: { TZ_OFFSET_MIN: string }, base: Date = new Date()): Date {
  return new Date(base.getTime() + tzOffsetMin(env) * 60_000);
}

export function dateStr(env: { TZ_OFFSET_MIN: string }, base: Date = new Date()): string {
  const d = nowInTz(env, base);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function hhmm(env: { TZ_OFFSET_MIN: string }, iso: string): string {
  const d = nowInTz(env, new Date(iso));
  const h = String(d.getUTCHours()).padStart(2, "0");
  const m = String(d.getUTCMinutes()).padStart(2, "0");
  return `${h}:${m}`;
}

export function diffMinutes(aIso: string, bIso: string): number {
  return Math.round((new Date(bIso).getTime() - new Date(aIso).getTime()) / 60_000);
}
