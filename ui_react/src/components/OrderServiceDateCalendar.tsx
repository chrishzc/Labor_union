import type { FC } from 'react';

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
  return <div className="service-calendar-workbench-layout">
    <div className="calendar-matrix-card">
      <div className="calendar-month-header">
        <h3>{year} 年 {monthNumber} 月</h3>
        <div className="order-case-action-row">{[-1, 1].map(delta => <button type="button" key={delta} aria-label={delta < 0 ? '上一個月' : '下一個月'} onClick={() => {
          const next = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
          onMonthChange(`${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}`);
        }}>{delta < 0 ? '‹' : '›'}</button>)}</div>
      </div>
      <div className="calendar-days-grid" role="group" aria-label="服務日期月曆" data-surface-id="orders.date.service-date-selection">
        {['日', '一', '二', '三', '四', '五', '六'].map(weekday => <span key={weekday} className="service-date-weekday" aria-hidden="true">{weekday}</span>)}
        {Array.from({ length: new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() }, (_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
        {Array.from({ length: new Date(Date.UTC(year, monthNumber, 0)).getUTCDate() }, (_, index) => `${month}-${String(index + 1).padStart(2, '0')}`).map(date => {
          const selected = selectedDates.includes(date);
          const details = dayDetails?.(date);
          return <button key={date} data-control-id="orders.date.service-date-select" type="button" aria-label={`服務日期 ${date}`} aria-pressed={selected}
            title={`${date}${details?.holidayName ? ` ${details.holidayName}` : details?.rest ? ' 建議休假' : ''}`}
            className={`calendar-date-cell${selected ? ' selected' : ''}${selected && details?.laterSegment ? ' later-segment' : ''}`}
            disabled={isDateDisabled(date)} onClick={() => onToggle(date)}>
            <time dateTime={date} title={date}>{Number(date.slice(8))}</time>
            {details?.holidayName && <small className="service-date-holiday" aria-label={details.holidayName}>假日</small>}
            {!details?.holidayName && details?.rest && !selected && <small>休</small>}
          </button>;
        })}
      </div>
      <small className="service-date-calendar-hint">{hint}</small>
    </div>
  </div>;
};
