import { useId } from 'react';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import type {
  HistoricalArrangementSegmentPayload,
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';

type Staff = ServiceDateConfirmationQueryView['bound_staff'];
type Allocation = Record<string, number>;

export function historicalScheduleSegments(
  staff: Staff, dates: string[], allocation: Allocation,
): HistoricalArrangementSegmentPayload[] | null {
  if (dates.length === 0 || staff.length === 0) return null;
  if (staff.length === 1) return [{ staff_id: staff[0].staff_id, service_dates: [...dates].sort() }];

  const segments: HistoricalArrangementSegmentPayload[] = [];
  const assigned = new Set<number>();
  for (const date of [...dates].sort()) {
    const staffId = allocation[date];
    if (!staff.some(person => person.staff_id === staffId)) return null;
    const previous = segments.at(-1);
    if (previous?.staff_id === staffId) previous.service_dates.push(date);
    else {
      if (assigned.has(staffId)) return null;
      assigned.add(staffId);
      segments.push({ staff_id: staffId, service_dates: [date] });
    }
  }
  return segments.length === staff.length ? segments : null;
}

interface Props {
  staff: Staff;
  dates: string[];
  allocation: Allocation;
  disabled: boolean;
  onSelect: (date: string, staffId: number) => void;
}

export function HistoricalRestartArrangementPanel({ staff, dates, allocation, disabled, onSelect }: Props) {
  const identity = useStaffIdentityLabels();
  const idPrefix = useId();
  if (staff.length === 0) return <p role="alert">歷史案件缺少既定月嫂，請先核對配對資料。</p>;
  const multiple = staff.length > 1;

  return <section className="historical-schedule-allocation" aria-label="月嫂分配">
    <h3>月嫂分配</h3>
    {multiple && <p>每位月嫂選一段連續的服務日。</p>}
    {[...staff].sort((a, b) => identity.compare(a.staff_id, b.staff_id)).map((person, index) => {
      const label = identity.label(person.staff_id, person.staff_name);
      const labelId = `${idPrefix}-${person.staff_id}`;
      return <fieldset key={person.staff_id} aria-labelledby={labelId} className="schedule-allocation-person" disabled={disabled}>
        <div className="schedule-allocation-person-heading">
          <p id={labelId}>{!multiple && '承接月嫂 '}<strong>{label}</strong></p>
        </div>
        {multiple && <div className="historical-schedule-date-choices">
          {[...dates].sort().map(date => {
            const selected = allocation[date] === person.staff_id;
            return <button type="button" key={date}
              className={`calendar-date-cell${selected ? ' selected' : ''}${index % 2 ? ' later-segment' : ''}`}
              aria-label={`${label} ${date}`} aria-pressed={selected}
              disabled={Boolean(allocation[date] && !selected)}
              onClick={() => onSelect(date, person.staff_id)}
            >{date.slice(5).replace('-', '/')}</button>;
          })}
        </div>}
      </fieldset>;
    })}
  </section>;
}
