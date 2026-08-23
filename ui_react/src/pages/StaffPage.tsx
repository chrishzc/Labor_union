/**
 * File: StaffPage.tsx
 * Description: 以 bounded Staff 契約呈現名冊、固定六區資格、偏好、不可服務期間與 lifecycle 流程。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './StaffPage.css';
import { Drawer } from '../components/Drawer';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { StaffDirectoryAbortedError } from '../api/staff_directory/staff_directory_errors';
import { staffPreferencesClient } from '../api/staff_preferences/staff_preferences_client';
import {
  StaffPreferencesAbortedError,
  StaffPreferencesConflictError,
  StaffPreferencesNetworkError,
  StaffPreferencesTimeoutError,
  StaffPreferencesUnavailableError,
} from '../api/staff_preferences/staff_preferences_errors';
import type {
  StaffPreferenceProfile,
  StaffPreferenceProfileApplyPayload,
  StaffPreferenceProfileApplyReceipt,
  StaffPreferenceProfilePreview,
  StaffPreferenceValueInput,
} from '../api/staff_preferences/staff_preferences_schemas';
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
import { StaffQualificationMasterError } from '../api/staff/qualification_master_errors';
import {
  adaptStaffDirectoryPage,
  type StaffDirectoryCardViewModel,
} from '../adapters/staff/staff_directory_adapter';
import {
  adaptStaffPreferencesProfile,
  type StaffPreferencesProfileViewModel,
} from '../adapters/staff/staff_preferences_adapter';
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

type StaffTab = 'roster' | 'preferences' | 'unavailability';
type DirectoryState =
  | { status: 'loading'; items: StaffDirectoryCardViewModel[] }
  | { status: 'ready'; items: StaffDirectoryCardViewModel[]; nextCursor: number | null }
  | { status: 'loading-more'; items: StaffDirectoryCardViewModel[]; nextCursor: number }
  | { status: 'error'; items: StaffDirectoryCardViewModel[]; message: string; retryCursor: number | null };
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

function isPreferencesOutcomeUnknown(error: unknown): boolean {
  return error instanceof StaffPreferencesTimeoutError
    || error instanceof StaffPreferencesNetworkError
    || (error instanceof StaffPreferencesUnavailableError && error.retryable);
}

function isAvailabilityOutcomeUnknown(error: unknown): boolean {
  return error instanceof StaffAvailabilityUnavailableError && error.retryable;
}

function isLifecycleOutcomeUnknown(error: unknown): boolean {
  return error instanceof StaffLifecycleUnavailableError && error.retryable;
}

function preferenceText(value: StaffPreferencesProfileViewModel['preferredServiceDays']): string {
  if (!value) return '尚未設定';
  if (value.value.kind === 'integer_range') {
    return `${value.value.minimum}–${value.value.maximum}`;
  }
  return value.value.values.join('、');
}

function preferenceRange(draft: readonly StaffPreferenceValueInput[], key: string): { minimum: number; maximum: number } | null {
  const item = draft.find((candidate) => candidate.preference_key === key);
  return item?.value.kind === 'integer_range'
    ? { minimum: item.value.minimum, maximum: item.value.maximum }
    : null;
}

function preferenceIntegerSet(draft: readonly StaffPreferenceValueInput[], key: string): readonly number[] {
  const item = draft.find((candidate) => candidate.preference_key === key);
  return item?.value.kind === 'integer_set' ? item.value.values : [];
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
  const [activeTab, setActiveTab] = useState<StaffTab>('roster');
  const [directory, setDirectory] = useState<DirectoryState>({ status: 'loading', items: [] });
  const [selectedStaff, setSelectedStaff] = useState<StaffDirectoryCardViewModel | null>(null);
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [preferences, setPreferences] = useState<QueryState<StaffPreferencesProfileViewModel>>({ status: 'idle' });
  const [preferencesRaw, setPreferencesRaw] = useState<StaffPreferenceProfile | null>(null);
  const [preferenceDraft, setPreferenceDraft] = useState<StaffPreferenceValueInput[]>([]);
  const [preferenceAction, setPreferenceAction] = useState<ActionState<StaffPreferenceProfilePreview, StaffPreferenceProfileApplyReceipt, StaffPreferenceProfileApplyPayload>>(initialActionState);
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
  const [lifecycleEffectiveAt, setLifecycleEffectiveAt] = useState('');
  const [lifecycleReasonCode, setLifecycleReasonCode] = useState('');
  const [lifecycleAction, setLifecycleAction] = useState<ActionState<StaffLifecyclePreview, StaffLifecycleApplyReceipt, StaffLifecycleApplyPayload> & { action: StaffLifecycleAction | null }>({
    ...initialActionState<StaffLifecyclePreview, StaffLifecycleApplyReceipt, StaffLifecycleApplyPayload>(),
    action: null,
  });
  const [rangeStart, setRangeStart] = useState('');
  const [rangeEnd, setRangeEnd] = useState('');
  const [sliceRetryGeneration, setSliceRetryGeneration] = useState(0);
  const mountedRef = useRef(false);
  const initialRequestedRef = useRef(false);
  const requestGenerationRef = useRef(0);
  const activeControllerRef = useRef<AbortController | null>(null);
  const sliceGenerationRef = useRef(0);
  const sliceControllerRef = useRef<AbortController | null>(null);

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
    const { generation, controller } = beginSliceRequest();
    setPreferences({ status: 'idle' });
    setPreferencesRaw(null);
    setPreferenceDraft([]);
    setPreferenceAction(initialActionState());
    setAvailability({ status: 'idle' });
    setAvailabilityAction(initialActionState());
    setEndPauseBlockId(null);
    setEndPauseResumeDate('');
    setEndPauseReason('');
    setLifecycle({ status: 'idle' });
    setQualification({ status: 'idle' });
    setLifecycleAction({ ...initialActionState(), action: null });
    if (selectedStaffId === null) return;

    const currentStaffId = selectedStaffId;

    if (activeTab === 'preferences') {
      setPreferences({ status: 'loading' });
      void Promise.all([
        staffPreferencesClient.queryDefinitions({ signal: controller.signal }),
        staffPreferencesClient.queryProfile(currentStaffId, { signal: controller.signal }),
      ]).then(([, profile]) => {
        if (isCurrentSlice(generation, controller.signal)) {
          setPreferencesRaw(profile);
          setPreferenceDraft(profile.values.map((item) => ({ preference_key: item.preference_key, value: item.value })));
          setPreferences({ status: 'ready', data: adaptStaffPreferencesProfile(profile) });
        }
      }).catch((error: unknown) => {
        if (error instanceof StaffPreferencesAbortedError || !isCurrentSlice(generation, controller.signal)) return;
        setPreferences({ status: 'error', message: error instanceof Error ? error.message : '偏好資料載入失敗。' });
      });
    } else if (activeTab === 'roster') {
      setLifecycle({ status: 'loading' });
      void staffLifecycleClient.query(currentStaffId, { signal: controller.signal }).then((view) => {
        if (isCurrentSlice(generation, controller.signal)) {
          setLifecycle({ status: 'ready', data: adaptStaffLifecycleView(view) });
        }
      }).catch((error: unknown) => {
        if (error instanceof StaffLifecycleAbortedError || !isCurrentSlice(generation, controller.signal)) return;
        setLifecycle({ status: 'error', message: error instanceof Error ? error.message : 'Lifecycle 載入失敗。' });
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
    }

    return () => controller.abort();
  }, [activeTab, selectedStaffId, sliceRetryGeneration]);

  const requeryPreferences = async (staffId: number, signal?: AbortSignal, generation?: number): Promise<boolean> => {
    const profile = await staffPreferencesClient.queryProfile(staffId, { signal });
    if (generation !== undefined && !isCurrentSlice(generation, signal)) return false;
    if (!mountedRef.current || signal?.aborted === true) return false;
    setPreferencesRaw(profile);
    setPreferenceDraft(profile.values.map((item) => ({ preference_key: item.preference_key, value: item.value })));
    setPreferences({ status: 'ready', data: adaptStaffPreferencesProfile(profile) });
    return true;
  };

  const updatePreferenceRange = (key: 'preferred_service_days' | 'daily_service_hours', edge: 'minimum' | 'maximum', value: string) => {
    invalidateSlice();
    setPreferenceAction((current) => ({ ...current, phase: 'editing', preview: null, payload: null, idempotencyKey: null, message: null }));
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed <= 0) return;
    setPreferenceDraft((current) => {
      const existing = current.find((item) => item.preference_key === key && item.value.kind === 'integer_range');
      if (!existing) {
        return [...current, {
          preference_key: key,
          value: { kind: 'integer_range', minimum: parsed, maximum: parsed },
        }];
      }
      return current.map((item) => {
        if (item.preference_key !== key || item.value.kind !== 'integer_range') return item;
        return { ...item, value: { ...item.value, [edge]: parsed } };
      });
    });
  };

  const updatePreferenceIntegerSet = (key: 'daily_service_hours', value: string) => {
    invalidateSlice();
    setPreferenceAction((current) => ({ ...current, phase: 'editing', preview: null, payload: null, idempotencyKey: null, message: null }));
    const parsed = value.split(',').map((item) => Number(item.trim()));
    if (parsed.length === 0 || parsed.some((item) => !Number.isInteger(item) || item <= 0)) return;
    setPreferenceDraft((current) => {
      const existing = current.find((item) => item.preference_key === key && item.value.kind === 'integer_set');
      if (!existing) {
        return [...current, { preference_key: key, value: { kind: 'integer_set', values: parsed } }];
      }
      return current.map((item) => (
        item.preference_key === key && item.value.kind === 'integer_set'
          ? { ...item, value: { ...item.value, values: parsed } }
          : item
      ));
    });
  };

  const refreshPreferencesAfterStale = async () => {
    if (selectedStaffId === null) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginSliceRequest();
    setPreferences({ status: 'loading' });
    try {
      const updated = await requeryPreferences(currentStaffId, controller.signal, generation);
      if (!updated || !isCurrentSlice(generation, controller.signal)) return;
      setPreferenceAction(initialActionState());
    } catch (error) {
      if (!isCurrentSlice(generation, controller.signal)) return;
      setPreferences({ status: 'error', message: errorMessage(error, '偏好重新查詢失敗。') });
    }
  };

  const previewPreferences = async () => {
    if (selectedStaffId === null || preferencesRaw === null) return;
    const { generation, controller } = beginSliceRequest();
    setPreferenceAction((current) => ({ ...current, phase: 'preview_loading', message: null }));
    try {
      const preview = await staffPreferencesClient.previewProfile(selectedStaffId, { values: preferenceDraft }, { signal: controller.signal });
      if (!isCurrentSlice(generation, controller.signal)) return;
      setPreferenceAction({ phase: 'preview_ready', preview, receipt: null, payload: null, idempotencyKey: null, message: null });
    } catch (error) {
      if (error instanceof StaffPreferencesAbortedError || !isCurrentSlice(generation, controller.signal)) return;
      setPreferenceAction({ ...initialActionState(), phase: error instanceof StaffPreferencesConflictError ? 'stale' : 'error', message: errorMessage(error, '偏好預覽失敗。') });
    }
  };

  const submitPreferences = async (retry = false) => {
    if (selectedStaffId === null || preferencesRaw === null) return;
    const currentStaffId = selectedStaffId;
    const actionGeneration = sliceGenerationRef.current;
    const previous = preferenceAction;
    const preview = previous.preview;
    const payload = retry ? previous.payload : preview ? {
      values: preferenceDraft,
      expected_version: preferencesRaw.version,
      preview_fingerprint: preview.preview_fingerprint,
      reason: '人工維護月嫂偏好',
    } : null;
    const idempotencyKey = retry ? previous.idempotencyKey : nextIntentKey('staff-preferences');
    if (payload === null || idempotencyKey === null) return;
    setPreferenceAction((current) => ({ ...current, phase: 'apply_pending', payload, idempotencyKey, message: null }));
    try {
      const receipt = await staffPreferencesClient.applyProfile(currentStaffId, payload, { idempotencyKey });
      if (!isCurrentSlice(actionGeneration)) return;
      setPreferenceAction((current) => ({ ...current, phase: 'receipt_received', receipt }));
      const { generation, controller } = beginSliceRequest();
      setPreferenceAction((current) => ({ ...current, phase: 'requery_loading' }));
      try {
        const updated = await requeryPreferences(currentStaffId, controller.signal, generation);
        if (!updated || !isCurrentSlice(generation, controller.signal)) return;
        setPreferenceAction((current) => ({ ...current, phase: 'observed', message: '已觀察最新偏好' }));
      } catch (error) {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setPreferenceAction((current) => ({ ...current, phase: 'observation_failed', message: `receipt 已收到，但重新查詢失敗：${errorMessage(error, '偏好觀察失敗。')}` }));
      }
    } catch (error) {
      if (!isCurrentSlice(actionGeneration)) return;
      if (error instanceof StaffPreferencesConflictError) {
        setPreferenceAction((current) => ({ ...current, phase: 'stale', message: error.message, idempotencyKey: null }));
      } else if (isPreferencesOutcomeUnknown(error)) {
        setPreferenceAction((current) => ({ ...current, phase: 'outcome_unknown', message: `結果未知：${errorMessage(error, '請以相同內容重試。')}` }));
      } else {
        setPreferenceAction((current) => ({ ...current, phase: 'error', message: errorMessage(error, '偏好套用失敗。'), idempotencyKey: null }));
      }
    }
  };

  const queryAvailability = async () => {
    if (selectedStaffId === null || !rangeStart || !rangeEnd) return;
    const currentStaffId = selectedStaffId;
    const { generation, controller } = beginSliceRequest();
    setAvailability({ status: 'loading' });
    try {
      const blocks = await staffAvailabilityClient.getBlocks(currentStaffId, rangeStart, rangeEnd, { signal: controller.signal });
      if (isCurrentSlice(generation, controller.signal)) {
        setAvailability({ status: 'ready', data: adaptStaffAvailabilityBlocks(blocks) });
        setAvailabilityAction(initialActionState());
        setEndPauseBlockId(null);
      }
    } catch (error) {
      if (error instanceof StaffAvailabilityAbortedError || !isCurrentSlice(generation, controller.signal)) return;
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
            ? 'Server Preview 未回傳同一筆可結束的暫停接案期間。'
            : 'Server Preview 判定目前不可套用。',
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
              : 'receipt 已收到，但尚未觀察同一筆 server 封閉暫停期間。',
          }));
          return;
        }
        setAvailabilityAction((current) => ({ ...current, phase: 'observed', message: '已觀察最新不可服務期間' }));
      } catch (error) {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setAvailabilityAction((current) => ({ ...current, phase: 'observation_failed', message: `receipt 已收到，但重新查詢失敗：${errorMessage(error, '不可服務期間觀察失敗。')}` }));
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
      setLifecycleAction({ ...initialActionState(), action, phase: error instanceof StaffLifecycleConflictError ? 'stale' : 'error', message: errorMessage(error, 'Lifecycle 預覽失敗。') });
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
      setLifecycle({ status: 'error', message: errorMessage(error, 'Lifecycle 重新查詢失敗。') });
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
        setLifecycleAction((current) => ({ ...current, phase: 'observed', message: '已觀察最新 lifecycle' }));
      } catch (error) {
        if (!isCurrentSlice(generation, controller.signal)) return;
        setLifecycleAction((current) => ({ ...current, phase: 'observation_failed', message: `receipt 已收到，但重新查詢失敗：${errorMessage(error, 'Lifecycle 觀察失敗。')}` }));
      }
    } catch (error) {
      if (!isCurrentSlice(actionGeneration)) return;
      if (error instanceof StaffLifecycleConflictError) {
        setLifecycleAction((current) => ({ ...current, phase: 'stale', message: error.message, idempotencyKey: null }));
      } else if (isLifecycleOutcomeUnknown(error)) {
        setLifecycleAction((current) => ({ ...current, phase: 'outcome_unknown', message: `結果未知：${errorMessage(error, '請以相同內容重試。')}` }));
      } else {
        setLifecycleAction((current) => ({ ...current, phase: 'error', message: errorMessage(error, 'Lifecycle 套用失敗。'), idempotencyKey: null }));
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
  const preferredDaysRange = preferenceRange(preferenceDraft, 'preferred_service_days');
  const dailyServiceHours = preferenceIntegerSet(preferenceDraft, 'daily_service_hours');
  const eligibleEndPauseBlocks = availability.status === 'ready'
    ? availability.data.filter((block) => isEligibleEndPauseBlock(block, selectedStaffId))
    : [];
  const selectedEndPauseBlock = eligibleEndPauseBlocks.find((block) => block.blockId === endPauseBlockId) ?? null;
  const interactionLocked = actionLocksNavigation(preferenceAction.phase)
    || actionLocksNavigation(availabilityAction.phase)
    || actionLocksNavigation(lifecycleAction.phase);

  const changeTab = (nextTab: StaffTab) => {
    if (nextTab !== activeTab) invalidateSlice();
    setActiveTab(nextTab);
  };

  const changeSelectedStaff = (value: string) => {
    if (selectedStaff !== null) return;
    invalidateSlice();
    setSelectedStaffId(value ? Number(value) : null);
  };

  return (
    <div data-surface-id="staff.page">
      <div className="page-header-banner staff-page-header">
        <div>
          <h1 className="page-title">👥 服務人員與工會成員名冊</h1>
          <p className="page-subtitle">選擇服務人員後，查詢資格、配對偏好、不可服務期間與 lifecycle。</p>
        </div>
      </div>

      <div className="staff-tab-bar" aria-label="服務人員管理分頁">
        <button type="button" data-control-id="staff.tab.roster" className={`staff-tab-btn ${activeTab === 'roster' ? 'active' : ''}`} disabled={interactionLocked} onClick={() => changeTab('roster')}>
          👩‍🍼 服務月嫂名冊與資格審核
        </button>
        <button type="button" data-control-id="staff.tab.preferences" className={`staff-tab-btn ${activeTab === 'preferences' ? 'active' : ''}`} disabled={interactionLocked} onClick={() => changeTab('preferences')}>
          🎯 配對偏好管理
        </button>
        <button type="button" data-control-id="staff.tab.unavailability" className={`staff-tab-btn ${activeTab === 'unavailability' ? 'active' : ''}`} disabled={interactionLocked} onClick={() => changeTab('unavailability')}>
          🏖️ 長假與暫停接案期間維護
        </button>
      </div>

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
          {staffItems.map((staff) => <option key={staff.id} value={staff.id}>{staff.displayName}（#{staff.id}）</option>)}
        </select>
        <span>不會自動選取第一筆；選擇後才查詢該人員資料。</span>
      </div>

      {activeTab === 'roster' && (
        <section data-surface-id="staff.directory">
          {selectedStaffId !== null && (
            <section className="staff-form-card wide" data-surface-id="staff.qualification-master">
              <h2>資格主檔 typed projection</h2>
              {qualification.status === 'loading' && <p role="status">正在載入資格主檔…</p>}
              {qualification.status === 'error' && <div role="alert"><p>{qualification.message}</p><button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((value) => value + 1)}>重試資格主檔</button></div>}
              {qualification.status === 'ready' && (
                <>
                  <p>
                    <strong>整體狀態：</strong>{qualification.data.overallAvailabilityLabel}
                    {' · '}資料日期：{qualification.data.as_of}
                  </p>
                  {qualification.data.officialDataNote && <p>{qualification.data.officialDataNote}</p>}
                  {qualification.data.sections.map((section) => {
                    const label = qualificationSectionLabel(section.kind);
                    return (
                      <div key={section.kind} className="staff-unavailable-slot" role="group" aria-label={label}>
                        <strong>{label} · {section.availabilityLabel}</strong>
                        {section.items.length === 0 ? (
                          <small style={{ display: 'block' }}>此區段目前沒有已登錄資料。</small>
                        ) : (
                          <ul>
                            {section.items.map((item) => (
                              <li key={item.code}>
                                {item.code}：{item.displayValue}{item.detail ? `（${item.detail}）` : ''}
                              </li>
                            ))}
                          </ul>
                        )}
                        {section.dataNote && <small style={{ display: 'block' }}>{section.dataNote}</small>}
                      </div>
                    );
                  })}
                </>
              )}
            </section>
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

          {staffItems.length > 0 && (
            <div className="staff-grid">
              {staffItems.map((staff) => (
                <article key={staff.id} className="staff-card" data-control-id={`staff.card.${staff.id}`}>
                  <div className="staff-card-header">
                    <div className="staff-avatar-name">
                      <div className="staff-avatar" aria-hidden="true">👩‍🍼</div>
                      <div>
                        <div className="staff-name">{staff.displayName}</div>
                        <div className="staff-phone">📞 {staff.displayPhone}</div>
                      </div>
                    </div>
                    <span className="staff-unavailable-pill">
                      {selectedStaffId === staff.id && lifecycle.status === 'ready' ? lifecycle.data.stateLabel : '狀態需選取查詢'}
                    </span>
                  </div>
                  <div className="staff-card-footer">
                    <button type="button" data-control-id={`staff.drawer.open.${staff.id}`} className="staff-view-btn" disabled={interactionLocked} onClick={() => { invalidateSlice(); setSelectedStaffId(staff.id); setSelectedStaff(staff); }}>
                      檢視服務人員摘要 ➔
                    </button>
                    <button type="button" data-control-id={`staff.lifecycle.open.${staff.id}`} className="staff-view-btn" disabled={interactionLocked} onClick={() => { invalidateSlice(); setSelectedStaffId(staff.id); setSelectedStaff(staff); }}>辦理退役／復職</button>
                  </div>
                </article>
              ))}
            </div>
          )}

          {directory.status === 'ready' && directory.nextCursor !== null && (
            <div className="staff-pagination">
              <button type="button" data-control-id="staff.directory.next-page" className="staff-next-btn" disabled={interactionLocked} onClick={() => void loadNextPage()}>
                載入下一頁
              </button>
            </div>
          )}
          {directory.status === 'loading-more' && <div className="staff-directory-message" role="status">正在載入下一頁摘要…</div>}
        </section>
      )}

      {activeTab === 'preferences' && (
        <section className="staff-workbench" data-surface-id="staff.preferences">
          <div className="staff-section-header">
            <div><h2>🎯 月嫂配對偏好管理</h2><p>只編輯核准的服務天數與每日時數；Preview 後才能 Apply。</p></div>
            <div className="staff-action-pair">
              <button type="button" className="staff-next-btn" onClick={() => { invalidateSlice(); setPreferenceAction((current) => ({ ...current, phase: 'editing', preview: null, payload: null, idempotencyKey: null, message: null })); }} disabled={preferences.status !== 'ready' || interactionLocked || preferenceAction.phase === 'stale'}>編輯核准偏好</button>
              <button type="button" data-control-id="staff.preferences.preview" className="staff-next-btn" disabled={preferenceAction.phase !== 'editing'} onClick={() => void previewPreferences()}>預覽偏好變更</button>
              <button type="button" data-control-id="staff.preferences.apply" className="staff-next-btn" disabled={preferenceAction.phase !== 'preview_ready'} onClick={() => void submitPreferences()}>套用偏好變更</button>
            </div>
          </div>
          {selectedStaffId === null && <div className="staff-directory-message">請先選擇服務人員。</div>}
          {preferences.status === 'loading' && <div className="staff-directory-message" role="status">正在載入偏好資料…</div>}
          {preferences.status === 'error' && <div className="staff-directory-message error" role="alert">{preferences.message}<button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((value) => value + 1)}>重試偏好資料</button></div>}
          <div className="staff-preference-grid">
            <div className="staff-form-card">
              <label htmlFor="staff-preference-days">可承接服務天數範圍</label>
              {preferenceAction.phase === 'editing' ? (
                <div className="staff-range-query">
                  <label>服務天數下限<input type="number" disabled={interactionLocked} value={preferredDaysRange?.minimum ?? ''} onChange={(event) => updatePreferenceRange('preferred_service_days', 'minimum', event.target.value)} /></label>
                  <label>服務天數上限<input type="number" disabled={interactionLocked} value={preferredDaysRange?.maximum ?? ''} onChange={(event) => updatePreferenceRange('preferred_service_days', 'maximum', event.target.value)} /></label>
                </div>
              ) : <input id="staff-preference-days" value={preferences.status === 'ready' ? preferenceText(preferences.data.preferredServiceDays) : '—'} disabled readOnly />}
            </div>
            <div className="staff-form-card">
              <label htmlFor="staff-preference-hours">可承接每日服務時數</label>
              {preferenceAction.phase === 'editing' ? (
                <input id="staff-preference-hours" aria-label="每日服務時數" value={dailyServiceHours.join(', ')} disabled={interactionLocked} onChange={(event) => updatePreferenceIntegerSet('daily_service_hours', event.target.value)} />
              ) : <input id="staff-preference-hours" value={preferences.status === 'ready' ? preferenceText(preferences.data.dailyServiceHours) : '—'} disabled readOnly />}
            </div>
          </div>
          {preferences.status === 'ready' && preferenceAction.phase !== 'editing' && (
            <p className="staff-form-hint">目前為檢視模式；按「編輯核准偏好」後才能修改，Preview 成功後才可套用。</p>
          )}
          {preferenceAction.preview && <div className="staff-action-status">Preview 指紋：{preferenceAction.preview.preview_fingerprint.slice(0, 12)}…</div>}
          {preferenceAction.message && <div className={`staff-action-status ${preferenceAction.phase === 'error' || preferenceAction.phase === 'stale' ? 'error' : ''}`} role="status">{preferenceAction.message}</div>}
          {preferenceAction.phase === 'stale' && <button type="button" className="staff-next-btn" onClick={() => void refreshPreferencesAfterStale()}>重新查詢偏好</button>}
          {preferenceAction.phase === 'outcome_unknown' && <button type="button" className="staff-next-btn" onClick={() => void submitPreferences(true)}>以相同內容重試</button>}
        </section>
      )}

      {activeTab === 'unavailability' && (
        <section className="staff-workbench" data-surface-id="staff.unavailability">
          <div className="staff-section-header">
            <div><h2>🏖️ 月嫂長假與暫停接案期間維護</h2><p>查詢後以 server Preview 驗證，再提交 append-only intent。</p></div>
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
            {availability.status === 'ready' && availability.data.length === 0 && <div className="staff-unavailability-row" role="row"><span role="cell">此範圍沒有不可服務紀錄。</span><span role="cell">—</span><span role="cell">—</span><span role="cell">無可取消紀錄</span></div>}
            {availability.status === 'ready' && availability.data.map((block) => (
              <div className="staff-unavailability-row" role="row" key={block.blockId}>
                <span role="cell">#{block.staffId}</span><span role="cell">{block.kindLabel}</span><span role="cell">{block.startDate} ～ {block.displayEndDate}</span>
                <span role="cell" className="staff-action-pair"><span>{block.statusLabel}</span><button type="button" data-control-id="staff.availability.cancel.preview" className="staff-next-btn" disabled={!cancelReason.trim() || block.status === 'cancelled' || interactionLocked || availabilityAction.phase === 'stale'} onClick={() => void previewAvailability({ action: 'cancel', block_id: block.blockId, reason: cancelReason.trim() })}>預覽取消</button></span>
              </div>
            ))}
            {availability.status === 'idle' && <div className="staff-unavailability-row" role="row"><span role="cell">請先設定日期範圍並查詢。</span><span role="cell">—</span><span role="cell">—</span><span role="cell">查詢後顯示可用操作</span></div>}
            {availability.status === 'loading' && <div className="staff-unavailability-row" role="row"><span role="cell">正在查詢不可服務期間…</span><span role="cell">—</span><span role="cell">—</span><span role="cell">請稍候</span></div>}
          </div>
          <div className="staff-range-query">
            <label>取消原因<input type="text" disabled={interactionLocked || availabilityAction.phase === 'stale'} value={cancelReason} onChange={(event) => { invalidateSlice(); setCancelReason(event.target.value); setAvailabilityAction(initialActionState()); }} /></label>
            <button type="button" data-control-id="staff.availability.cancel.apply" className="staff-next-btn" disabled={availabilityAction.phase !== 'preview_ready' || availabilityAction.payload?.action !== 'cancel'} onClick={() => void submitAvailability()}>套用取消</button>
          </div>
          {availabilityAction.preview && <div className="staff-action-status">日數：—　Preview 指紋：{availabilityAction.preview.preview_fingerprint.slice(0, 12)}…</div>}
          {availabilityAction.message && <div className={`staff-action-status ${availabilityAction.phase === 'error' || availabilityAction.phase === 'stale' ? 'error' : ''}`} role="status">{availabilityAction.message}</div>}
          {availabilityAction.phase === 'stale' && <button type="button" className="staff-next-btn" disabled={!rangeStart || !rangeEnd} onClick={() => void queryAvailability()}>重新查詢不可服務期間</button>}
          {availabilityAction.phase === 'outcome_unknown' && <button type="button" className="staff-next-btn" onClick={() => void submitAvailability(true)}>以相同內容重試</button>}
          <section className="staff-form-card wide" data-surface-id="staff.availability.end-pause">
            <h3>結束 open-ended 暫停接案</h3>
            <p>只列出本次 Query 中屬於所選月嫂、仍生效且沒有結束日的暫停接案期間。</p>
            <div className="staff-range-query">
              <label>
                暫停接案紀錄
                <select
                  aria-label="暫停接案紀錄"
                  disabled={eligibleEndPauseBlocks.length === 0 || interactionLocked || availabilityAction.phase === 'stale'}
                  value={endPauseBlockId ?? ''}
                  onChange={(event) => {
                    invalidateSlice();
                    setEndPauseBlockId(event.target.value ? Number(event.target.value) : null);
                    setAvailabilityAction(initialActionState());
                  }}
                >
                  <option value="">請選擇 open-ended 暫停紀錄</option>
                  {eligibleEndPauseBlocks.map((block) => (
                    <option key={block.blockId} value={block.blockId}>#{block.blockId}｜{block.startDate}｜{block.reason}</option>
                  ))}
                </select>
              </label>
              <label>
                恢復接案日期
                <input
                  type="date"
                  aria-label="恢復接案日期"
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
      )}

      <Drawer
        isOpen={selectedStaff !== null}
        onClose={() => { if (!interactionLocked) setSelectedStaff(null); }}
        title={`👩‍🍼 服務人員摘要 - ${selectedStaff?.displayName ?? ''}`}
        footer={
          <div className="staff-drawer-footer">
            <button type="button" data-control-id="staff.drawer.close" className="staff-close-btn" disabled={interactionLocked} onClick={() => setSelectedStaff(null)}>關閉</button>
            <button type="button" aria-describedby="staff-lifecycle-guidance" data-control-id="staff.lifecycle.retirement.preview" className="staff-next-btn" hidden={lifecycle.status === 'ready' && !lifecycle.data.canRetire} disabled={lifecycle.status !== 'ready' || !lifecycle.data.canRetire || !lifecycleEffectiveAt || !lifecycleReasonCode.trim() || interactionLocked || lifecycleAction.phase === 'stale' || lifecycleAction.phase === 'preview_loading'} onClick={() => void previewLifecycle('retirement')}>預覽退役</button>
            <button type="button" aria-describedby="staff-lifecycle-guidance" data-control-id="staff.lifecycle.retirement.apply" className="staff-next-btn" hidden={lifecycleAction.action !== 'retirement'} disabled={lifecycleAction.phase !== 'preview_ready'} onClick={() => void submitLifecycle()}>套用退役</button>
            <button type="button" aria-describedby="staff-lifecycle-guidance" data-control-id="staff.lifecycle.reactivation.preview" className="staff-next-btn" hidden={lifecycle.status === 'ready' && !lifecycle.data.canReactivate} disabled={lifecycle.status !== 'ready' || !lifecycle.data.canReactivate || !lifecycleEffectiveAt || !lifecycleReasonCode.trim() || interactionLocked || lifecycleAction.phase === 'stale' || lifecycleAction.phase === 'preview_loading'} onClick={() => void previewLifecycle('reactivation')}>預覽復職</button>
            <button type="button" aria-describedby="staff-lifecycle-guidance" data-control-id="staff.lifecycle.reactivation.apply" className="staff-next-btn" hidden={lifecycleAction.action !== 'reactivation'} disabled={lifecycleAction.phase !== 'preview_ready'} onClick={() => void submitLifecycle()}>套用復職</button>
          </div>
        }
      >
        {selectedStaff && (
          <div className="staff-drawer-content">
            <section className="staff-drawer-section">
              <h3>基本摘要</h3>
              <p><strong>Staff ID：</strong>#{selectedStaff.id}</p><p><strong>姓名：</strong>{selectedStaff.displayName}</p><p><strong>電話：</strong>{selectedStaff.displayPhone}</p>
            </section>
            <section className="staff-drawer-section" data-surface-id="staff.lifecycle">
              <h3>Lifecycle</h3>
              {lifecycle.status === 'loading' && <p>正在載入 lifecycle…</p>}
              {lifecycle.status === 'error' && <div role="alert"><p>{lifecycle.message}</p><button type="button" className="staff-next-btn" onClick={() => setSliceRetryGeneration((value) => value + 1)}>重試 Lifecycle</button></div>}
              {lifecycle.status === 'ready' && <><p><strong>狀態：</strong>{lifecycle.data.stateLabel}</p><p><strong>版本：</strong>{lifecycle.data.version}</p><p><strong>生效時間：</strong>{lifecycle.data.displayEffectiveAt}</p><p><strong>原因代碼：</strong>{lifecycle.data.maskedReasonCode ?? '—'}</p></>}
              {lifecycle.status === 'idle' && <p>請先選擇服務人員。</p>}
              <label>Lifecycle 生效時間<input type="text" disabled={interactionLocked || lifecycleAction.phase === 'stale'} value={lifecycleEffectiveAt} placeholder="2026-08-20T12:00:00+08:00" onChange={(event) => { invalidateSlice(); setLifecycleEffectiveAt(event.target.value); setLifecycleAction({ ...initialActionState(), action: null }); }} /></label>
              <label>Lifecycle 原因代碼<input type="text" disabled={interactionLocked || lifecycleAction.phase === 'stale'} value={lifecycleReasonCode} onChange={(event) => { invalidateSlice(); setLifecycleReasonCode(event.target.value); setLifecycleAction({ ...initialActionState(), action: null }); }} /></label>
              <p id="staff-lifecycle-guidance">在職狀態可辦理退役，已退役狀態可辦理復職；填寫生效時間與原因後才能 Preview，Preview 通過後才能 Apply。</p>
              {lifecycleAction.preview && <p>Preview 後狀態：{lifecycleAction.preview.after_state}</p>}
              {lifecycleAction.message && <p role="status">{lifecycleAction.message}</p>}
              {lifecycleAction.phase === 'stale' && <button type="button" className="staff-next-btn" onClick={() => void refreshLifecycleAfterStale()}>重新查詢 Lifecycle</button>}
              {lifecycleAction.phase === 'outcome_unknown' && <button type="button" className="staff-next-btn" onClick={() => void submitLifecycle(true)}>以相同內容重試</button>}
            </section>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default StaffPage;
