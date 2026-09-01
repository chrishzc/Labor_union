/**
 * File: historical_completion.test.tsx
 * Description: 驗證 HOB-E strict decode、closed owner referral、收合技術證據與 Step 11 不假完成顯示。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { sessionClient } from '../api/auth/session_client';
import {
  queryHistoricalCompletion,
  type HistoricalCompletionClient,
} from '../api/orders/historical_completion_client';
import {
  HistoricalCompletionSchema,
  type HistoricalCompletion,
} from '../api/orders/historical_completion_schemas';
import { HistoricalCompletionPanel } from '../components/HistoricalCompletionPanel';

const blocked: HistoricalCompletion = {
  case_no: 'CASE-1',
  state: 'blocked',
  step_11_status: 'blocked',
  step_11_completed: false,
  historical_alerts_completed: false,
  active_alerts: [{
    code: 'client_finance_settlement_open',
    owner: 'client_finance',
    field_path: 'client_finance.open_obligation_count',
    referral: 'client_finance.settlement',
    message: 'Client Finance 尚有未結清義務',
  }],
  owner_versions: [{ owner: 'orders', version: '3' }, { owner: 'client_finance', version: '4' }],
  owner_source_versions: [{ kind: 'staff_obligation', identity: 'obligation:1', version: '2' }],
  source_fingerprint: 'a'.repeat(64),
  projection_fingerprint: 'b'.repeat(64),
};

function client(projection: HistoricalCompletion): HistoricalCompletionClient {
  return {
    query: vi.fn().mockResolvedValue(projection),
    preview: vi.fn().mockResolvedValue({
      case_no: projection.case_no,
      before_status: '歷史訂單－服務完成',
      after_status: '歷史訂單－帳務完成',
      expected_order_version: '3',
      resulting_order_version: '4',
      expected_client_finance_version: '4',
      expected_source_versions: projection.owner_source_versions,
      business_date: '2026-09-01',
      preview_fingerprint: 'c'.repeat(64),
    }),
    apply: vi.fn().mockResolvedValue({
      case_no: projection.case_no,
      lifecycle_event_id: 10,
      resulting_order_version: '4',
      after_status: '歷史訂單－帳務完成',
      replayed: false,
    }),
  };
}

describe('HistoricalCompletionPanel', () => {
  afterEach(() => sessionClient.clearSession());

  it('keeps Step 11 open and displays exact owner referral', async () => {
    render(<HistoricalCompletionPanel caseNo="CASE-1" client={client(blocked)} />);

    await waitFor(() => expect(screen.getByText(/尚有 1 項必要資料/)).toBeInTheDocument());
    expect(screen.getByText(/客戶帳務結清/).closest('li')).toHaveTextContent('客戶帳務');
    expect(screen.getByText(/client_finance_settlement_open/).closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText(/source fingerprint/).closest('details')).not.toHaveAttribute('open');
  });

  it('shows completion only when all terminal flags and alerts agree', async () => {
    const completed: HistoricalCompletion = {
      ...blocked,
      state: 'completed',
      step_11_status: 'completed',
      step_11_completed: true,
      historical_alerts_completed: true,
      active_alerts: [],
    };
    render(<HistoricalCompletionPanel caseNo="CASE-1" client={client(completed)} />);

    await waitFor(() => expect(screen.getByText(/皆已確認完成/)).toBeInTheDocument());
    expect(screen.queryByRole('list', { name: '待處理項目' })).not.toBeInTheDocument();
  });

  it('requires explicit confirmation before applying accounting completion', async () => {
    const completed: HistoricalCompletion = {
      ...blocked,
      state: 'completed',
      step_11_status: 'completed',
      step_11_completed: true,
      historical_alerts_completed: true,
      active_alerts: [],
    };
    const completionClient = client(completed);
    render(<HistoricalCompletionPanel caseNo="CASE-1" client={completionClient} />);

    fireEvent.click(await screen.findByRole('button', { name: '預覽並確認帳務完成' }));
    const applyButton = await screen.findByRole('button', { name: '確認推進至帳務完成' });
    expect(applyButton).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /客戶款項及所有月嫂款項/ }));
    fireEvent.click(applyButton);

    await waitFor(() => expect(screen.getByText(/已推進至歷史訂單－帳務完成/)).toBeInTheDocument());
    expect(completionClient.apply).toHaveBeenCalledTimes(1);
  });

  it('does not expose an unclassified runtime error', async () => {
    const failingClient: HistoricalCompletionClient = {
      query: vi.fn().mockRejectedValue(new Error('raw transport detail')),
      preview: vi.fn(),
      apply: vi.fn(),
    };
    render(<HistoricalCompletionPanel caseNo="CASE-1" client={failingClient} />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('歷史案件完成狀態目前無法載入。'));
    expect(screen.queryByText('raw transport detail')).not.toBeInTheDocument();
  });

  it('strict decoder rejects extra fields instead of passing raw dictionaries', async () => {
    sessionClient.setSession('token', {
      id: 1,
      username: 'tester',
      display_name: '測試',
      role: 'operator',
      linked_line_user_id: null,
      capabilities: [],
      is_root: false,
      access_control_version: 1,
    });
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      message: 'ok',
      data: { ...blocked, raw_owner_payload: {} },
      error: null,
    }), { status: 200, headers: { 'content-type': 'application/json' } }));

    await expect(queryHistoricalCompletion('CASE-1')).rejects.toBeTruthy();
  });

  it('preserves versions above the JavaScript safe integer range as strings', () => {
    const lossless: HistoricalCompletion = {
      ...blocked,
      owner_versions: [{ owner: 'orders', version: '9223372036854775807' }],
      owner_source_versions: [{ kind: 'staff_payout_event', identity: 'payout:1', version: '9007199254740993' }],
    };

    expect(lossless.owner_versions[0].version).toBe('9223372036854775807');
    expect(lossless.owner_source_versions[0].version).toBe('9007199254740993');
  });

  it('accepts exact historical staff payout source lineage', () => {
    const decoded = HistoricalCompletionSchema.parse({
      ...blocked,
      owner_source_versions: [
        { kind: 'historical_staff_payout_projection', identity: 'obligation:1', version: '4' },
        { kind: 'historical_staff_payout_event', identity: 'historical-payout:1', version: '4' },
        { kind: 'historical_staff_payout_link', identity: '1:1', version: '2' },
      ],
    });

    expect(decoded.owner_source_versions).toHaveLength(3);
  });
});
