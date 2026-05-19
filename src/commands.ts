import type { Env, PunchKind, Staff } from "./types";
import { getProfile, push, reply } from "./line";
import { createPunch, createStaff, createWorkLog, findStaffByLineId, listPunchesOfDay, listWorkLogsOfDay } from "./notion";
import { dateStr, hhmm } from "./time";
import { fmtDuration, generateDailyReport, summarizeDay } from "./reports";

const HELP = [
  "📘 勤怠コマンド",
  "",
  "■ 打刻",
  "・おはようございます → 出勤打刻",
  "・お疲れ様でした → 退勤打刻＋日報自動生成",
  "・休憩 → 休憩開始",
  "・再開 → 休憩終了",
  "",
  "■ 業務報告",
  "💡 普通に文章を送るだけで業務内容として記録されます",
  "  例) 動画編集 30分 #脳育×知育",
  "  例) 教具制作 自宅",
  "※ 1時間ごとに「今なにしてる？」と自動でお伺いします",
  "",
  "■ 確認",
  "・状況 → 今日の打刻状況を表示",
  "・日報 → 今日の日報を表示",
  "・ヘルプ → このメッセージ",
].join("\n");

const REPORT_GUIDE = [
  "📝 業務報告の入力方法",
  "",
  "そのまま本文に内容を送ってください。",
  "",
  "例)",
  "・動画編集 30分",
  "・教具制作 自宅",
  "・打ち合わせ準備 #脳育×知育",
  "",
  "「#案件名」をつけると案件タグで仕分けされます。",
].join("\n");

// 「報告 動画編集 30分」「報告: 〜」「報告／〜」など揺らぎ吸収
function parseArgs(text: string): { cmd: string; rest: string } {
  const trimmed = text.trim();
  const m = trimmed.match(/^([^\s:：/／]+)[\s:：/／]*(.*)$/s);
  if (!m) return { cmd: trimmed, rest: "" };
  return { cmd: m[1] ?? trimmed, rest: (m[2] ?? "").trim() };
}

function normalize(cmd: string): string {
  const map: Record<string, string> = {
    // 出勤系
    "出勤": "in", "出社": "in", "始業": "in",
    "おはよう": "in", "おはようございます": "in",
    // 退勤系（バリエーション全部拾う）
    "退勤": "out", "退社": "out", "終業": "out",
    "おつかれ": "out", "お疲れ": "out",
    "お疲れさま": "out", "おつかれさま": "out", "お疲れ様": "out",
    "お疲れさまでした": "out", "おつかれさまでした": "out", "お疲れ様でした": "out", "お疲れさまです": "out", "お疲れ様です": "out",
    "休憩": "break", "ブレイク": "break", "離席": "break",
    "再開": "resume", "戻り": "resume", "復帰": "resume",
    "報告": "log", "業務": "log", "メモ": "log",
    "案件": "project",
    "状況": "status", "ステータス": "status", "今": "status",
    "日報": "report",
    "ヘルプ": "help", "help": "help", "?": "help", "？": "help",
  };
  return map[cmd] ?? "";
}

export async function handleText(env: Env, userId: string, replyToken: string, text: string): Promise<void> {
  const { cmd, rest } = parseArgs(text);
  const key = normalize(cmd);

  // 未登録ユーザーの初回登録
  let staff = await findStaffByLineId(env, userId);
  if (!staff) {
    if (key === "help" || key === "status") {
      await reply(env, replyToken, "あなたはまだスタッフ登録されていません。「登録 山田太郎」のように送ってください。");
      return;
    }
    if (cmd === "登録") {
      const profile = await getProfile(env, userId);
      const name = rest || profile?.displayName || "新規スタッフ";
      staff = await createStaff(env, { name, lineUserId: userId });
      await reply(env, replyToken,
        `登録しました：${staff.name}\n\n` +
        `💡 業務中は、やっていることを普通にメッセージで送るだけでOK。\n` +
        `自動で業務日報にまとまります。\n\n${HELP}`);
      return;
    }
    await reply(env, replyToken,
      "スタッフ登録が必要です。「登録 山田太郎」のように送ってください（名前は後から Notion で変更できます）。");
    return;
  }

  switch (key) {
    case "in":  return doPunch(env, staff, replyToken, "出勤");
    case "out": return doClockOut(env, staff, replyToken);
    case "break":  return doPunch(env, staff, replyToken, "休憩開始");
    case "resume": return doPunch(env, staff, replyToken, "休憩終了");
    case "log": return doWorkLog(env, staff, replyToken, rest);
    case "status": return doStatus(env, staff, replyToken);
    case "report": return doReport(env, staff, replyToken);
    case "help": return reply(env, replyToken, HELP);
    case "project": return doProject(env, staff, replyToken, rest);
    default:
      // コマンド未指定のメッセージは「業務内容の報告」として扱う（外注スタッフの定着優先）
      return doWorkLog(env, staff, replyToken, text);
  }
}

