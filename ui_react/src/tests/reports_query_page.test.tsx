/**
 * File: reports_query_page.test.tsx
 * Description: 驗證ReportsPage active subsidy GET、weekly unavailable與disabled exports。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { ReportsPage } from '../pages/ReportsPage';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';
describe('ReportsPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(subsidyReportQueryClient, 'query').mockImplementation(async (query) => ({ ...SUBSIDY_REPORT_RESPONSE.data, period_kind: query.kind, application_year: query.applicationYear, quarter: query.kind === 'quarterly' ? query.quarter : null }));
  });
  it('renders server report, switches view with one GET and keeps exports disabled', async () => {
    render(<ReportsPage />);
    await waitFor(() => expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument());
    expect(screen.getAllByText('NT$ 12,000').length).toBeGreaterThan(0);
    expect(screen.getByText(/A\*+/)).toBeInTheDocument();
    expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-control-id="reports.export.quarterly-xlsx"]')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('檢視'), { target: { value: 'annual' } });
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(2));
    expect(document.querySelector('[data-control-id="reports.export.annual-xlsx"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /週報案件受理總表/ }));
    expect(screen.getByText(/後端尚未提供approved typed authority/)).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="reports.export.weekly-summary"]')).toBeDisabled();
    expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(2);
  });
});
