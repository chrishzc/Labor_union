/**
 * File: official_holiday_csv.ts
 * Description: Parse the official government office-calendar CSV and orchestrate the existing Holiday Preview -> Apply flow.
 */
import type {
  HolidayApplyRequest,
  HolidayCalendar,
  HolidayPreview,
  HolidayPreviewRequest,
  HolidayReceipt,
} from './holiday_flow_adapter';

const REQUIRED_HEADERS = ['西元日期', '星期', '是否放假', '備註'] as const;
const VALID_WEEKDAYS = new Set(['一', '二', '三', '四', '五', '六', '日']);
const VALID_HOLIDAY_FLAGS = new Set(['0', '2']);

export interface OfficialHolidayCandidate {
  readonly holiday_date: string;
  readonly holiday_name: string;
}

export interface OfficialHolidayCsvSuccess {
  readonly ok: true;
  readonly year: number;
  readonly holidays: readonly OfficialHolidayCandidate[];
}

export interface OfficialHolidayCsvFailure {
  readonly ok: false;
  readonly error: string;
}

export type OfficialHolidayCsvResult = OfficialHolidayCsvSuccess | OfficialHolidayCsvFailure;

export interface OfficialHolidayImportPlan {
  readonly pending: readonly OfficialHolidayCandidate[];
  readonly existingSkipCount: number;
}

export interface OfficialHolidayImportFailure {
  readonly holiday_date: string;
  readonly reason: string;
}

export interface OfficialHolidayImportSummary {
  readonly successCount: number;
  readonly skipCount: number;
  readonly failureCount: number;
  readonly failures: readonly OfficialHolidayImportFailure[];
}

export interface OfficialHolidayImportOperations {
  readonly query: (query: { readonly from_date: string; readonly to_date: string }) => Promise<HolidayCalendar>;
  readonly preview: (request: HolidayPreviewRequest) => Promise<HolidayPreview>;
  readonly apply: (request: HolidayApplyRequest) => Promise<HolidayReceipt>;
  readonly setDraft: (request: HolidayPreviewRequest) => void;
}

function parseCsvRows(text: string): readonly (readonly string[])[] | null {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let inQuotes = false;
  let afterQuote = false;

  const pushCell = () => {
    row.push(cell);
    cell = '';
    afterQuote = false;
  };
  const pushRow = () => {
    pushCell();
    rows.push(row);
    row = [];
  };

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (inQuotes) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          cell += '"';
          index += 1;
        } else {
          inQuotes = false;
          afterQuote = true;
        }
      } else {
        cell += character;
      }
      continue;
    }

    if (afterQuote) {
      if (character === ',') {
        pushCell();
        continue;
      }
      if (character === '\n') {
        pushRow();
        continue;
      }
      if (character === '\r' && text[index + 1] === '\n') continue;
      return null;
    }

    if (character === '"') {
      if (cell.length !== 0) return null;
      inQuotes = true;
    } else if (character === ',') {
      pushCell();
    } else if (character === '\n') {
      pushRow();
    } else if (character === '\r' && text[index + 1] === '\n') {
      // The following LF will finish the row.
    } else {
      cell += character;
    }
  }

  if (inQuotes) return null;
  if (cell.length > 0 || row.length > 0 || afterQuote) pushRow();
  while (rows.length > 0 && rows[rows.length - 1].every((value) => value.trim() === '')) rows.pop();
  return rows;
}

function normalizeDate(value: string): string | null {
  const normalized = value.trim();
  const match = normalized.match(/^(\d{4})(?:[-/]?)(\d{2})(?:[-/]?)(\d{2})$/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) return null;
  return `${match[1]}-${match[2]}-${match[3]}`;
}

function fail(error: string): OfficialHolidayCsvFailure {
  return { ok: false, error };
}

function failureReason(cause: unknown): string {
  if (cause instanceof Error && cause.message.trim()) return cause.message.trim();
  return 'Holiday Preview／Apply 失敗。';
}

