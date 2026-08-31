/**
 * File: LineIdentityReviewWorkbench.tsx
 * Description: 呈現 LINE 身分審核 typed Query／Preview／Apply／receipt／readback 工作台。
 */
import { useEffect, useRef, useState } from 'react';
import {
  adaptLineIdentityReview,
  adaptLineIdentityReviewPage,
  adaptLineIdentityReviewPreview,
  adaptLineIdentityReviewReceipt,
  adaptLineIdentityReviewSummary,
  type LineIdentityReviewPageViewModel,
  type LineIdentityReviewPreviewViewModel,
  type LineIdentityReviewReceiptViewModel,
  type LineIdentityReviewRowViewModel,
  type LineIdentityReviewSummaryViewModel,
} from '../adapters/line_identity/line_identity_adapter';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import type {
  LineIdentityReviewDecision,
  LineIdentityReviewType,
} from '../api/line_identity/line_identity_schemas';

export type LineIdentityReviewClient = Pick<
  LineIdentityClient,
  | 'listReviews'
  | 'getReviewSummary'
  | 'getReview'
  | 'previewReviewDecision'
  | 'applyReviewDecision'
>;

type QueryStatus = 'idle' | 'loading' | 'loaded' | 'error';
type MutationStatus = 'idle' | 'loading' | 'success' | 'error';

interface QueryState<T> {
  status: QueryStatus;
  value: T | null;
  error: string | null;
}

const idleState = <T,>(): QueryState<T> => ({ status: 'idle', value: null, error: null });
const loadingState = <T,>(): QueryState<T> => ({ status: 'loading', value: null, error: null });
const loadedState = <T,>(value: T): QueryState<T> => ({ status: 'loaded', value, error: null });
const errorState = <T,>(error: string): QueryState<T> => ({ status: 'error', value: null, error });

function safeError(error: unknown, fallback: string): string {
  if (error instanceof LineIdentityClientError) {
    if (error.outcomeUnknown) {
      return '審核結果尚未確認，請先重新查詢最新結果，不要再次提交。';
    }
    if (error.code === 'UNAUTHENTICATED') return '登入已失效，請重新登入後再試。';
    if (error.code === 'FORBIDDEN') return '目前帳號沒有執行此審核的權限。';
    if (error.code === 'NOT_FOUND') return '找不到這筆審核紀錄，請重新整理審核佇列。';
    if (error.code === 'CONFLICT') return '審核紀錄已變更，請重新查詢後再次確認。';
    if (error.code === 'REQUEST_INVALID') return '審核資料不完整，請檢查後再試。';
    return 'LINE 身分審核服務目前無法安全完成這項操作，請稍後再試。';
  }
  return fallback;
}

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

interface LineIdentityReviewWorkbenchProps {
  client: LineIdentityReviewClient;
}

function useReviewQueue(client: LineIdentityReviewClient) {
  const [summary, setSummary] = useState<QueryState<LineIdentityReviewSummaryViewModel>>(idleState);
  const [page, setPage] = useState<QueryState<LineIdentityReviewPageViewModel>>(idleState);
  const [reviewType, setReviewType] = useState<'all' | LineIdentityReviewType>('all');
  const [pageNumber, setPageNumber] = useState(1);
  const [reload, setReload] = useState(0);
  const generationRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setSummary(loadingState());
    setPage(loadingState());
    void client.getReviewSummary({ signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted && generation === generationRef.current) setSummary(loadedState(adaptLineIdentityReviewSummary(value)));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && generation === generationRef.current) setSummary(errorState(safeError(error, 'LINE 身分審核摘要載入失敗。')));
      });
    void client.listReviews({
      review_status: 'pending',
      review_type: reviewType === 'all' ? undefined : reviewType,
      page: pageNumber,
      page_size: 25,
    }, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted && generation === generationRef.current) setPage(loadedState(adaptLineIdentityReviewPage(value)));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && generation === generationRef.current) setPage(errorState(safeError(error, 'LINE 身分審核清單載入失敗。')));
      });
    return () => controller.abort();
  }, [client, pageNumber, reload, reviewType]);

  return {
    summary,
    page,
    reviewType,
    setReviewType,
    setPageNumber,
    refresh: () => {
      setPageNumber(1);
      setReload((value) => value + 1);
    },
  };
}

