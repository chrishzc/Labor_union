import { expect, it } from 'vitest';
import { NAV_ITEMS, PAGE_SECTION_MAP } from '../../../../../../../components/MasterLayout';

it('exposes one file-settings entry under audit without replacing storage retention', () => {
  expect(NAV_ITEMS.filter(item => item.id === 'file-settings')).toEqual([
    expect.objectContaining({ label: '檔案設定', section: 'audit' }),
  ]);
  expect(PAGE_SECTION_MAP['file-settings']).toBe('audit');
  expect(NAV_ITEMS.some(item => item.id === 'storage-management')).toBe(true);
});
