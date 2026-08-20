/**
 * File: data_browser_query_contract_fixtures.ts
 * Description: 提供 masked Data Browser strict contract 測試資料。
 */
import type { DataBrowserMaskedPage } from '../../../api/data_browser/data_browser_query_schemas';

export const VALID_DATA_BROWSER_PAGE: DataBrowserMaskedPage = {
  source_id: 'orders',
  items: [
    {
      source_id: 'orders',
      row_identity: '115000001',
      display_title: '訂單 115000001',
      summary_cells: [
        { field_id: 'status', label: '訂單狀態', value: '服務中', presentation: 'status' },
        { field_id: 'start_date', label: '服務開始', value: '2026-08-01', presentation: 'date' },
      ],
      detail_cells: [
        { field_id: 'status', label: '訂單狀態', value: '服務中', presentation: 'status' },
        { field_id: 'start_date', label: '服務開始', value: '2026-08-01', presentation: 'date' },
        { field_id: 'end_date', label: '服務結束', value: '2026-08-31', presentation: 'date' },
      ],
      recorded_at: '2026-08-17T10:00:00+08:00',
      source_actor_label: null,
      version_identity: 'a'.repeat(64),
    },
  ],
  next_cursor: null,
};

export const VALID_DATA_BROWSER_ENVELOPE = {
  success: true,
  message: '成功取得去敏資料來源',
  data: VALID_DATA_BROWSER_PAGE,
  error: null,
};
