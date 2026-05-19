import type { Env, PunchKind, PunchRecord, Staff, WorkLogRecord } from "./types";
import { dateStr, hhmm } from "./time";

const NOTION_VERSION = "2022-06-28";
const BASE = "https://api.notion.com/v1";

async function notion<T = unknown>(env: Env, path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.NOTION_TOKEN}`,
      "Notion-Version": NOTION_VERSION,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`Notion API ${r.status}: ${t}`);
  }
  return (await r.json()) as T;
}

// --- スタッフ ---

export async function findStaffByLineId(env: Env, lineUserId: string): Promise<Staff | null> {
  const data = await notion<{ results: NotionPage[] }>(env, `/databases/${env.NOTION_DB_STAFF}/query`, {
    method: "POST",
    body: JSON.stringify({
      filter: {
        and: [
          { property: "LINE_UID", rich_text: { equals: lineUserId } },
          { property: "有効", checkbox: { equals: true } },
        ],
      },
      page_size: 1,
    }),
  });
  const page = data.results[0];
  return page ? toStaff(page) : null;
}

export async function createStaff(env: Env, params: {
  name: string;
  lineUserId: string;
  category?: string;
  hourlyWage?: number;
}): Promise<Staff> {
  const page = await notion<NotionPage>(env, `/pages`, {
    method: "POST",
    body: JSON.stringify({
      parent: { database_id: env.NOTION_DB_STAFF },
      properties: {
        名前: { title: [{ text: { content: params.name } }] },
        LINE_UID: { rich_text: [{ text: { content: params.lineUserId } }] },
        区分: { select: { name: params.category ?? "外注" } },
        時給: { number: params.hourlyWage ?? 0 },
        有効: { checkbox: true },
      },
    }),
  });
  return toStaff(page);
}

// --- 打刻 ---

export async function createPunch(env: Env, params: {
  staff: Staff;
  kind: PunchKind;
  timestamp: string;
  project?: string | null;
}): Promise<void> {
  const { staff, kind, timestamp, project } = params;
  const day = dateStr(env, new Date(timestamp));
  const time = hhmm(env, timestamp);
  await notion(env, `/pages`, {
    method: "POST",
    body: JSON.stringify({
      parent: { database_id: env.NOTION_DB_PUNCH },
      properties: {
        名前: { title: [{ text: { content: `${day} ${time} ${staff.name} ${kind}` } }] },
        スタッフ: { relation: [{ id: staff.pageId }] },
        種別: { select: { name: kind } },
        時刻: { date: { start: timestamp } },
        日付: { rich_text: [{ text: { content: day } }] },
        ...(project ? { 案件: { select: { name: project } } } : {}),
      },
    }),
  });
}

export async function listPunchesOfDay(env: Env, staff: Staff, day: string): Promise<PunchRecord[]> {
  const data = await notion<{ results: NotionPage[] }>(env, `/databases/${env.NOTION_DB_PUNCH}/query`, {
    method: "POST",
    body: JSON.stringify({
      filter: {
        and: [
          { property: "スタッフ", relation: { contains: staff.pageId } },
          { property: "日付", rich_text: { equals: day } },
        ],
      },
      sorts: [{ property: "時刻", direction: "ascending" }],
      page_size: 100,
    }),
  });
  return data.results.map(toPunch);
}

// 「今、出勤中で休憩中でない」スタッフ一覧（CRON でナッジ送る用）
export async function listActiveStaff(env: Env, day: string): Promise<Staff[]> {
  // 当日の打刻が1件以上あるスタッフを抽出
  const data = await notion<{ results: NotionPage[] }>(env, `/databases/${env.NOTION_DB_PUNCH}/query`, {
    method: "POST",
    body: JSON.stringify({
      filter: { property: "日付", rich_text: { equals: day } },
      page_size: 100,
    }),
  });
  const ids = new Set<string>();
  for (const r of data.results) {
    const rel = (r.properties["スタッフ"] as NotionRelationProp | undefined)?.relation;
    rel?.forEach((x) => ids.add(x.id));
  }
  return Promise.all([...ids].map((id) => getStaffById(env, id))).then(
    (xs) => xs.filter((x): x is Staff => !!x),
  );
}

export async function getStaffById(env: Env, pageId: string): Promise<Staff | null> {
  try {
    const p = await notion<NotionPage>(env, `/pages/${pageId}`);
    return toStaff(p);
  } catch {
    return null;
  }
}

// --- 業務ログ ---

export async function createWorkLog(env: Env, params: {
  staff: Staff;
  timestamp: string;
  content: string;
  project?: string | null;
}): Promise<void> {
  const { staff, timestamp, content, project } = params;
  const day = dateStr(env, new Date(timestamp));
  const head = content.length > 40 ? content.slice(0, 40) + "…" : content;
  await notion(env, `/pages`, {
    method: "POST",
    body: JSON.stringify({
      parent: { database_id: env.NOTION_DB_WORKLOG },
      properties: {
        名前: { title: [{ text: { content: head || "(空)" } }] },
        スタッフ: { relation: [{ id: staff.pageId }] },
        時刻: { date: { start: timestamp } },
        日付: { rich_text: [{ text: { content: day } }] },
        内容: { rich_text: [{ text: { content } }] },
        ...(project ? { 案件: { select: { name: project } } } : {}),
      },
    }),
  });
}

export async function listWorkLogsOfDay(env: Env, staff: Staff, day: string): Promise<WorkLogRecord[]> {
  const data = await notion<{ results: NotionPage[] }>(env, `/databases/${env.NOTION_DB_WORKLOG}/query`, {
    method: "POST",
    body: JSON.stringify({
      filter: {
        and: [
          { property: "スタッフ", relation: { contains: staff.pageId } },
          { property: "日付", rich_text: { equals: day } },
        ],
      },
      sorts: [{ property: "時刻", direction: "ascending" }],
      page_size: 100,
    }),
  });
  return data.results.map(toWorkLog);
}

// --- 日報 ---

export async function createReport(env: Env, params: {
  staff: Staff;
  dateStr: string;
  clockIn: string | null;
  clockOut: string | null;
  breakMinutes: number;
  workMinutes: number;
  summary: string;
  estimatedPay: number;
}): Promise<string> {
  const r = await notion<NotionPage>(env, `/pages`, {
    method: "POST",
    body: JSON.stringify({
      parent: { database_id: env.NOTION_DB_REPORT },
      properties: {
        名前: { title: [{ text: { content: `${params.dateStr} ${params.staff.name}` } }] },
        スタッフ: { relation: [{ id: params.staff.pageId }] },
        日付: { rich_text: [{ text: { content: params.dateStr } }] },
        ...(params.clockIn ? { 出勤: { date: { start: params.clockIn } } } : {}),
        ...(params.clockOut ? { 退勤: { date: { start: params.clockOut } } } : {}),
        休憩分: { number: params.breakMinutes },
        "稼働分": { number: params.workMinutes },
        業務サマリー: { rich_text: [{ text: { content: params.summary.slice(0, 1900) } }] },
        報酬概算: { number: params.estimatedPay },
        承認: { select: { name: "未承認" } },
      },
    }),
  });
  return r.id;
}

// --- 内部 ---

interface NotionPage {
  id: string;
  properties: Record<string, unknown>;
}
interface NotionRelationProp {
  relation: { id: string }[];
}

function toStaff(p: NotionPage): Staff {
  const props = p.properties as Record<string, any>;
  return {
    pageId: p.id,
    name: props["名前"]?.title?.[0]?.plain_text ?? props["名前"]?.title?.[0]?.text?.content ?? "(無名)",
    lineUserId: props["LINE_UID"]?.rich_text?.[0]?.plain_text ?? "",
    hourlyWage: props["時給"]?.number ?? 0,
    category: props["区分"]?.select?.name ?? "外注",
    active: props["有効"]?.checkbox ?? true,
  };
}

function toPunch(p: NotionPage): PunchRecord {
  const props = p.properties as Record<string, any>;
  return {
    pageId: p.id,
    staffPageId: props["スタッフ"]?.relation?.[0]?.id ?? "",
    kind: (props["種別"]?.select?.name ?? "出勤") as PunchKind,
    timestamp: props["時刻"]?.date?.start ?? "",
    dateStr: props["日付"]?.rich_text?.[0]?.plain_text ?? "",
    project: props["案件"]?.select?.name ?? null,
  };
}

function toWorkLog(p: NotionPage): WorkLogRecord {
  const props = p.properties as Record<string, any>;
  return {
    pageId: p.id,
    staffPageId: props["スタッフ"]?.relation?.[0]?.id ?? "",
    timestamp: props["時刻"]?.date?.start ?? "",
    dateStr: props["日付"]?.rich_text?.[0]?.plain_text ?? "",
    project: props["案件"]?.select?.name ?? null,
    content: props["内容"]?.rich_text?.map((x: any) => x.plain_text).join("") ?? "",
  };
}