export function parseOfficialHolidayCsv(text: string): OfficialHolidayCsvResult {
  const rows = parseCsvRows(text.replace(/^\uFEFF/, ''));
  if (!rows || rows.length < 2) return fail('CSV 格式不正確或沒有資料列。');

  const headers = rows[0];
  const headerIndexes = new Map<string, number>();
  headers.forEach((header, index) => {
    if (!headerIndexes.has(header)) headerIndexes.set(header, index);
  });
  const missing = REQUIRED_HEADERS.filter((header) => !headerIndexes.has(header));
  if (missing.length > 0) return fail(`CSV 缺少必要欄位：${missing.join('、')}。`);

  const dateIndex = headerIndexes.get('西元日期')!;
  const weekdayIndex = headerIndexes.get('星期')!;
  const flagIndex = headerIndexes.get('是否放假')!;
  const noteIndex = headerIndexes.get('備註')!;
  const years = new Set<number>();
  const holidays: OfficialHolidayCandidate[] = [];
  const seenHolidayKeys = new Set<string>();

  for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    if (row.every((value) => value.trim() === '')) continue;

    const holidayDate = normalizeDate(row[dateIndex] ?? '');
    const weekday = (row[weekdayIndex] ?? '').trim();
    const holidayFlag = (row[flagIndex] ?? '').trim();
    const note = (row[noteIndex] ?? '').trim();
    if (!holidayDate) return fail(`第 ${rowIndex + 1} 列的西元日期無效。`);
    if (!VALID_WEEKDAYS.has(weekday)) return fail(`第 ${rowIndex + 1} 列的星期無效。`);
    if (!VALID_HOLIDAY_FLAGS.has(holidayFlag)) return fail(`第 ${rowIndex + 1} 列的是否放假無效。`);

    years.add(Number(holidayDate.slice(0, 4)));
    if (holidayFlag !== '2' || note === '') continue;
    if (note.length > 100) return fail(`第 ${rowIndex + 1} 列的備註超過 Holiday 名稱上限。`);

    const key = `${holidayDate}\u0000${note}`;
    if (seenHolidayKeys.has(key)) continue;
    seenHolidayKeys.add(key);
    holidays.push({ holiday_date: holidayDate, holiday_name: note });
  }

  if (years.size !== 1) return fail('CSV 日期必須全部屬於同一年度。');
  const [year] = years;
  if (!year) return fail('無法判定 CSV 年度。');
  return { ok: true, year, holidays };
}

export function planOfficialHolidayImport(
  parsed: OfficialHolidayCsvSuccess,
  calendar: HolidayCalendar,
): OfficialHolidayImportPlan {
  const existingKeys = new Set(
    calendar.holidays.map((holiday) => `${holiday.holiday_date}\u0000${holiday.holiday_name}`),
  );
  const pending = parsed.holidays.filter(
    (holiday) => !existingKeys.has(`${holiday.holiday_date}\u0000${holiday.holiday_name}`),
  );
  return {
    pending,
    existingSkipCount: parsed.holidays.length - pending.length,
  };
}

function yearHorizon(year: number): { readonly from_date: string; readonly to_date: string } {
  return {
    from_date: `${year}-01-01`,
    to_date: `${year}-12-31`,
  };
}

export async function importOfficialHolidayCandidates(
  candidates: readonly OfficialHolidayCandidate[],
  year: number,
  existingSkipCount: number,
  operations: OfficialHolidayImportOperations,
): Promise<OfficialHolidayImportSummary> {
  const horizon = yearHorizon(year);
  let successCount = 0;
  let skipCount = existingSkipCount;
  const failures: OfficialHolidayImportFailure[] = [];

  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index];
    const previewRequest: HolidayPreviewRequest = {
      action: 'upsert',
      holiday_date: candidate.holiday_date,
      holiday_name: candidate.holiday_name,
      is_double_pay_default: false,
      ...horizon,
    };

    try {
      operations.setDraft(previewRequest);
      const preview = await operations.preview(previewRequest);
      const receipt = await operations.apply({
        ...previewRequest,
        expected_calendar_version: preview.command.expected_calendar_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: `匯入政府官方 ${year} 年辦公日曆 CSV`,
      });
      if (receipt.changed) successCount += 1;
      else skipCount += 1;
    } catch (cause) {
      failures.push({ holiday_date: candidate.holiday_date, reason: failureReason(cause) });
      try {
        await operations.query(horizon);
      } catch (queryCause) {
        const reason = `無法取得最新 Holiday readback：${failureReason(queryCause)}`;
        for (const remaining of candidates.slice(index + 1)) {
          failures.push({ holiday_date: remaining.holiday_date, reason });
        }
        break;
      }
    }
  }

  await operations.query(horizon);
  return {
    successCount,
    skipCount,
    failureCount: failures.length,
    failures,
  };
}
