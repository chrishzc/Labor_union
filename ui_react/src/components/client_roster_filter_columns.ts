import type { ClientRegistryColumnFilter, ClientRegistryFilterField, ClientRegistryFilterOperator } from '../api/client_registry/client_registry_schemas';

export interface RosterFilterColumn { field: ClientRegistryFilterField; label: string; kind: 'text' | 'number' | 'date' | 'boolean' }
export const rosterFilterColumns: RosterFilterColumn[] = [
  { field: 'case_no', label: '案件編號', kind: 'text' },
  { field: 'name', label: '客戶姓名', kind: 'text' },
  { field: 'phone', label: '電話', kind: 'text' },
  { field: 'district', label: '行政區', kind: 'text' },
  { field: 'multi_birth_count', label: 'BeClass 胎數', kind: 'text' },
  { field: 'service_days', label: '服務天數', kind: 'number' },
  { field: 'service_type', label: '服務方式', kind: 'text' },
  { field: 'requires_cooking', label: '下廚需求', kind: 'boolean' },
  { field: 'planned_start_date', label: '預計服務日期', kind: 'date' },
  { field: 'order_status', label: '案件／訂單狀態', kind: 'text' },
  { field: 'deposit_due_date', label: '定金應繳日', kind: 'date' },
  { field: 'first_due_date', label: '第一期應繳日', kind: 'date' },
  { field: 'second_due_date', label: '第二期應繳日', kind: 'date' },
  { field: 'staff_payment_due_date', label: '訂單月嫂應付日', kind: 'date' },
  { field: 'subsidy_return_due_date', label: '客戶補助退還日', kind: 'date' },
];
export const rosterFilterValueLabel = (column: RosterFilterColumn, value: string | null) => value === null ? '空白／未登錄' : column.kind === 'boolean' ? value === 'true' ? '需要' : '不需要' : value;
export const operatorLabels: Record<ClientRegistryFilterOperator, string> = {
  in: '勾選值', not_in: '排除值', contains: '包含', starts_with: '開頭是', equals: '等於',
  gt: '大於', lt: '小於', between: '介於', blank: '空白／未登錄',
};
export function rosterFilterSummary(predicate: ClientRegistryColumnFilter) {
  const column = rosterFilterColumns.find((item) => item.field === predicate.field)!;
  const values = predicate.values.map((value) => rosterFilterValueLabel(column, value));
  if (predicate.operator === 'in' && !values.length) return `${column.label}：未選取任何值`;
  return `${column.label}：${operatorLabels[predicate.operator]}${values.length ? ` ${values.slice(0, 3).join('、')}${values.length > 3 ? ` 等 ${values.length} 項` : ''}` : ''}`;
}
