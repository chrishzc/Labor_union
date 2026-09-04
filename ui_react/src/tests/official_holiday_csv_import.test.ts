/**
 * File: official_holiday_csv_import.test.ts
 * Description: 驗證政府辦公日曆 CSV 的必要欄位、年度與假日篩選邊界。
 */

import { describe, expect, it } from 'vitest';
import {
  OfficialHolidayCsvError,
  parseOfficialHolidayCsv,
} from '../adapters/scheduling/official_holiday_csv_import';

describe('official holiday CSV import parser', () => {
  it('以備註建立官方假日，略過備註空白的週末列', () => {
    const preview = parseOfficialHolidayCsv([
      '\uFEFF西元日期,星期,是否放假,備註',
      '20260217,二,2,去敏春節假日',
      '20260221,六,2,',
      '20260223,一,0,補班日',
      '20260928,一,2,去敏教師節假日',
    ].join('\r\n'));

    expect(preview.year).toBe(2026);
    expect(preview.holidays).toEqual([
      { holidayDate: '2026-02-17', holidayName: '去敏春節假日' },
      { holidayDate: '2026-09-28', holidayName: '去敏教師節假日' },
    ]);
  });

  it('缺少必要欄位時 fail closed', () => {
    expect(() => parseOfficialHolidayCsv([
      '西元日期,星期,備註',
      '20260217,二,去敏春節假日',
    ].join('\n'))).toThrow(OfficialHolidayCsvError);
  });

  it('混合年度時 fail closed', () => {
    expect(() => parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20261231,四,2,去敏年末假日',
      '20270101,五,2,去敏年初假日',
    ].join('\n'))).toThrow('混合年度');
  });

  it('支援政府 CSV 常見的 quoted 欄位與逗號', () => {
    const preview = parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20261010,六,2,"去敏紀念日,補充說明"',
    ].join('\n'));

    expect(preview.holidays).toEqual([
      { holidayDate: '2026-10-10', holidayName: '去敏紀念日,補充說明' },
    ]);
  });
});
