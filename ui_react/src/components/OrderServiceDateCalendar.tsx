import { useEffect, useState, type FC } from 'react';
import { holidayClient } from '../api/scheduling/holiday_client';

interface Props {
  month: string;
  onMonthChange: (month: string) => void;
  selectedDates: readonly string[];
  isDateDisabled: (date: string) => boolean;
  onToggle: (date: string) => void;
  hint: string;
  dayDetails?: (date: string) => { holidayName?: string | null; rest?: boolean; laterSegment?: boolean };
}

// The same case calendar is used before service and for audited corrections after completion.
export const OrderServiceDateCalendar: FC<Props> = ({ month, onMonthChange, selectedDates, isDateDisabled, onToggle, hint, dayDetails }) => {
  const [year, monthNumber] = month.split('-').map(Number);
  const [holidayNames, setHolidayNames] = useState<Record<string, string>>({});
  const [holidayLoading, setHolidayLoading] = useState(true);
  const [holidayError, setHolidayError] = useState<string | null>(null);
  const [holidayReload, setHolidayReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setHolidayNames({});
    setHolidayLoading(true);
    setHolidayError(null);
    const lastDay = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
    void holidayClient.query({ from_date: `${month}-01`, to_date: `${month}-${lastDay}` }, { signal: controller.signal })
      .then(calendar => {
        if (!controller.signal.aborted) setHolidayNames(Object.fromEntries(calendar.holidays.map(holiday => [holiday.holiday_date, holiday.holiday_name])));
      })
      .catch(error => {
        if (!controller.signal.aborted) setHolidayError(error instanceof Error ? error.message : '無法讀取國定假日。');
      })
      .finally(() => { if (!controller.signal.aborted) setHolidayLoading(false); });
    return () => controller.abort();
  }, [month, year, monthNumber, holidayReload]);

  return <div className="service-calendar-workbench-layout">
    <div className="calendar-matrix-card">
      <div className="calendar-month-header">
        <h3>{year} 年 {monthNumber} 月</h3>
        <div className="order-case-action-row">{[-1, 1].map(delta => <button type="button" key={delta} aria-label={delta < 0 ? '上一個月' : '下一個月'} onClick={() => {
          const next = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
          onMonthChange(`${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}`);
        }}>{delta < 0 ? '‹' : '›'}</button>)}</div>
      </div>
      {holidayLoading && <small role="status">正在讀取當月國定假日…</small>}
      {holidayError && <div role="alert">國定假日標示載入失敗：{holidayError} <button type="button" onClick={() => setHolidayReload(value => value + 1)}>重新讀取假日</button></div>}
      <div className="calendar-days-grid" role="group" aria-label="服務日期月曆" data-surface-id="orders.date.service-date-selection">
        {['日', '一', '二', '三', '四', '五', '六'].map(weekday => <span key={weekday} className="service-date-weekday" aria-hidden="true">{weekday}</span>)}
        {Array.from({ length: new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() }, (_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
        {Array.from({ length: new Date(Date.UTC(year, monthNumber, 0)).getUTCDate() }, (_, index) => `${month}-${String(index + 1).padStart(2, '0')}`).map(date => {
          const selected = selectedDates.includes(date);
          const details = dayDetails?.(date);
          const holidayName = holidayNames[date];
          return <button key={date} data-control-id="orders.date.service-date-select" type="button" aria-label={`服務日期 ${date}`} aria-pressed={selected}
            title={`${date}${holidayName ? ` ${holidayName}` : details?.rest ? ' 建議休假' : ''}${selected ? '（已選服務日）' : ''}`}
            className={`calendar-date-cell${selected ? ' selected' : ''}${selected && details?.laterSegment ? ' later-segment' : ''}`}
            disabled={isDateDisabled(date)} onClick={() => onToggle(date)}>
            <time dateTime={date} title={date}>{Number(date.slice(8))}</time>
            {holidayName && <small className="service-date-holiday" aria-label={holidayName} title={holidayName}>{holidayName}</small>}
            {!holidayName && details?.rest && !selected && <small>休</small>}
          </button>;
        })}
      </div>
      <small className="service-date-calendar-hint">{hint}</small>
    </div>
  </div>;
};
