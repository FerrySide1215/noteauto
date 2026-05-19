export interface Env {
  LINE_CHANNEL_SECRET: string;
  LINE_CHANNEL_ACCESS_TOKEN: string;
  NOTION_TOKEN: string;
  NOTION_DB_STAFF: string;
  NOTION_DB_PUNCH: string;
  NOTION_DB_WORKLOG: string;
  NOTION_DB_REPORT: string;
  ADMIN_LINE_USER_IDS: string;
  TZ_OFFSET_MIN: string;
}

export type PunchKind = "出勤" | "退勤" | "休憩開始" | "休憩終了";

export interface Staff {
  pageId: string;
  name: string;
  lineUserId: string;
  hourlyWage: number;
  category: string; // 正社員 / 外注 / 自分
  active: boolean;
}

export interface PunchRecord {
  pageId: string;
  staffPageId: string;
  kind: PunchKind;
  timestamp: string; // ISO
  dateStr: string;   // YYYY-MM-DD（JST基準）
  project: string | null;
}

export interface WorkLogRecord {
  pageId: string;
  staffPageId: string;
  timestamp: string;
  dateStr: string;
  project: string | null;
  content: string;
}

export interface DailyReport {
  staff: Staff;
  dateStr: string;
  clockIn: string | null;
  clockOut: string | null;
  breakMinutes: number;
  workMinutes: number;
  worklogs: WorkLogRecord[];
  estimatedPay: number;
}
