import { useId, useState } from 'react';
import { OrderServiceDateCalendar } from './OrderServiceDateCalendar';
import { useStaffIdentityLabels } from './StaffIdentityProvider';

export interface CaregiverScheduleBlock {
  key: number;
  staffId: number;
  name?: string;
}

export interface CaregiverScheduleManagement {
  options: { staffId: number; name?: string }[];
  onAdd: (staffId: number) => void;
  onRemove?: (key: number) => void;
  canRemove?: (key: number) => boolean;
  limit: number;
}

interface Props {
  blocks: CaregiverScheduleBlock[];
  dates: string[];
  allocation: Record<string, number>;
  onSelect: (date: string, key: number) => void;
  management?: CaregiverScheduleManagement;
}

export function OrderCaregiverScheduleCalendars({ blocks, dates, allocation, onSelect, management }: Props) {
  const staff = useStaffIdentityLabels();
  const headingId = useId();
  const [adding, setAdding] = useState(false);
  const [months, setMonths] = useState<Record<number, string>>({});
  const sorted = [...dates].sort();
  const firstMonth = sorted[0]?.slice(0, 7);
  const lastMonth = sorted.at(-1)?.slice(0, 7);
  const allowedDates = new Set(dates);
  const options = management?.options.filter(person => !blocks.some(block => block.staffId === person.staffId))
    .sort((a, b) => staff.compare(a.staffId, b.staffId)) ?? [];
  const label = (block: CaregiverScheduleBlock) => staff.label(block.staffId, block.name);
  const missing = dates.filter(date => allocation[date] === undefined).length;

  return <section className="caregiver-schedule-calendars" aria-labelledby={headingId}>
    <header>
      <div>
        <h4 id={headingId}>月嫂分配</h4>
        <p>在各月嫂的月曆點選服務日。點選已有安排的日期，會將當天轉給這位月嫂。</p>
      </div>
      {management && <button type="button" disabled={adding || blocks.length >= management.limit || !options.length}
        onClick={() => setAdding(true)}>＋ 新增月嫂</button>}
    </header>
    <p aria-live="polite">已分配 {dates.length - missing}／{dates.length} 日 · {blocks.length} 個月嫂區塊
      {missing > 0 && ` · 尚有 ${missing} 日未分配`}</p>
    {!dates.length && <p>目前沒有可分配的服務日。</p>}
    <div className="caregiver-schedule-blocks">
      {blocks.map(block => {
        const selected = sorted.filter(date => allocation[date] === block.key);
        const month = months[block.key] ?? firstMonth;
        const visibleMonth = month && firstMonth && lastMonth ? [firstMonth, month, lastMonth].sort()[1] : null;
        const duplicates = blocks.filter(item => item.staffId === block.staffId);
        const name = label(block) + (duplicates.length > 1 ? ` · 區段 ${duplicates.indexOf(block) + 1}` : '');
        return <section key={block.key} className="caregiver-schedule-block" aria-label={name}>
          <header><h4>{name}</h4><span>負責 {selected.length} 日</span>
            {management?.onRemove && (management.canRemove?.(block.key) ?? true) &&
              <button type="button" onClick={() => management.onRemove?.(block.key)}>移除該月嫂</button>}
          </header>
          {visibleMonth && firstMonth && lastMonth && <OrderServiceDateCalendar month={visibleMonth}
            onMonthChange={value => setMonths(current => ({ ...current, [block.key]: value }))}
            selectedDates={selected} showHolidays={false} monthRange={[firstMonth, lastMonth]}
            isDateDisabled={date => !allowedDates.has(date)}
            dayLabel={date => {
              const owner = blocks.find(item => item.key === allocation[date]);
              const status = !allowedDates.has(date) ? '不可分配' : owner?.key === block.key ? '由此區塊負責'
                : owner ? `目前由 ${label(owner)} 負責` : '尚未分配';
              return `服務日期 ${date}，${status}`;
            }}
            onToggle={date => onSelect(date, block.key)} />}
        </section>;
      })}
      {adding && management && <section className="caregiver-schedule-block" aria-label="新增月嫂區塊">
        <label>選擇月嫂 <select autoFocus value="" onChange={event => {
          if (!event.target.value) return;
          management.onAdd(Number(event.target.value));
          setAdding(false);
        }}>
          <option value="">請選擇月嫂</option>
          {options.map(person => <option key={person.staffId} value={person.staffId}>{staff.label(person.staffId, person.name)}</option>)}
        </select></label>
        <button type="button" onClick={() => setAdding(false)}>取消新增</button>
      </section>}
    </div>
  </section>;
}
