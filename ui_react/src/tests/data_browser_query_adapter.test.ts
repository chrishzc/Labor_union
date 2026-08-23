/**
 * File: data_browser_query_adapter.test.ts
 * Description: 驗證 Data Browser adapter 不推導 raw business facts。
 */
import { describe, expect, it } from 'vitest';
import { adaptDataBrowserPage, DATA_BROWSER_TABS } from '../adapters/data_browser/data_browser_query_adapter';
import { VALID_DATA_BROWSER_PAGE } from './fixtures/data_browser/data_browser_query_contract_fixtures';

describe('Data Browser query adapter', () => {
  it('freezes six tab IDs to six canonical sources', () => {
    expect(DATA_BROWSER_TABS.map((tab) => tab.sourceId)).toEqual([
      'orders', 'clients', 'staff', 'beclass_intake', 'hcm_review', 'bank_facts',
    ]);
  });

  it('maps typed cells and renders an absent optional actor label neutrally', () => {
    const view = adaptDataBrowserPage(VALID_DATA_BROWSER_PAGE);
    expect(view.rows[0].summary[0]).toEqual({ id: 'status', label: '訂單狀態', value: '服務中' });
    expect(view.rows[0].actorLabel).toBe('—');
  });

  it('rejects row source mismatch and duplicate cells', () => {
    expect(() => adaptDataBrowserPage({
      ...VALID_DATA_BROWSER_PAGE,
      items: [{ ...VALID_DATA_BROWSER_PAGE.items[0], source_id: 'clients' }],
    })).toThrow('data_browser_row_identity_mismatch');
    expect(() => adaptDataBrowserPage({
      ...VALID_DATA_BROWSER_PAGE,
      items: [{
        ...VALID_DATA_BROWSER_PAGE.items[0],
        summary_cells: [
          VALID_DATA_BROWSER_PAGE.items[0].summary_cells[0],
          VALID_DATA_BROWSER_PAGE.items[0].summary_cells[0],
        ],
      }],
    })).toThrow('data_browser_duplicate_cell');
  });
});
