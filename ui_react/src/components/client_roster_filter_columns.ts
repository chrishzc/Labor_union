/**
 * File: client_roster_filter_columns.ts
 * Description: 定義客戶名冊表格 19 個欄位設定、篩選中繼資料與條件摘要格式化工具。
 */
import type {
  ClientRegistryColumnFilter,
  ClientRegistryFilterField,
  ClientRegistryFilterOperator,
  ClientRegistrySortBy,
} from '../api/client_registry/client_registry_schemas';
import type { RosterColumnDefinition } from './RosterTableLayout';

export interface RosterFilterColumn { field: ClientRegistryFilterField; label: string; kind: 'text' | 'number' | 'date' | 'boolean' }
export const rosterFilterColumns: RosterFilterColumn[] = [
  { field: 'case_no', label: '案件編號', kind: 'text' },
  { field: 'name', label: '客戶姓名', kind: 'text' },
  { field: 'identity_status', label: '補助身分', kind: 'text' },
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
  { field: 'subsidy_return_due_date', label: '客戶補助退還日', kind: 'date' },
];

export type ClientRosterColumnId =
  | 'case_no'
  | 'virtual_account'
  | 'name'
  | 'identity_status'
  | 'phone'
  | 'district'
  | 'multi_birth_count'
  | 'service_days'
  | 'service_type'
  | 'requires_cooking'
  | 'planned_start_date'
  | 'order_status'
  | 'deposit_due_date'
  | 'first_due_date'
  | 'second_due_date'
  | 'staff_obligation_due_date'
  | 'subsidy_return_due_date'
  | 'estimated_self_funded_staff_due_date'
  | 'claim_application_ym';

export interface ClientRosterColumnConfig extends RosterColumnDefinition<ClientRosterColumnId> {
  group: '基本識別' | '服務與訂單條件' | '帳務與補助日期';
  filterField?: ClientRegistryFilterField;
  sortBy?: ClientRegistrySortBy;
  headerTitle?: string;
}

export const clientRosterColumns: readonly ClientRosterColumnConfig[] = [
  { id: 'case_no', label: '案件編號', group: '基本識別', defaultWidth: 120, locked: true, defaultFrozen: true, filterField: 'case_no', sortBy: 'case_no' },
  { id: 'virtual_account', label: '虛擬帳號', group: '基本識別', defaultWidth: 150 },
  { id: 'name', label: '客戶姓名', group: '基本識別', defaultWidth: 110, filterField: 'name', sortBy: 'customer_name' },
  { id: 'identity_status', label: '補助身分', group: '基本識別', defaultWidth: 115, filterField: 'identity_status' },
  { id: 'phone', label: '電話', group: '基本識別', defaultWidth: 120, filterField: 'phone' },
  { id: 'district', label: '行政區', group: '基本識別', defaultWidth: 95, filterField: 'district' },
  { id: 'multi_birth_count', label: 'BeClass 胎數', group: '服務與訂單條件', defaultWidth: 125, filterField: 'multi_birth_count' },
  { id: 'service_days', label: '服務天數', group: '服務與訂單條件', defaultWidth: 105, filterField: 'service_days', sortBy: 'service_days' },
  { id: 'service_type', label: '服務方式', group: '服務與訂單條件', defaultWidth: 120, filterField: 'service_type' },
  { id: 'requires_cooking', label: '下廚需求', group: '服務與訂單條件', defaultWidth: 105, filterField: 'requires_cooking' },
  { id: 'planned_start_date', label: '預計服務日期', group: '服務與訂單條件', defaultWidth: 135, filterField: 'planned_start_date', sortBy: 'expected_start_date' },
  { id: 'order_status', label: '案件／訂單狀態', group: '服務與訂單條件', defaultWidth: 145, filterField: 'order_status' },
  { id: 'deposit_due_date', label: '定金應繳日', group: '帳務與補助日期', defaultWidth: 125, filterField: 'deposit_due_date', headerTitle: 'client_obligations.due_date（deposit）' },
  { id: 'first_due_date', label: '第一期應繳日', group: '帳務與補助日期', defaultWidth: 130, filterField: 'first_due_date', headerTitle: 'client_obligations.due_date（first）' },
  { id: 'second_due_date', label: '第二期應繳日', group: '帳務與補助日期', defaultWidth: 130, filterField: 'second_due_date', headerTitle: 'client_obligations.due_date（second）' },
  { id: 'staff_obligation_due_date', label: '月嫂義務應付日', group: '帳務與補助日期', defaultWidth: 175, headerTitle: 'staff_obligations.due_date' },
  { id: 'subsidy_return_due_date', label: '客戶補助退還日', group: '帳務與補助日期', defaultWidth: 145, filterField: 'subsidy_return_due_date', headerTitle: 'client_obligations.due_date（subsidy_return）' },
  { id: 'estimated_self_funded_staff_due_date', label: '薪資預估日期', group: '帳務與補助日期', defaultWidth: 125, headerTitle: '自費薪資以實際或預定服務結束日估算，為次月 15 日。' },
  { id: 'claim_application_ym', label: '補助預計申請年月', group: '帳務與補助日期', defaultWidth: 145, headerTitle: '依實際服務結束日估算，尚無實際日期時使用預定結束日。' },
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
