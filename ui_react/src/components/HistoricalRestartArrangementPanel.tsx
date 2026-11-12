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
  if (staff.length === 0) return <p role="alert">歷史案件缺少既定月嫂，請先核對配對資料。</p>;
  if (staff.length === 1) return <p>選定服務日期由 {identity.label(staff[0].staff_id, staff[0].staff_name)} 承接。</p>;

  return <section className="historical-schedule-allocation" aria-label="月嫂分配">
    <h3>月嫂分配</h3>
    <p>請在每位月嫂下方選日期，每位各安排一段連續服務日。</p>
    {[...staff].sort((a, b) => identity.compare(a.staff_id, b.staff_id)).map((person, index) => {
      const label = identity.label(person.staff_id, person.staff_name);
      return <fieldset key={person.staff_id} disabled={disabled}>
        <legend>{label}</legend>
        <div className="historical-schedule-date-choices">
          {[...dates].sort().map(date => {
            const selected = allocation[date] === person.staff_id;
            return <button type="button" key={date}
              className={`calendar-date-cell${selected ? ' selected' : ''}${index % 2 ? ' later-segment' : ''}`}
              aria-label={`${label} ${date}`} aria-pressed={selected}
              disabled={Boolean(allocation[date] && !selected)}
              onClick={() => onSelect(date, person.staff_id)}
            >{date.slice(5).replace('-', '/')}</button>;
          })}
        </div>
      </fieldset>;
    })}
  </section>;
}
