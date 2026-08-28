/**
 * File: historical_completion.test.tsx
 * Description: 驗證 HOB-E strict decode、owner referral 與 Step 11 不假完成顯示。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { sessionClient } from '../api/auth/session_client';
import {
  queryHistoricalCompletion,
  type HistoricalCompletionClient,
} from '../api/orders/historical_completion_client';
import type { HistoricalCompletion } from '../api/orders/historical_completion_schemas';
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
  return { query: vi.fn().mockResolvedValue(projection) };
}

describe('HistoricalCompletionPanel', () => {
  afterEach(() => sessionClient.clearSession());

  it('keeps Step 11 open and displays exact owner referral', async () => {
    render(<HistoricalCompletionPanel caseNo="CASE-1" client={client(blocked)} />);

    await waitFor(() => expect(screen.getByText(/尚有 1 項 owner 根事實/)).toBeInTheDocument());
    expect(screen.getByText(/Client Finance 尚有未結清義務/).closest('li')).toHaveTextContent('客戶帳務');
    expect(screen.getByText(/client_finance.settlement/)).toBeInTheDocument();
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

    await waitFor(() => expect(screen.getByText(/共同確認完成/)).toBeInTheDocument());
    expect(screen.queryByRole('list', { name: '待處理 owner 根事實' })).not.toBeInTheDocument();
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
});