async function doPunch(env: Env, staff: Staff, replyToken: string, kind: PunchKind): Promise<void> {
  const now = new Date().toISOString();
  const day = dateStr(env, new Date(now));
  const punches = await listPunchesOfDay(env, staff, day);
  const state = summarizeDay(punches, now);

  // 連打ガード
  if (kind === "出勤" && state.clockIn && !state.clockOut) {
    await reply(env, replyToken, `すでに ${hhmm(env, state.clockIn.timestamp)} に出勤打刻があります。`);
    return;
  }
  if (kind === "休憩開始" && state.onBreakSince) {
    await reply(env, replyToken, `すでに ${hhmm(env, state.onBreakSince)} から休憩中です。`);
    return;
  }
  if (kind === "休憩終了" && !state.onBreakSince) {
    await reply(env, replyToken, "現在、休憩中ではありません。");
    return;
  }
  if (kind !== "出勤" && !state.clockIn) {
    await reply(env, replyToken, "まず「出勤」と送ってください。");
    return;
  }

  await createPunch(env, { staff, kind, timestamp: now });
  const t = hhmm(env, now);
  const msg = {
    "出勤": `🟢 ${t} 出勤打刻しました。今日もよろしくお願いします。`,
    "退勤": `🔴 ${t} 退勤打刻しました。`,
    "休憩開始": `☕ ${t} 休憩開始。`,
    "休憩終了": `▶️ ${t} 休憩終了、業務に戻ります。`,
  }[kind];
  await reply(env, replyToken, msg);
}

async function doClockOut(env: Env, staff: Staff, replyToken: string): Promise<void> {
  const now = new Date().toISOString();
  const day = dateStr(env, new Date(now));
  const punches = await listPunchesOfDay(env, staff, day);
  const state = summarizeDay(punches, now);

  if (!state.clockIn) {
    await reply(env, replyToken, "本日の出勤打刻が見つかりません。");
    return;
  }
  if (state.clockOut) {
    await reply(env, replyToken, `すでに ${hhmm(env, state.clockOut.timestamp)} に退勤打刻があります。`);
    return;
  }
  if (state.onBreakSince) {
    // 退勤前に休憩終了を自動で打つ
    await createPunch(env, { staff, kind: "休憩終了", timestamp: now });
  }
  await createPunch(env, { staff, kind: "退勤", timestamp: now });

  const { text } = await generateDailyReport(env, staff, day);

  await reply(env, replyToken, `🔴 ${hhmm(env, now)} 退勤打刻しました。お疲れさまでした。\n\n${text}`);

  // 業務報告が0件なら本人に push で促す
  const worklogs = await listWorkLogsOfDay(env, staff, day);
  if (worklogs.length === 0 && staff.lineUserId) {
    await push(env, staff.lineUserId,
      "📝 本日の業務内容のご報告がまだありません。\nどんな作業をされましたか？ そのまま本文で送ってください。\n例) 動画編集 30分 #脳育×知育",
    );
  }

  // 管理者にも日報を push
  const admins = (env.ADMIN_LINE_USER_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  await Promise.all(admins.map((to) => push(env, to, text)));
}

async function doWorkLog(env: Env, staff: Staff, replyToken: string, content: string): Promise<void> {
  if (!content.trim()) {
    await reply(env, replyToken, REPORT_GUIDE);
    return;
  }
  // 案件タグの簡易抽出："#案件名" を1つだけ拾う
  let project: string | null = null;
  const tag = content.match(/#([^\s#]+)/);
  if (tag) project = tag[1] ?? null;

  const now = new Date().toISOString();
  await createWorkLog(env, { staff, timestamp: now, content, project });
  await reply(env, replyToken, `📝 ${hhmm(env, now)} 業務記録しました${project ? `（案件：${project}）` : ""}。`);
}

async function doStatus(env: Env, staff: Staff, replyToken: string): Promise<void> {
  const now = new Date().toISOString();
  const day = dateStr(env, new Date(now));
  const punches = await listPunchesOfDay(env, staff, day);
  const state = summarizeDay(punches, now);
  if (!state.clockIn) {
    await reply(env, replyToken, `${day} まだ出勤打刻はありません。`);
    return;
  }
  const lines = [
    `📊 ${day} ${staff.name} の状況`,
    `出勤：${hhmm(env, state.clockIn.timestamp)}`,
    state.clockOut ? `退勤：${hhmm(env, state.clockOut.timestamp)}` : `退勤：未`,
    `休憩：${fmtDuration(state.breakMinutes)}${state.onBreakSince ? `（${hhmm(env, state.onBreakSince)}〜 継続中）` : ""}`,
    `稼働：${fmtDuration(state.workMinutes)}${state.clockOut ? "" : "（現時刻まで）"}`,
  ];
  await reply(env, replyToken, lines.join("\n"));
}

async function doReport(env: Env, staff: Staff, replyToken: string): Promise<void> {
  const day = dateStr(env);
  const { text } = await generateDailyReport(env, staff, day);
  await reply(env, replyToken, text);
}

async function doProject(env: Env, staff: Staff, replyToken: string, name: string): Promise<void> {
  if (!name) {
    await reply(env, replyToken, "案件名を続けて指定してください。例) 案件 叶結び");
    return;
  }
  // MVP では「以後の業務ログのデフォルト案件」までは持たず、明示タグ運用に倒す
  await reply(env, replyToken,
    `案件タグは業務報告本文に "#${name}" を入れてください。\n例) 報告 動画編集 30分 #${name}`);
}
