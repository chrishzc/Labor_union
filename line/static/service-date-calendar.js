export const calendarWeekdays = ['日', '一', '二', '三', '四', '五', '六'];

const occupancyLabels = new Map([
  ['official_workday', '已有排班'],
  ['waiting_deposit_service', '檔期保留'],
  ['staff_unavailability', '不可服務'],
]);

export function buildCalendarMonth(month) {
  const [year, monthNumber] = month.split('-').map(Number);
  const dayCount = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  return {
    year,
    monthNumber,
    leadingDays: new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay(),
    firstDate: `${month}-01`,
    lastDate: `${month}-${dayCount}`,
    dates: Array.from({ length: dayCount }, (_, index) => `${month}-${String(index + 1).padStart(2, '0')}`),
  };
}

export function shiftCalendarMonth(month, delta) {
  const [year, monthNumber] = month.split('-').map(Number);
  const next = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function calendarOccupancyByDate(entries, caseNo) {
  const days = new Map();
  for (const entry of entries) {
    const label = occupancyLabels.get(entry.kind);
    if (!label || entry.caseNo === caseNo) continue;
    const labels = days.get(entry.date) ?? [];
    if (!labels.includes(label)) labels.push(label);
    days.set(entry.date, labels);
  }
  return days;
}
