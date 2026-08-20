/**
 * File: StaffPage.tsx
 * Description: 以 bounded Staff 摘要唯讀呈現名冊，並將未核准主檔與變更控制原位鎖定。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './StaffPage.css';
import { Drawer } from '../components/Drawer';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { StaffDirectoryAbortedError } from '../api/staff_directory/staff_directory_errors';
import {
  adaptStaffDirectoryPage,
  STAFF_DIRECTORY_UNAVAILABLE,
  type StaffDirectoryCardViewModel,
} from '../adapters/staff/staff_directory_adapter';

type StaffTab = 'roster' | 'preferences' | 'unavailability';
type DirectoryState =
  | { status: 'loading'; items: StaffDirectoryCardViewModel[] }
  | { status: 'ready'; items: StaffDirectoryCardViewModel[]; nextCursor: number | null }
  | { status: 'loading-more'; items: StaffDirectoryCardViewModel[]; nextCursor: number }
  | { status: 'error'; items: StaffDirectoryCardViewModel[]; message: string };

const UNAVAILABLE_TITLE = '[查詢模式] 後端 typed contract 尚未開放';

function DisabledButton({
  controlId,
  children,
  className,
}: {
  controlId: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      data-control-id={controlId}
      className={className ?? 'staff-disabled-btn'}
      disabled
      title={UNAVAILABLE_TITLE}
    >
      {children}
    </button>
  );
}

export const StaffPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<StaffTab>('roster');
  const [directory, setDirectory] = useState<DirectoryState>({ status: 'loading', items: [] });
  const [selectedStaff, setSelectedStaff] = useState<StaffDirectoryCardViewModel | null>(null);
  const mountedRef = useRef(false);
  const initialRequestedRef = useRef(false);
  const requestGenerationRef = useRef(0);
  const activeControllerRef = useRef<AbortController | null>(null);

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
      queueMicrotask(() => {
        if (!mountedRef.current) {
          requestGenerationRef.current += 1;
          activeControllerRef.current?.abort();
          staffDirectoryClient.resetPagination();
        }
      });
    };
  }, [loadInitialDirectory]);

  const loadNextPage = async () => {
    if (directory.status !== 'ready' || directory.nextCursor === null) return;
    const existingItems = directory.items;
    const cursor = directory.nextCursor;
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
      });
    }
  };

  const staffItems = directory.items;

  return (
    <div data-surface-id="staff.page">
      <div className="page-header-banner staff-page-header">
        <div>
          <h1 className="page-title">👥 服務人員與工會成員名冊</h1>
          <p className="page-subtitle">
            目前接入月嫂摘要名冊；主檔、證照、偏好與不可服務流程仍依各自正式契約開放。
          </p>
        </div>
        <DisabledButton controlId="staff.master.create" className="staff-primary-disabled">
          + 新增服務人員
        </DisabledButton>
      </div>

      <div className="staff-tab-bar" aria-label="服務人員管理分頁">
        <button type="button" data-control-id="staff.tab.roster" className={`staff-tab-btn ${activeTab === 'roster' ? 'active' : ''}`} onClick={() => setActiveTab('roster')}>
          👩‍🍼 服務月嫂名冊與資格審核
        </button>
        <button type="button" data-control-id="staff.tab.preferences" className={`staff-tab-btn ${activeTab === 'preferences' ? 'active' : ''}`} onClick={() => setActiveTab('preferences')}>
          🎯 配對偏好與料理能力管理
        </button>
        <button type="button" data-control-id="staff.tab.unavailability" className={`staff-tab-btn ${activeTab === 'unavailability' ? 'active' : ''}`} onClick={() => setActiveTab('unavailability')}>
          🏖️ 長假與暫停接案期間維護
        </button>
      </div>

      {activeTab === 'roster' && (
        <section data-surface-id="staff.directory">
          <div className="staff-unavailable-banner">
            <span aria-hidden="true">⚠️</span>
            <div>
              <strong>證照提醒：{STAFF_DIRECTORY_UNAVAILABLE}</strong>
              <p>摘要 API 未提供證照有效期、資格或派單阻擋投影。</p>
            </div>
            <DisabledButton controlId="staff.master.certificate-approve">立即排查證照</DisabledButton>
          </div>

          {directory.status === 'loading' && (
            <div className="staff-directory-message" data-control-id="staff.directory.query" role="status">
              正在載入服務人員摘要名冊…
            </div>
          )}
          {directory.status === 'error' && (
            <div className="staff-directory-message error" role="alert">
              載入服務人員名冊失敗：{directory.message}
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
                    <span className="staff-unavailable-pill">狀態 unavailable</span>
                  </div>
                  <div className="staff-summary-lines">
                    <div>📍 偏好服務區：{STAFF_DIRECTORY_UNAVAILABLE}</div>
                    <div>⭐ 實務年資／問卷：{STAFF_DIRECTORY_UNAVAILABLE}</div>
                  </div>
                  <div className="staff-unavailable-slot">📝 偏好備註：{STAFF_DIRECTORY_UNAVAILABLE}</div>
                  <div className="staff-unavailable-slot">技能與料理能力：{STAFF_DIRECTORY_UNAVAILABLE}</div>
                  <div className="staff-certification-row"><span>良民證：unavailable</span><span>體檢：unavailable</span></div>
                  <div className="staff-card-footer">
                    <button type="button" data-control-id={`staff.drawer.open.${staff.id}`} className="staff-view-btn" onClick={() => setSelectedStaff(staff)}>
                      檢視摘要與未開放欄位 ➔
                    </button>
                    <DisabledButton controlId="staff.lifecycle.retirement.apply">辦理離職封存</DisabledButton>
                  </div>
                </article>
              ))}
            </div>
          )}

          {directory.status === 'ready' && directory.nextCursor !== null && (
            <div className="staff-pagination">
              <button type="button" data-control-id="staff.directory.next-page" className="staff-next-btn" onClick={() => void loadNextPage()}>
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
            <div><h2>🎯 月嫂配對偏好與料理能力管理</h2><p>Staff 摘要不包含 preference profile；欄位保留但目前不可編輯。</p></div>
            <div className="staff-action-pair">
              <DisabledButton controlId="staff.preferences.preview">預覽偏好變更</DisabledButton>
              <DisabledButton controlId="staff.preferences.apply">套用偏好變更</DisabledButton>
            </div>
          </div>
          <div className="staff-preference-grid">
            <div className="staff-form-card">
              <label htmlFor="staff-preference-days">可承接服務天數範圍</label>
              <input id="staff-preference-days" value="後端尚未提供 typed profile" disabled readOnly />
            </div>
            <div className="staff-form-card">
              <span className="staff-form-label">可承接每日服務時數</span>
              <DisabledButton controlId="staff.preferences.cooking-skills">時數／料理能力 unavailable</DisabledButton>
            </div>
            <div className="staff-form-card wide">
              <label htmlFor="staff-preference-notes">實務偏好與特殊排除備註</label>
              <textarea id="staff-preference-notes" data-control-id="staff.preferences.special-notes" rows={3} value="" placeholder="後端尚未提供 typed special notes contract" disabled readOnly />
            </div>
          </div>
        </section>
      )}

      {activeTab === 'unavailability' && (
        <section className="staff-workbench" data-surface-id="staff.unavailability">
          <div className="staff-section-header">
            <div><h2>🏖️ 月嫂長假與暫停接案期間維護</h2><p>本 query slice 未開放不可服務期間的 Query／Preview／Apply。</p></div>
            <div className="staff-action-pair">
              <DisabledButton controlId="staff.availability.create.preview">預覽新增</DisabledButton>
              <DisabledButton controlId="staff.availability.create.apply">套用新增</DisabledButton>
            </div>
          </div>
          <div className="staff-unavailability-table" role="table" aria-label="不可服務期間">
            <div className="staff-unavailability-row header" role="row">
              <span role="columnheader">月嫂姓名</span><span role="columnheader">類別</span><span role="columnheader">不可服務區間</span><span role="columnheader">狀態／操作</span>
            </div>
            <div className="staff-unavailability-row" role="row">
              <span role="cell">{STAFF_DIRECTORY_UNAVAILABLE}</span><span role="cell">—</span><span role="cell">—</span>
              <span role="cell" className="staff-action-pair">
                <DisabledButton controlId="staff.availability.cancel.preview">預覽取消</DisabledButton>
                <DisabledButton controlId="staff.availability.cancel.apply">套用取消</DisabledButton>
              </span>
            </div>
          </div>
          <div className="staff-secondary-controls"><DisabledButton controlId="staff.availability.end-pause">結束暫停接案</DisabledButton></div>
        </section>
      )}

      <Drawer
        isOpen={selectedStaff !== null}
        onClose={() => setSelectedStaff(null)}
        title={`👩‍🍼 服務人員摘要 - ${selectedStaff?.displayName ?? ''}`}
        footer={
          <div className="staff-drawer-footer">
            <button type="button" data-control-id="staff.drawer.close" className="staff-close-btn" onClick={() => setSelectedStaff(null)}>關閉</button>
            <DisabledButton controlId="staff.lifecycle.retirement.preview">預覽退役</DisabledButton>
            <DisabledButton controlId="staff.lifecycle.reactivation.preview">預覽復職</DisabledButton>
            <DisabledButton controlId="staff.lifecycle.reactivation.apply">套用復職</DisabledButton>
            <DisabledButton controlId="staff.master.save">審核通過並儲存</DisabledButton>
          </div>
        }
      >
        {selectedStaff && (
          <div className="staff-drawer-content">
            <section className="staff-drawer-section">
              <h3>基本摘要與問卷得分</h3>
              <p><strong>Staff ID：</strong>#{selectedStaff.id}</p><p><strong>姓名：</strong>{selectedStaff.displayName}</p><p><strong>電話：</strong>{selectedStaff.displayPhone}</p>
              <p><strong>專業年資／服務區域／問卷：</strong>{STAFF_DIRECTORY_UNAVAILABLE}</p>
            </section>
            <section className="staff-drawer-section">
              <h3>📝 月嫂實際承接偏好備註</h3>
              <textarea data-control-id="staff.master.edit" rows={2} value="" placeholder="後端尚未提供 typed staff master／notes contract" disabled readOnly aria-label="月嫂實際承接偏好備註" />
            </section>
            <section className="staff-drawer-section"><h3>📂 證件與影本上傳附件</h3><p>{STAFF_DIRECTORY_UNAVAILABLE}</p><DisabledButton controlId="staff.master.attachment-upload">上傳附件</DisabledButton><DisabledButton controlId="staff.master.certificate-approve">核准證照</DisabledButton></section>
            <section className="staff-drawer-section"><h3>🏦 受款銀行帳號</h3><p>{STAFF_DIRECTORY_UNAVAILABLE}</p><DisabledButton controlId="staff.master.bank-edit">編輯銀行資料</DisabledButton></section>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default StaffPage;
