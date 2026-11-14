const taipeiCalendar = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Taipei',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export function taipeiDate(instant = new Date()): string {
  return taipeiCalendar.format(instant);
}

const taipeiDateTime = new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei',
  dateStyle: 'medium',
  timeStyle: 'medium',
  hourCycle: 'h23',
});

export function formatTaipeiDateTime(value: string, assumeUtc = false): string {
  if (!/^[\d-]+[T ]\d{2}:\d{2}/.test(value)) return value;
  const hasOffset = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  if (!hasOffset && !assumeUtc) return value;
  const instant = new Date(value.replace(' ', 'T') + (hasOffset ? '' : 'Z'));
  return Number.isNaN(instant.getTime()) ? value : taipeiDateTime.format(instant);
}
