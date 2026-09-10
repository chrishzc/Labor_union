/** Download the existing authenticated, archived accounts-payable workbook. */
import { sessionClient } from '../auth/session_client';

export const accountsPayableExportClient = {
  async download(targetMonth: string, signal?: AbortSignal): Promise<{ blob: Blob; filename: string }> {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(targetMonth)) throw new Error('月份格式不正確。');
    const token = sessionClient.getToken();
    if (!token) throw Object.assign(new Error('請先登入。'), { status: 401 });
    const response = await fetch(`/api/v1/finance-reports/accounts-payable/export?target_month=${targetMonth}`, {
      headers: { Authorization: `Bearer ${token}` }, signal,
    });
    if (!response.ok) throw Object.assign(new Error('應付帳款下載失敗。'), { status: response.status });
    if (!response.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
      throw new Error('下載格式不正確。');
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error('下載檔案沒有內容。');
    const candidate = response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i)?.[1];
    const filename = candidate && /^[\w.-]+\.xlsx$/i.test(candidate)
      ? candidate : `accounts-payable-${targetMonth}.xlsx`;
    return { blob, filename };
  },
};
