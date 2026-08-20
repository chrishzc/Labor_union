/**
 * File: AlertGroupSecurity.tsx
 * Description: 繁體中文 - LINE 幹部異常通知群組狀態監控與最高管理員重設解鎖工作台。
 */
import React, { useState } from 'react';
import '../LineManagementPage.css';

export const AlertGroupSecurity: React.FC = () => {
  const [groupId, setGroupId] = useState<string | null>('c98a72b0123456789abcdef');
  const [groupName, setGroupName] = useState<string>('新竹市月子工會 ｜ 幹部督導應變群');
  const [boundAt, setBoundAt] = useState<string>('2026-08-15 14:30:22');
  const [boundBy, setBoundBy] = useState<string>('王專員 (System Admin)');
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
  const [alertSuccessToast, setAlertSuccessToast] = useState<string | null>(null);

  const handleResetGroup = () => {
    setGroupId(null);
    setGroupName('尚未綁定');
    setBoundAt('-');
    setBoundBy('-');
    setShowConfirmModal(false);
    setAlertSuccessToast('✅ 已成功重設並清空 alert_group_id！現在可在新的 LINE 群組輸入「設定異常通知群組」進行綁定。');
    setTimeout(() => setAlertSuccessToast(null), 3500);
  };

  return (
    <div className="alert-group-security-container">
      {alertSuccessToast && (
        <div className="line-success" style={{ marginBottom: '20px' }}>
          {alertSuccessToast}
        </div>
      )}

      {/* 狀態監控卡片 */}
      <div className="line-workspace-card" style={{ marginBottom: '24px' }}>
        <div className="line-section-heading">
          <div>
            <h3>📢 LINE 幹部異常通知群組狀態</h3>
            <p>全系統所有「爭議客訴急件」、「調休順延被拒」、「連續 2 次綁定失敗」之重大異常唯一即時廣播管道。</p>
          </div>
          <span className={`line-status ${groupId ? 'line-status-resolved' : 'line-status-waiting'}`}>
            {groupId ? '🟢 正常監聽中 (已鎖定)' : '⚪ 尚未綁定群組'}
          </span>
        </div>

        <div className="line-detail-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
          <div>
            <span>目前綁定之群組名稱</span>
            <strong>{groupName}</strong>
          </div>
          <div>
            <span>LINE Group ID</span>
            <code>{groupId || '(NULL - 空值)'}</code>
          </div>
          <div>
            <span>綁定時間</span>
            <strong>{boundAt}</strong>
          </div>
          <div>
            <span>操作綁定之人員</span>
            <strong>{boundBy}</strong>
          </div>
        </div>

        <div className="line-events" style={{ marginTop: '20px' }}>
          <h4>🔒 單一互斥鎖定保護機制</h4>
          <p style={{ color: '#57423b', fontSize: '0.9rem', lineHeight: '1.6' }}>
            依據工會資安規範，系統資料庫中僅允許存在 <strong>1 個唯一的 <code>alert_group_id</code></strong>。
            只要當前有綁定群組，其他任何 LINE 群組發送「<code>設定異常通知群組</code>」指令一律<strong>自動失效並拒絕</strong>，徹底防止通知錯亂。
          </p>
        </div>
      </div>

      {/* 管理員專用重設解除卡片 */}
      <div className="line-workspace-card" style={{ borderColor: '#fecdd3', background: '#fff5f5' }}>
        <div className="line-section-heading" style={{ borderBottomColor: '#fed7aa' }}>
          <div>
            <h3 style={{ color: '#991b1b' }}>⚠️ 最高權限管理員專區 (Super Admin Only)</h3>
            <p style={{ color: '#9a3412' }}>若工會更換了幹部 LINE 群組，必須由管理員在此重設清空綁定後，新群組方可重新綁定。</p>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <strong>重設異常通知群組</strong>
            <p style={{ color: '#74593f', fontSize: '0.85rem', margin: '4px 0 0' }}>
              點擊後將資料庫中的 <code>alert_group_id</code> 清空為 <code>NULL</code>。已禁止透過 LINE 聊天室文字指令解綁。
            </p>
          </div>
          <button
            className="mock-primary-btn"
            style={{ background: '#be123c', color: '#fff', padding: '10px 18px', borderRadius: '10px' }}
            onClick={() => setShowConfirmModal(true)}
            disabled={groupId === null}
          >
            🔴 重設異常通知群組 (清空 NULL)
          </button>
        </div>
      </div>

      {/* 確認彈窗 */}
      {showConfirmModal && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <h3 style={{ color: '#991b1b', margin: '0 0 12px' }}>🚨 確認重設異常通知群組？</h3>
            <p style={{ color: '#57423b', lineHeight: '1.6' }}>
              確定要清空當前綁定的【<strong>{groupName}</strong>】嗎？
              <br />
              清空後，系統將暫停推播群組急件告警，直到幹部在新群組中輸入「<code>設定異常通知群組</code>」為止。
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button className="line-secondary-btn" onClick={() => setShowConfirmModal(false)}>
                取消
              </button>
              <button
                className="mock-primary-btn"
                style={{ background: '#be123c', color: '#fff' }}
                onClick={handleResetGroup}
              >
                確認清空重設
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
