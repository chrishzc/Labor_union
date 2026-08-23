/**
 * File: navigation.ts
 * Description: 定義系統 canonical 導航型別、分區映射與側邊欄項目。
 */

export type SectionType = 'operations' | 'line' | 'finance' | 'audit';

export type PageType =
  | 'order-tracker'
  | 'orders'
  | 'scheduling'
  | 'staff'
  | 'data-import'
  | 'reports'
  | 'line-management'
  | 'finance'
  | 'anomalies'
  | 'data-browser'
  | 'account-management';

export const PAGE_SECTION_MAP: Record<PageType, SectionType> = {
  'order-tracker': 'operations',
  'orders': 'operations',
  'scheduling': 'operations',
  'staff': 'operations',
  'data-import': 'operations',
  'reports': 'operations',

  'line-management': 'line',

  'finance': 'finance',

  'anomalies': 'audit',
  'data-browser': 'audit',
  'account-management': 'audit',
};

export interface NavItem {
  id: PageType;
  icon: string;
  label: string;
  section: SectionType;
}

export const NAV_ITEMS: NavItem[] = [
  // Operations Section
  { id: 'order-tracker', icon: '📌', label: '待辦看板', section: 'operations' },
  { id: 'orders', icon: '📦', label: '訂單管理', section: 'operations' },
  { id: 'scheduling', icon: '📅', label: '排班日曆', section: 'operations' },
  { id: 'staff', icon: '👩‍🍼', label: '月嫂名冊', section: 'operations' },
  { id: 'data-import', icon: '📥', label: '資料匯入', section: 'operations' },
  { id: 'reports', icon: '📊', label: '營運報表', section: 'operations' },

  // LINE Section
  { id: 'line-management', icon: '💬', label: 'LINE 作業中心', section: 'line' },

  // Finance Section
  { id: 'finance', icon: '💰', label: '帳務中心', section: 'finance' },

  // Audit & System Section
  { id: 'anomalies', icon: '⚠️', label: '異常審核', section: 'audit' },
  { id: 'data-browser', icon: '🔍', label: '數據瀏覽', section: 'audit' },
  { id: 'account-management', icon: '👤', label: '帳號權限', section: 'audit' },
];
