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

export function calendarOccupancyByDate(
  entries: Iterable<{ date: string; caseNo?: string | null; kind: string }>,
  caseNo: string,
): Map<string, string[]>;
