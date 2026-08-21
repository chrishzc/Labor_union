/**
 * File: holiday_adapter.test.ts
 * Description: 驗證國定假日 Query、Preview、Apply、same-key retry 與 receipt 觀察狀態。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyHolidayFlow,
  holidayFlowStore,
  previewHolidayFlow,
  queryHolidayFlow,
  resolveHolidayMachineState,
  retryHolidayApplyFlow,
  retryHolidayObservationFlow,
  setHolidayDraft,
} from '../adapters/scheduling/holiday_flow_adapter';
import type { HolidayClient } from '../api/scheduling/holiday_client';
import {
  HolidayConflictError,
  HolidayNetworkError,
  HolidayUnavailableError,
} from '../api/scheduling/holiday_errors';
import {
  HOLIDAY_APPLY_REQUEST,
  HOLIDAY_CALENDAR,
  HOLIDAY_DRAFT,
  HOLIDAY_PREVIEW,
  HOLIDAY_QUERY,
  HOLIDAY_RECEIPT,
} from './fixtures/holiday_contract_fixtures';

function fakeClient(overrides?: Partial<HolidayClient>): HolidayClient {
  return {
    query: vi.fn().mockResolvedValue(HOLIDAY_CALENDAR),
    queryCalendar: vi.fn().mockResolvedValue(HOLIDAY_CALENDAR),
    preview: vi.fn().mockResolvedValue(HOLIDAY_PREVIEW),
    apply: vi.fn().mockResolvedValue(HOLIDAY_RECEIPT),
    ...overrides,
  };
}

async function preparePreview(client: HolidayClient): Promise<void> {
  await queryHolidayFlow(HOLIDAY_QUERY.from_date, HOLIDAY_QUERY.to_date, { client });
  setHolidayDraft(HOLIDAY_DRAFT);
  await previewHolidayFlow(HOLIDAY_DRAFT, { client });
}

describe('holiday flow adapter', () => {
  beforeEach(() => {
    holidayFlowStore.clear();
  });

  it('遵循 Query → Preview → Apply → receipt → re-query，且送出 exact server payload', async () => {
    const client = fakeClient();
    await preparePreview(client);

    const receipt = await applyHolidayFlow(HOLIDAY_APPLY_REQUEST, { client });

    expect(receipt).toEqual(HOLIDAY_RECEIPT);
    expect(client.query).toHaveBeenCalledTimes(2);
    expect(client.preview).toHaveBeenCalledWith(HOLIDAY_DRAFT, expect.anything());
    expect(client.apply).toHaveBeenCalledWith(
      HOLIDAY_APPLY_REQUEST,
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
    expect(resolveHolidayMachineState(holidayFlowStore.get())).toMatchObject({
      type: 'observed',
      calendar: HOLIDAY_CALENDAR,
      receipt: HOLIDAY_RECEIPT,
    });
  });

  it('stale Preview 只能進入 stale，不能自動 Apply 或猜測新版本', async () => {
    const client = fakeClient({
      preview: vi.fn().mockRejectedValue(
        new HolidayConflictError('國定假日版本已過期。', {
          publicCode: 'stale_preview',
        }),
      ),
    });
    await queryHolidayFlow(HOLIDAY_QUERY.from_date, HOLIDAY_QUERY.to_date, { client });
    setHolidayDraft(HOLIDAY_DRAFT);

    await expect(previewHolidayFlow(HOLIDAY_DRAFT, { client })).rejects.toBeInstanceOf(
      HolidayConflictError,
    );
    expect(resolveHolidayMachineState(holidayFlowStore.get())).toMatchObject({
      type: 'stale',
      requiresFreshQuery: true,
    });
    expect(client.apply).not.toHaveBeenCalled();
  });

  it('outcome_unknown 僅能以相同 payload 與同一 Idempotency-Key retry', async () => {
    const apply = vi
      .fn<HolidayClient['apply']>()
      .mockRejectedValueOnce(new HolidayUnavailableError('暫時無法確認套用結果'))
      .mockResolvedValueOnce(HOLIDAY_RECEIPT);
    const client = fakeClient({ apply });
    await preparePreview(client);

    await expect(
      applyHolidayFlow(HOLIDAY_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(HolidayUnavailableError);
    const unknown = resolveHolidayMachineState(holidayFlowStore.get());
    expect(unknown).toMatchObject({ type: 'outcome_unknown' });
    if (unknown.type !== 'outcome_unknown') throw new Error('expected outcome_unknown');

    await retryHolidayApplyFlow({ client });

    expect(apply).toHaveBeenCalledTimes(2);
    expect(apply.mock.calls[1]?.[0]).toEqual(apply.mock.calls[0]?.[0]);
    expect(apply.mock.calls[1]?.[1]?.idempotencyKey).toBe(
      unknown.idempotencyKey,
    );
    expect(resolveHolidayMachineState(holidayFlowStore.get())).toMatchObject({
      type: 'observed',
      receipt: HOLIDAY_RECEIPT,
    });
  });

  it('receipt 已收到但 re-query 失敗時保留 receipt，不把 observation failure 改寫成 Apply failure', async () => {
    const query = vi
      .fn<HolidayClient['query']>()
      .mockResolvedValueOnce(HOLIDAY_CALENDAR)
      .mockRejectedValueOnce(new HolidayNetworkError('觀察連線失敗'));
    const client = fakeClient({ query });
    await preparePreview(client);

    await expect(
      applyHolidayFlow(HOLIDAY_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(HolidayNetworkError);
    expect(resolveHolidayMachineState(holidayFlowStore.get())).toMatchObject({
      type: 'observation_failed',
      receipt: HOLIDAY_RECEIPT,
    });

    query.mockResolvedValueOnce(HOLIDAY_CALENDAR);
    await retryHolidayObservationFlow({ client });
    expect(resolveHolidayMachineState(holidayFlowStore.get())).toMatchObject({
      type: 'observed',
      receipt: HOLIDAY_RECEIPT,
    });
  });

  it('adapter 不計算雙倍薪、coverage、eligibility 或結束日，只傳遞 server candidate', async () => {
    const client = fakeClient();
    await preparePreview(client);
    await applyHolidayFlow(HOLIDAY_APPLY_REQUEST, { client });

    const previewPayload = vi.mocked(client.preview).mock.calls[0]?.[0];
    const applyPayload = vi.mocked(client.apply).mock.calls[0]?.[0];
    expect(previewPayload).toEqual(HOLIDAY_DRAFT);
    expect(applyPayload).toEqual(HOLIDAY_APPLY_REQUEST);
    expect(applyPayload).not.toHaveProperty('coverage');
    expect(applyPayload).not.toHaveProperty('eligibility');
    expect(applyPayload).not.toHaveProperty('end_date');
    expect(applyPayload).not.toHaveProperty('double_pay_amount');
  });
});
