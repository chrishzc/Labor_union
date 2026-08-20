/**
 * File: data_import_no_fake_mutation.test.tsx
 * Description: 驗證匯入結果頁沒有upload／Apply，其他匯入family控制皆原生鎖定且無假成功。
 */
import { fireEvent, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataImportPage } from '../pages/DataImportPage';

const LOCKED_CONTROL_IDS = [
  'imports.hcm-historical.preview',
  'imports.hcm-historical.apply',
  'imports.client-beclass.preview',
  'imports.client-beclass.apply',
  'imports.staff-historical.preview',
  'imports.staff-historical.apply',
  'imports.historic-orders.preview',
  'imports.historic-orders.apply',
  'imports.bank-statements.preview',
  'imports.bank-statements.apply',
] as const;

describe('DataImportPage zero fake mutation gate', () => {
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
  const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => false);

  beforeEach(() => {
    alertSpy.mockClear();
    confirmSpy.mockClear();
  });

  it('keeps every out-of-wave card control natively disabled with no handler effect', () => {
    render(<DataImportPage />);
    for (const id of LOCKED_CONTROL_IDS) {
      const control = document.querySelector(`[data-control-id="${id}"]`);
      expect(control, id).not.toBeNull();
      expect(control as HTMLButtonElement).toBeDisabled();
      fireEvent.click(control as HTMLButtonElement);
    }
    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('removes the superseded HCM file Preview and Apply controls', () => {
    render(<DataImportPage />);
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeNull();
    expect(document.querySelector('[data-control-id="imports.hcm-current.apply"]')).toBeNull();
    expect(alertSpy).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});
