/**
 * File: LineUnboundPairingWorkbench.tsx
 * Description: 提供未綁定 LINE 之正式訂單與狀態 C 產婦暫存登記手動配對工作台。
 */
import { useEffect, useRef, useState } from 'react';
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
    if (!selectedOrder || !selectedProvisional) return;
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
        `✅ 配對成功！案號 ${result.case_no}（${result.client_name}）已成功綁定 LINE 帳號，並已排入 Rich Menu 晉級！`
      );
      setSelectedOrder(null);
      setSelectedProvisional(null);

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
      className="line-table-container"
      data-control-id="line.identity.unbound-pairing-workbench"
      style={{ marginTop: '24px' }}
    >
      <div className="line-section-heading">
        <div>
          <h3>🔗 待配對訂單與狀態 C 產婦手動歸戶</h3>
          <p>
            當產婦先於 LINE 完成狀態 C 登記（已提交問卷但市府尚未派案），而市府匯入名冊時因姓名或電話微幅不一致未自動撮合，可於此處選定正式訂單與對應
            LINE 產婦登記，執行一鍵手動配對與綁定。
          </p>
        </div>
        <button
          type="button"
          className="line-btn"
          onClick={() => void loadCandidates()}
          disabled={loading}
          style={{ whiteSpace: 'nowrap' }}
        >
          {loading ? '載入中…' : '🔄 重新整理清單'}
        </button>
      </div>

      {queryError && (
        <div className="line-error" role="alert" style={{ marginBottom: '16px' }}>
          {queryError}
        </div>
      )}

      {successMessage && (
        <div className="line-success" role="status" style={{ marginBottom: '16px' }}>
          {successMessage}
        </div>
      )}

      {actionError && (
        <div className="line-error" role="alert" style={{ marginBottom: '16px' }}>
          {actionError}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
          gap: '20px',
          marginBottom: '20px',
        }}
      >
        {/* Panel 1: Unbound Orders */}
        <div
          style={{
            border: '1px solid #e2d7ce',
            borderRadius: '10px',
            padding: '16px',
            backgroundColor: '#faf8f6',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '12px',
            }}
          >
            <h4 style={{ margin: 0, color: '#3d2b1f', fontSize: '1rem' }}>
              📋 1. 選擇未綁定 LINE 的訂單 ({orders.length})
            </h4>
            {selectedOrder && (
              <span
                style={{
                  fontSize: '0.8rem',
                  backgroundColor: '#e6f4ea',
                  color: '#137333',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontWeight: 600,
                }}
              >
                已選取: {selectedOrder.case_no}
              </span>
            )}
          </div>

          {orders.length === 0 ? (
            <div style={{ color: '#888', padding: '24px 0', textAlign: 'center' }}>
              {loading ? '載入中…' : '目前無待綁定訂單 🎉'}
            </div>
          ) : (
            <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
              <table className="line-table" style={{ width: '100%', fontSize: '0.88rem' }}>
                <thead>
                  <tr>
                    <th>案號</th>
                    <th>客戶姓名</th>
                    <th>電話</th>
                    <th>狀態</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => {
                    const isSelected = selectedOrder?.case_no === o.case_no;
                    return (
                      <tr
                        key={o.case_no}
                        style={{
                          backgroundColor: isSelected ? '#e8f0fe' : undefined,
                          cursor: 'pointer',
                        }}
                        onClick={() => setSelectedOrder(isSelected ? null : o)}
                      >
                        <td>
                          <strong>{o.case_no}</strong>
                        </td>
                        <td>{o.client_name}</td>
                        <td>{o.client_phone}</td>
                        <td>
                          <span
                            style={{
                              fontSize: '0.78rem',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#f1f3f4',
                            }}
                          >
                            {o.status}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="line-btn"
                            style={{
                              fontSize: '0.8rem',
                              padding: '3px 8px',
                              backgroundColor: isSelected ? '#1a73e8' : undefined,
                              color: isSelected ? '#fff' : undefined,
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedOrder(isSelected ? null : o);
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
        <div
          style={{
            border: '1px solid #e2d7ce',
            borderRadius: '10px',
            padding: '16px',
            backgroundColor: '#faf8f6',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '12px',
            }}
          >
            <h4 style={{ margin: 0, color: '#3d2b1f', fontSize: '1rem' }}>
              🤰 2. 選擇待發號 LINE 產婦登記 ({provisionals.length})
            </h4>
            {selectedProvisional && (
              <span
                style={{
                  fontSize: '0.8rem',
                  backgroundColor: '#e6f4ea',
                  color: '#137333',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontWeight: 600,
                }}
              >
                已選取: #{selectedProvisional.registration_id} {selectedProvisional.name}
              </span>
            )}
          </div>

          {provisionals.length === 0 ? (
            <div style={{ color: '#888', padding: '24px 0', textAlign: 'center' }}>
              {loading ? '載入中…' : '目前無狀態 C 待配對產婦 🎉'}
            </div>
          ) : (
            <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
              <table className="line-table" style={{ width: '100%', fontSize: '0.88rem' }}>
                <thead>
                  <tr>
                    <th>序號</th>
                    <th>登記姓名</th>
                    <th>電話</th>
                    <th>登記時間</th>
                    <th>操作</th>
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
                        style={{
                          backgroundColor: isSelected
                            ? '#e8f0fe'
                            : suggested
                            ? '#fef7e0'
                            : undefined,
                          cursor: 'pointer',
                        }}
                        onClick={() => setSelectedProvisional(isSelected ? null : p)}
                      >
                        <td>
                          #{p.registration_id}
                          {suggested && (
                            <span
                              style={{
                                marginLeft: '6px',
                                fontSize: '0.72rem',
                                color: '#b06000',
                                backgroundColor: '#fde293',
                                padding: '1px 4px',
                                borderRadius: '3px',
                              }}
                            >
                              💡 建議配對
                            </span>
                          )}
                        </td>
                        <td>
                          <strong>{p.name}</strong>
                        </td>
                        <td>{p.phone}</td>
                        <td style={{ fontSize: '0.78rem', color: '#666' }}>
                          {p.submitted_at || '-'}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="line-btn"
                            style={{
                              fontSize: '0.8rem',
                              padding: '3px 8px',
                              backgroundColor: isSelected ? '#1a73e8' : undefined,
                              color: isSelected ? '#fff' : undefined,
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedProvisional(isSelected ? null : p);
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
      <div
        style={{
          border: '1px solid #d2c4b8',
          borderRadius: '10px',
          padding: '16px 20px',
          backgroundColor: selectedOrder && selectedProvisional ? '#f0f7ff' : '#f9f9f9',
          transition: 'background-color 0.2s ease',
        }}
      >
        <div style={{ marginBottom: '12px' }}>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '0.98rem', color: '#2d3748' }}>
            🤝 配對確認與送出
          </h4>
          {selectedOrder && selectedProvisional ? (
            <div
              style={{
                fontSize: '0.92rem',
                lineHeight: 1.6,
                color: '#1a365d',
                padding: '10px 14px',
                backgroundColor: '#e1effe',
                borderRadius: '6px',
                border: '1px solid #b4d3fe',
              }}
            >
              即將將訂單 <strong>【{selectedOrder.case_no}】</strong>（客戶：
              <strong>{selectedOrder.client_name}</strong>，電話：
              {selectedOrder.client_phone}）
              <br />
              與 LINE 登記 <strong>【#{selectedProvisional.registration_id}】</strong>（產婦：
              <strong>{selectedProvisional.name}</strong>，電話：
              {selectedProvisional.phone}，UID：
              <code>{selectedProvisional.line_user_id}</code>）進行手動歸戶配對。
            </div>
          ) : (
            <div style={{ fontSize: '0.88rem', color: '#718096' }}>
              請於上方左側勾選「未綁定訂單」，並於右側勾選「待發號產婦登記」以啟用配對。
            </div>
          )}
        </div>

        {selectedOrder && selectedProvisional && (
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 300px' }}>
              <label
                htmlFor="line-pairing-reason"
                style={{
                  display: 'block',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  marginBottom: '4px',
                  color: '#4a5568',
                }}
              >
                配對審核原因備註
              </label>
              <input
                id="line-pairing-reason"
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={1000}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e0',
                  fontSize: '0.88rem',
                }}
              />
            </div>
            <div style={{ marginTop: '22px' }}>
              <button
                type="button"
                className="line-btn line-btn-primary"
                disabled={submitting || !reason.trim()}
                onClick={() => void handlePair()}
                style={{
                  padding: '9px 20px',
                  fontWeight: 600,
                  fontSize: '0.92rem',
                  backgroundColor: '#1a73e8',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: submitting ? 'not-allowed' : 'pointer',
                }}
              >
                {submitting ? '正在進行原子綁定…' : '確認手動配對並綁定'}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
