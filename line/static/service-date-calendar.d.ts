export const calendarWeekdays: readonly string[];

export function buildCalendarMonth(month: string): {
  year: number;
  monthNumber: number;
  leadingDays: number;
  firstDate: string;
  lastDate: string;
  dates: readonly string[];
};

export function shiftCalendarMonth(month: string, delta: number): string;
export function shiftCalendarDate(date: string, delta: number): string;

export function calendarOccupancyByDate(
  entries: Iterable<{ date: string; caseNo?: string | null; kind: string }>,
  caseNo: string,
): Map<string, string[]>;

export type CalendarServicePeriod = { summary: string; full: string; lastOccupiedDate: string };

export function calendarServicePeriod(start: string | null | undefined, end: string | null | undefined): CalendarServicePeriod | null;

export type CalendarOccupancyDetail = {
  label: string;
  caseNo: string | null;
  period: CalendarServicePeriod | null;
  continues: boolean;
};

export function calendarOccupancyDetailsByDate(
  entries: Iterable<{
    date: string;
    caseNo: string | null;
    kind: string;
    actualStartDate?: string | null;
    serviceStartAt?: string | null;
    serviceEndAt?: string | null;
  }>,
  view: { caseNo: string; actualStartDate?: string | null; firstDate: string; lastDate: string },
): Map<string, CalendarOccupancyDetail[]>;
