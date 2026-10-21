import { useUnsavedDraft, useUnsavedNavigation } from '../components/UnsavedChanges';
/**
 * File: StaffPage.tsx
 * Description: 管理月嫂名冊、資格、接案偏好、不可服務期間與任職狀態。
 */
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import './StaffPage.css';
import { Drawer } from '../components/Drawer';
import { StaffRegistryEditor } from '../components/StaffRegistryEditor';
import { StaffQualificationEditor } from '../components/StaffQualificationEditor';
import {
  loadAllStaffDirectoryPages,
  staffDirectoryClient,
} from '../api/staff_directory/staff_directory_client';
import { StaffDirectoryAbortedError } from '../api/staff_directory/staff_directory_errors';
import { staffCasePreferenceManualClient } from '../api/staff_case_preferences/staff_case_preferences_client';
import type { StaffCasePreferenceManualSnapshot, StaffCasePreferenceRelations, StaffCasePreferenceOptions } from '../api/staff_case_preferences/staff_case_preferences_schemas';
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
  compareStaffUnionNumbers,
  staffDisplayLabel,
  type StaffDirectoryCardViewModel,
} from '../adapters/staff/staff_directory_adapter';
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
import type { StaffProfile } from '../api/staff_profile/staff_profile_schemas';
import type { StaffRosterServiceProfile } from '../api/staff_directory/staff_directory_schemas';

const rosterServiceColumns: Array<[keyof StaffRosterServiceProfile, string]> = [
  ['care_babies', '最多照顧寶寶數'], ['service_regions', '可承接區域'],
  ['service_time_slots', '可承接時段'], ['cooking_skills', '下廚能力'],
  ['transportation', '交通方式'], ['weekly_rest', '週間服務／排休'],
  ['holiday_availability', '特殊節日意願'], ['baby_types', '可承接胎數'],
];
const rosterServiceValue = (profile: StaffRosterServiceProfile | undefined, field: keyof StaffRosterServiceProfile) => {
  if (!profile) return '未載入';
  if (field === 'care_babies') return profile.care_babies === null ? '尚未登錄' : `${profile.care_babies} 位`;
  return profileItemsText(profile[field]);
};

const rosterProfileColumns: Array<[keyof StaffProfile, string]> = [
  ['registered_at', '登錄日期'], ['identity_card', '身分證'], ['birthday', '生日'],
  ['telephone', '市話'], ['telephone_extension', '分機'], ['email', 'Email'],
  ['city', '縣市'], ['zip_code', '郵遞區號'], ['address', '地址'],
  ['emergency_contact_name', '緊急聯絡人'], ['emergency_contact_phone', '緊急聯絡電話'],
  ['admin_notes', '行政註記'],
];
const rosterBankColumns = ['銀行代碼', '分行代碼', '銀行帳號', '主要帳戶', '帳戶狀態'];
const rosterProfileValue = (profile: StaffProfile | undefined, field: keyof StaffProfile) => {
  if (!profile) return '未載入';
  const value = profile[field];
  return value === null || value === undefined || value === '' ? '未登錄'
    : field === 'registered_at' ? String(value).slice(0, 10) : String(value);
};

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
const PREFERENCE_RELATION_KEYS = ['service_regions', 'rest_schedule'] as const;
const IMPORTED_SERVICE_KEYS = ['service_periods', 'cooking_skills', 'holiday_availability', 'baby_types'] as const;
const MANUAL_RELATION_LABELS: Record<typeof MANUAL_RELATION_KEYS[number], string> = {
  service_regions: '可承接區域', service_periods: '可承接時段', cooking_skills: '下廚能力',
  holiday_availability: '特殊節日意願', rest_schedule: '週間服務', baby_types: '可承接胎數／型態',
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
  // The existing six-relation writer receives every untouched imported fact.
  return { ...draft, ...Object.fromEntries(PREFERENCE_RELATION_KEYS.map(key => [key,
    draft[key].filter(item => item.value.trim()).map(item => ({ value: item.value.trim(), detail: item.detail })),
  ])) };
}

function displayRelations(values: readonly { value: string; detail: string | null }[]): string {
  return values.map((item) => item.detail ? item.value + '（' + item.detail + '）' : item.value).join('、') || '尚未登錄';
}

export function StaffCasePreferenceManualPreview({ preview }: { preview: StaffCasePreferenceManualSnapshot }) {
  return <div data-testid="staff-case-preference-manual-preview">
    <h4>服務偏好變更預覽</h4>
    {PREFERENCE_RELATION_KEYS.map((key) => <div key={key}>
      <span>{MANUAL_RELATION_LABELS[key]}（變更前）: {displayRelations(preview.before[key])}</span>
      {' '}
      <span>{MANUAL_RELATION_LABELS[key]}（變更後）: {displayRelations(preview.after[key])}</span>
    </div>)}
  </div>;
}

