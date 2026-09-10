/**
 * File: StaffPage.tsx
 * Description: 管理月嫂名冊、資格、接案偏好、不可服務期間與任職狀態。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './StaffPage.css';
import { Drawer } from '../components/Drawer';
import {
  loadAllStaffDirectoryPages,
  staffDirectoryClient,
} from '../api/staff_directory/staff_directory_client';
import { StaffDirectoryAbortedError } from '../api/staff_directory/staff_directory_errors';
import { staffCasePreferenceSummaryClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_client';
import { staffCasePreferenceManualClient } from '../api/staff_case_preferences/staff_case_preferences_client';
import type { StaffCasePreferenceManualSnapshot, StaffCasePreferenceRelations } from '../api/staff_case_preferences/staff_case_preferences_schemas';
import { staffAvailabilityClient } from '../api/staff_availability/staff_availability_client';
import {
  StaffAvailabilityAbortedError,
  StaffAvailabilityConflictError,
  StaffAvailabilityUnavailableError,
} from '../api/staff_availability/staff_availability_errors';
import type {
  StaffAvailabilityApplyPayload,
  StaffAvailabilityIntent,
  StaffAvailabilityPreview,
  StaffAvailabilityReceipt,
} from '../api/staff_availability/staff_availability_schemas';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import {
  StaffLifecycleAbortedError,
  StaffLifecycleConflictError,
  StaffLifecycleUnavailableError,
} from '../api/staff_lifecycle/staff_lifecycle_errors';
import type {
  StaffLifecycleAction,
  StaffLifecycleApplyPayload,
  StaffLifecycleApplyReceipt,
  StaffLifecyclePreview,
} from '../api/staff_lifecycle/staff_lifecycle_schemas';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { staffProfileClient } from '../api/staff_profile/staff_profile_client';
import { StaffQualificationMasterError } from '../api/staff/qualification_master_errors';
import {
  adaptStaffDirectoryPage,
  type StaffDirectoryCardViewModel,
} from '../adapters/staff/staff_directory_adapter';
import {
  adaptStaffCasePreferenceSummary,
  type StaffCasePreferenceSummaryViewModel,
} from '../adapters/staff/staff_case_preference_summary_adapter';
import {
  adaptStaffAvailabilityBlocks,
  type StaffAvailabilityBlockViewModel,
} from '../adapters/staff/staff_availability_adapter';
import {
  adaptStaffLifecycleView,
  type StaffLifecycleViewModel,
} from '../adapters/staff/staff_lifecycle_adapter';
import {
  adaptStaffQualificationMaster,
  type StaffQualificationMasterViewModel,
} from '../adapters/staff/qualification_master_adapter';
import {
  adaptStaffProfile,
  type StaffProfileViewModel,
} from '../adapters/staff/staff_profile_adapter';

type DirectoryState =
  | { status: 'loading'; items: StaffDirectoryCardViewModel[] }
  | { status: 'ready'; items: StaffDirectoryCardViewModel[]; nextCursor: number | null }
  | { status: 'loading-more'; items: StaffDirectoryCardViewModel[]; nextCursor: number }
  | { status: 'error'; items: StaffDirectoryCardViewModel[]; message: string; retryCursor: number | null };
type DirectorySearchState =
  | { status: 'idle'; items: StaffDirectoryCardViewModel[] }
  | { status: 'loading'; items: StaffDirectoryCardViewModel[] }
  | { status: 'ready'; items: StaffDirectoryCardViewModel[] }
  | { status: 'error'; items: StaffDirectoryCardViewModel[]; message: string };
type QueryState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string };

type ActionPhase =
  | 'idle'
  | 'editing'
  | 'preview_loading'
  | 'preview_ready'
  | 'apply_pending'
  | 'receipt_received'
  | 'requery_loading'
  | 'observed'
  | 'stale'
  | 'outcome_unknown'
  | 'observation_failed'
  | 'error';

interface ActionState<TPreview, TReceipt, TPayload> {
  phase: ActionPhase;
  preview: TPreview | null;
  receipt: TReceipt | null;
  payload: TPayload | null;
  idempotencyKey: string | null;
  message: string | null;
}

function initialActionState<TPreview, TReceipt, TPayload>(): ActionState<TPreview, TReceipt, TPayload> {
  return { phase: 'idle', preview: null, receipt: null, payload: null, idempotencyKey: null, message: null };
}

let intentSequence = 0;

function nextIntentKey(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }
  intentSequence += 1;
  return `${prefix}-${intentSequence.toString(36)}`;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

const MANUAL_RELATION_KEYS = ['service_regions', 'service_periods', 'cooking_skills', 'holiday_availability', 'rest_schedule', 'baby_types'] as const;
const MANUAL_RELATION_LABELS: Record<typeof MANUAL_RELATION_KEYS[number], string> = {
  service_regions: '可承接區域', service_periods: '可承接時段', cooking_skills: '下廚能力',
  holiday_availability: '特殊節日意願', rest_schedule: '週間服務／排休', baby_types: '可承接胎數／型態',
};
type ManualRelationKey = typeof MANUAL_RELATION_KEYS[number];
const EMPTY_MANUAL_RELATIONS: StaffCasePreferenceRelations = {
  service_regions: [], service_periods: [], cooking_skills: [],
  holiday_availability: [], rest_schedule: [], baby_types: [],
};

export function updateManualDraftRow(current: StaffCasePreferenceRelations, key: ManualRelationKey, index: number, field: 'value' | 'detail', value: string): StaffCasePreferenceRelations {
  const rows = current[key].map((item, rowIndex) => rowIndex === index ? { ...item, [field]: field === 'detail' ? (value || null) : value } : item);
  return { ...current, [key]: rows };
}

export function appendManualDraftRow(current: StaffCasePreferenceRelations, key: ManualRelationKey): StaffCasePreferenceRelations {
  return { ...current, [key]: [...current[key], { value: '', detail: null }] };
}

function requestRelations(draft: StaffCasePreferenceRelations): StaffCasePreferenceRelations {
  return Object.fromEntries(MANUAL_RELATION_KEYS.map((key) => [
    key,
    draft[key].filter((item) => item.value.trim()).map((item) => ({ value: item.value.trim(), detail: item.detail?.trim() || null })),
  ])) as StaffCasePreferenceRelations;
}

function displayRelations(values: readonly { value: string; detail: string | null }[]): string {
  return values.map((item) => item.detail ? item.value + '（' + item.detail + '）' : item.value).join('、') || '（空）';
}

export function StaffCasePreferenceManualPreview({ preview }: { preview: StaffCasePreferenceManualSnapshot }) {
  return <div data-testid="staff-case-preference-manual-preview">
    <h4>六大接案能力變更預覽</h4>
    {MANUAL_RELATION_KEYS.map((key) => <div key={key}>
      <span>{MANUAL_RELATION_LABELS[key]}（變更前）: {displayRelations(preview.before[key])}</span>
      {' '}
      <span>{MANUAL_RELATION_LABELS[key]}（變更後）: {displayRelations(preview.after[key])}</span>
    </div>)}
  </div>;
}

export function StaffCasePreferenceManualEditor({ staffId, surfaceId = 'staff.drawer.case-preference-manual' }: { staffId: number; surfaceId?: string }) {
  const [snapshot, setSnapshot] = useState<StaffCasePreferenceManualSnapshot | null>(null);
  const [draft, setDraft] = useState<StaffCasePreferenceRelations>(() => EMPTY_MANUAL_RELATIONS);
  const [preview, setPreview] = useState<StaffCasePreferenceManualSnapshot | null>(null);
  const [reason, setReason] = useState('');
  const [status, setStatus] = useState('');
  const [phase, setPhase] = useState<'loading' | 'ready' | 'editing' | 'previewing' | 'preview_ready' | 'applying' | 'error'>('loading');
  const loadEpoch = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setPhase('loading');
    setSnapshot(null);
    setPreview(null);
    setReason('');
    setStatus('');
    try {
      const next = await staffCasePreferenceManualClient.query(staffId, { signal: controller.signal });
      if (epoch !== loadEpoch.current) return false;
      setSnapshot(next);
      setDraft(next.after);
      setPhase('ready');
      return true;
    } catch (error) {
      if (epoch === loadEpoch.current) {
        setPhase('error');
        setStatus(error instanceof Error ? error.message : '六大接案能力載入失敗。');
      }
      return false;
    }
  }, [staffId]);
  useEffect(() => {
    void load();
    return () => {
      loadEpoch.current += 1;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
    };
  }, [load]);
  const doPreview = async () => {
    if (!snapshot || phase !== 'editing') return;
    const epoch = loadEpoch.current;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setPhase('previewing');
    setPreview(null);
    setStatus('');
    try {
      const next = await staffCasePreferenceManualClient.preview(staffId, requestRelations(draft), { signal: controller.signal });
      if (epoch !== loadEpoch.current) return;
      setPreview(next);
      setPhase('preview_ready');
      setStatus('預覽已完成，尚未寫入。');
    } catch (error) {
      if (epoch === loadEpoch.current) {
        setPhase('editing');
        setStatus(error instanceof Error ? error.message : '預覽失敗。');
      }
    }
  };
  const doApply = async () => {
    if (!snapshot || !preview?.preview_fingerprint || !reason.trim() || phase !== 'preview_ready') return;
    const epoch = loadEpoch.current;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setPhase('applying');
    setStatus('');
    try {
      await staffCasePreferenceManualClient.apply(staffId, {
        ...requestRelations(draft),
        expected_snapshot_fingerprint: snapshot.snapshot_fingerprint,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
      }, { idempotencyKey: nextIntentKey('staff-case-preference-manual'), signal: controller.signal });
    } catch (error) {
      if (epoch === loadEpoch.current) {
        setPhase('error');
        setStatus(error instanceof Error ? error.message : '儲存結果尚未確認，請重新查詢。');
      }
      return;
    }
    if (epoch !== loadEpoch.current) return;
    if (await load()) setStatus('已儲存並重新查詢六大接案能力。');
  };
  const editing = ['editing', 'previewing', 'preview_ready', 'applying'].includes(phase);
  const locked = phase === 'loading' || phase === 'previewing' || phase === 'applying';
  return <section data-surface-id={surfaceId}>
    <h3>六大接案能力人工維護</h3>
    <p>直接編輯六項接案能力，預覽後確認儲存。交通方式仍於資格主檔唯讀顯示。</p>
    {phase === 'loading' && <p role="status">正在載入六大接案能力…</p>}
    {phase === 'ready' && snapshot && <button type="button" className="staff-next-btn" onClick={() => { setDraft(snapshot.after); setStatus(''); setPhase('editing'); }}>編輯六項偏好</button>}
    {snapshot && <div className="staff-qual-grid">
      {MANUAL_RELATION_KEYS.map((key) => <div key={key} className="staff-qual-card" role="group" aria-label={MANUAL_RELATION_LABELS[key]}>
        <h4>{MANUAL_RELATION_LABELS[key]}</h4>
        {!editing ? <p>{displayRelations(snapshot.after[key])}</p> : <>
          {draft[key].map((item, index) => <div key={index}>
            <input aria-label={MANUAL_RELATION_LABELS[key] + '值' + (index + 1)} disabled={locked} value={item.value} onChange={(event) => { setPreview(null); setStatus(''); setPhase('editing'); setDraft((current) => updateManualDraftRow(current, key, index, 'value', event.target.value)); }} />
            <input aria-label={MANUAL_RELATION_LABELS[key] + '說明' + (index + 1)} disabled={locked} value={item.detail ?? ''} onChange={(event) => { setPreview(null); setStatus(''); setPhase('editing'); setDraft((current) => updateManualDraftRow(current, key, index, 'detail', event.target.value)); }} />
          </div>)}
          <button type="button" disabled={locked} onClick={() => { setPreview(null); setStatus(''); setPhase('editing'); setDraft((current) => appendManualDraftRow(current, key)); }}>新增一列</button>
        </>}
      </div>)}
    </div>}
    {editing && <label>變更原因<input aria-label="六大接案能力變更原因" disabled={locked} value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
    <div className="staff-action-pair">
      {phase === 'editing' && <button type="button" onClick={() => void doPreview()}>預覽變更</button>}
      {phase === 'preview_ready' && <button type="button" disabled={!preview?.preview_fingerprint || !reason.trim()} onClick={() => void doApply()}>確認儲存</button>}
      {phase === 'error' && <button type="button" onClick={() => void load()}>重新查詢</button>}
    </div>
    {preview && <StaffCasePreferenceManualPreview preview={preview} />}
    {status && <p role="status">{status}</p>}
  </section>;
}

function todayIsoDate(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? '';
  return `${value('year')}-${value('month')}-${value('day')}`;
}

function qualificationSectionLabel(kind: StaffQualificationMasterViewModel['sections'][number]['kind']): string {
  return {
    skills: '技能',
    cooking: '料理能力',
    certifications: '證照',
    medical: '醫療／體檢',
    validity: '資格有效期',
    unavailability: '不可服務期間',
  }[kind];
}

function qualificationFactLabel(
  kind: StaffQualificationMasterViewModel['sections'][number]['kind'],
  code: string,
): string {
  if (kind === 'skills') return '專長';
  if (kind === 'cooking') return '料理類型';
  if (kind === 'certifications' && code === 'massage_certificate') return '寶寶按摩證照';
  if (kind === 'certifications') return '資格證明';
  if (kind === 'unavailability') return '不可服務類型';
  return '資格資料';
}

function qualificationEmptyMessage(
  section: StaffQualificationMasterViewModel['sections'][number],
): string {
  if (section.kind === 'unavailability' && section.availability === 'available') {
    return '目前沒有生效中的不可服務期間。';
  }
  return '尚未登錄。';
}

function profileItemsText(items: ReadonlyArray<{ value: string; detail: string | null }>): string {
  if (items.length === 0) return '尚未登錄';
  return items.map((item) => item.detail ? `${item.value}（${item.detail}）` : item.value).join('、');
}

function isAvailabilityOutcomeUnknown(error: unknown): boolean {
  return error instanceof StaffAvailabilityUnavailableError && error.retryable;
}

function isLifecycleOutcomeUnknown(error: unknown): boolean {
  return error instanceof StaffLifecycleUnavailableError && error.retryable;
}

function actionLocksNavigation(phase: ActionPhase): boolean {
  return phase === 'apply_pending'
    || phase === 'receipt_received'
    || phase === 'requery_loading'
    || phase === 'outcome_unknown';
}

function isEligibleEndPauseBlock(
  block: StaffAvailabilityBlockViewModel,
  staffId: number | null
): boolean {
  return staffId !== null
    && block.staffId === staffId
    && block.kind === 'paused_service'
    && block.status === 'effective'
    && block.endDate === null;
}

export const StaffPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [drawerTab, setDrawerTab] = useState<'qualification' | 'preferences' | 'unavailability'>('qualification');
  const [directory, setDirectory] = useState<DirectoryState>({ status: 'loading', items: [] });
  const [directorySearch, setDirectorySearch] = useState<DirectorySearchState>({ status: 'idle', items: [] });
  const [selectedStaff, setSelectedStaff] = useState<StaffDirectoryCardViewModel | null>(null);
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [availability, setAvailability] = useState<QueryState<StaffAvailabilityBlockViewModel[]>>({ status: 'idle' });
  const [availabilityKind, setAvailabilityKind] = useState<'create_long_leave' | 'create_pause'>('create_pause');
  const [availabilityReason, setAvailabilityReason] = useState('');
  const [cancelReason, setCancelReason] = useState('');
  const [endPauseBlockId, setEndPauseBlockId] = useState<number | null>(null);
  const [endPauseResumeDate, setEndPauseResumeDate] = useState('');
  const [endPauseReason, setEndPauseReason] = useState('');
  const [availabilityAction, setAvailabilityAction] = useState<ActionState<StaffAvailabilityPreview, StaffAvailabilityReceipt, StaffAvailabilityApplyPayload>>(initialActionState);
  const [lifecycle, setLifecycle] = useState<QueryState<StaffLifecycleViewModel>>({ status: 'idle' });
  const [qualification, setQualification] = useState<QueryState<StaffQualificationMasterViewModel>>({ status: 'idle' });
  const [profile, setProfile] = useState<QueryState<StaffProfileViewModel>>({ status: 'idle' });
  const [casePreferenceSummary, setCasePreferenceSummary] = useState<QueryState<StaffCasePreferenceSummaryViewModel>>({ status: 'idle' });
  const [lifecycleEffectiveAt, setLifecycleEffectiveAt] = useState('');
  const [lifecycleReasonCode, setLifecycleReasonCode] = useState('');
  const [lifecycleAction, setLifecycleAction] = useState<ActionState<StaffLifecyclePreview, StaffLifecycleApplyReceipt, StaffLifecycleApplyPayload> & { action: StaffLifecycleAction | null }>({
    ...initialActionState<StaffLifecyclePreview, StaffLifecycleApplyReceipt, StaffLifecycleApplyPayload>(),
    action: null,
  });
  const [showLifecycleForm, setShowLifecycleForm] = useState(false);
  const [rangeStart, setRangeStart] = useState('2026-01-01');
  const [rangeEnd, setRangeEnd] = useState('2026-12-31');
  const [sliceRetryGeneration, setSliceRetryGeneration] = useState(0);
  const mountedRef = useRef(false);
  const initialRequestedRef = useRef(false);
  const requestGenerationRef = useRef(0);
  const activeControllerRef = useRef<AbortController | null>(null);
  const searchGenerationRef = useRef(0);
  const searchControllerRef = useRef<AbortController | null>(null);
  const sliceGenerationRef = useRef(0);
  const sliceControllerRef = useRef<AbortController | null>(null);
  const availabilityQueryGenerationRef = useRef(0);
  const availabilityQueryControllerRef = useRef<AbortController | null>(null);

  const invalidateSlice = () => {
    sliceGenerationRef.current += 1;
    sliceControllerRef.current?.abort();
  };

  const beginSliceRequest = (): { generation: number; controller: AbortController } => {
    const generation = sliceGenerationRef.current + 1;
    sliceGenerationRef.current = generation;
    sliceControllerRef.current?.abort();
    const controller = new AbortController();
    sliceControllerRef.current = controller;
    return { generation, controller };
  };

  const isCurrentSlice = (generation: number, signal?: AbortSignal): boolean => (
    mountedRef.current
    && generation === sliceGenerationRef.current
    && signal?.aborted !== true
  );

  const beginAvailabilityQuery = (): { generation: number; controller: AbortController } => {
    const generation = availabilityQueryGenerationRef.current + 1;
    availabilityQueryGenerationRef.current = generation;
    availabilityQueryControllerRef.current?.abort();
    const controller = new AbortController();
    availabilityQueryControllerRef.current = controller;
    return { generation, controller };
  };

  const isCurrentAvailabilityQuery = (generation: number, signal: AbortSignal): boolean => (
    mountedRef.current
    && generation === availabilityQueryGenerationRef.current
    && !signal.aborted
  );

  const loadInitialDirectory = useCallback(async () => {
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setDirectory({ status: 'loading', items: [] });
    try {
      const response = await staffDirectoryClient.queryPage(
        { pageSize: 200 },
        { signal: controller.signal }
      );
      if (!mountedRef.current || generation !== requestGenerationRef.current) return;
      const page = adaptStaffDirectoryPage(response);
      setDirectory({ status: 'ready', items: page.items, nextCursor: page.nextCursor });
    } catch (error) {
      if (
        error instanceof StaffDirectoryAbortedError ||
        !mountedRef.current ||
        generation !== requestGenerationRef.current
      ) return;
      setDirectory({
        status: 'error',
        items: [],
        message: error instanceof Error ? error.message : '服務人員名冊載入失敗。',
        retryCursor: null,
      });
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (!initialRequestedRef.current) {
      initialRequestedRef.current = true;
      void loadInitialDirectory();
    }
    return () => {
      mountedRef.current = false;
      sliceGenerationRef.current += 1;
      sliceControllerRef.current?.abort();
      availabilityQueryGenerationRef.current += 1;
      availabilityQueryControllerRef.current?.abort();
      searchGenerationRef.current += 1;
      searchControllerRef.current?.abort();
      queueMicrotask(() => {
        if (!mountedRef.current) {
          requestGenerationRef.current += 1;
          activeControllerRef.current?.abort();
          staffDirectoryClient.resetPagination();
        }
      });
    };
  }, [loadInitialDirectory]);

  useEffect(() => {
    const query = searchQuery.trim();
    const generation = searchGenerationRef.current + 1;
    searchGenerationRef.current = generation;
    searchControllerRef.current?.abort();
    if (!query) {
      staffDirectoryClient.resetPagination();
      setDirectorySearch({ status: 'idle', items: [] });
      return undefined;
    }

    const controller = new AbortController();
    searchControllerRef.current = controller;
    setDirectorySearch((current) => ({ status: 'loading', items: current.items }));
    const timer = window.setTimeout(() => {
      void loadAllStaffDirectoryPages(
        staffDirectoryClient.queryPage.bind(staffDirectoryClient),
        { pageSize: 200 },
        { signal: controller.signal },
      ).then((page) => {
        if (!mountedRef.current || controller.signal.aborted || generation !== searchGenerationRef.current) return;
        setDirectorySearch({ status: 'ready', items: adaptStaffDirectoryPage(page).items });
      }).catch((error: unknown) => {
        if (error instanceof StaffDirectoryAbortedError || !mountedRef.current || controller.signal.aborted || generation !== searchGenerationRef.current) return;
        setDirectorySearch({ status: 'error', items: [], message: error instanceof Error ? error.message : '服務人員搜尋失敗。' });
      });
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [searchQuery]);

  useEffect(() => {
    const { generation, controller } = beginSliceRequest();
    setAvailability({ status: 'idle' });
    setAvailabilityAction(initialActionState());
    setEndPauseBlockId(null);
    setEndPauseResumeDate('');
    setEndPauseReason('');
    setLifecycle({ status: 'idle' });
    setQualification({ status: 'idle' });
    setProfile({ status: 'idle' });
    setCasePreferenceSummary({ status: 'idle' });
    setLifecycleAction({ ...initialActionState(), action: null });
    if (selectedStaffId === null) return;

    const currentStaffId = selectedStaffId;

      setProfile({ status: 'loading' });
      void staffProfileClient.query(currentStaffId, { signal: controller.signal }).then((value) => {
        if (isCurrentSlice(generation, controller.signal)) {
          setProfile({ status: 'ready', data: adaptStaffProfile(value) });
        }
      }).catch((error: unknown) => {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setProfile({ status: 'error', message: errorMessage(error, '個人與聯絡資料載入失敗。') });
      });
      setCasePreferenceSummary({ status: 'loading' });
      void staffCasePreferenceSummaryClient.query(currentStaffId, { signal: controller.signal }).then((summary) => {
        if (isCurrentSlice(generation, controller.signal)) {
          setCasePreferenceSummary({ status: 'ready', data: adaptStaffCasePreferenceSummary(summary) });
        }
      }).catch((error: unknown) => {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setCasePreferenceSummary({ status: 'error', message: errorMessage(error, '接案偏好摘要載入失敗。') });
      });
      setLifecycle({ status: 'loading' });
      void staffLifecycleClient.query(currentStaffId, { signal: controller.signal }).then((view) => {
        if (isCurrentSlice(generation, controller.signal)) {
          setLifecycle({ status: 'ready', data: adaptStaffLifecycleView(view) });
        }
      }).catch((error: unknown) => {
        if (error instanceof StaffLifecycleAbortedError || !isCurrentSlice(generation, controller.signal)) return;
        setLifecycle({ status: 'error', message: error instanceof Error ? error.message : '任職狀態載入失敗。' });
      });
      setQualification({ status: 'loading' });
      void staffQualificationMasterClient.query(currentStaffId, todayIsoDate(), { signal: controller.signal }).then((master) => {
        if (isCurrentSlice(generation, controller.signal)) {
          setQualification({ status: 'ready', data: adaptStaffQualificationMaster(master) });
        }
      }).catch((error: unknown) => {
        if (error instanceof StaffQualificationMasterError && error.code === 'STAFF_QUALIFICATION_ABORTED') return;
        if (!isCurrentSlice(generation, controller.signal)) return;
        setQualification({ status: 'error', message: error instanceof Error ? error.message : '資格主檔載入失敗。' });
      });
    return () => controller.abort();
  }, [selectedStaffId, sliceRetryGeneration]);

  useEffect(() => {
    if (selectedStaffId !== null && drawerTab === 'unavailability') {
      const from = rangeStart || '2026-01-01';
      const to = rangeEnd || '2026-12-31';
      const { generation, controller } = beginAvailabilityQuery();
      setAvailability({ status: 'loading' });
      staffAvailabilityClient
        .getBlocks(selectedStaffId, from, to, { signal: controller.signal })
        .then((blocks) => {
          if (isCurrentAvailabilityQuery(generation, controller.signal)) {
            setAvailability({ status: 'ready', data: adaptStaffAvailabilityBlocks(blocks) });
          }
        })
        .catch((error: unknown) => {
          if (isCurrentAvailabilityQuery(generation, controller.signal)) {
            setAvailability({
              status: 'error',
              message: error instanceof Error ? error.message : '不可服務期間載入失敗。',
            });
          }
        });
      return () => controller.abort();
    }
  }, [selectedStaffId, drawerTab, rangeStart, rangeEnd]);

  const queryAvailability = async () => {
    if (selectedStaffId === null || !rangeStart || !rangeEnd) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginAvailabilityQuery();
    setAvailability({ status: 'loading' });
    try {
      const blocks = await staffAvailabilityClient.getBlocks(currentStaffId, rangeStart, rangeEnd, { signal: controller.signal });
      if (isCurrentAvailabilityQuery(generation, controller.signal)) {
        setAvailability({ status: 'ready', data: adaptStaffAvailabilityBlocks(blocks) });
        setAvailabilityAction(initialActionState());
        setEndPauseBlockId(null);
      }
    } catch (error) {
      if (error instanceof StaffAvailabilityAbortedError || !isCurrentAvailabilityQuery(generation, controller.signal)) return;
      setAvailability({ status: 'error', message: error instanceof Error ? error.message : '不可服務期間載入失敗。' });
    }
  };

  const requeryAvailability = async (
    staffId: number,
    signal?: AbortSignal,
    generation?: number
  ): Promise<StaffAvailabilityBlockViewModel[] | null> => {
    const blocks = await staffAvailabilityClient.getBlocks(staffId, rangeStart, rangeEnd, { signal });
    if (generation !== undefined && !isCurrentSlice(generation, signal)) return null;
    if (!mountedRef.current || signal?.aborted === true) return null;
    const adapted = adaptStaffAvailabilityBlocks(blocks);
    setAvailability({ status: 'ready', data: adapted });
    return adapted;
  };

  const previewAvailability = async (intent: StaffAvailabilityIntent) => {
    if (selectedStaffId === null) return;
    const { generation, controller } = beginSliceRequest();
    setAvailabilityAction((current) => ({ ...current, phase: 'preview_loading', payload: null, idempotencyKey: null, message: null }));
    try {
      const preview = await staffAvailabilityClient.previewChange(selectedStaffId, intent, { signal: controller.signal });
      if (!isCurrentSlice(generation, controller.signal)) return;
      const endPauseTarget = preview.target_block;
      const invalidEndPausePreview = intent.action === 'end_pause' && (
        preview.action !== 'end_pause'
        || preview.staff_id !== selectedStaffId
        || endPauseTarget === null
        || endPauseTarget.block_id !== intent.block_id
        || endPauseTarget.staff_id !== selectedStaffId
        || endPauseTarget.kind !== 'paused_service'
        || endPauseTarget.status !== 'effective'
        || endPauseTarget.end_date !== null
      );
      if (!preview.can_apply || preview.blockers.length > 0 || invalidEndPausePreview) {
        setAvailabilityAction({
          ...initialActionState(),
          phase: 'error',
          message: invalidEndPausePreview
            ? '預覽結果中沒有同一筆可結束的暫停接案期間。'
            : preview.blockers.length > 0
              ? `預覽判定目前不可套用：${preview.blockers.join('、')}`
              : '預覽判定目前不可套用。',
        });
        return;
      }
      const payload: StaffAvailabilityApplyPayload = {
        ...intent,
        expected_version: preview.source_version,
        preview_fingerprint: preview.preview_fingerprint,
      };
      setAvailabilityAction({ phase: 'preview_ready', preview, receipt: null, payload, idempotencyKey: null, message: null });
    } catch (error) {
      if (error instanceof StaffAvailabilityAbortedError || !isCurrentSlice(generation, controller.signal)) return;
      setAvailabilityAction({ ...initialActionState(), phase: error instanceof StaffAvailabilityConflictError ? 'stale' : 'error', message: errorMessage(error, '不可服務期間預覽失敗。') });
    }
  };

  const submitAvailability = async (retry = false) => {
    if (selectedStaffId === null || availabilityAction.payload === null) return;
    const currentStaffId = selectedStaffId;
    const actionGeneration = sliceGenerationRef.current;
    const payload = availabilityAction.payload;
    const idempotencyKey = retry ? availabilityAction.idempotencyKey : nextIntentKey('staff-availability');
    if (idempotencyKey === null) return;
    setAvailabilityAction((current) => ({ ...current, phase: 'apply_pending', idempotencyKey, message: null }));
    try {
      const receipt = await staffAvailabilityClient.applyChange(currentStaffId, payload, { idempotencyKey });
      if (!isCurrentSlice(actionGeneration)) return;
      setAvailabilityAction((current) => ({ ...current, phase: 'receipt_received', receipt }));
      const { generation, controller } = beginSliceRequest();
      setAvailabilityAction((current) => ({ ...current, phase: 'requery_loading' }));
      try {
        const updated = await requeryAvailability(currentStaffId, controller.signal, generation);
        if (updated === null || !isCurrentSlice(generation, controller.signal)) return;
        if (payload.action === 'end_pause') {
          const observedBlock = updated.find((block) => block.blockId === payload.block_id);
          const observedClosedPause = receipt.action === 'end_pause'
            && receipt.staff_id === currentStaffId
            && receipt.block.block_id === payload.block_id
            && receipt.block.end_date !== null
            && observedBlock?.staffId === currentStaffId
            && observedBlock.kind === 'paused_service'
            && observedBlock.status === 'effective'
            && observedBlock.endDate === receipt.block.end_date;
          setAvailabilityAction((current) => ({
            ...current,
            phase: observedClosedPause ? 'observed' : 'observation_failed',
            message: observedClosedPause
              ? '已觀察 server 封閉暫停期間'
              : '變更已受理，但重新查詢尚未看到同一筆暫停期間已結束。',
          }));
          return;
        }
        setAvailabilityAction((current) => ({ ...current, phase: 'observed', message: '已觀察最新不可服務期間' }));
      } catch (error) {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setAvailabilityAction((current) => ({ ...current, phase: 'observation_failed', message: `變更已受理，但重新查詢失敗：${errorMessage(error, '不可服務期間查詢失敗。')}` }));
      }
    } catch (error) {
      if (!isCurrentSlice(actionGeneration)) return;
      if (error instanceof StaffAvailabilityConflictError) {
        setAvailabilityAction((current) => ({ ...current, phase: 'stale', message: error.message, idempotencyKey: null }));
      } else if (isAvailabilityOutcomeUnknown(error)) {
        setAvailabilityAction((current) => ({ ...current, phase: 'outcome_unknown', message: `結果未知：${errorMessage(error, '請以相同內容重試。')}` }));
      } else {
        setAvailabilityAction((current) => ({ ...current, phase: 'error', message: errorMessage(error, '不可服務期間套用失敗。'), idempotencyKey: null }));
      }
    }
  };

  const previewLifecycle = async (action: StaffLifecycleAction) => {
    if (
      selectedStaffId === null
      || lifecycle.status !== 'ready'
      || !lifecycleEffectiveAt
      || !lifecycleReasonCode.trim()
      || lifecycleAction.phase === 'preview_loading'
    ) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginSliceRequest();
    setLifecycleAction((current) => ({ ...current, action, phase: 'preview_loading', payload: null, idempotencyKey: null, message: null }));
    try {
      const preview = await staffLifecycleClient.preview(currentStaffId, action, {
        effective_at: lifecycleEffectiveAt,
        reason_code: lifecycleReasonCode.trim(),
      }, { signal: controller.signal });
      if (!isCurrentSlice(generation, controller.signal)) return;
      const payload: StaffLifecycleApplyPayload = {
        effective_at: lifecycleEffectiveAt,
        reason_code: lifecycleReasonCode.trim(),
        expected_version: lifecycle.data.version,
        preview_fingerprint: preview.preview_fingerprint,
      };
      setLifecycleAction({ action, phase: 'preview_ready', preview, receipt: null, payload, idempotencyKey: null, message: null });
    } catch (error) {
      if (error instanceof StaffLifecycleAbortedError || !isCurrentSlice(generation, controller.signal)) return;
      setLifecycleAction({ ...initialActionState(), action, phase: error instanceof StaffLifecycleConflictError ? 'stale' : 'error', message: errorMessage(error, '任職異動預覽失敗。') });
    }
  };

  const requeryLifecycle = async (staffId: number, signal?: AbortSignal, generation?: number): Promise<boolean> => {
    const view = await staffLifecycleClient.query(staffId, { signal });
    if (generation !== undefined && !isCurrentSlice(generation, signal)) return false;
    if (!mountedRef.current || signal?.aborted === true) return false;
    setLifecycle({ status: 'ready', data: adaptStaffLifecycleView(view) });
    return true;
  };

  const refreshLifecycleAfterStale = async () => {
    if (selectedStaffId === null) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginSliceRequest();
    setLifecycle({ status: 'loading' });
    try {
      const updated = await requeryLifecycle(currentStaffId, controller.signal, generation);
      if (!updated || !isCurrentSlice(generation, controller.signal)) return;
      setLifecycleAction({ ...initialActionState(), action: null });
    } catch (error) {
      if (!isCurrentSlice(generation, controller.signal)) return;
      setLifecycle({ status: 'error', message: errorMessage(error, '任職狀態重新查詢失敗。') });
    }
  };

  const submitLifecycle = async (retry = false) => {
    if (selectedStaffId === null || lifecycleAction.action === null || lifecycleAction.payload === null) return;
    const currentStaffId = selectedStaffId;
    const actionGeneration = sliceGenerationRef.current;
    const action = lifecycleAction.action;
    const payload = lifecycleAction.payload;
    const idempotencyKey = retry ? lifecycleAction.idempotencyKey : nextIntentKey('staff-lifecycle');
    if (idempotencyKey === null) return;
    setLifecycleAction((current) => ({ ...current, phase: 'apply_pending', idempotencyKey, message: null }));
    try {
      const receipt = await staffLifecycleClient.apply(currentStaffId, action, payload, { idempotencyKey });
      if (!isCurrentSlice(actionGeneration)) return;
      setLifecycleAction((current) => ({ ...current, phase: 'receipt_received', receipt }));
      const { generation, controller } = beginSliceRequest();
      setLifecycleAction((current) => ({ ...current, phase: 'requery_loading' }));
      try {
        const updated = await requeryLifecycle(currentStaffId, controller.signal, generation);
        if (!updated || !isCurrentSlice(generation, controller.signal)) return;
        setLifecycleAction((current) => ({ ...current, phase: 'observed', message: '已確認最新任職狀態' }));
      } catch (error) {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setLifecycleAction((current) => ({ ...current, phase: 'observation_failed', message: `變更已受理，但重新查詢失敗：${errorMessage(error, '任職狀態查詢失敗。')}` }));
      }
    } catch (error) {
      if (!isCurrentSlice(actionGeneration)) return;
      if (error instanceof StaffLifecycleConflictError) {
        setLifecycleAction((current) => ({ ...current, phase: 'stale', message: error.message, idempotencyKey: null }));
      } else if (isLifecycleOutcomeUnknown(error)) {
        setLifecycleAction((current) => ({ ...current, phase: 'outcome_unknown', message: `結果未知：${errorMessage(error, '請以相同內容重試。')}` }));
      } else {
        setLifecycleAction((current) => ({ ...current, phase: 'error', message: errorMessage(error, '任職異動套用失敗。'), idempotencyKey: null }));
      }
    }
  };

  const loadNextPage = async () => {
    if (directory.status !== 'ready' && directory.status !== 'error') return;
    const nextCursor = directory.status === 'ready' ? directory.nextCursor : directory.retryCursor;
    if (nextCursor === null) return;
    const existingItems = directory.items;
    const cursor = nextCursor;
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setDirectory({ status: 'loading-more', items: existingItems, nextCursor: cursor });
    try {
      const response = await staffDirectoryClient.queryPage(
        { pageSize: 200, afterId: cursor },
        { signal: controller.signal }
      );
      if (!mountedRef.current || generation !== requestGenerationRef.current) return;
      const page = adaptStaffDirectoryPage(response);
      setDirectory({
        status: 'ready',
        items: [...existingItems, ...page.items],
        nextCursor: page.nextCursor,
      });
    } catch (error) {
      if (
        error instanceof StaffDirectoryAbortedError ||
        !mountedRef.current ||
        generation !== requestGenerationRef.current
      ) return;
      setDirectory({
        status: 'error',
        items: existingItems,
        message: error instanceof Error ? error.message : '下一頁名冊載入失敗。',
        retryCursor: cursor,
      });
    }
  };

  const staffItems = directory.items;
  const eligibleEndPauseBlocks = availability.status === 'ready'
    ? availability.data.filter((block) => isEligibleEndPauseBlock(block, selectedStaffId))
    : [];
  const selectedEndPauseBlock = eligibleEndPauseBlocks.find((block) => block.blockId === endPauseBlockId) ?? null;
  const interactionLocked = actionLocksNavigation(availabilityAction.phase)
    || actionLocksNavigation(lifecycleAction.phase);
  const endPauseDisabledReason = availabilityAction.phase === 'stale'
    ? '資料已變更，請先重新查詢不可服務期間。'
    : eligibleEndPauseBlocks.length === 0
      ? (availability.status === 'ready'
          ? '目前查詢範圍沒有可結束的無期限暫停紀錄。'
          : '請先查詢包含目前暫停期間的日期範圍。')
      : selectedEndPauseBlock === null
        ? '請先選擇要結束的暫停接案紀錄。'
        : !endPauseResumeDate
          ? '請填寫恢復接案日期。'
          : !endPauseReason.trim()
            ? '請填寫結束暫停原因。'
            : interactionLocked
              ? '目前有其他操作進行中，請稍候。'
              : null;



  const changeSelectedStaff = (value: string) => {
    if (selectedStaff !== null) return;
    invalidateSlice();
    setSelectedStaffId(value ? Number(value) : null);
  };

  const filteredStaffItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const searchableItems = query && directorySearch.status === 'ready'
      ? directorySearch.items
      : staffItems;
    return searchableItems.filter((staff) => {
      if (query) {
        const matchId = String(staff.id).includes(query);
        const matchName = staff.displayName.toLowerCase().includes(query);
        const matchPhone = staff.displayPhone.toLowerCase().includes(query);
        if (!matchId && !matchName && !matchPhone) return false;
      }
      return true;
    });
  }, [directorySearch, staffItems, searchQuery]);

  const renderAvailabilityWorkbench = () => (
        <section className="staff-workbench" data-surface-id="staff.unavailability">
          <div className="staff-section-header">
            <div><h2>🏖️ 月嫂長假與暫停接案期間維護</h2><p>查詢後預覽變更，確認無衝突再套用。</p></div>
            <div className="staff-action-pair">
              <button type="button" data-control-id="staff.availability.create.preview" className="staff-next-btn" disabled={selectedStaffId === null || !rangeStart || (availabilityKind === 'create_long_leave' && !rangeEnd) || !availabilityReason.trim() || availabilityAction.phase === 'preview_loading' || interactionLocked || availabilityAction.phase === 'stale'} onClick={() => void previewAvailability({ action: availabilityKind, reason: availabilityReason.trim(), start_date: rangeStart, ...(availabilityKind === 'create_long_leave' ? { end_date: rangeEnd } : {}) })}>預覽新增</button>
              <button type="button" data-control-id="staff.availability.create.apply" className="staff-next-btn" disabled={availabilityAction.phase !== 'preview_ready' || !['create_long_leave', 'create_pause'].includes(availabilityAction.payload?.action ?? '')} onClick={() => void submitAvailability()}>套用新增</button>
            </div>
          </div>
          <div className="staff-range-query">
            <label>新增類型<select aria-label="新增類型" disabled={interactionLocked || availabilityAction.phase === 'stale'} value={availabilityKind} onChange={(event) => { invalidateSlice(); setAvailabilityKind(event.target.value as 'create_long_leave' | 'create_pause'); setAvailabilityAction(initialActionState()); }}><option value="create_pause">暫停接案</option><option value="create_long_leave">長假</option></select></label>
            <label>開始日期<input type="date" data-control-id="staff.availability.range-start" disabled={interactionLocked || availabilityAction.phase === 'stale'} value={rangeStart} onInput={(event) => setRangeStart(event.currentTarget.value)} onChange={(event) => { invalidateSlice(); setRangeStart(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
            <label>結束日期<input type="date" data-control-id="staff.availability.range-end" disabled={interactionLocked || availabilityAction.phase === 'stale'} value={rangeEnd} onInput={(event) => setRangeEnd(event.currentTarget.value)} onChange={(event) => { invalidateSlice(); setRangeEnd(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
            <label>新增原因<input type="text" disabled={interactionLocked || availabilityAction.phase === 'stale'} value={availabilityReason} onChange={(event) => { invalidateSlice(); setAvailabilityReason(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
            <button type="button" className="staff-next-btn" data-control-id="staff.availability.query" disabled={selectedStaffId === null || !rangeStart || !rangeEnd || availability.status === 'loading' || interactionLocked} onClick={() => void queryAvailability()}>
              {availability.status === 'loading' ? '查詢中…' : '查詢不可服務期間'}
            </button>
          </div>
          {selectedStaffId === null && <div className="staff-directory-message">請先選擇服務人員。</div>}
          {availability.status === 'error' && <div className="staff-directory-message error" role="alert">{availability.message}<button type="button" className="staff-next-btn" onClick={() => void queryAvailability()}>重試不可服務期間</button></div>}
          <div className="staff-unavailability-table" role="table" aria-label="不可服務期間">
            <div className="staff-unavailability-row header" role="row">
              <span role="columnheader">月嫂姓名</span><span role="columnheader">類別</span><span role="columnheader">不可服務區間</span><span role="columnheader">狀態／操作</span>
            </div>
            {availability.status === 'ready' && availability.data.length === 0 && <div className="staff-unavailability-row" role="row"><span role="cell">此範圍沒有不可服務紀錄。是否可派工仍需依案件日期、既有排班與資格條件查詢。</span><span role="cell">—</span><span role="cell">—</span><span role="cell">無可取消紀錄</span></div>}
            {availability.status === 'ready' && availability.data.map((block) => (
              <div className="staff-unavailability-row" role="row" key={block.blockId}>
                <span role="cell">#{block.staffId}</span><span role="cell">{block.kindLabel}</span><span role="cell">{block.startDate} ～ {block.displayEndDate}</span>
                <span role="cell" className="staff-action-pair"><span>{block.statusLabel}</span><button type="button" data-control-id="staff.availability.cancel.preview" className="staff-next-btn" disabled={!cancelReason.trim() || block.status === 'cancelled' || interactionLocked || availabilityAction.phase === 'stale'} onClick={() => void previewAvailability({ action: 'cancel', block_id: block.blockId, reason: cancelReason.trim() })}>預覽取消</button>{block.status === 'cancelled' && <small>此紀錄已取消，不可再次取消。</small>}</span>
              </div>
            ))}
            {availability.status === 'idle' && <div className="staff-unavailability-row" role="row"><span role="cell">請先設定日期範圍並查詢。</span><span role="cell">—</span><span role="cell">—</span><span role="cell">查詢後顯示可用操作</span></div>}
            {availability.status === 'loading' && <div className="staff-unavailability-row" role="row"><span role="cell">正在查詢不可服務期間…</span><span role="cell">—</span><span role="cell">—</span><span role="cell">請稍候</span></div>}
          </div>
          <div className="staff-range-query">
            <label>取消原因<input type="text" disabled={interactionLocked || availabilityAction.phase === 'stale'} value={cancelReason} onChange={(event) => { invalidateSlice(); setCancelReason(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
            <button type="button" data-control-id="staff.availability.cancel.apply" className="staff-next-btn" disabled={availabilityAction.phase !== 'preview_ready' || availabilityAction.payload?.action !== 'cancel'} onClick={() => void submitAvailability()}>套用取消</button>
          </div>
          {availabilityAction.preview && <div className="staff-action-status">預覽已完成：不可服務期間變更已通過檢查，請確認後套用。</div>}
          {availabilityAction.receipt && <div className="staff-action-status" role="status" aria-label="不可服務期間變更結果">不可服務期間已更新：{availabilityAction.receipt.block.start_date} ～ {availabilityAction.receipt.block.end_date ?? '持續中'}</div>}
          {availabilityAction.message && <div className={`staff-action-status ${availabilityAction.phase === 'error' || availabilityAction.phase === 'stale' ? 'error' : ''}`} role="status">{availabilityAction.message}</div>}
          {availabilityAction.phase === 'stale' && <button type="button" className="staff-next-btn" disabled={!rangeStart || !rangeEnd} onClick={() => void queryAvailability()}>重新查詢不可服務期間</button>}
          {availabilityAction.phase === 'outcome_unknown' && <button type="button" className="staff-next-btn" onClick={() => void submitAvailability(true)}>以相同內容重試</button>}
          <section className="staff-form-card wide" data-surface-id="staff.availability.end-pause">
            <h3>結束無指定期限的暫停接案</h3>
            <p>只列出本次查詢中屬於所選月嫂、仍生效且沒有結束日的暫停接案期間。</p>
            {endPauseDisabledReason && <p id="staff-end-pause-blocker" className="staff-directory-message" role="status">{endPauseDisabledReason}</p>}
            <div className="staff-range-query">
              <label>
                暫停接案紀錄
                <select
                  aria-label="暫停接案紀錄"
                  aria-describedby={endPauseDisabledReason ? 'staff-end-pause-blocker' : undefined}
                  disabled={eligibleEndPauseBlocks.length === 0 || interactionLocked || availabilityAction.phase === 'stale'}
                  value={endPauseBlockId ?? ''}
                  onChange={(event) => {
                    invalidateSlice();
                    setEndPauseBlockId(event.target.value ? Number(event.target.value) : null);
                    setAvailabilityAction(initialActionState());
                  }}
                >
                  <option value="">請選擇無指定結束日的暫停紀錄</option>
                  {eligibleEndPauseBlocks.map((block) => (
                    <option key={block.blockId} value={block.blockId}>{block.startDate} 起｜{block.reason}</option>
                  ))}
                </select>
              </label>
              <label>
                恢復接案日期
                <input
                  type="date"
                  aria-label="恢復接案日期"
                  aria-describedby={endPauseDisabledReason ? 'staff-end-pause-blocker' : undefined}
                  disabled={selectedEndPauseBlock === null || interactionLocked || availabilityAction.phase === 'stale'}
                  value={endPauseResumeDate}
                  onChange={(event) => {
                    invalidateSlice();
                    setEndPauseResumeDate(event.target.value);
                    setAvailabilityAction(initialActionState());
                  }}
                />
              </label>
              <label>
                結束暫停原因
                <input
                  type="text"
                  aria-label="結束暫停原因"
                  aria-describedby={endPauseDisabledReason ? 'staff-end-pause-blocker' : undefined}
                  disabled={selectedEndPauseBlock === null || interactionLocked || availabilityAction.phase === 'stale'}
                  value={endPauseReason}
                  onChange={(event) => {
                    invalidateSlice();
                    setEndPauseReason(event.target.value);
                    setAvailabilityAction(initialActionState());
                  }}
                />
              </label>
              <button
                type="button"
                data-control-id="staff.availability.end-pause"
                className="staff-next-btn"
                aria-describedby={endPauseDisabledReason ? 'staff-end-pause-blocker' : undefined}
                disabled={selectedEndPauseBlock === null || !endPauseResumeDate || !endPauseReason.trim() || interactionLocked || availabilityAction.phase === 'stale' || availabilityAction.phase === 'preview_loading'}
                onClick={() => {
                  if (!selectedEndPauseBlock) return;
                  void previewAvailability({
                    action: 'end_pause',
                    block_id: selectedEndPauseBlock.blockId,
                    resume_date: endPauseResumeDate,
                    reason: endPauseReason.trim(),
                  });
                }}
              >預覽結束暫停</button>
              <button
                type="button"
                data-control-id="staff.availability.end-pause.apply"
                className="staff-next-btn"
                disabled={availabilityAction.phase !== 'preview_ready' || availabilityAction.payload?.action !== 'end_pause'}
                onClick={() => void submitAvailability()}
              >套用結束暫停</button>
            </div>
          </section>
        </section>
  );

  return (
    <div data-surface-id="staff.page">
      <div className="page-header-banner staff-page-header">
        <div>
          <h1 className="page-title">👥 服務人員與工會成員名冊</h1>
          <p className="page-subtitle">即時搜尋月嫂、檢視資格主檔、設定接案偏好、維護長假留停與辦理人事異動。</p>
        </div>
      </div>


      <div className="staff-toolbar-card" data-surface-id="staff.toolbar">
        <div className="staff-search-input-row">
          <div className="staff-search-input-box">
            <span className="search-icon" aria-hidden="true">🔍</span>
            <input
              type="text"
              aria-label="即時搜尋月嫂"
              placeholder="搜尋月嫂姓名、電話或 Staff ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          {searchQuery && (
            <button
              type="button"
              className="staff-clear-btn"
              onClick={() => setSearchQuery('')}
            >
              ✕ 清除搜尋
            </button>
          )}
        </div>
        <div className="staff-filter-pills-row">
          <span className="staff-directory-count" role="status">
            目前已載入 {directory.items.length} 位服務人員
          </span>
          <div className="staff-query-selector" data-surface-id="staff.selector" style={{ margin: 0, padding: '4px 10px' }}>
            <label htmlFor="staff-query-staff" style={{ fontSize: '0.82rem', fontWeight: 600 }}>查詢服務人員</label>
            <select
              id="staff-query-staff"
              data-control-id="staff.selector.staff"
              disabled={interactionLocked || selectedStaff !== null}
              value={selectedStaffId ?? ''}
              onChange={(event) => changeSelectedStaff(event.target.value)}
              style={{ minHeight: '32px', fontSize: '0.82rem' }}
            >
              <option value="">請選擇服務人員</option>
              {staffItems.map((staff) => <option key={staff.id} value={staff.id}>{staff.displayName}（#{staff.id}）</option>)}
            </select>
          </div>
        </div>
      </div>

        <section data-surface-id="staff.directory">
          {selectedStaffId !== null && qualification.status === 'error' && (
            <div role="alert" className="staff-directory-message error">
              資格主檔查詢失敗：{qualification.message}
              <button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((v) => v + 1)}>
                重試資格主檔
              </button>
            </div>
          )}
          {selectedStaffId !== null && selectedStaff === null && qualification.status === 'ready' && (
            <div className="sr-only" data-surface-id="staff.qualification-master">
              <p>整體狀態：{qualification.data.overallAvailabilityLabel}</p>
              {qualification.data.sections.map((section) => {
                const label = qualificationSectionLabel(section.kind);
                return (
                  <div key={section.kind} role="group" aria-label={label}>
                    <h4>{label} · {section.availabilityLabel}</h4>
                    {section.items.length === 0 ? (
                      <small>{qualificationEmptyMessage(section)}</small>
                    ) : (
                      <ul>
                        {section.items.map((item) => (
                          <li key={item.code}>
                            <strong>{qualificationFactLabel(section.kind, item.code)}</strong>：{item.displayValue}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {directory.status === 'loading' && (
            <div className="staff-directory-message" data-control-id="staff.directory.query" role="status">
              正在載入服務人員摘要名冊…
            </div>
          )}
          {directory.status === 'error' && (
            <div className="staff-directory-message error" role="alert">
              載入服務人員名冊失敗：{directory.message}
              <button type="button" className="staff-next-btn" onClick={() => directory.retryCursor === null ? void loadInitialDirectory() : void loadNextPage()}>
                {directory.retryCursor === null ? '重試名冊查詢' : '重試載入下一頁'}
              </button>
            </div>
          )}
          {directory.status === 'ready' && staffItems.length === 0 && (
            <div className="staff-directory-message" role="status">目前沒有可顯示的服務人員摘要。</div>
          )}

          {searchQuery.trim() && directorySearch.status === 'loading' && (
            <div className="staff-directory-message" role="status">正在搜尋完整服務人員名冊…</div>
          )}
          {searchQuery.trim() && directorySearch.status === 'error' && (
            <div className="staff-directory-message error" role="alert">搜尋服務人員失敗：{directorySearch.message}</div>
          )}

          {directory.status === 'ready' && staffItems.length > 0 && directorySearch.status === 'ready' && filteredStaffItems.length === 0 && (
            <div className="staff-directory-message" role="status">
              找不到符合「{searchQuery.trim()}」的服務人員。
              <button type="button" className="staff-next-btn" onClick={() => setSearchQuery('')}>
                清除搜尋
              </button>
            </div>
          )}

          {filteredStaffItems.length > 0 && (
            <div className="staff-grid">
              {filteredStaffItems.map((staff) => (
                <article key={staff.id} className="staff-card" data-control-id={`staff.card.${staff.id}`}>
                  <div className="staff-card-header">
                    <div className="staff-avatar-name">
                      <div className="staff-avatar" aria-hidden="true">👩‍🍼</div>
                      <div>
                        <div className="staff-name">
                          {staff.displayName}
                          <span className="staff-id-badge">#{staff.id}</span>
                        </div>
                        <div className="staff-phone">電話：{staff.phone ?? '未登錄'}</div>
                        <div className="staff-phone">學歷：{staff.displayEducation}</div>
                      </div>
                    </div>
                  </div>


                  <div className="staff-card-footer">
                    <button
                      type="button"
                      data-control-id={`staff.drawer.open.${staff.id}`}
                      className="staff-view-btn"
                      aria-label={`查看 ${staff.displayName} 的詳情`}
                      aria-haspopup="dialog"
                      disabled={interactionLocked}
                      onClick={() => {
                        invalidateSlice();
                        setSelectedStaffId(staff.id);
                        setSelectedStaff(staff);
                        setDrawerTab('qualification');
                      }}
                    >
                      查看詳情 →
                    </button>
                    <button
                      type="button"
                      data-control-id={`staff.lifecycle.open.${staff.id}`}
                      className="sr-only"
                      disabled={interactionLocked}
                      onClick={() => {
                        invalidateSlice();
                        setSelectedStaffId(staff.id);
                        setSelectedStaff(staff);
                        setDrawerTab('unavailability');
                      }}
                    >
                      辦理退役／復職
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}

          {!searchQuery.trim() && directory.status === 'ready' && directory.nextCursor !== null && (
            <div className="staff-pagination">
              <button type="button" data-control-id="staff.directory.next-page" className="staff-next-btn" disabled={interactionLocked} onClick={() => void loadNextPage()}>
                載入下一頁
              </button>
            </div>
          )}
          {directory.status === 'loading-more' && <div className="staff-directory-message" role="status">正在載入下一頁摘要…</div>}
        </section>

      <Drawer
        isOpen={selectedStaff !== null}
        onClose={() => { if (!interactionLocked) setSelectedStaff(null); }}
        title={`月嫂詳情 — ${selectedStaff?.displayName ?? ''}`}
        size="wide"
        footer={
          <div className="staff-drawer-footer">
            <button type="button" data-control-id="staff.drawer.close" className="staff-close-btn" disabled={interactionLocked} onClick={() => setSelectedStaff(null)}>關閉</button>
          </div>
        }
      >
        {selectedStaff && (
          <div className="staff-drawer-content">
            <div className="staff-drawer-tabs-nav" role="tablist" aria-label="月嫂個人檔案分頁">
              <button
                type="button"
                role="tab"
                aria-selected={drawerTab === 'qualification'}
                className={`staff-drawer-tab-btn ${drawerTab === 'qualification' ? 'active' : ''}`}
                onClick={() => setDrawerTab('qualification')}
              >
                📋 完整資格主檔
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={drawerTab === 'preferences'}
                className={`staff-drawer-tab-btn ${drawerTab === 'preferences' ? 'active' : ''}`}
                onClick={() => setDrawerTab('preferences')}
              >
                🎯 接案偏好設定
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={drawerTab === 'unavailability'}
                className={`staff-drawer-tab-btn ${drawerTab === 'unavailability' ? 'active' : ''}`}
                onClick={() => setDrawerTab('unavailability')}
              >
                🏖️ 接案狀態管理 (長假與暫停／退役復職)
              </button>
            </div>

            {/* Drawer Tab 1: 完整資格主檔 */}
            {drawerTab === 'qualification' && (
              <section className="staff-drawer-section" data-surface-id="staff.qualification-master">
                {/* 基本資料摘要卡片 */}
                <div style={{ background: '#fffdfc', border: '1px solid #dec0b6', borderRadius: '12px', padding: '16px', marginBottom: '18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="staff-avatar" style={{ width: '44px', height: '44px', fontSize: '1.3rem', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#ffe4d6', borderRadius: '50%' }}>👩‍🍼</div>
                      <div>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#4a2818' }}>
                          {selectedStaff.displayName} <span className="staff-id-badge">#{selectedStaff.id}</span>
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#74593f', marginTop: '2px' }}>聯絡電話：{selectedStaff.displayPhone}</div>
                      </div>
                    </div>
                    {lifecycle.status === 'ready' && (
                      <span className={`staff-unavailable-pill ${lifecycle.data.state === 'retired' ? 'retired' : 'active'}`}>
                        {lifecycle.data.stateLabel}
                      </span>
                    )}
                  </div>
                </div>

                <h3 style={{ margin: '0 0 10px', fontSize: '1.05rem', color: '#7c2d12', fontWeight: 700 }}>
                  👤 個人與聯絡資料
                </h3>
                {profile.status === 'loading' && <p role="status">正在載入個人與聯絡資料…</p>}
                {profile.status === 'error' && (
                  <div role="alert">
                    <p>{profile.message}</p>
                    <button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((value) => value + 1)}>重試個人資料</button>
                  </div>
                )}
                {profile.status === 'ready' && (
                  <div data-surface-id="staff.profile-detail" data-testid="staff-profile-detail">
                    <div className="staff-qual-grid" style={{ marginBottom: '18px' }}>
                      {[
                      ['身分證', profile.data.identityCardLabel],
                      ['生日', profile.data.birthdayLabel],
                      ['行動電話', profile.data.phoneLabel],
                      ['市話', profile.data.telephoneLabel],
                      ['Email', profile.data.emailLabel],
                      ['居住地址', profile.data.addressLabel],
                      ['學歷', profile.data.educationLabel],
                      ['緊急聯絡人', profile.data.emergencyContactLabel],
                      ['報名日期', profile.data.registeredAtLabel],
                      ['內部行政註記', profile.data.adminNotesLabel],
                      ].map(([label, value]) => (
                        <div key={label} className="staff-qual-card" role="group" aria-label={label}>
                          <h4>{label}</h4>
                          <p style={{ margin: 0 }}>{value}</p>
                        </div>
                      ))}
                    </div>
                    <h3 className="staff-profile-subheading">🏦 銀行帳戶</h3>
                    {profile.data.bankAccountLabels.length === 0 ? (
                      <p className="staff-bank-empty">尚未登錄</p>
                    ) : (
                      <ul className="staff-bank-list" aria-label="銀行帳戶">
                        {profile.data.bankAccountLabels.map((account, index) => (
                          <li key={`${index}-${account}`}><strong>帳戶 {index + 1}</strong><span>{account}</span></li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {qualification.status === 'ready' && (
                  <>
                    <h3 style={{ margin: '0 0 10px', fontSize: '1.05rem', color: '#7c2d12', fontWeight: 700 }}>
                      🧭 服務能力與接案資料
                    </h3>
                    <div className="staff-qual-grid" style={{ marginBottom: '18px' }}>
                      {[
                        ['最多照顧寶寶數', qualification.data.service_profile.care_babies === null ? '尚未登錄' : `${qualification.data.service_profile.care_babies} 位`],
                        ['可承接區域', profileItemsText(qualification.data.service_profile.service_regions)],
                        ['可承接時段', profileItemsText(qualification.data.service_profile.service_time_slots)],
                        ['交通方式', profileItemsText(qualification.data.service_profile.transportation)],
                        ['週間服務／排休', profileItemsText(qualification.data.service_profile.weekly_rest)],
                        ['特殊節日意願', profileItemsText(qualification.data.service_profile.holiday_availability)],
                        ['可承接胎數', profileItemsText(qualification.data.service_profile.baby_types)],
                      ].map(([label, value]) => (
                        <div key={label} className="staff-qual-card" role="group" aria-label={label}>
                          <h4>{label}</h4>
                          <p style={{ margin: 0 }}>{value}</p>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {/* 6 大專業資格審核主檔 */}
                <h3 style={{ margin: '0 0 10px', fontSize: '1.05rem', color: '#7c2d12', fontWeight: 700 }}>
                  📋 完整資格與審核主檔 (6 大專業區段)
                </h3>
                {qualification.status === 'loading' && <p role="status">正在載入資格主檔…</p>}
                {qualification.status === 'error' && (
                  <div role="alert">
                    <p>{qualification.message}</p>
                    <button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((v) => v + 1)}>重試資格主檔</button>
                  </div>
                )}
                {qualification.status === 'ready' && (
                  <>
                    <p style={{ margin: '4px 0 14px', color: '#74593f', fontSize: '0.9rem' }}>
                      <strong>整體狀態：</strong>{qualification.data.overallAvailabilityLabel}
                      {' · '}資料基準日：{qualification.data.as_of}
                    </p>
                    {qualification.data.officialDataNote && (
                      <p style={{ fontSize: '0.85rem', color: '#9a3412', background: '#fff7ed', padding: '6px 12px', borderRadius: '6px', margin: '0 0 14px' }}>
                        {qualification.data.officialDataNote}
                      </p>
                    )}
                    <div className="staff-qual-grid">
                      {qualification.data.sections.map((section) => {
                        const label = qualificationSectionLabel(section.kind);
                        return (
                          <div key={section.kind} className="staff-qual-card" role="group" aria-label={label}>
                            <h4>{label} · {section.availabilityLabel}</h4>
                            {section.items.length === 0 ? (
                              <small>{qualificationEmptyMessage(section)}</small>
                            ) : (
                              <ul>
                                {section.items.map((item) => (
                                  <li key={item.code}>
                                    <strong>{qualificationFactLabel(section.kind, item.code)}</strong>：{item.displayValue}
                                  </li>
                                ))}
                              </ul>
                            )}
                            {section.dataNote && <small>{section.dataNote}</small>}
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </section>
            )}

            {/* Drawer Tab 2: 接案偏好設定 */}
            {drawerTab === 'preferences' && (
              <section className="staff-drawer-section" data-surface-id="staff.drawer.preferences">
                {casePreferenceSummary.status === 'loading' && <p role="status">正在讀取接案偏好…</p>}
                {casePreferenceSummary.status === 'error' && <p role="alert">接案偏好摘要暫時無法取得。</p>}
                {casePreferenceSummary.status === 'ready' && <details><summary>查看接案偏好摘要</summary>
                  {casePreferenceSummary.data.topics.map((topic) => <p key={topic.key}><strong>{topic.label}</strong>：{topic.valuesText}{topic.otherDetailStatus === 'ready' && topic.detailText ? `；${topic.detailText}` : ''}</p>)}
                </details>}
                {selectedStaffId !== null && <StaffCasePreferenceManualEditor staffId={selectedStaffId} />}
              </section>
            )}

            {/* Drawer Tab 3: 接案狀態管理 (採用國定假日 QUERY → PREVIEW → APPLY → RECEIPT 工作台模式) */}
            {drawerTab === 'unavailability' && (
              <section className="staff-drawer-section">
                {renderAvailabilityWorkbench()}
                {/* 區塊 1: 📇 人事任職狀態與異動辦理 */}
                <div className="staff-holiday-workbench" data-surface-id="staff.lifecycle">
                  <header className="staff-workbench-header">
                    <div>
                      <p className="staff-workbench-kicker">查詢 → 預覽 → 確認套用</p>
                      <h2 className="staff-workbench-title">📇 人事任職狀態與異動辦理</h2>
                      <p className="staff-workbench-desc">任職狀態與生效時間以正式人事資料為準，點擊「辦理異動」進行退役或復職登記。</p>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                      <span className={`staff-unavailable-pill ${lifecycle.status === 'ready' && lifecycle.data.state === 'retired' ? 'retired' : 'active'}`}>
                        {lifecycle.status === 'ready'
                          ? lifecycle.data.stateLabel
                          : lifecycle.status === 'loading'
                            ? '正在查詢任職狀態'
                            : lifecycle.status === 'error'
                              ? '任職狀態載入失敗'
                              : '尚未查詢任職狀態'}
                      </span>
                    </div>
                  </header>

                  {lifecycle.status === 'loading' && <p role="status">正在載入人事異動主檔…</p>}
                  {lifecycle.status === 'error' && (
                    <div role="alert" className="staff-directory-message error">
                      <p>{lifecycle.message}</p>
                      <button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((value) => value + 1)}>重試任職狀態</button>
                    </div>
                  )}
                  {lifecycle.status === 'ready' && (
                    <div className="staff-holiday-meta-bar">
                      <span>最近生效時間：{lifecycle.data.displayEffectiveAt}</span>
                      <span>最近異動原因：{lifecycle.data.reasonCode ?? '—'}</span>
                    </div>
                  )}
                  {lifecycle.status === 'idle' && <p>請先選擇服務人員。</p>}

                  {/* 目前任職狀態卡片 (Item list) */}
                  {lifecycle.status === 'ready' && (
                    <ul className="staff-holiday-list">
                      <li className="staff-holiday-item">
                        <div className="staff-item-left">
                          <span className="staff-item-date-badge">📅 {lifecycle.data.displayEffectiveAt} 起生效</span>
                          <span className="staff-item-title">{selectedStaff.displayName}（#{selectedStaff.id}）目前任職狀態</span>
                          <span className={`staff-item-tag ${lifecycle.data.state === 'retired' ? 'retired' : ''}`}>
                            {lifecycle.data.state === 'retired' ? '⚪ 已辦理退役（暫停派工）' : '🟢 正常在職中'}
                          </span>
                        </div>
                        <div>
                          {lifecycle.data.canRetire && (
                            <button
                              type="button"
                              className="staff-btn-item-edit"
                              onClick={() => {
                                invalidateSlice();
                                setLifecycleAction({ ...initialActionState(), action: 'retirement' });
                                setShowLifecycleForm((prev) => !prev);
                              }}
                            >
                              {showLifecycleForm && lifecycleAction.action === 'retirement' ? '✕ 收合設定' : '✏️ 辦理退役登記'}
                            </button>
                          )}
                          {lifecycle.data.canReactivate && (
                            <button
                              type="button"
                              className="staff-btn-item-edit"
                              onClick={() => {
                                invalidateSlice();
                                setLifecycleAction({ ...initialActionState(), action: 'reactivation' });
                                setShowLifecycleForm((prev) => !prev);
                              }}
                            >
                              {showLifecycleForm && lifecycleAction.action === 'reactivation' ? '✕ 收合設定' : '✏️ 辦理復職登記'}
                            </button>
                          )}
                        </div>
                      </li>
                    </ul>
                  )}

                  {/* 內嵌操作設定面板 (點擊辦理登記按鈕後展開，未展開時以 sr-only 維護測試相容) */}
                  <div className={showLifecycleForm ? 'staff-holiday-op-card' : 'sr-only'}>
                    <h3 className="staff-op-title">
                      ⚙️ 人事任職狀態變更設定
                    </h3>

                    <div className="staff-op-grid">
                      <label className="staff-op-field">
                        異動動作
                        <select disabled value={lifecycleAction.action ?? (lifecycle.status === 'ready' && lifecycle.data.state === 'retired' ? 'reactivation' : 'retirement')}>
                          <option value="retirement">辦理退役</option>
                          <option value="reactivation">辦理復職</option>
                        </select>
                      </label>
                      <label className="staff-op-field">
                        生效時間
                        <input
                          type="text"
                          disabled={interactionLocked || lifecycleAction.phase === 'stale'}
                          value={lifecycleEffectiveAt}
                          placeholder="2026-08-20T12:00:00+08:00"
                          onChange={(event) => {
                            invalidateSlice();
                            setLifecycleEffectiveAt(event.target.value);
                            setLifecycleAction((prev) => ({ ...prev, phase: 'idle', preview: null, message: null }));
                          }}
                        />
                      </label>
                      <label className="staff-op-field">
                        異動原因
                        <input
                          type="text"
                          disabled={interactionLocked || lifecycleAction.phase === 'stale'}
                          value={lifecycleReasonCode}
                          placeholder={lifecycle.status === 'ready' && lifecycle.data.state === 'retired' ? '請填寫復職原因' : '請填寫退役原因'}
                          onChange={(event) => {
                            invalidateSlice();
                            setLifecycleReasonCode(event.target.value);
                            setLifecycleAction((prev) => ({ ...prev, phase: 'idle', preview: null, message: null }));
                          }}
                        />
                      </label>
                    </div>

                    <p id="staff-lifecycle-guidance" style={{ fontSize: '0.8rem', color: '#74593f', margin: '2px 0 6px' }}>
                      在職狀態可辦理退役，已退役狀態可辦理復職；填寫生效時間與原因後，點擊「預覽影響」進行檢查，檢查通過後即可確認套用。
                    </p>

                    <div className="staff-op-actions">
                      {/* 退役按鈕組 */}
                      {(lifecycleAction.action === 'retirement' || (!lifecycleAction.action && lifecycle.status === 'ready' && lifecycle.data.canRetire)) && (
                        <>
                          <button
                            type="button"
                            aria-describedby="staff-lifecycle-guidance"
                            data-control-id="staff.lifecycle.retirement.preview"
                            className="staff-secondary-btn"
                            style={{ flex: 1 }}
                            disabled={lifecycle.status !== 'ready' || !lifecycle.data.canRetire || !lifecycleEffectiveAt || !lifecycleReasonCode.trim() || interactionLocked || lifecycleAction.phase === 'stale' || lifecycleAction.phase === 'preview_loading'}
                            onClick={() => void previewLifecycle('retirement')}
                          >
                            {lifecycleAction.phase === 'preview_loading' && lifecycleAction.action === 'retirement' ? '⏳ 預覽檢查中…' : '🔍 預覽退役影響'}
                          </button>
                          <button
                            type="button"
                            aria-describedby="staff-lifecycle-guidance"
                            data-control-id="staff.lifecycle.retirement.apply"
                            className="staff-primary-btn"
                            style={{ flex: 1 }}
                            hidden={lifecycleAction.action !== 'retirement'}
                            disabled={lifecycleAction.phase !== 'preview_ready'}
                            onClick={() => void submitLifecycle()}
                          >
                            {lifecycleAction.phase === 'apply_pending' ? '⏳ 套用中…' : '✍️ 確認套用退役'}
                          </button>
                        </>
                      )}

                      {/* 復職按鈕組 */}
                      {(lifecycleAction.action === 'reactivation' || (!lifecycleAction.action && lifecycle.status === 'ready' && lifecycle.data.canReactivate)) && (
                        <>
                          <button
                            type="button"
                            aria-describedby="staff-lifecycle-guidance"
                            data-control-id="staff.lifecycle.reactivation.preview"
                            className="staff-secondary-btn"
                            style={{ flex: 1 }}
                            disabled={lifecycle.status !== 'ready' || !lifecycle.data.canReactivate || !lifecycleEffectiveAt || !lifecycleReasonCode.trim() || interactionLocked || lifecycleAction.phase === 'stale' || lifecycleAction.phase === 'preview_loading'}
                            onClick={() => void previewLifecycle('reactivation')}
                          >
                            {lifecycleAction.phase === 'preview_loading' && lifecycleAction.action === 'reactivation' ? '⏳ 預覽檢查中…' : '🔍 預覽復職影響'}
                          </button>
                          <button
                            type="button"
                            aria-describedby="staff-lifecycle-guidance"
                            data-control-id="staff.lifecycle.reactivation.apply"
                            className="staff-primary-btn"
                            style={{ flex: 1 }}
                            hidden={lifecycleAction.action !== 'reactivation'}
                            disabled={lifecycleAction.phase !== 'preview_ready'}
                            onClick={() => void submitLifecycle()}
                          >
                            {lifecycleAction.phase === 'apply_pending' ? '⏳ 套用中…' : '✍️ 確認套用復職'}
                          </button>
                        </>
                      )}

                      {lifecycleAction.phase === 'stale' && (
                        <button type="button" className="staff-secondary-btn" onClick={() => void refreshLifecycleAfterStale()}>
                          重新查詢任職狀態
                        </button>
                      )}
                      {lifecycleAction.phase === 'outcome_unknown' && (
                        <button type="button" className="staff-primary-btn" onClick={() => void submitLifecycle(true)}>
                          以相同內容重試
                        </button>
                      )}
                    </div>

                    {lifecycleAction.preview && (
                      <div className="staff-action-status" style={{ marginTop: '6px' }}>
                        ✅ <strong>預覽已產生：</strong>{lifecycleAction.action === 'retirement' ? '辦理退役' : '辦理復職'} ｜ 生效時間：{lifecycleEffectiveAt} ｜ 變更後狀態：<strong>{lifecycleAction.preview.after_state === 'retired' ? '已退役' : '在職'}</strong>
                      </div>
                    )}
                    {lifecycleAction.message && (
                      <div className={`staff-action-status ${lifecycleAction.phase === 'error' || lifecycleAction.phase === 'stale' ? 'error' : ''}`} role="status" style={{ marginTop: '6px' }}>
                        {lifecycleAction.message}
                      </div>
                    )}
                  </div>
                </div>


              </section>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default StaffPage;
