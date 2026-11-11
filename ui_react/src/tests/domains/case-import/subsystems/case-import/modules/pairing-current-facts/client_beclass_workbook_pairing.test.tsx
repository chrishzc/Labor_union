import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { ClientBeClassWorkbookSnapshot } from '../../../../../../../api/case_import/client_beclass_workbook/client';
import { DataImportPage } from '../../../../../../../pages/DataImportPage';

afterEach(() => {
  vi.unstubAllGlobals();
  sessionClient.clearSession();
});

it('groups shared cases in a drawer, retains links across groups and closing, and confirms the batch', async () => {
  sessionClient.setSession('synthetic-session', {
    id: 1, username: 'tester', display_name: '測試', role: 'operator',
    linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1,
  });
  const file = new File(['pairing fixture'], 'pairing.xlsx');
  const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(file);
  const previewFingerprint = 'c'.repeat(64);
  const shared = { name: '測試客戶', masked_phone: '09•••••678', city: '新竹市' };
  const pairings = [
    { source_row: 2, case_no: 'HCM-B' },
    { source_row: 3, case_no: 'HCM-A' },
    { source_row: 4, case_no: 'HCM-D' },
  ];
  const queryNos = ['BC-FIRST', 'BC-SECOND', 'BC-THIRD'];
  const response = (data: unknown) => new Response(
    JSON.stringify({ success: true, message: 'ok', error: null, data }),
    { headers: { 'content-type': 'application/json' } },
  );
  const request = vi.fn()
    .mockResolvedValueOnce(response({
      source_content_digest: snapshot.sha256, sheet_identity: 'b'.repeat(64),
      source_row_count: 3, create_count: 0, review_required_count: 0,
      existing_conflict_count: 0, existing_source_count: 0, preview_fingerprint: previewFingerprint,
      manual_rows: queryNos.map((query_no, index) => ({
        ...shared, source_row: index + 2, query_no, submitted_at: '2026-08-02 10:00',
        case_nos: index === 0 ? ['HCM-B', 'HCM-C'] : index === 1 ? ['HCM-A', 'HCM-B'] : ['HCM-D', 'HCM-E'],
      })),
      candidates: ['HCM-A', 'HCM-B', 'HCM-C', 'HCM-D', 'HCM-E'].map((case_no, index) => ({
        ...shared, case_no, created_at: `2026-08-0${index + 1} 09:30`,
        start_date: `2026-09-0${index + 1}`,
      })),
    }))
    .mockResolvedValueOnce(response({
      source_content_digest: snapshot.sha256, source_row_count: 3, created_count: 3,
      exact_replay_count: 0, review_required_count: 0, existing_conflict_count: 0,
      existing_source_count: 0, replayed_workbook: false,
      manual_bindings: pairings.map((pairing, index) => ({ ...pairing, query_no: queryNos[index] })),
    }));
  vi.stubGlobal('fetch', request);
  const { container } = render(<DataImportPage />);
  fireEvent.click(screen.getByRole('button', { name: '客戶 BeClass' }));
  fireEvent.change(screen.getByLabelText('選擇客戶 BeClass Workbook'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '匯入' }));

  const openDrawer = await screen.findByRole('button', { name: '開啟人工配對' });
  expect(screen.queryByRole('region', { name: 'BeClass 問卷' })).not.toBeInTheDocument();
  fireEvent.click(openDrawer);
  const drawer = within(screen.getByRole('dialog', { name: '客戶 BeClass 人工配對' }));
  const sources = within(drawer.getByRole('region', { name: 'BeClass 問卷' }));
  const cases = within(drawer.getByRole('region', { name: 'HCM 候選案件' }));
  const check = screen.getByRole('button', { name: '檢查配對' });
  expect(check).toBeDisabled();
  expect(cases.getAllByRole('button', { name: /HCM-B/ })).toHaveLength(1);
  expect(cases.queryByRole('button', { name: /HCM-D/ })).not.toBeInTheDocument();
  expect(sources.getByRole('button', { name: /BC-FIRST/ })).toHaveTextContent('問卷報名時間');
  expect(cases.getByRole('button', { name: /HCM-B/ })).toHaveTextContent('預計服務日期 2026-09-02');
  fireEvent.click(sources.getByRole('button', { name: /BC-FIRST/ }));
  fireEvent.click(cases.getByRole('button', { name: /HCM-B/ }));
  fireEvent.click(sources.getByRole('button', { name: /BC-SECOND/ }));
  expect(cases.getByRole('button', { name: /HCM-B/ })).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(cases.getByRole('button', { name: /HCM-A/ }));
  expect(container.querySelectorAll('.beclass-pairing-wires path')).toHaveLength(2);
  expect(check).toBeDisabled();
  fireEvent.click(drawer.getByRole('button', { name: '下一組待配對' }));
  expect(cases.queryByRole('button', { name: /HCM-B/ })).not.toBeInTheDocument();
  fireEvent.click(sources.getByRole('button', { name: /BC-THIRD/ }));
  fireEvent.click(cases.getByRole('button', { name: /HCM-D/ }));
  fireEvent.click(drawer.getByRole('button', { name: '關閉配對抽屜' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByText(/2 組 · 已配對 3/)).toBeVisible();
  fireEvent.click(openDrawer);
  fireEvent.change(screen.getByRole('combobox', { name: '配對組別' }), { target: { value: '0' } });
  expect(container.querySelectorAll('.beclass-pairing-wires path')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: '檢查配對' }));
  expect(request).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/第 2 列 · BC-FIRST/)).toHaveTextContent('HCM-B');
  fireEvent.click(screen.getByRole('button', { name: '返回修改' }));
  expect(container.querySelectorAll('.beclass-pairing-wires path')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: '檢查配對' }));
  fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));

  expect(await screen.findByText('人工綁定明細（3 筆）')).toBeVisible();
  expect(screen.getByRole('row', { name: /BC-FIRST/ })).toHaveTextContent('HCM-B');
  expect(screen.getByRole('row', { name: /BC-SECOND/ })).toHaveTextContent('HCM-A');
  expect(screen.getByRole('row', { name: /BC-THIRD/ })).toHaveTextContent('HCM-D');
  const applied = request.mock.calls[1][1].body as FormData;
  expect(applied.get('preview_fingerprint')).toBe(previewFingerprint);
  expect(JSON.parse(String(applied.get('manual_pairings')))).toEqual(pairings);
});
