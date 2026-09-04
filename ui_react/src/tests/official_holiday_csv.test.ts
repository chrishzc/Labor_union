/**
 * File: official_holiday_csv.test.ts
 * Description: Focused deterministic coverage for official holiday CSV parsing and import orchestration.
 */
import { describe, expect, it, vi } from 'vitest';
import type {
  HolidayCalendar,
  HolidayPreview,
  HolidayReceipt,
} from '../adapters/scheduling/holiday_flow_adapter';
import {
  importOfficialHolidayCandidates,
  parseOfficialHolidayCsv,
  planOfficialHolidayImport,
} from '../adapters/scheduling/official_holiday_csv';

const VERSION = 'a'.repeat(64);
const PREVIEW_FINGERPRINT = 'b'.repeat(64);
const RESULT_VERSION = 'c'.repeat(64);

function calendar(holidays: HolidayCalendar['holidays'] = []): HolidayCalendar {
  return {
    planning_horizon: { from_date: '2026-01-01', to_date: '2026-12-31' },
    source_identity: 'test-calendar',
    calendar_version: VERSION,
    holidays,
  };
}

function previewFor(date: string, name: string): HolidayPreview {
  return {
    command: {
      action: 'upsert',
      holiday_date: date,
      holiday_name: name,
      is_double_pay_default: false,
      from_date: '2026-01-01',
      to_date: '2026-12-31',
      expected_calendar_version: VERSION,
    },
    before: null,
    planning_horizon: { from_date: '2026-01-01', to_date: '2026-12-31' },
    source_identity: 'test-calendar',
    calendar_version: VERSION,
    schedule_impact: 'none',
    payroll_impact: 'none',
    preview_fingerprint: PREVIEW_FINGERPRINT,
  };
}

function receiptFor(date: string, changed = true): HolidayReceipt {
  return {
    receipt_key: `receipt-${date}`,
    action: 'upsert',
    holiday_date: date,
    changed,
    planning_horizon: { from_date: '2026-01-01', to_date: '2026-12-31' },
    source_identity: 'test-calendar',
    previous_calendar_version: VERSION,
    resulting_calendar_version: RESULT_VERSION,
    preview_fingerprint: PREVIEW_FINGERPRINT,
  };
}

describe('official holiday CSV parsing', () => {
  it('imports named official holidays and ignores blank-note weekends', () => {
    const result = parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20260101,四,2,中華民國開國紀念日',
      '20260103,六,2,',
      '20260104,日,2,',
      '20260228,六,2,和平紀念日',
      '20260302,一,0,',
    ].join('\r\n'));

    expect(result).toEqual({
      ok: true,
      year: 2026,
      holidays: [
        { holiday_date: '2026-01-01', holiday_name: '中華民國開國紀念日' },
        { holiday_date: '2026-02-28', holiday_name: '和平紀念日' },
      ],
    });
  });

  it('supports quoted official notes without inventing a name', () => {
    const result = parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20261010,六,2,"國慶日,「雙十」"',
    ].join('\n'));

    expect(result).toEqual({
      ok: true,
      year: 2026,
      holidays: [{ holiday_date: '2026-10-10', holiday_name: '國慶日,「雙十」' }],
    });
  });

  it('fails closed when a required column is missing', () => {
    const result = parseOfficialHolidayCsv([
      '西元日期,星期,是否放假',
      '20260101,四,2',
    ].join('\n'));

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain('備註');
  });

  it('fails closed for invalid rows or mixed years', () => {
    expect(parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20260230,一,2,不存在的日期',
    ].join('\n')).ok).toBe(false);

    expect(parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20260101,四,2,元旦',
      '20270101,五,2,元旦',
    ].join('\n')).ok).toBe(false);
  });

  it('skips an existing identical date/name before mutation', () => {
    const parsed = parseOfficialHolidayCsv([
      '西元日期,星期,是否放假,備註',
      '20260101,四,2,元旦',
      '20260228,六,2,和平紀念日',
    ].join('\n'));
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    const plan = planOfficialHolidayImport(parsed, calendar([
      { holiday_date: '2026-01-01', holiday_name: '元旦', is_double_pay_default: false },
    ]));
    expect(plan.existingSkipCount).toBe(1);
    expect(plan.pending).toEqual([
      { holiday_date: '2026-02-28', holiday_name: '和平紀念日' },
    ]);
  });
});

describe('official holiday import orchestration', () => {
  it('uses Preview -> Apply for each candidate, then performs the final Query', async () => {
    const calls: string[] = [];
    const query = vi.fn(async () => {
      calls.push('query');
      return calendar();
    });
    const preview = vi.fn(async (request) => {
      calls.push(`preview:${request.holiday_date}`);
      return previewFor(request.holiday_date, request.holiday_name ?? '');
    });
    const apply = vi.fn(async (request) => {
      calls.push(`apply:${request.holiday_date}`);
      return receiptFor(request.holiday_date);
    });

    const summary = await importOfficialHolidayCandidates([
      { holiday_date: '2026-01-01', holiday_name: '元旦' },
      { holiday_date: '2026-02-28', holiday_name: '和平紀念日' },
    ], 2026, 1, {
      query,
      preview,
      apply,
      setDraft: (request) => { calls.push(`draft:${request.holiday_date}`); },
    });

    expect(calls).toEqual([
      'draft:2026-01-01',
      'preview:2026-01-01',
      'apply:2026-01-01',
      'draft:2026-02-28',
      'preview:2026-02-28',
      'apply:2026-02-28',
      'query',
    ]);
    expect(summary).toEqual({
      successCount: 2,
      skipCount: 1,
      failureCount: 0,
      failedDates: [],
    });
  });

  it('records one failed date, refreshes Query state, and continues without rollback', async () => {
    const calls: string[] = [];
    const query = vi.fn(async () => {
      calls.push('query');
      return calendar();
    });
    const preview = vi.fn(async (request) => {
      calls.push(`preview:${request.holiday_date}`);
      if (request.holiday_date === '2026-01-01') throw new Error('preview rejected');
      return previewFor(request.holiday_date, request.holiday_name ?? '');
    });
    const apply = vi.fn(async (request) => {
      calls.push(`apply:${request.holiday_date}`);
      return receiptFor(request.holiday_date);
    });

    const summary = await importOfficialHolidayCandidates([
      { holiday_date: '2026-01-01', holiday_name: '元旦' },
      { holiday_date: '2026-02-28', holiday_name: '和平紀念日' },
    ], 2026, 0, {
      query,
      preview,
      apply,
      setDraft: (request) => { calls.push(`draft:${request.holiday_date}`); },
    });

    expect(calls).toEqual([
      'draft:2026-01-01',
      'preview:2026-01-01',
      'query',
      'draft:2026-02-28',
      'preview:2026-02-28',
      'apply:2026-02-28',
      'query',
    ]);
    expect(summary).toEqual({
      successCount: 1,
      skipCount: 0,
      failureCount: 1,
      failedDates: ['2026-01-01'],
    });
  });
});