export function StaffCasePreferenceManualEditor({ staffId, surfaceId = 'staff.drawer.case-preference-manual', onUpdated, directEditing = false, renderQualifications }: { staffId: number; surfaceId?: string; onUpdated?: () => void | Promise<void>; directEditing?: boolean; renderQualifications?: (information: React.ReactNode) => React.ReactNode }) {
  const saveGuidanceId = useId();
  const [snapshot, setSnapshot] = useState<StaffCasePreferenceManualSnapshot | null>(null);
  const [draft, setDraft] = useState<StaffCasePreferenceRelations>(() => EMPTY_MANUAL_RELATIONS);
  const [preview, setPreview] = useState<StaffCasePreferenceManualSnapshot | null>(null);
  const [reason, setReason] = useState('');
  const [status, setStatus] = useState('');
  const [statusError, setStatusError] = useState(false);
  const [options, setOptions] = useState<StaffCasePreferenceOptions | null>(null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'editing' | 'previewing' | 'preview_ready' | 'applying' | 'error'>('loading');
  const [applying, setApplying] = useState(false);
  const loadEpoch = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setPhase('loading');
    setStatusError(false);
    setSnapshot(null);
    setPreview(null);
    setReason('');
    setStatus('');
    try {
      const [next, choices] = await Promise.all([
        staffCasePreferenceManualClient.query(staffId, { signal: controller.signal }),
        staffCasePreferenceManualClient.queryOptions({ signal: controller.signal }),
      ]);
      if (epoch !== loadEpoch.current) return false;
      setSnapshot(next);
      setDraft(next.after);
      setOptions(choices);
      setPhase(directEditing ? 'editing' : 'ready');
      return true;
    } catch (error) {
      if (epoch === loadEpoch.current) {
        setPhase('error');
        setStatusError(true);
        setStatus(error instanceof Error ? error.message : '服務偏好載入失敗。');
      }
      return false;
    }
  }, [staffId, directEditing]);
  useEffect(() => {
    void load();
    return () => {
      loadEpoch.current += 1;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
    };
  }, [load]);
  const doApply = async () => {
    if (!snapshot || !['editing', 'preview_ready'].includes(phase)) return;
    if (PREFERENCE_RELATION_KEYS.some(key => draft[key].some(item => !item.value.trim()))) { setStatusError(true); setStatus('請選擇新增條件，或移除尚未選擇的項目。'); return; }
    setStatusError(false);
    const epoch = loadEpoch.current;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setPhase('applying');
    setApplying(true);
    setStatus('');
    try {
      const approved = preview ?? await staffCasePreferenceManualClient.preview(staffId, requestRelations(draft), { signal: controller.signal });
      if (epoch !== loadEpoch.current) return;
      await staffCasePreferenceManualClient.apply(staffId, {
        ...requestRelations(draft),
        expected_snapshot_fingerprint: snapshot.snapshot_fingerprint,
        preview_fingerprint: approved.preview_fingerprint!,
        reason: reason.trim(),
      }, { idempotencyKey: nextIntentKey('staff-case-preference-manual'), signal: controller.signal });
      if (epoch !== loadEpoch.current) return;
      if (await load()) { setStatus('已儲存並重新查詢服務偏好。'); await onUpdated?.(); }
    } catch (error) {
      if (epoch === loadEpoch.current) {
        setPhase('error');
        setStatusError(true);
        setStatus(error instanceof Error ? error.message : '儲存結果尚未確認，請重新查詢。');
      }
    } finally {
      setApplying(false);
    }
  };
  const editing = ['editing', 'previewing', 'preview_ready', 'applying'].includes(phase);
  const locked = phase === 'loading' || phase === 'previewing' || applying;
  const editRow = (key: ManualRelationKey, index: number, field: 'value' | 'detail', value: string) => {
    setPreview(null); setStatus(''); setPhase('editing');
    setDraft(current => { const next = updateManualDraftRow(current, key, index, field, value); if (field === 'value' && value !== current[key][index].value) next[key][index].detail = null; return next; });
  };
  useUnsavedDraft('服務偏好', { '接案能力': draft, '備註': reason }, { enabled: !!snapshot, baseline: snapshot ? { '接案能力': snapshot.after, '備註': '' } : null, busy: phase === 'previewing' || applying });

  const importedInformation = <section className="staff-imported-service-information" aria-label="匯入服務資訊">
    <h4>匯入服務資訊</h4>
    <p>原登錄內容保留，供查閱，不列入配對條件。</p>
    {snapshot ? <dl className="staff-imported-service-grid">{IMPORTED_SERVICE_KEYS.map(key => <div key={key}>
      <dt>{MANUAL_RELATION_LABELS[key]}</dt><dd>{displayRelations(snapshot.after[key])}</dd>
    </div>)}</dl> : <p>{phase === 'loading' ? '正在載入匯入服務資訊…' : '匯入服務資訊尚未取得，請重新查詢。'}</p>}
  </section>;

  return <>
    {renderQualifications ? renderQualifications(importedInformation) : <section aria-label="專業資格與服務資料"><h3>專業資格與服務資料</h3>{importedInformation}</section>}
    <section data-surface-id={surfaceId} aria-label="服務偏好">
      <h3>服務偏好</h3>
      <p>只維護可承接區域與週間服務。配對池顯示符合狀態及月嫂登錄值，不因偏好排除人選。</p>
      {phase === 'loading' && <p role="status">正在載入服務偏好…</p>}
      {phase === 'ready' && snapshot && <button type="button" className="staff-next-btn" onClick={() => { setDraft(snapshot.after); setStatus(''); setPhase('editing'); }}>編輯服務偏好</button>}
      {snapshot && options && <div className="staff-qual-grid staff-preference-grid">
        {PREFERENCE_RELATION_KEYS.map(key => <div key={key} className="staff-qual-card" role="group" aria-label={MANUAL_RELATION_LABELS[key]}>
          <h4>{MANUAL_RELATION_LABELS[key]}</h4>
          {!editing ? <p>{displayRelations(snapshot.after[key])}</p> : <>
            {draft[key].length === 0 && <p className="staff-manual-empty">尚未設定條件</p>}
            {draft[key].map((item, index) => <div className="staff-manual-condition" key={index}>
              <div className="staff-manual-condition-main">
                <select aria-label={MANUAL_RELATION_LABELS[key] + '值' + (index + 1)} disabled={locked} value={item.value} onChange={event => editRow(key, index, 'value', event.target.value)}>
                  <option value="">請選擇條件</option>
                  {item.value && !options[key].includes(item.value) && <option value={item.value}>既有值：{item.value}</option>}
                  {options[key].map(value => <option key={value} value={value} disabled={draft[key].some((row, rowIndex) => rowIndex !== index && row.value === value)}>{value}</option>)}
                </select>
                <button type="button" className="staff-secondary-btn" disabled={locked} aria-label={`移除${MANUAL_RELATION_LABELS[key]}第${index + 1}項`} onClick={() => { setPreview(null); setStatus(''); setPhase('editing'); setDraft(current => ({ ...current, [key]: current[key].filter((_, rowIndex) => rowIndex !== index) })); }}>移除</button>
              </div>
              {item.detail && <small className="staff-source-note">來源資料：{item.detail}</small>}
            </div>)}
            <button type="button" className="staff-secondary-btn" aria-label={`新增${MANUAL_RELATION_LABELS[key]}條件`} disabled={locked || draft[key].some(item => !item.value) || options[key].every(value => draft[key].some(item => item.value === value))} onClick={() => { setPreview(null); setStatus(''); setPhase('editing'); setDraft(current => appendManualDraftRow(current, key)); }}>＋ 新增條件</button>
          </>}
        </div>)}
      </div>}
      {editing && <label className="staff-op-field">備註（選填）<input aria-label="接案條件備註（選填）" placeholder="有需要補充的內容再填寫" disabled={locked} value={reason} onChange={event => { setReason(event.target.value); if (statusError) { setStatusError(false); setStatus(''); } }} /></label>}
      {editing && <p id={saveGuidanceId} className="staff-op-hint">{locked ? '正在處理，請稍候。' : '可直接儲存；備註可留白。'}</p>}
      <div className="staff-op-actions">
        {editing && <button type="button" className="staff-secondary-btn" disabled={locked} onClick={() => { if (snapshot) setDraft(snapshot.after); setPreview(null); setReason(''); setStatus('已取消變更。'); setStatusError(false); setPhase(directEditing ? 'editing' : 'ready'); }}>取消變更</button>}
        {editing && <button type="button" className="staff-primary-btn" aria-describedby={saveGuidanceId} disabled={locked} onClick={() => void doApply()}>儲存服務偏好</button>}
        {phase === 'error' && <button type="button" className="staff-secondary-btn" onClick={() => void load()}>重新查詢</button>}
      </div>
      {preview && <StaffCasePreferenceManualPreview preview={preview} />}
      {status && <p role={statusError ? 'alert' : 'status'} className={statusError ? 'staff-op-error' : undefined}>{status}</p>}
    </section>
  </>;
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
  const [directory, setDirectory] = useState<DirectoryState>({ status: 'loading', items: [] });
  const [rosterLifecycle, setRosterLifecycle] = useState<'active' | 'retired'>('active');
  const rosterTabsId = useId();
  const [directorySearch, setDirectorySearch] = useState<DirectorySearchState>({ status: 'idle', items: [] });
  const [selectedStaff, setSelectedStaff] = useState<StaffDirectoryCardViewModel | null>(null);
  const drawerStaffId = selectedStaff?.id ?? null;
  const [openAtStatus, setOpenAtStatus] = useState(false);
  const statusSectionRef = useRef<HTMLElement>(null);
  const [resumeContainer, setResumeContainer] = useState<HTMLElement | null>(null);
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [availability, setAvailability] = useState<QueryState<StaffAvailabilityBlockViewModel[]>>({ status: 'idle' });
  const [availabilityKind, setAvailabilityKind] = useState<'create_long_leave' | 'create_pause'>('create_long_leave');
  const [showAvailabilityForm, setShowAvailabilityForm] = useState(false);
  const [availabilityStart, setAvailabilityStart] = useState(todayIsoDate);
  const [availabilityEnd, setAvailabilityEnd] = useState(todayIsoDate);
  const [availabilityReason, setAvailabilityReason] = useState('');
  const [cancelReason, setCancelReason] = useState('');
  const [endPauseBlockId, setEndPauseBlockId] = useState<number | null>(null);
  const [endPauseResumeDate, setEndPauseResumeDate] = useState('');
  const [endPauseReason, setEndPauseReason] = useState('');
  const [availabilityAction, setAvailabilityAction] = useState<ActionState<StaffAvailabilityPreview, StaffAvailabilityReceipt, StaffAvailabilityApplyPayload>>(initialActionState);
  const [lifecycle, setLifecycle] = useState<QueryState<StaffLifecycleViewModel>>({ status: 'idle' });
  const [qualification, setQualification] = useState<QueryState<StaffQualificationMasterViewModel>>({ status: 'idle' });
  const [profile, setProfile] = useState<QueryState<StaffProfileViewModel>>({ status: 'idle' });
  const [lifecycleEffectiveAt, setLifecycleEffectiveAt] = useState('');
  const [lifecycleReasonCode, setLifecycleReasonCode] = useState('');
  const [lifecycleAction, setLifecycleAction] = useState<ActionState<StaffLifecyclePreview, StaffLifecycleApplyReceipt, StaffLifecycleApplyPayload> & { action: StaffLifecycleAction | null }>({
    ...initialActionState<StaffLifecyclePreview, StaffLifecycleApplyReceipt, StaffLifecycleApplyPayload>(),
    action: null,
  });
  const [showLifecycleForm, setShowLifecycleForm] = useState(false);
  const [sliceRetryGeneration, setSliceRetryGeneration] = useState(0);
  const mountedRef = useRef(false);
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
    activeControllerRef.current?.abort();
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setDirectory({ status: 'loading', items: [] });
    try {
      const response = await loadAllStaffDirectoryPages(
        staffDirectoryClient.queryPage.bind(staffDirectoryClient),
        { pageSize: 200, includeProfile: true, lifecycleState: rosterLifecycle },
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
  }, [rosterLifecycle]);

  useEffect(() => {
    mountedRef.current = true;
    void loadInitialDirectory();
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
      setDirectorySearch({ status: 'idle', items: [] });
      return undefined;
    }

    const controller = new AbortController();
    searchControllerRef.current = controller;
    setDirectorySearch((current) => ({ status: 'loading', items: current.items }));
    const timer = window.setTimeout(() => {
      void loadAllStaffDirectoryPages(
        staffDirectoryClient.queryPage.bind(staffDirectoryClient),
        { pageSize: 200, includeProfile: true, lifecycleState: rosterLifecycle },
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
  }, [searchQuery, rosterLifecycle]);

  const refreshProfile = async (staffId: number, generation: number, signal?: AbortSignal): Promise<void> => {
    const value = await staffProfileClient.query(staffId, { signal });
    if (!isCurrentSlice(generation, signal)) throw new Error('月嫂資料已切換，請重新確認。');
    setProfile({ status: 'ready', data: adaptStaffProfile(value) });
    const refreshed = adaptStaffDirectoryPage({ items: [{
      id: value.staff_id, union_no: value.union_no ?? null, name: value.name,
      phone: value.phone, education: value.education, profile: value,
    }], next_cursor: null }).items[0];
    setDirectory((current) => ({ ...current, items: current.items.map((staff) => staff.id === refreshed.id ? { ...staff, ...refreshed } : staff) }));
    setDirectorySearch((current) => ({ ...current, items: current.items.map((staff) => staff.id === refreshed.id ? { ...staff, ...refreshed } : staff) }));
    setSelectedStaff((current) => current?.id === refreshed.id ? { ...current, ...refreshed } : current);
  };

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
    setLifecycleAction({ ...initialActionState(), action: null });
    if (selectedStaffId === null) return;

    const currentStaffId = selectedStaffId;

      setProfile({ status: 'loading' });
      void refreshProfile(currentStaffId, generation, controller.signal).catch((error: unknown) => {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setProfile({ status: 'error', message: errorMessage(error, '個人與聯絡資料載入失敗。') });
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
          const serviceProfile: StaffRosterServiceProfile = {
            ...master.service_profile,
            cooking_skills: (master.sections.find(section => section.kind === 'cooking')?.items ?? [])
              .filter(item => typeof item.value === 'string')
              .map(item => ({ value: String(item.value), detail: item.detail })),
          };
          const refreshService = (staff: StaffDirectoryCardViewModel) => staff.id === currentStaffId ? { ...staff, serviceProfile } : staff;
          setDirectory(current => ({ ...current, items: current.items.map(refreshService) }));
          setDirectorySearch(current => ({ ...current, items: current.items.map(refreshService) }));
          setSelectedStaff(current => current ? refreshService(current) : current);
        }
      }).catch((error: unknown) => {
        if (error instanceof StaffQualificationMasterError && error.code === 'STAFF_QUALIFICATION_ABORTED') return;
        if (!isCurrentSlice(generation, controller.signal)) return;
        setQualification({ status: 'error', message: error instanceof Error ? error.message : '資格主檔載入失敗。' });
      });
    return () => controller.abort();
  }, [selectedStaffId, sliceRetryGeneration]);

  useEffect(() => {
    if (selectedStaffId !== null && drawerStaffId === selectedStaffId) {
      const { generation, controller } = beginAvailabilityQuery();
      setAvailability({ status: 'loading' });
      staffAvailabilityClient
        .getAllBlocks(selectedStaffId, { signal: controller.signal })
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
  }, [selectedStaffId, drawerStaffId]);

  const queryAvailability = async () => {
    if (selectedStaffId === null) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginAvailabilityQuery();
    setAvailability({ status: 'loading' });
    try {
      const blocks = await staffAvailabilityClient.getAllBlocks(currentStaffId, { signal: controller.signal });
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
    const blocks = await staffAvailabilityClient.getAllBlocks(staffId, { signal });
    if (generation !== undefined && !isCurrentSlice(generation, signal)) return null;
    if (!mountedRef.current || signal?.aborted === true) return null;
    const adapted = adaptStaffAvailabilityBlocks(blocks);
    setAvailability({ status: 'ready', data: adapted });
    return adapted;
  };

  const refreshQualificationSummary = async (staffId: number, signal: AbortSignal, generation: number) => {
    setQualification({ status: 'loading' });
    try {
      const master = await staffQualificationMasterClient.query(staffId, todayIsoDate(), { signal });
      if (isCurrentSlice(generation, signal)) setQualification({ status: 'ready', data: adaptStaffQualificationMaster(master) });
    } catch (error) {
      if (isCurrentSlice(generation, signal)) setQualification({ status: 'error', message: errorMessage(error, '資格主檔重新查詢失敗。') });
    }
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
      const prepared = { phase: 'preview_ready' as const, preview, receipt: null, payload, idempotencyKey: null, message: null };
      setAvailabilityAction(prepared);
      await submitAvailability(false, prepared);
    } catch (error) {
      if (error instanceof StaffAvailabilityAbortedError || !isCurrentSlice(generation, controller.signal)) return;
      setAvailabilityAction({ ...initialActionState(), phase: error instanceof StaffAvailabilityConflictError ? 'stale' : 'error', message: errorMessage(error, '不可服務期間預覽失敗。') });
    }
  };

  const submitAvailability = async (retry = false, prepared = availabilityAction) => {
    if (selectedStaffId === null || prepared.payload === null) return;
    const currentStaffId = selectedStaffId;
    const actionGeneration = sliceGenerationRef.current;
    const payload = prepared.payload;
    const idempotencyKey = retry ? prepared.idempotencyKey : nextIntentKey('staff-availability');
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
          if (observedClosedPause) void refreshQualificationSummary(currentStaffId, controller.signal, generation);
          return;
        }
        setAvailabilityAction((current) => ({ ...current, phase: 'observed', message: '已觀察最新不可服務期間' }));
        void refreshQualificationSummary(currentStaffId, controller.signal, generation);
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
      || lifecycleAction.phase === 'preview_loading'
    ) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginSliceRequest();
    setLifecycleAction((current) => ({ ...current, action, phase: 'preview_loading', payload: null, idempotencyKey: null, message: null }));
    try {
      const effectiveAt = `${lifecycleEffectiveAt}T00:00:00+08:00`;
      const preview = await staffLifecycleClient.preview(currentStaffId, action, {
        effective_at: effectiveAt,
        reason_code: lifecycleReasonCode.trim(),
      }, { signal: controller.signal });
      if (!isCurrentSlice(generation, controller.signal)) return;
      const payload: StaffLifecycleApplyPayload = {
        effective_at: effectiveAt,
        reason_code: lifecycleReasonCode.trim(),
        expected_version: lifecycle.data.version,
        preview_fingerprint: preview.preview_fingerprint,
      };
      const prepared = { action, phase: 'preview_ready' as const, preview, receipt: null, payload, idempotencyKey: null, message: null };
      setLifecycleAction(prepared);
      await submitLifecycle(false, prepared);
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
    if (view.state !== rosterLifecycle) {
      setDirectory((current) => ({ ...current, items: current.items.filter((staff) => staff.id !== staffId) }));
      setDirectorySearch((current) => ({ ...current, items: current.items.filter((staff) => staff.id !== staffId) }));
    }
    setLifecycleReasonCode('');
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

  const submitLifecycle = async (retry = false, prepared = lifecycleAction) => {
    if (selectedStaffId === null || prepared.action === null || prepared.payload === null) return;
    const currentStaffId = selectedStaffId;
    const actionGeneration = sliceGenerationRef.current;
    const action = prepared.action;
    const payload = prepared.payload;
    const idempotencyKey = retry ? prepared.idempotencyKey : nextIntentKey('staff-lifecycle');
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
        { pageSize: 200, afterId: cursor, includeProfile: true, lifecycleState: rosterLifecycle },
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

  const staffItems = useMemo(() => [...directory.items].sort(compareStaffUnionNumbers), [directory.items]);
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
          ? '沒有可恢復的無期限暫停接案紀錄。'
          : '正在載入暫停接案紀錄。')
      : selectedEndPauseBlock === null
        ? '請先選擇要結束的暫停接案紀錄。'
        : !endPauseResumeDate
          ? '請填寫恢復接案日期。'
          : interactionLocked
              ? '目前有其他操作進行中，請稍候。'
              : null;



  const { requestLeave } = useUnsavedNavigation();
  const changeSelectedStaff = (value: string) => {
    if (selectedStaff !== null) return;
    invalidateSlice();
    setSelectedStaffId(value ? Number(value) : null);
  };

  const openStaffDetail = (staff: StaffDirectoryCardViewModel) => {
    if (interactionLocked) return;
    if (selectedStaffId !== staff.id) invalidateSlice();
    setSelectedStaffId(staff.id);
    setSelectedStaff(staff);
    setOpenAtStatus(false);
  };

  useEffect(() => {
    if (drawerStaffId !== null && openAtStatus) statusSectionRef.current?.scrollIntoView({ block: 'start' });
  }, [drawerStaffId, openAtStatus]);

  const filteredStaffItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const searchableItems = query && directorySearch.status === 'ready'
      ? directorySearch.items
      : staffItems;
    return searchableItems.filter((staff) => {
      if (query) {
        const matchId = (staff.unionNo ?? '').toLowerCase().includes(query);
        const matchName = staff.displayName.toLowerCase().includes(query);
        const matchPhone = staff.displayPhone.toLowerCase().includes(query);
        if (!matchId && !matchName && !matchPhone) return false;
      }
      return true;
    }).sort(compareStaffUnionNumbers);
  }, [directorySearch, staffItems, searchQuery]);

  const resetAvailabilityForm = () => {
    setShowAvailabilityForm(false);
    setAvailabilityKind('create_long_leave');
    setAvailabilityStart(todayIsoDate());
    setAvailabilityEnd(todayIsoDate());
    setAvailabilityReason('');
  };

  useEffect(() => {
    resetAvailabilityForm();
    setCancelReason('');
  }, [drawerStaffId]);

  useEffect(() => {
    if (availabilityAction.phase === 'observed') {
      resetAvailabilityForm();
      setCancelReason('');
      setEndPauseBlockId(null);
      setEndPauseReason('');
    }
  }, [availabilityAction.phase]);

  const availabilityToday = todayIsoDate();
  const availabilityState = (block: StaffAvailabilityBlockViewModel) => block.status === 'cancelled'
    ? 'cancelled' : block.startDate > availabilityToday ? 'upcoming'
      : block.endDate !== null && block.endDate < availabilityToday ? 'ended' : 'paused';
  const availabilityRecords = availability.status === 'ready' ? availability.data : [];
  const currentPauses = availabilityRecords.filter(block => availabilityState(block) === 'paused');
  const upcomingPauses = availabilityRecords.filter(block => availabilityState(block) === 'upcoming');
  const historicalPauses = availabilityRecords.filter(block => ['ended', 'cancelled'].includes(availabilityState(block)));
  const renderAvailabilityRecords = (blocks: StaffAvailabilityBlockViewModel[], label: string) => (
    <div className="staff-unavailability-table" role="table" aria-label={label}>
      <div className="staff-availability-row header" role="row"><span role="columnheader">類型</span><span role="columnheader">暫停期間</span><span role="columnheader">狀態／操作</span></div>
      {blocks.map(block => {
        const state = availabilityState(block);
        return <div className={`staff-availability-row is-${state}`} role="row" key={block.blockId}>
          <span role="cell">{block.kind === 'long_leave' ? '暫停接案' : '無期限暫停接案'}</span>
          <span role="cell">{block.startDate} ～ {block.endDate ?? '無期限'}</span>
          <span role="cell" className="staff-action-pair">
            <span className={`staff-availability-badge is-${state}`}>{({ cancelled: '已取消，不影響接案', upcoming: '尚未開始', ended: '已結束', paused: '暫停中' })[state]}</span>
            {(state === 'paused' || state === 'upcoming') && <button type="button" data-control-id="staff.availability.cancel.preview" className="staff-secondary-btn" disabled={interactionLocked || availabilityAction.phase === 'stale'} onClick={() => void previewAvailability({ action: 'cancel', block_id: block.blockId, reason: cancelReason.trim() })}>取消此期間</button>}
            {isEligibleEndPauseBlock(block, selectedStaffId) && <button type="button" className="staff-next-btn" aria-expanded={endPauseBlockId === block.blockId} disabled={interactionLocked || availabilityAction.phase === 'stale'} onClick={() => { setEndPauseBlockId(block.blockId); setEndPauseResumeDate(todayIsoDate()); setEndPauseReason(''); }}>{state === 'upcoming' ? '設定恢復日期' : '恢復接案'}</button>}
          </span>
        </div>;
      })}
    </div>
  );

  const renderAvailabilityWorkbench = () => (
    <section className="staff-workbench staff-availability-workbench" data-surface-id="staff.unavailability">
      <div className="staff-availability-header">
        <p className="staff-availability-person">{selectedStaff ? staffDisplayLabel(selectedStaff.unionNo, selectedStaff.displayName) : '請先選擇月嫂'}</p>
        {!showAvailabilityForm && <button type="button" className="staff-next-btn" aria-expanded={false} aria-controls="staff-availability-create-form" disabled={interactionLocked || availabilityAction.phase === 'stale'} onClick={() => { resetAvailabilityForm(); setShowAvailabilityForm(true); }}>新增</button>}
      </div>
      {availability.status === 'ready' && <div className={`staff-availability-summary ${currentPauses.length > 0 ? 'is-paused' : 'is-clear'}`} role="status" aria-label="目前暫停接案狀態">
        <strong>目前：{currentPauses.length > 0 ? '暫停接案中' : '未暫停接案'}</strong>
        <p>{currentPauses.length > 0 ? '目前位於暫停期間內，該期間不能安排新接案。' : '目前沒有生效中的暫停期間。'}{upcomingPauses.length > 0 ? ` 另有 ${upcomingPauses.length} 筆未來暫停。` : ''}</p>
        <small>實際可派工仍依案件日期、既有排班與資格判定。</small>
      </div>}
      {showAvailabilityForm && <section id="staff-availability-create-form" className="staff-holiday-op-card" aria-label="新增暫停接案">
        <h3 className="staff-op-title">新增暫停接案</h3>
        <div className="staff-op-grid staff-availability-form-grid">
          <label className="staff-op-field">類型<select aria-label="新增類型" value={availabilityKind} disabled={interactionLocked} onChange={event => { invalidateSlice(); setAvailabilityKind(event.target.value as typeof availabilityKind); setAvailabilityAction(initialActionState()); }}><option value="create_long_leave">暫停接案</option><option value="create_pause">無期限暫停接案</option></select></label>
          <label className="staff-op-field">開始日期<input type="date" data-control-id="staff.availability.range-start" value={availabilityStart} disabled={interactionLocked} onChange={event => { invalidateSlice(); setAvailabilityStart(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
          {availabilityKind === 'create_long_leave' && <label className="staff-op-field">結束日期<input type="date" data-control-id="staff.availability.range-end" value={availabilityEnd} disabled={interactionLocked} onChange={event => { invalidateSlice(); setAvailabilityEnd(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>}
        </div>
        {availabilityKind === 'create_pause' && <p className="staff-op-hint">從開始日期起暫停接案，直到另行設定恢復接案日期。</p>}
        <label className="staff-op-field">備註（選填）<input aria-label="新增暫停備註（選填）" value={availabilityReason} maxLength={500} disabled={interactionLocked} onChange={event => { invalidateSlice(); setAvailabilityReason(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
        <div className="staff-op-actions">
          <button type="button" className="staff-secondary-btn" disabled={interactionLocked} onClick={resetAvailabilityForm}>取消新增</button>
          <button type="button" data-control-id="staff.availability.create.preview" className="staff-primary-btn" disabled={selectedStaffId === null || !availabilityStart || (availabilityKind === 'create_long_leave' && !availabilityEnd) || interactionLocked || availabilityAction.phase === 'preview_loading' || availabilityAction.phase === 'stale'} onClick={() => void previewAvailability({ action: availabilityKind, reason: availabilityReason.trim(), start_date: availabilityStart, ...(availabilityKind === 'create_long_leave' ? { end_date: availabilityEnd } : {}) })}>儲存新增</button>
        </div>
      </section>}
      {(availability.status === 'idle' || availability.status === 'loading') && <p role="status">正在載入暫停接案紀錄…</p>}
      {availability.status === 'error' && <div className="staff-directory-message error" role="alert">{availability.message}<button type="button" className="staff-next-btn" onClick={() => void queryAvailability()}>重試不可服務期間</button></div>}
      {availability.status === 'ready' && <>
        {availabilityRecords.length === 0 && <p className="staff-availability-empty">無</p>}
        {currentPauses.length > 0 && renderAvailabilityRecords(currentPauses, '目前暫停紀錄')}
        {upcomingPauses.length > 0 && <section className="staff-availability-record-group" aria-label="未來暫停"><h3>未來暫停</h3>{renderAvailabilityRecords(upcomingPauses, '未來暫停紀錄')}</section>}
        {historicalPauses.length > 0 && <details key={selectedStaffId} className="staff-availability-history"><summary>歷史與已取消紀錄（{historicalPauses.length}）</summary>{renderAvailabilityRecords(historicalPauses, '歷史與已取消紀錄')}</details>}
        {(currentPauses.length > 0 || upcomingPauses.length > 0) && <details className="staff-availability-cancel-note"><summary>取消紀錄備註（選填）</summary><label className="staff-op-field">備註（選填）<input aria-label="取消暫停備註（選填）" value={cancelReason} maxLength={500} disabled={interactionLocked} onChange={event => { invalidateSlice(); setCancelReason(event.target.value); setAvailabilityAction(initialActionState()); }} /></label></details>}
      </>}
      {availabilityAction.preview && ['preview_ready', 'apply_pending', 'receipt_received', 'requery_loading'].includes(availabilityAction.phase) && <div className="staff-action-status">正在儲存並更新暫停紀錄…</div>}
      {availabilityAction.receipt && <div className="staff-action-status" role="status" aria-label="不可服務期間變更結果">{availabilityAction.receipt.action === 'cancel' ? '這筆暫停紀錄已取消，不再影響接案。' : availabilityAction.receipt.action === 'end_pause' ? `已設定 ${availabilityAction.payload?.resume_date} 起恢復接案。` : '暫停紀錄已儲存。'}</div>}
      {availabilityAction.message && availabilityAction.phase !== 'observed' && <div className={`staff-action-status ${availabilityAction.phase === 'error' || availabilityAction.phase === 'stale' ? 'error' : ''}`} role="status">{availabilityAction.message}</div>}
      {availabilityAction.phase === 'stale' && <button type="button" className="staff-next-btn" onClick={() => void queryAvailability()}>重新載入紀錄</button>}
      {availabilityAction.phase === 'outcome_unknown' && <button type="button" className="staff-next-btn" onClick={() => void submitAvailability(true)}>以相同內容重試</button>}
      {selectedEndPauseBlock && <section className="staff-holiday-op-card" data-surface-id="staff.availability.end-pause" aria-label="恢復接案設定">
        <h3 className="staff-op-title">恢復接案</h3>
        <p>{selectedEndPauseBlock.startDate} 起的無期限暫停接案</p>
        <label className="staff-op-field">恢復接案日期<input type="date" value={endPauseResumeDate} disabled={interactionLocked || availabilityAction.phase === 'stale'} onChange={event => { invalidateSlice(); setEndPauseResumeDate(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
        <label className="staff-op-field">備註（選填）<input aria-label="恢復接案備註（選填）" value={endPauseReason} maxLength={500} disabled={interactionLocked} onChange={event => { invalidateSlice(); setEndPauseReason(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
        {endPauseDisabledReason && <p role="status">{endPauseDisabledReason}</p>}
        <div className="staff-op-actions"><button type="button" className="staff-secondary-btn" disabled={interactionLocked} onClick={() => { setEndPauseBlockId(null); setEndPauseReason(''); }}>取消設定</button><button type="button" data-control-id="staff.availability.end-pause" className="staff-primary-btn" disabled={!endPauseResumeDate || interactionLocked || availabilityAction.phase === 'stale' || availabilityAction.phase === 'preview_loading'} onClick={() => void previewAvailability({ action: 'end_pause', block_id: selectedEndPauseBlock.blockId, resume_date: endPauseResumeDate, reason: endPauseReason.trim() })}>儲存恢復接案</button></div>
      </section>}
    </section>
  );
  useUnsavedDraft('月嫂請假與暫停', { '開始日期': showAvailabilityForm ? availabilityStart : undefined, '結束日期': showAvailabilityForm && availabilityKind === 'create_long_leave' ? availabilityEnd : undefined, '類型': showAvailabilityForm ? availabilityKind : undefined, '新增備註': availabilityReason, '取消備註': cancelReason, '恢復日期': selectedEndPauseBlock ? endPauseResumeDate : undefined, '恢復備註': endPauseReason }, { enabled: selectedStaff !== null, busy: interactionLocked, baseline: { '開始日期': showAvailabilityForm ? todayIsoDate() : undefined, '結束日期': showAvailabilityForm && availabilityKind === 'create_long_leave' ? todayIsoDate() : undefined, '類型': showAvailabilityForm ? 'create_long_leave' : undefined, '新增備註': '', '取消備註': '', '恢復日期': selectedEndPauseBlock ? todayIsoDate() : undefined, '恢復備註': '' }, discard: () => { resetAvailabilityForm(); setCancelReason(''); setEndPauseBlockId(null); setEndPauseReason(''); } });
  useUnsavedDraft('月嫂任職狀態', { '狀態生效日': lifecycleEffectiveAt, '狀態原因': lifecycleReasonCode }, { enabled: selectedStaff !== null, busy: interactionLocked, resetKey: lifecycleAction.phase === 'observed' ? lifecycleAction.receipt : null, discard: () => { setLifecycleEffectiveAt(''); setLifecycleReasonCode(''); } });


  return (
    <div data-surface-id="staff.page">
      <div className="page-header-banner staff-page-header">
        <div>
          <h1 className="page-title">👥 服務人員與工會成員名冊</h1>
          <p className="page-subtitle">即時搜尋月嫂、檢視資格主檔、設定接案偏好、維護長假留停與辦理人事異動。</p>
        </div>
      </div>


      <div className="staff-toolbar-card" data-surface-id="staff.toolbar">
        <div className="staff-filter-pills staff-roster-tabs" role="tablist" aria-label="月嫂任職名冊">
          {(['active', 'retired'] as const).map((state, index) => (
            <button
              key={state}
              id={`${rosterTabsId}-${state}`}
              type="button"
              role="tab"
              aria-selected={rosterLifecycle === state}
              aria-controls={`${rosterTabsId}-panel`}
              tabIndex={rosterLifecycle === state ? 0 : -1}
              className={`staff-filter-pill ${rosterLifecycle === state ? 'active' : ''}`}
              disabled={interactionLocked}
              onClick={() => setRosterLifecycle(state)}
              onKeyDown={(event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                const next = event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - index;
                setRosterLifecycle(next === 0 ? 'active' : 'retired');
                event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
              }}
            >{state === 'active' ? '現役月嫂' : '已退役月嫂'}</button>
          ))}
        </div>
        <div className="staff-search-input-row">
          <div className="staff-search-input-box">
            <span className="search-icon" aria-hidden="true">🔍</span>
            <input
              type="text"
              aria-label="即時搜尋月嫂"
              placeholder="搜尋公會編號、月嫂姓名或電話…"
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
            {searchQuery.trim()
              ? directorySearch.status === 'loading' || directorySearch.status === 'idle'
                ? '搜尋中…'
                : directorySearch.status === 'error'
                  ? '搜尋未完成'
                  : `搜尋結果 ${filteredStaffItems.length} 位服務人員`
              : `目前已載入 ${directory.items.length} 位服務人員`}
          </span>
          <details className="staff-quick-query">
            <summary>快速查詢資格主檔</summary>
          <div className="staff-query-selector" data-surface-id="staff.selector">
            <label htmlFor="staff-query-staff">查詢服務人員</label>
            <select
              id="staff-query-staff"
              data-control-id="staff.selector.staff"
              disabled={interactionLocked || selectedStaff !== null}
              value={selectedStaffId ?? ''}
              onChange={(event) => changeSelectedStaff(event.target.value)}
            >
              <option value="">請選擇服務人員</option>
              {staffItems.map((staff) => <option key={staff.id} value={staff.id}>{staffDisplayLabel(staff.unionNo, staff.displayName)}</option>)}
            </select>
          </div>
          </details>
        </div>
      </div>

        <section data-surface-id="staff.directory" role="tabpanel" id={`${rosterTabsId}-panel`} aria-labelledby={`${rosterTabsId}-${rosterLifecycle}`}>
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
            <div className="staff-directory-message" role="status">{rosterLifecycle === 'active' ? '目前沒有現役月嫂。' : '目前沒有已退役月嫂。'}</div>
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
            <div className="staff-directory-table-wrap" role="region" aria-label="月嫂完整主檔清單，可橫向捲動" tabIndex={0} aria-busy={directory.status === 'loading-more'}>
              <table className="staff-directory-table">
                <caption>月嫂名冊清單</caption>
                <thead><tr>
                  <th scope="col">公會編號</th><th scope="col">姓名</th>
                  <th scope="col">電話</th><th scope="col">學歷</th>
                  {rosterServiceColumns.map(([field, label]) => <th scope="col" key={field}>{label}</th>)}
                  {rosterProfileColumns.map(([field, label]) => <th scope="col" key={field}>{label}</th>)}
                  {rosterBankColumns.map((label) => <th scope="col" key={label}>{label}</th>)}
                  <th scope="col">操作</th>
                </tr></thead>
                <tbody>
              {filteredStaffItems.map((staff) => (
                <tr key={staff.id} data-control-id={`staff.row.${staff.id}`} tabIndex={interactionLocked ? -1 : 0}
                  aria-label={`開啟 ${staff.displayName} 的詳情`} aria-haspopup="dialog"
                  aria-expanded={selectedStaff?.id === staff.id} aria-disabled={interactionLocked}
                  className={selectedStaff?.id === staff.id ? 'is-selected' : undefined}
                  onClick={(event) => { if (!interactionLocked) { event.currentTarget.focus(); openStaffDetail(staff); } }}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return;
                    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openStaffDetail(staff); }
                  }}>
                  <td>{staff.unionNo ?? '未設定'}</td><td>{staff.displayName}</td>
                  <td>{staff.phone ?? '未登錄'}</td><td>{staff.displayEducation}</td>
                  {rosterServiceColumns.map(([field]) => <td key={field}>{rosterServiceValue(staff.serviceProfile, field)}</td>)}
                  {rosterProfileColumns.map(([field]) => <td key={field}>{rosterProfileValue(staff.profile, field)}</td>)}
                  {rosterBankColumns.map((label, index) => <td key={label}>
                    {!staff.profile ? '未載入' : staff.profile.bank_accounts.length === 0 ? '未登錄'
                      : staff.profile.bank_accounts.map((account) => <div key={account.account_id}>
                        {index === 0 ? account.bank_code ?? '未登錄'
                          : index === 1 ? account.branch_code ?? '未登錄'
                          : index === 2 ? account.account_no ?? (account.account_last4 ? `末四碼 ${account.account_last4}` : '未登錄')
                          : index === 3 ? account.is_primary ? '是' : '否'
                          : account.is_active ? '有效' : '已停用'}
                      </div>)}
                  </td>)}
                  <td>
                    <button
                      type="button"
                      data-control-id={`staff.drawer.open.${staff.id}`}
                      className="staff-view-btn"
                      aria-label={`查看 ${staff.displayName} 的詳情`}
                      aria-haspopup="dialog"
                      disabled={interactionLocked}
                      onClick={(event) => { event.stopPropagation(); openStaffDetail(staff); }}
                    >
                      查看詳情 →
                    </button>
                    <button
                      type="button"
                      data-control-id={`staff.lifecycle.open.${staff.id}`}
                      className="sr-only"
                      disabled={interactionLocked}
                      onClick={(event) => {
                        event.stopPropagation();
                        invalidateSlice();
                        setSelectedStaffId(staff.id);
                        setSelectedStaff(staff);
                        setOpenAtStatus(true);
                      }}
                    >
                      辦理退役／復職
                    </button>
                  </td>
                </tr>
              ))}
                </tbody>
              </table>
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
        title={`月嫂詳情 — ${selectedStaff ? staffDisplayLabel(selectedStaff.unionNo, selectedStaff.displayName) : ''}`}
        size="wide"
        footer={
          <div className="staff-drawer-footer">
            <button type="button" data-control-id="staff.drawer.close" className="staff-close-btn" disabled={interactionLocked} onClick={() => requestLeave(() => setSelectedStaff(null))}>關閉</button>
          </div>
        }
      >
        {selectedStaff && (
          <div className="staff-drawer-content">
            {/* 完整資格主檔：個資、履歷、銀行與接案條件 */}
              <section className="staff-drawer-section" data-surface-id="staff.qualification-master" aria-label="完整資格主檔">
                <h2 className="staff-management-title">📋 完整資格主檔</h2>
                <p>各區分別儲存。請先儲存本區變更，再修改下一區。</p>
                {/* 基本資料摘要卡片 */}
                <div style={{ background: '#fffdfc', border: '1px solid #dec0b6', borderRadius: '12px', padding: '16px', marginBottom: '18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="staff-avatar" style={{ width: '44px', height: '44px', fontSize: '1.3rem', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#ffe4d6', borderRadius: '50%' }}>👩‍🍼</div>
                      <div>
                        <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#4a2818' }}>
                          <span className="staff-id-badge">公會編號：{selectedStaff.unionNo ?? '未設定'}</span> {selectedStaff.displayName}
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
                    <StaffRegistryEditor profile={profile.data} resumeContainer={resumeContainer} onUpdated={() => refreshProfile(profile.data.staff_id, sliceGenerationRef.current, sliceControllerRef.current?.signal)} />
                  </div>
                )}

                <section data-surface-id="staff.qualification.preferences">
                  {selectedStaffId !== null && <StaffCasePreferenceManualEditor staffId={selectedStaffId} directEditing surfaceId="staff.qualification.case-preference-manual" onUpdated={() => setSliceRetryGeneration(value => value + 1)} renderQualifications={information => qualification.status === 'ready'
                    ? <StaffQualificationEditor staffId={selectedStaffId} importedServiceInformation={information} onUpdated={() => setSliceRetryGeneration(value => value + 1)} />
                    : <section aria-label="專業資格與服務資料"><h3>專業資格與服務資料</h3>{information}</section>} />}
                </section>

                {/* 6 大專業資格審核主檔 */}
                <h3 style={{ margin: '0 0 10px', fontSize: '1.05rem', color: '#7c2d12', fontWeight: 700 }}>
                  📋 資格狀態與來源摘要
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
                      系統狀態依正式資料推導；醫療／體檢及有效期尚無登錄來源，不提供人工修改。<br />
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
            {/* 接案狀態管理 (採用國定假日 QUERY → PREVIEW → APPLY → RECEIPT 工作台模式) */}
              <section className="staff-drawer-section" data-surface-id="staff.availability-management" aria-label="接案狀態管理" ref={statusSectionRef}>
                <h2 className="staff-management-title">🏖️ 接案狀態管理</h2>
                {renderAvailabilityWorkbench()}
                {/* 區塊 1: 📇 人事任職狀態與異動辦理 */}
                <div className="staff-holiday-workbench" data-surface-id="staff.lifecycle">
                  <header className="staff-workbench-header">
                    <div>
                      <p className="staff-workbench-kicker">查詢 → 儲存</p>
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
                          <span className="staff-item-title">{staffDisplayLabel(selectedStaff.unionNo, selectedStaff.displayName)}目前任職狀態</span>
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
                                setShowLifecycleForm(!showLifecycleForm || lifecycleAction.action !== 'retirement');
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
                                setShowLifecycleForm(!showLifecycleForm || lifecycleAction.action !== 'reactivation');
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
                        生效日期
                        <input
                          type="date"
                          disabled={interactionLocked || lifecycleAction.phase === 'stale'}
                          value={lifecycleEffectiveAt}
                          onChange={(event) => {
                            invalidateSlice();
                            setLifecycleEffectiveAt(event.target.value);
                            setLifecycleAction((prev) => ({ ...prev, phase: 'idle', preview: null, message: null }));
                          }}
                        />
                      </label>
                      <label className="staff-op-field">
                        異動原因（選填）
                        <select
                          disabled={interactionLocked || lifecycleAction.phase === 'stale'}
                          value={lifecycleReasonCode}
                          onChange={(event) => {
                            invalidateSlice();
                            setLifecycleReasonCode(event.target.value);
                            setLifecycleAction((prev) => ({ ...prev, phase: 'idle', preview: null, message: null }));
                          }}
                        >
                          <option value="">不填寫</option>
                          {lifecycle.status === 'ready' && lifecycle.data.state === 'retired' ? (
                            <option value="returned_to_service">恢復服務</option>
                          ) : <>
                            <option value="left_union">離會</option>
                            <option value="no_longer_available">不再接案</option>
                            <option value="qualification_changed">資格異動</option>
                          </>}
                        </select>
                      </label>
                    </div>

                    <p id="staff-lifecycle-guidance" style={{ fontSize: '0.8rem', color: 'var(--md-sys-color-error)', margin: '2px 0 6px' }}>
                      退役生效日期是停止接案的日期；仍有未結束案件時，須先完成案件或辦理改派。已退役者可辦理復職；原因可選填。
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
                            disabled={lifecycle.status !== 'ready' || !lifecycle.data.canRetire || !lifecycleEffectiveAt || interactionLocked || lifecycleAction.phase === 'stale' || lifecycleAction.phase === 'preview_loading'}
                            onClick={() => void previewLifecycle('retirement')}
                          >
                            {lifecycleAction.phase === 'preview_loading' && lifecycleAction.action === 'retirement' ? '⏳ 處理中…' : '辦理退役'}
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
                            disabled={lifecycle.status !== 'ready' || !lifecycle.data.canReactivate || !lifecycleEffectiveAt || interactionLocked || lifecycleAction.phase === 'stale' || lifecycleAction.phase === 'preview_loading'}
                            onClick={() => void previewLifecycle('reactivation')}
                          >
                            {lifecycleAction.phase === 'preview_loading' && lifecycleAction.action === 'reactivation' ? '⏳ 處理中…' : '辦理復職'}
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
                        ✅ <strong>變更檢查結果：</strong>{lifecycleAction.action === 'retirement' ? '辦理退役' : '辦理復職'} ｜ 生效時間：{lifecycleEffectiveAt} ｜ 變更後狀態：<strong>{lifecycleAction.preview.after_state === 'retired' ? '已退役' : '在職'}</strong>
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
              {profile.status === 'ready' && <section className="staff-drawer-section" data-surface-id="staff.resume" aria-label="月嫂履歷 PDF" ref={setResumeContainer} />}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default StaffPage;
