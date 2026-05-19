import type { Env, PunchRecord, Staff, WorkLogRecord } from "./types";
import { hhmm, diffMinutes } from "./time";
import { createReport, listPunchesOfDay, listWorkLogsOfDay } from "./notion";

export interface DayState {
  clockIn: PunchRecord | null;
  clockOut: PunchRecord | null;
  breakMinutes: number;
  onBreakSince: string | null; // 休憩中なら開始時刻 ISO
  workMinutes: number;         // 退勤までの想定稼働分（退勤前は現在時刻基準）
  punches: PunchRecord[];
}

export function summarizeDay(punches: PunchRecord[], nowIso: string): DayState {
  let clockIn: PunchRecord | null = null;
  let clockOut: PunchRecord | null = null;
  let breakMin = 0;
  let breakStart: string | null = null;

  for (const p of punches) {
    if (p.kind === "出勤" && !clockIn) clockIn = p;
    else if (p.kind === "退勤") clockOut = p;
    else if (p.kind === "休憩開始") breakStart = p.timestamp;
    else if (p.kind === "休憩終了" && breakStart) {
      breakMin += diffMinutes(breakStart, p.timestamp);
      breakStart = null;
    }
  }

  // 退勤打刻が打たれずに休憩中のまま終わっている可能性は CRON 側で扱う
  let workMin = 0;
  if (clockIn) {
    const end = clockOut?.timestamp ?? nowIso;
    workMin = diffMinutes(clockIn.timestamp, end) - breakMin;
    if (breakStart && !clockOut) {
      // まだ休憩中：休憩分は加算済みではないので、開始からの分を差し引く
      workMin -= diffMinutes(breakStart, nowIso);
    }
    if (workMin < 0) workMin = 0;
  }

  return {
    clockIn,
    clockOut,
    breakMinutes: breakMin,
    onBreakSince: breakStart,
    workMinutes: workMin,
    punches,
  };
}

export function fmtDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h > 0 ? `${h}時間${m}分` : `${m}分`;
}

export function buildSummaryText(env: Env, worklogs: WorkLogRecord[]): string {
  if (worklogs.length === 0) return "（業務内容の報告なし）";
  const byProject = new Map<string, string[]>();
  for (const w of worklogs) {
    const key = w.project ?? "未分類";
    const arr = byProject.get(key) ?? [];
    arr.push(`・${hhmm(env, w.timestamp)} ${w.content}`);
    byProject.set(key, arr);
  }
  return [...byProject.entries()]
    .map(([proj, lines]) => `【${proj}】\n${lines.join("\n")}`)
    .join("\n\n");
}

export async function generateDailyReport(env: Env, staff: Staff, day: string): Promise<{
  text: string;
  pageId: string;
}> {
  const nowIso = new Date().toISOString();
  const punches = await listPunchesOfDay(env, staff, day);
  const worklogs = await listWorkLogsOfDay(env, staff, day);
  const state = summarizeDay(punches, nowIso);

  const summary = buildSummaryText(env, worklogs);
  const pay = Math.round((staff.hourlyWage * state.workMinutes) / 60);

  const pageId = await createReport(env, {
    staff,
    dateStr: day,
    clockIn: state.clockIn?.timestamp ?? null,
    clockOut: state.clockOut?.timestamp ?? null,
    breakMinutes: state.breakMinutes,
    workMinutes: state.workMinutes,
    summary,
    estimatedPay: pay,
  });

  const text = [
    `📋 ${day} ${staff.name} 日報`,
    `出勤：${state.clockIn ? hhmm(env, state.clockIn.timestamp) : "—"}`,
    `退勤：${state.clockOut ? hhmm(env, state.clockOut.timestamp) : "—"}`,
    `休憩：${fmtDuration(state.breakMinutes)}`,
    `稼働：${fmtDuration(state.workMinutes)}`,
    staff.hourlyWage > 0 ? `報酬概算：¥${pay.toLocaleString()}` : null,
    "",
    "▼ 業務内容",
    summary,
  ]
    .filter(Boolean)
    .join("\n");

  return { text, pageId };
}
