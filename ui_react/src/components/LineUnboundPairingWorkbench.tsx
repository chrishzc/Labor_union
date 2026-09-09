/**
 * File: LineUnboundPairingWorkbench.tsx
 * Description: 提供未綁定 LINE 之正式訂單與狀態 C 產婦暫存登記手動配對工作台。
 */
import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  ClipboardList,
  Handshake,
  Lightbulb,
  Link,
  RefreshCw,
  UserRound,
} from 'lucide-react';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import type {
  UnboundOrderCandidate,
  UnboundProvisionalCandidate,
} from '../api/line_identity/line_identity_schemas';

export type LineUnboundPairingClient = Pick<
  LineIdentityClient,
  'listUnboundCandidates' | 'pairProvisionalRegistration'
>;

interface LineUnboundPairingWorkbenchProps {
  client: LineUnboundPairingClient;
  onPairSuccess?: () => void;
}

function operationIdentity(prefix: string): string {
  const suffix =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function maskPhone(value: string): string {
  const compact = value.replace(/\s/g, '');
  if (compact.length <= 4) return '••••';
  return `${compact.slice(0, 2)}••••${compact.slice(-3)}`;
}

function maskLineUserId(value: string): string {
  if (value.length <= 8) return '••••••••';
  return `${value.slice(0, 4)}••••••${value.slice(-4)}`;
}

export function LineUnboundPairingWorkbench({
  client,
  onPairSuccess,
}: LineUnboundPairingWorkbenchProps) {
  const [orders, setOrders] = useState<UnboundOrderCandidate[]>([]);
  const [provisionals, setProvisionals] = useState<UnboundProvisionalCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  const [selectedOrder, setSelectedOrder] = useState<UnboundOrderCandidate | null>(null);
  const [selectedProvisional, setSelectedProvisional] = useState<UnboundProvisionalCandidate | null>(null);
  const [reason, setReason] = useState('管理員手動配對市府訂單與狀態 C 產婦');
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const loadCandidates = async () => {
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setQueryError(null);
    try {
      const data = await client.listUnboundCandidates({ signal: controller.signal });
      if (!controller.signal.aborted) {
        setOrders(data.orders);
        setProvisionals(data.provisional_registrations);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        if (err instanceof LineIdentityClientError) {
          setQueryError(err.message);
        } else {
          setQueryError('載入未綁定名單失敗，請稍後再試。');
        }
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void loadCandidates();
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const handlePair = async () => {
    if (!selectedOrder || !selectedProvisional || !confirmed) return;
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setActionError('請填寫配對原因。');
      return;
    }

    setSubmitting(true);
    setActionError(null);
    setSuccessMessage(null);

    const idempotencyKey = operationIdentity('pair-provisional');
    const correlationId = operationIdentity('corr-provisional');

    try {
      const result = await client.pairProvisionalRegistration({
        provisional_registration_id: selectedProvisional.registration_id,
        target_case_no: selectedOrder.case_no,
        reason: trimmedReason,
        idempotency_key: idempotencyKey,
        correlation_id: correlationId,
      });

      setSuccessMessage(
        `配對成功：案號 ${result.case_no}（${result.client_name}）已綁定 LINE 帳號，並排入 Rich Menu 晉級。`
      );
      setSelectedOrder(null);
      setSelectedProvisional(null);
      setConfirmed(false);

      // Refresh candidate list and trigger parent refresh
      await loadCandidates();
      onPairSuccess?.();
    } catch (err) {
      if (err instanceof LineIdentityClientError) {
        setActionError(err.message);
      } else {
        setActionError('手動配對操作失敗，請重新整理後再試。');
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Helper to detect likely matching candidates
  const isSuggestedMatch = (
    order: UnboundOrderCandidate,
    prov: UnboundProvisionalCandidate
  ) => {
    if (order.client_name.trim() === prov.name.trim()) return true;
    const cleanOrderPhone = order.client_phone.replace(/\D/g, '');
    const cleanProvPhone = prov.phone.replace(/\D/g, '');
    if (
      cleanOrderPhone &&
      cleanProvPhone &&
      cleanOrderPhone.slice(-6) === cleanProvPhone.slice(-6)
    ) {
      return true;
    }
    return false;
  };

  return (
    <section
      className="line-table-container line-pairing-workbench"
      data-control-id="line.identity.unbound-pairing-workbench"
    >
      <div className="line-section-heading">
        <div>
          <h3 className="line-heading-with-icon"><Link aria-hidden="true" />待配對訂單與狀態 C 產婦手動歸戶</h3>
          <p>
            當產婦先於 LINE 完成狀態 C 登記（已提交問卷但市府尚未派案），而市府匯入名冊時因姓名或電話微幅不一致未自動撮合，可於此處選定正式訂單與對應
            LINE 產婦登記，執行一鍵手動配對與綁定。
          </p>
        </div>
        <button
          type="button"
          className="line-secondary-btn line-nowrap"
          onClick={() => void loadCandidates()}
          disabled={loading}
        >
          <RefreshCw aria-hidden="true" />{loading ? '載入中…' : '重新整理'}
        </button>
      </div>

      {queryError && (
        <div className="line-error line-section-bottom" role="alert">
          {queryError}
        </div>
      )}

      {successMessage && (
        <div className="line-success line-section-bottom line-message-with-icon" role="status">
          <CheckCircle2 aria-hidden="true" />{successMessage}
        </div>
      )}

      {actionError && (
        <div className="line-error line-section-bottom" role="alert">
          {actionError}
        </div>
      )}

      <div className="line-pairing-candidate-grid">
        {/* Panel 1: Unbound Orders */}
        <div className="line-pairing-candidate-panel">
          <div className="line-pairing-panel-header">
            <h4><ClipboardList aria-hidden="true" />選擇未綁定 LINE 的訂單（{orders.length}）
            </h4>
            {selectedOrder && (
              <span className="line-pairing-selected-badge">
                已選取：{selectedOrder.case_no}
              </span>
            )}
          </div>

          {orders.length === 0 ? (
            <div className="line-pairing-empty">
              {loading ? '載入中…' : '目前沒有未綁定訂單；請確認市府名冊是否已完成匯入。'}
            </div>
          ) : (
            <div className="line-pairing-table-scroll">
              <table className="line-table line-pairing-table">
                <caption className="sr-only">尚未綁定 LINE 的訂單</caption>
                <thead>
                  <tr>
                    <th scope="col">案號</th>
                    <th scope="col">客戶姓名</th>
                    <th scope="col">電話</th>
                    <th scope="col">狀態</th>
                    <th scope="col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => {
                    const isSelected = selectedOrder?.case_no === o.case_no;
                    return (
                      <tr
                        key={o.case_no}
                        className={isSelected ? 'is-selected' : ''}
                        aria-selected={isSelected}
                        onClick={() => {
                          setSelectedOrder(isSelected ? null : o);
                          setConfirmed(false);
                        }}
                      >
                        <td>
                          <strong>{o.case_no}</strong>
                        </td>
                        <td>{o.client_name}</td>
                        <td>{maskPhone(o.client_phone)}</td>
                        <td>
                          <span className="line-pairing-status-badge">
                            {o.status}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className={`line-pairing-select-button${isSelected ? ' is-selected' : ''}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedOrder(isSelected ? null : o);
                              setConfirmed(false);
                            }}
                          >
                            {isSelected ? '取消' : '選取'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Panel 2: Provisional Registrations (State C) */}
        <div className="line-pairing-candidate-panel">
          <div className="line-pairing-panel-header">
            <h4><UserRound aria-hidden="true" />選擇待發號 LINE 產婦登記（{provisionals.length}）
            </h4>
            {selectedProvisional && (
              <span className="line-pairing-selected-badge">
                已選取：#{selectedProvisional.registration_id} {selectedProvisional.name}
              </span>
            )}
          </div>

          {provisionals.length === 0 ? (
            <div className="line-pairing-empty">
              {loading ? '載入中…' : '目前沒有狀態 C 待配對產婦；請確認 LINE 登記流程是否已有待發號資料。'}
            </div>
          ) : (
            <div className="line-pairing-table-scroll">
              <table className="line-table line-pairing-table">
                <caption className="sr-only">待配對的 LINE 產婦登記</caption>
                <thead>
                  <tr>
                    <th scope="col">序號</th>
                    <th scope="col">登記姓名</th>
                    <th scope="col">電話</th>
                    <th scope="col">登記時間</th>
                    <th scope="col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {provisionals.map((p) => {
                    const isSelected =
                      selectedProvisional?.registration_id === p.registration_id;
                    const suggested =
                      selectedOrder ? isSuggestedMatch(selectedOrder, p) : false;
                    return (
                      <tr
                        key={p.registration_id}
                        className={`${isSelected ? 'is-selected' : ''}${suggested && !isSelected ? ' is-suggested' : ''}`}
                        aria-selected={isSelected}
                        onClick={() => {
                          setSelectedProvisional(isSelected ? null : p);
                          setConfirmed(false);
                        }}
                      >
                        <td>
                          #{p.registration_id}
                          {suggested && (
                            <span className="line-pairing-suggestion-badge">
                              <Lightbulb aria-hidden="true" />建議配對
                            </span>
                          )}
                        </td>
                        <td>
                          <strong>{p.name}</strong>
                        </td>
                        <td>{maskPhone(p.phone)}</td>
                        <td className="line-table-secondary">
                          {p.submitted_at || '-'}
                        </td>
                        <td>
                          <button
                            type="button"
                            className={`line-pairing-select-button${isSelected ? ' is-selected' : ''}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedProvisional(isSelected ? null : p);
                              setConfirmed(false);
                            }}
                          >
                            {isSelected ? '取消' : '選取'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Panel 3: Pairing Confirmation Action Bar */}
      <div className={`line-pairing-confirmation${selectedOrder && selectedProvisional ? ' is-ready' : ''}`}>
        <div className="line-pairing-confirmation-summary">
          <h4><Handshake aria-hidden="true" />配對確認與送出
          </h4>
          {selectedOrder && selectedProvisional ? (
            <div className="line-pairing-ready-summary">
              即將將訂單 <strong>【{selectedOrder.case_no}】</strong>（客戶：
              <strong>{selectedOrder.client_name}</strong>，電話：
              {maskPhone(selectedOrder.client_phone)}）
              <br />
              與 LINE 登記 <strong>【#{selectedProvisional.registration_id}】</strong>（產婦：
              <strong>{selectedProvisional.name}</strong>，電話：
              {maskPhone(selectedProvisional.phone)}，LINE ID：
              <code>{maskLineUserId(selectedProvisional.line_user_id)}</code>）進行手動歸戶配對。
            </div>
          ) : (
            <div className="line-pairing-missing-side">
              {!selectedOrder && !selectedProvisional
                ? '尚缺未綁定訂單與待發號產婦登記，請先在上方各選一筆。'
                : !selectedOrder
                  ? '尚缺未綁定訂單，請先在左側選一筆。'
                  : '尚缺待發號產婦登記，請先在右側選一筆。'}
            </div>
          )}
        </div>

        {selectedOrder && selectedProvisional && (
          <div className="line-pairing-action-area">
            <div className="line-pairing-reason-field">
              <label htmlFor="line-pairing-reason">
                配對審核原因備註
              </label>
              <input
                id="line-pairing-reason"
                type="text"
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  setConfirmed(false);
                }}
                maxLength={1000}
                className="richmenu-form-input"
              />
            </div>
            <label className="line-pairing-confirm-check">
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              我已核對兩側姓名、遮罩電話與案件資訊，確認執行手動配對。
            </label>
            <div className="line-pairing-submit-row">
              <button
                type="button"
                className="line-primary-btn"
                disabled={submitting || !reason.trim() || !confirmed}
                onClick={() => void handlePair()}
              >
                <Link aria-hidden="true" />{submitting ? '正在執行配對…' : '確認手動配對並綁定'}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
