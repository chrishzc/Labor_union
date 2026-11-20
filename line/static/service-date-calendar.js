export const calendarWeekdays = ['日', '一', '二', '三', '四', '五', '六'];

const occupancyLabels = new Map([
  ['official_workday', '已有排班'],
  ['historical_reservation', '服務檔期'],
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

export function shiftCalendarDate(date, delta) {
  const day = new Date(`${date}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + delta);
  return day.toISOString().slice(0, 10);
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

const taipeiDay = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit' });
const taipeiClock = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Taipei', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

export function calendarServicePeriod(start, end) {
  if (!start || !end) return null;
  const startAt = new Date(start);
  const endAt = new Date(end);
  if (!Number.isFinite(startAt.valueOf()) || !Number.isFinite(endAt.valueOf()) || endAt <= startAt) return null;
  const startDate = taipeiDay.format(startAt);
  const endDate = taipeiDay.format(endAt);
  const startTime = taipeiClock.format(startAt);
  const endTime = taipeiClock.format(endAt);
  const crossDay = endDate !== startDate;
  return {
    summary: `${startTime}–${crossDay ? '跨日 ' : ''}${endTime}`,
    full: `${startDate} ${startTime} 至 ${endDate} ${endTime}`,
    lastOccupiedDate: taipeiDay.format(new Date(endAt.valueOf() - 1)),
  };
}

export function calendarOccupancyDetailsByDate(entries, { caseNo, actualStartDate, firstDate, lastDate }) {
  const days = new Map();
  for (const entry of entries) {
    const label = occupancyLabels.get(entry.kind);
    if (!label || entry.caseNo === caseNo) continue;
    const hasService = entry.kind === 'official_workday' || entry.kind === 'historical_reservation';
    const advisory = hasService && (actualStartDate == null || entry.actualStartDate == null);
    const period = calendarServicePeriod(entry.serviceStartAt, entry.serviceEndAt);
    const dayLabel = advisory ? '歷史／暫定' : label;
    const lastOccupiedDate = period?.lastOccupiedDate ?? entry.date;
    for (let day = entry.date < firstDate ? firstDate : entry.date; day <= lastDate && day <= lastOccupiedDate; day = shiftCalendarDate(day, 1)) {
      const items = days.get(day) ?? [];
      const detail = { label: dayLabel, caseNo: entry.caseNo, period, continues: day !== entry.date };
      if (items.some(item => item.caseNo === detail.caseNo && item.label === detail.label && item.period?.full === period?.full)) continue;
      items.push(detail);
      days.set(day, items);
    }
  }
  return days;
}
