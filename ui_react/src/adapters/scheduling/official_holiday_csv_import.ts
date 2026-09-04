/**
 * File: official_holiday_csv_import.ts
 * Description: 將政府辦公日曆 CSV 驗證並轉為可交給既有 Holiday Preview → Apply 的年度假日清單。
 */

export interface OfficialHolidayCsvRow {
  readonly holidayDate: string;
  readonly holidayName: string;
}

export interface OfficialHolidayCsvPreview {
  readonly year: number;
  readonly holidays: readonly OfficialHolidayCsvRow[];
}

export class OfficialHolidayCsvError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OfficialHolidayCsvError';
  }
}

const REQUIRED_HEADERS = ['西元日期', '星期', '是否放假', '備註'] as const;

function parseCsvRows(source: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quoted) {
      if (character === '"') {
        if (source[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
      continue;
    }

    if (character === '"') {
      quoted = true;
    } else if (character === ',') {
      row.push(field);
      field = '';
    } else if (character === '\n') {
      row.push(field.replace(/\r$/, ''));
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += character;
    }
  }

  if (quoted) throw new OfficialHolidayCsvError('CSV 引號格式不完整，未執行匯入。');
  if (field.length > 0 || row.length > 0) {
    row.push(field.replace(/\r$/, ''));
    rows.push(row);
  }
  return rows;
}

function normalizeCalendarDate(value: string): string | null {
  const normalized = value.trim();
  let year: number;
  let month: number;
  let day: number;

  const compact = normalized.match(/^(\d{4})(\d{2})(\d{2})$/);
  const separated = normalized.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})$/);
  if (compact) {
    year = Number(compact[1]);
    month = Number(compact[2]);
    day = Number(compact[3]);
  } else if (separated) {
    year = Number(separated[1]);
    month = Number(separated[2]);
    day = Number(separated[3]);
  } else {
    return null;
  }

  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) return null;

  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export function parseOfficialHolidayCsv(source: string): OfficialHolidayCsvPreview {
  const rows = parseCsvRows(source.replace(/^\uFEFF/, ''));
  const headerIndex = rows.findIndex((row) => row.some((cell) => cell.trim().length > 0));
  if (headerIndex === -1) throw new OfficialHolidayCsvError('CSV 沒有標題列，未執行匯入。');

  const headers = rows[headerIndex].map((cell) => cell.trim());
  const indexes = Object.fromEntries(REQUIRED_HEADERS.map((header) => [header, headers.indexOf(header)])) as Record<(typeof REQUIRED_HEADERS)[number], number>;
  const missing = REQUIRED_HEADERS.filter((header) => indexes[header] < 0);
  if (missing.length > 0) {
    throw new OfficialHolidayCsvError(`CSV 缺少必要欄位：${missing.join('、')}。未執行匯入。`);
  }

  const years = new Set<number>();
  const holidayByDate = new Map<string, OfficialHolidayCsvRow>();

  rows.slice(headerIndex + 1).forEach((row, offset) => {
    if (row.every((cell) => cell.trim().length === 0)) return;
    const sourceRow = headerIndex + offset + 2;
    const date = normalizeCalendarDate(row[indexes['西元日期']] ?? '');
    if (!date) throw new OfficialHolidayCsvError(`CSV 第 ${sourceRow} 列的西元日期格式無效，未執行匯入。`);
    years.add(Number(date.slice(0, 4)));

    const isHoliday = (row[indexes['是否放假']] ?? '').trim() === '2';
    const note = (row[indexes['備註']] ?? '').trim();
    if (!isHoliday || !note) return;
    if (note.length > 100) {
      throw new OfficialHolidayCsvError(`CSV 第 ${sourceRow} 列的備註超過 100 字，未執行匯入。`);
    }

    const existing = holidayByDate.get(date);
    if (existing && existing.holidayName !== note) {
      throw new OfficialHolidayCsvError(`CSV 日期 ${date} 有不同備註，無法判定唯一假日名稱，未執行匯入。`);
    }
    holidayByDate.set(date, { holidayDate: date, holidayName: note });
  });

  if (years.size !== 1) {
    throw new OfficialHolidayCsvError(years.size === 0
      ? 'CSV 無法判定資料年度，未執行匯入。'
      : 'CSV 含有混合年度日期，未執行匯入。');
  }

  return {
    year: [...years][0],
    holidays: [...holidayByDate.values()].sort((left, right) => left.holidayDate.localeCompare(right.holidayDate)),
  };
}
