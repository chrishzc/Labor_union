/**
 * File: safe_review_link_workbench.test.tsx
 * Description: M4 safe-review-link 管理端／行動端 readback 與 typed action oracle。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SafeReviewLinkWorkbench } from '../components/SafeReviewLinkWorkbench';
import type { SafeReviewLinkClient } from '../api/line_safe_review_link/line_safe_review_link_client';

const view = {
  link_id: 'link-96-1',
  status: 'issued' as const,
  canonical_internal_target: '/api/v1/runtime/health-status',
  target_version: 3,
  source_alert_identity: 'alert:96:1',
  expires_at_utc: '2026-09-01T08:00:00+00:00',
  redeemed_at_utc: null,
  revoked_at_utc: null,
  root_version: 0,
};

describe('M4 safe-review-link workbench', () => {
  it('queries and renders only the masked target/status readback', async () => {
    const client: SafeReviewLinkClient = {
      query: vi.fn().mockResolvedValue(view),
      redeem: vi.fn(),
      revoke: vi.fn(),
    };
    render(<SafeReviewLinkWorkbench client={client} />);

    fireEvent.change(screen.getByLabelText('連結識別'), { target: { value: 'link-96-1' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢去敏狀態' }));

    await waitFor(() => expect(screen.getByText('待審核')).toBeInTheDocument());
    expect(client.query).toHaveBeenCalledWith('link-96-1', expect.objectContaining({ correlationId: expect.any(String) }));
    expect(screen.getByText('/api/v1/runtime/health-status')).toBeInTheDocument();
    expect(screen.queryByText('opaque-token-123456')).not.toBeInTheDocument();
  });

  it('redeems through typed client and clears the one-time token after readback', async () => {
    const redeemed = { ...view, status: 'redeemed' as const, redeemed_at_utc: '2026-09-01T07:00:00+00:00', root_version: 1 };
    const client: SafeReviewLinkClient = {
      query: vi.fn().mockResolvedValue(view),
      redeem: vi.fn().mockResolvedValue({ receipt_id: 'redeem-96-1', outcome: 'redeemed', replayed: false, root_version: 1, readback: redeemed }),
      revoke: vi.fn(),
    };
    render(<SafeReviewLinkWorkbench client={client} />);

    fireEvent.change(screen.getByLabelText('連結識別'), { target: { value: 'link-96-1' } });
    fireEvent.change(screen.getByLabelText(/一次性 token/), { target: { value: 'opaque-token-123456' } });
    fireEvent.change(screen.getByLabelText('目前目標路徑'), { target: { value: '/api/v1/runtime/health-status' } });
    fireEvent.change(screen.getByLabelText('目標版本'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: '確認使用審核連結' }));

    await waitFor(() => expect(screen.getByText('已使用')).toBeInTheDocument());
    expect(client.redeem).toHaveBeenCalledWith('link-96-1', expect.objectContaining({ raw_token: 'opaque-token-123456', current_target_version: 3 }));
    expect(screen.getByLabelText(/一次性 token/)).toHaveValue('');
    expect(screen.getByText(/receipt：redeem-96-1/)).toBeInTheDocument();
  });
});