function useReviewDetail(client: LineIdentityReviewClient) {
  const [state, setState] = useState<QueryState<LineIdentityReviewRowViewModel>>(idleState);
  const controllerRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const load = async (requestId: number) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setState(loadingState());
    try {
      const value = await client.getReview(requestId, { signal: controller.signal });
      if (!controller.signal.aborted && generation === generationRef.current) {
        setState(loadedState(adaptLineIdentityReview(value)));
      }
    } catch (error: unknown) {
      if (!controller.signal.aborted && generation === generationRef.current) {
        setState(errorState(safeError(error, 'LINE 身分審核明細載入失敗。')));
      }
    }
  };

  return { state, load };
}

interface ReviewQueuePanelProps {
  summary: QueryState<LineIdentityReviewSummaryViewModel>;
  page: QueryState<LineIdentityReviewPageViewModel>;
  reviewType: 'all' | LineIdentityReviewType;
  onReviewTypeChange: (value: 'all' | LineIdentityReviewType) => void;
  onOpenDetail: (requestId: number) => void;
  onPageChange: (page: number) => void;
  onRefresh: () => void;
}

function ReviewQueuePanel(props: ReviewQueuePanelProps) {
  const { summary, page, reviewType } = props;
  const totalPages = page.value ? Math.max(1, Math.ceil(page.value.total / page.value.pageSize)) : 1;
  const first = page.value && page.value.total > 0 ? ((page.value.page - 1) * page.value.pageSize) + 1 : 0;
  const last = page.value ? Math.min(page.value.total, page.value.page * page.value.pageSize) : 0;
  return (
    <>
      <div className="line-section-heading">
        <div>
          <h3>🪪 LINE 身分人工審核</h3>
          <p>只有具審核權限的真人管理員可核准或拒絕；等待時間不會自動做出決定。</p>
        </div>
        <button type="button" className="line-secondary-btn" onClick={props.onRefresh}>🔄 重新整理審核佇列</button>
      </div>
      {summary.status === 'loading' && <div className="line-loading">正在載入審核摘要…</div>}
      {summary.status === 'error' && <div className="line-error" role="alert">{summary.error}</div>}
      {summary.value && (
        <div className="line-kpi-grid" aria-label="LINE 身分審核摘要">
          <div><span>待人工審核</span><strong>{summary.value.pendingTotal}</strong></div>
          <div><span>月嫂驗證</span><strong>{summary.value.staffPending}</strong></div>
          <div><span>客戶重綁</span><strong>{summary.value.rebindPending}</strong></div>
          <div><span>今日已處理</span><strong>{summary.value.processedToday}</strong></div>
        </div>
      )}
      <label htmlFor="line-identity-review-type">審核類型</label>
      <select id="line-identity-review-type" value={reviewType} onChange={(event) => props.onReviewTypeChange(event.target.value as 'all' | LineIdentityReviewType)}>
        <option value="all">全部待審類型</option>
        <option value="client_rebind">客戶重新綁定</option>
        <option value="staff_verification">月嫂身分驗證</option>
        <option value="admin_binding">管理員綁定</option>
      </select>
      {page.status === 'loading' && <div className="line-loading">正在載入待審清單…</div>}
      {page.status === 'error' && <div className="line-error" role="alert">{page.error}</div>}
      {page.value && page.value.items.length === 0 && <div className="line-empty-state"><h4>目前沒有符合條件的待審記錄</h4></div>}
      {page.value && page.value.items.length > 0 && (
        <div className="line-table-scroll">
          <table className="line-data-table">
            <thead><tr><th>申請</th><th>類型</th><th>對象</th><th>LINE ID</th><th>狀態</th><th>操作</th></tr></thead>
            <tbody>{page.value.items.map((item) => (
              <tr key={item.requestId}>
                <td>#{item.requestId}</td><td>{item.reviewTypeLabel}</td>
                <td>{item.displayName}<br /><small>{item.subjectTypeLabel}｜{item.subjectReference ?? '尚未連結'}</small></td>
                <td><code>{item.maskedLineUserId}</code></td><td>{item.statusLabel}</td>
                <td><button type="button" aria-label={`查看審核 #${item.requestId}`} onClick={() => props.onOpenDetail(item.requestId)}>查看審核明細</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {page.value && (
        <div className="line-action-row" aria-label="審核清單分頁">
          <span>顯示 {first}-{last} / {page.value.total} 件</span>
          <button type="button" disabled={page.value.page <= 1} onClick={() => props.onPageChange(page.value!.page - 1)}>上一頁</button>
          <button type="button" disabled={page.value.page >= totalPages} onClick={() => props.onPageChange(page.value!.page + 1)}>下一頁</button>
        </div>
      )}
    </>
  );
}

interface ReviewDetailPanelProps {
  detail: QueryState<LineIdentityReviewRowViewModel>;
  decision: LineIdentityReviewDecision;
  reason: string;
  preview: LineIdentityReviewPreviewViewModel | null;
  confirmed: boolean;
  mutationStatus: MutationStatus;
  mutationError: string | null;
  receipt: LineIdentityReviewReceiptViewModel | null;
  onDecisionChange: (value: LineIdentityReviewDecision) => void;
  onReasonChange: (value: string) => void;
  onConfirm: (value: boolean) => void;
  onPreview: () => void;
  onApply: () => void;
  onReadBack: () => void;
}

function ReviewDetailPanel(props: ReviewDetailPanelProps) {
  const { detail, preview, receipt } = props;
  if (detail.status === 'loading') return <div className="line-loading">正在載入審核明細…</div>;
  if (detail.status === 'error') return <div className="line-error" role="alert">{detail.error}</div>;
  if (!detail.value) return null;
  return (
    <div className="line-action-panel" aria-label="LINE 身分審核明細">
      <h4>審核 #{detail.value.requestId}｜{detail.value.reviewTypeLabel}</h4>
      <p>{detail.value.displayName}｜{detail.value.subjectTypeLabel}｜<code>{detail.value.maskedLineUserId}</code></p>
      <p>目前狀態：<strong>{detail.value.statusLabel}</strong></p>
      {detail.value.status !== 'pending' ? (
        <div className="line-scope-note" role="status">此審核已是 {detail.value.statusLabel}，不可再提交決定；可保留明細作為最新審核結果。</div>
      ) : (
        <>
          <label htmlFor="line-identity-review-decision">人工決定</label>
          <select id="line-identity-review-decision" value={props.decision} onChange={(event) => props.onDecisionChange(event.target.value as LineIdentityReviewDecision)}>
            <option value="approve">核准</option><option value="reject">拒絕</option>
          </select>
          <label htmlFor="line-identity-review-reason">審核原因</label>
          <textarea id="line-identity-review-reason" rows={3} maxLength={1000} value={props.reason} onChange={(event) => props.onReasonChange(event.target.value)} />
          <button type="button" disabled={!props.reason.trim() || props.mutationStatus === 'loading'} onClick={props.onPreview}>預覽審核決定</button>
        </>
      )}
      {preview && (
        <div className="line-preview-result">
          <h4>預覽：{preview.decisionLabel}</h4>
          <p>{preview.beforeStatusLabel} → {preview.afterStatusLabel}</p>
          <p>{preview.subjectTypeLabel}｜{preview.subjectReference ?? '尚未連結'}｜<code>{preview.maskedLineUserId}</code></p>
          <label><input type="checkbox" checked={props.confirmed} onChange={(event) => props.onConfirm(event.target.checked)} />我已確認審核對象與決定</label>
          {!receipt && <button type="button" disabled={!props.confirmed || props.mutationStatus === 'loading'} onClick={props.onApply}>提交審核決定</button>}
        </div>
      )}
      {props.mutationStatus === 'loading' && <div className="line-loading">正在處理審核操作…</div>}
      {props.mutationError && <div className="line-error" role="alert">{props.mutationError}</div>}
      {receipt && (
        <div className="line-success" role="status">
          <strong>審核決定已受理</strong><p>{receipt.statusLabel}</p>
          <p>{receipt.outcomeLabel}</p>
          <p>{receipt.notice}</p><button type="button" onClick={props.onReadBack}>重新查詢審核結果</button>
        </div>
      )}
    </div>
  );
}

export function LineIdentityReviewWorkbench({ client }: LineIdentityReviewWorkbenchProps) {
  const queue = useReviewQueue(client);
  const detailQuery = useReviewDetail(client);
  const [decision, setDecision] = useState<LineIdentityReviewDecision>('approve');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<LineIdentityReviewPreviewViewModel | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [mutationStatus, setMutationStatus] = useState<MutationStatus>('idle');
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<LineIdentityReviewReceiptViewModel | null>(null);
  const mutationController = useRef<AbortController | null>(null);
  const idempotencyKey = useRef<string | null>(null);

  useEffect(() => () => {
    mutationController.current?.abort();
  }, []);

  const resetDecision = () => {
    mutationController.current?.abort();
    idempotencyKey.current = null;
    setReason('');
    setDecision('approve');
    setPreview(null);
    setConfirmed(false);
    setMutationStatus('idle');
    setMutationError(null);
    setReceipt(null);
  };

  const openDetail = (requestId: number, preserveReceipt = false) => {
    if (!preserveReceipt) resetDecision();
    return detailQuery.load(requestId);
  };

  const invalidatePreview = () => {
    mutationController.current?.abort();
    idempotencyKey.current = null;
    setPreview(null);
    setConfirmed(false);
    setMutationStatus('idle');
    setMutationError(null);
    setReceipt(null);
  };

  const runPreview = async () => {
    const current = detailQuery.state.value;
    const normalizedReason = reason.trim();
    if (!current || current.status !== 'pending' || !normalizedReason) return;
    mutationController.current?.abort();
    const controller = new AbortController();
    mutationController.current = controller;
    idempotencyKey.current = operationIdentity('line-review-decision');
    setMutationStatus('loading');
    setMutationError(null);
    setReceipt(null);
    try {
      const value = await client.previewReviewDecision(current.requestId, decision, {
        expected_version: current.version,
        reason: normalizedReason,
      }, { signal: controller.signal });
      if (!controller.signal.aborted) {
        setPreview(adaptLineIdentityReviewPreview(value));
        setConfirmed(false);
        setMutationStatus('idle');
      }
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        idempotencyKey.current = null;
        setPreview(null);
        setMutationStatus('error');
        setMutationError(safeError(error, 'LINE 身分審核預覽失敗。'));
      }
    }
  };

  const runApply = async () => {
    const candidate = preview;
    const key = idempotencyKey.current;
    if (!candidate || !key || !confirmed || !reason.trim()) return;
    mutationController.current?.abort();
    const controller = new AbortController();
    mutationController.current = controller;
    setMutationStatus('loading');
    setMutationError(null);
    try {
      const value = await client.applyReviewDecision(candidate.requestId, candidate.decision, {
        expected_version: candidate.expectedVersion,
        idempotency_key: key,
        reason: reason.trim(),
        preview_fingerprint: candidate.previewFingerprint,
      }, { signal: controller.signal });
      if (!controller.signal.aborted) {
        setReceipt(adaptLineIdentityReviewReceipt(value));
        setMutationStatus('success');
      }
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        setMutationStatus('error');
        setMutationError(safeError(error, 'LINE 身分審核提交失敗。'));
      }
    }
  };

  const readBack = async () => {
    if (!receipt) return;
    await openDetail(receipt.requestId, true);
    queue.refresh();
  };

  return (
    <section className="line-table-container" data-control-id="line.identity.review-workbench">
      <ReviewQueuePanel
        summary={queue.summary}
        page={queue.page}
        reviewType={queue.reviewType}
        onReviewTypeChange={(value) => {
          queue.setPageNumber(1);
          queue.setReviewType(value);
        }}
        onOpenDetail={(requestId) => void openDetail(requestId)}
        onPageChange={queue.setPageNumber}
        onRefresh={queue.refresh}
      />
      <ReviewDetailPanel
        detail={detailQuery.state}
        decision={decision}
        reason={reason}
        preview={preview}
        confirmed={confirmed}
        mutationStatus={mutationStatus}
        mutationError={mutationError}
        receipt={receipt}
        onDecisionChange={(value) => {
          setDecision(value);
          invalidatePreview();
        }}
        onReasonChange={(value) => {
          setReason(value);
          invalidatePreview();
        }}
        onConfirm={setConfirmed}
        onPreview={() => void runPreview()}
        onApply={() => void runApply()}
        onReadBack={() => void readBack()}
      />
    </section>
  );
}
