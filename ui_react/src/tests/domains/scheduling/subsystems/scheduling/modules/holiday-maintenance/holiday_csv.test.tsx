/**
 * File: holiday_csv.test.tsx
 * Description: 驗證國定假日 CSV 的實際 parser、transport 與 Scheduling UI 邊界。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { createHolidayClient, holidayClient, parseHolidayCsv } from '../../../../../../../api/scheduling/holiday_client';
import * as holidayFlow from '../../../../../../../adapters/scheduling/holiday_flow_adapter';
import { OfficialHolidayCsvImport } from '../../../../../../../components/scheduling/OfficialHolidayCsvImport';
import { HOLIDAY_CALENDAR, HOLIDAY_PREVIEW, HOLIDAY_RECEIPT } from '../../../../../../fixtures/holiday_contract_fixtures';

vi.mock('../../../../../../../adapters/scheduling/holiday_flow_adapter', async (importOriginal) => {
  const actual = await importOriginal<typeof holidayFlow>();
  return { ...actual, previewHolidayFlow: vi.fn(), applyHolidayFlow: vi.fn() };
});

const CSV_HEADER = '西元日期,星期,是否放假,備註';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

function envelope(data: unknown) {
  return { success: true, message: 'ok', data, error: null };
}

function calendarFor(date: string, version: string, holidays: readonly unknown[] = []) {
  return { ...HOLIDAY_CALENDAR, planning_horizon: { from_date: date, to_date: date }, calendar_version: version, holidays };
}

function previewFor(date: string, version: string, fingerprint: string) {
  return {
    ...HOLIDAY_PREVIEW,
    command: { ...HOLIDAY_PREVIEW.command, holiday_date: date, from_date: date, to_date: date, expected_calendar_version: version },
    planning_horizon: { from_date: date, to_date: date },
    calendar_version: version,
    preview_fingerprint: fingerprint,
  };
}

function receiptFor(date: string, previousVersion: string, nextVersion: string, changed = true) {
  return { ...HOLIDAY_RECEIPT, holiday_date: date, changed, previous_calendar_version: previousVersion, resulting_calendar_version: nextVersion, preview_fingerprint: 'f'.repeat(64) };
}

function setSession(): void {
  sessionClient.setSession('holiday-csv-canonical-token', {
    id: 7, username: 'holiday-csv-canonical-admin', display_name: '國定假日測試管理員', role: 'system_admin',
  });
}

describe('canonical holiday maintenance CSV', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    setSession();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('實際 parser 遵守官方 0/2、單一年度、空白週末與壞引號規則', () => {
    const parsed = parseHolidayCsv([
      CSV_HEADER,
      '2026-01-01,四,2,元旦',
      '2026-01-02,五,0,',
      '2026-01-03,六,2,',
    ].join('\n'));
    expect(parsed.year).toBe(2026);
    expect(parsed.rows.map((row) => row.holiday_date)).toEqual(['2026-01-01']);
    expect(parsed.rows[0]?.holiday_name).toBe('元旦');
    expect(parsed.blank_weekend_rows).toBe(1);
    expect(parsed.issues).toEqual([]);

    const mixedYear = parseHolidayCsv([CSV_HEADER, '2026-01-01,四,2,元旦', '2027-01-01,五,2,跨年資料'].join('\n'));
    expect(mixedYear.rows).toHaveLength(1);
    expect(mixedYear.issues.join(' ')).toContain('不是同一年度');

    const malformed = parseHolidayCsv([CSV_HEADER, '2026-01-01,四,2,"未關閉'].join('\n'));
    expect(malformed.rows).toEqual([]);
    expect(malformed.issues.join(' ')).toContain('引號未關閉');
  });

  it('實際 transport 的 preview 零寫入，Apply 每筆 fresh version 並保留既有雙薪事實，部分失敗逐筆回報', async () => {
    const dateOne = '2026-01-01';
    const dateTwo = '2026-02-28';
    const versionOne = 'a'.repeat(64);
    const versionTwo = 'b'.repeat(64);
    const versionThree = 'c'.repeat(64);
    const versionFour = 'd'.repeat(64);
    const existing = { holiday_date: dateOne, holiday_name: '既有名稱', is_double_pay_default: true };
    const p1 = previewFor(dateOne, versionOne, '1'.repeat(64));
    const p2 = previewFor(dateTwo, versionTwo, '2'.repeat(64));
    const freshP1 = previewFor(dateOne, versionThree, '3'.repeat(64));
    const csv = [CSV_HEADER, dateOne + ',四,2,新名稱', dateTwo + ',六,2,補休日'].join('\n');

    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(dateOne, versionOne, [existing]))))
      .mockResolvedValueOnce(jsonResponse(envelope(p1)))
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(dateTwo, versionTwo))))
      .mockResolvedValueOnce(jsonResponse(envelope(p2)))
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(dateOne, versionThree, [existing]))))
      .mockResolvedValueOnce(jsonResponse(envelope(freshP1)))
      .mockResolvedValueOnce(jsonResponse(envelope(receiptFor(dateOne, versionThree, versionFour))))
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(dateTwo, versionFour))))
      .mockResolvedValueOnce(jsonResponse({
        detail: { error: { category: 'conflict', code: 'stale_preview', message: '版本已過期', field_errors: [], domain_blockers: ['calendar_version'], retryable: false, correlation_id: 'holiday-csv-partial', current_version: null } },
      }, 409));

    const client = createHolidayClient();
    const parsed = client.parseCsv(csv);
    const batch = await client.previewCsv(parsed);
    expect(batch.zero_write).toBe(true);
    expect(batch.entries).toHaveLength(2);
    expect(vi.mocked(globalThis.fetch).mock.calls.slice(0, 4).map((call) => call[0])).toEqual([
      '/api/v1/holidays?from_date=2026-01-01&to_date=2026-01-01',
      '/api/v1/holidays/preview',
      '/api/v1/holidays?from_date=2026-02-28&to_date=2026-02-28',
      '/api/v1/holidays/preview',
    ]);
    const firstPreviewBody = JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[1]?.[1]?.body));
    expect(firstPreviewBody.is_double_pay_default).toBe(true);
    expect(vi.mocked(globalThis.fetch).mock.calls.some((call) => call[0] === '/api/v1/holidays/apply')).toBe(false);

    const result = await client.applyCsv(batch, '官方 CSV canonical test', { idempotencyKey: 'holiday-csv-confirm' });
    expect(result.attempted).toBe(2);
    expect(result.applied).toBe(1);
    expect(result.failures).toHaveLength(1);
    expect(result.failures[0]?.holiday_date).toBe(dateTwo);
    expect(result.failures[0]?.message).toContain('版本已過期');
    expect(result.replayed).toBe(0);
    const applyCall = vi.mocked(globalThis.fetch).mock.calls.find((call) => call[0] === '/api/v1/holidays/apply');
    expect(applyCall?.[1]?.headers).toMatchObject({ 'Idempotency-Key': 'holiday-csv-confirm-' + dateOne });
    expect(JSON.parse(String(applyCall?.[1]?.body)).expected_calendar_version).toBe(versionThree);
  });

  it('兩次成功 Apply 都以最新回讀版本建立 fresh preview', async () => {
    const date = '2026-03-01';
    const versionOne = '1'.repeat(64);
    const versionTwo = '2'.repeat(64);
    const versionThree = '3'.repeat(64);
    const parsed = parseHolidayCsv([CSV_HEADER, date + ',日,2,春假'].join('\n'));
    const batch = {
      parsed,
      entries: [{ row: parsed.rows[0]!, preview: previewFor(date, versionOne, 'a'.repeat(64)) }],
      skipped: [],
      issues: [],
      zero_write: true as const,
    };
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(date, versionOne))))
      .mockResolvedValueOnce(jsonResponse(envelope(previewFor(date, versionOne, 'a'.repeat(64)))))
      .mockResolvedValueOnce(jsonResponse(envelope(receiptFor(date, versionOne, versionTwo))))
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(date, versionTwo))))
      .mockResolvedValueOnce(jsonResponse(envelope(previewFor(date, versionTwo, 'b'.repeat(64)))))
      .mockResolvedValueOnce(jsonResponse(envelope(receiptFor(date, versionTwo, versionThree))));

    const client = createHolidayClient();
    const first = await client.applyCsv(batch, 'first fresh apply', { idempotencyKey: 'holiday-csv-sequential' });
    const second = await client.applyCsv(batch, 'second fresh apply', { idempotencyKey: 'holiday-csv-sequential' });
    expect(first.applied).toBe(1);
    expect(second.applied).toBe(1);
    const applyBodies = vi.mocked(globalThis.fetch).mock.calls
      .filter((call) => call[0] === '/api/v1/holidays/apply')
      .map((call) => JSON.parse(String(call[1]?.body)));
    expect(applyBodies.map((body) => body.expected_calendar_version)).toEqual([versionOne, versionTwo]);
  });

  it('實際 transport 對相同資料只 skip，changed=false 保持 unchanged 而不冒充 replay', async () => {
    const date = '2026-01-01';
    const version = 'e'.repeat(64);
    const sameHoliday = { holiday_date: date, holiday_name: '元旦', is_double_pay_default: true };
    const csv = [CSV_HEADER, date + ',四,2,元旦'].join('\n');
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(date, version, [sameHoliday]))))
      .mockResolvedValueOnce(jsonResponse(envelope(calendarFor(date, version, [sameHoliday]))))
      .mockResolvedValueOnce(jsonResponse(envelope(previewFor(date, version, '4'.repeat(64)))))
      .mockResolvedValueOnce(jsonResponse(envelope(receiptFor(date, version, 'f'.repeat(64), false))));

    const client = createHolidayClient();
    const parsed = client.parseCsv(csv);
    const previewBatch = await client.previewCsv(parsed);
    expect(previewBatch.entries).toEqual([]);
    expect(previewBatch.skipped).toHaveLength(1);
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1);

    const changedParsed = client.parseCsv([CSV_HEADER, date + ',四,2,新元旦'].join('\n'));
    const changedBatch = {
      ...previewBatch,
      entries: [{ row: changedParsed.rows[0]!, preview: previewFor(date, version, '4'.repeat(64)) }],
      skipped: [],
    };
    const result = await client.applyCsv(changedBatch, 'same-data canonical test', { idempotencyKey: 'holiday-csv-same' });
    expect(result.unchanged).toBe(1);
    expect(result.replayed).toBe(0);
  });

  it('React UI 使用實際 parser，預覽顯示零寫入，Apply 後回讀失敗可觀察', async () => {
    let readbackFailure = false;
    const query = vi.spyOn(holidayClient, 'query').mockImplementation(async () => {
      if (readbackFailure) throw new Error('CSV readback unavailable');
      return HOLIDAY_CALENDAR;
    });
    const preview = vi.mocked(holidayFlow.previewHolidayFlow).mockReset().mockResolvedValue(HOLIDAY_PREVIEW);
    const apply = vi.mocked(holidayFlow.applyHolidayFlow).mockReset().mockResolvedValue(HOLIDAY_RECEIPT);
    render(<OfficialHolidayCsvImport />);
    const file = new File([[CSV_HEADER, '2026-01-01,四,2,元旦'].join('\n')], 'official-2026.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('選擇政府官方國定假日 CSV'), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText('可匯入：1')).toBeInTheDocument());
    expect(query).toHaveBeenCalledTimes(1);
    expect(preview).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
    readbackFailure = true;
    fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('CSV readback unavailable'));
    expect(preview).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('匯入完成')).not.toBeInTheDocument();
  });
});
